r"""Weekly replay acceptance: grade a replay's fills against LIVE on entries, exits and sizing/dollars.

    python tools/replay_acceptance.py --pull <DIR>          # read-only pull; keep <DIR> outside the repo
    python tools/replay_acceptance.py --feature-store <DIR>/futures_feature_store.jsonl \
        --runtime-state <DIR>/futures_runtime_state.json \
        --replay my_replay_fills.json [--exits my_exit_engine_on_live_entries.json] [--flows flows.json] \
        [--days 28 | --since 2026-08-24 --until 2026-09-22T12:00] [--sleeves WILDCARD,TREND] [--json-out out.json]

WHY: the 2026-09-23 impartial assessment graded the replay D and set a standing rule - no configuration change other
than the dial until a scorer has graded the replay. This is that scorer (futuresbot/replay/acceptance.py holds the
logic and the THRESHOLDS with their justifications); run it weekly on a trailing 28-day window (WILDCARD makes ~12
fills a week, below the 20-fill minimum a one-week window would need).

LIVE DATA, READ-ONLY. --pull runs one read-only command on the production container and writes only to the local
directory you give it:
    railway ssh --service Futures-bot --environment production \
        "tar czf - -C /data futures_feature_store.jsonl futures_runtime_state.json | base64 -w0"
(from the repo dir; on Git Bash set MSYS_NO_PATHCONV=1 so /data is not rewritten). Nothing on the container is written,
no order is placed, no key is read or printed. The runtime state is used only for trade_history (entry price and
contracts -> contract size, and the precise entry time).

REPLAY FILLS: a JSON list (or {"fills": [...]}) with, per fill: sym, side, sleeve, ts (entry, epoch s or ISO), exit_ts,
r (net R per unit of risk; `net` accepted), and optionally sl_frac/stop_frac + lev (margin locked), mult (regime
scaler), entry + contract_size. A replay's own `usd`/`risk_usdt` are reported but NEVER used: every replay is re-priced
through futuresbot.replay.sizing (compounding on free margin, from live's cash, with live's flows).

FLOWS: deposits/withdrawals inside the window are not in the bot's files. Pass them as a JSON list of [ts, amount] or
{ts, amount, label}; a missing one shows up as a SIZING failure with a note naming the first fill where live's
available balance departs from the engine's.

DIALS: the engine prices history with futuresbot.replay.sizing.LIVE_DIALS. When the owner changes a dial, add the
change there, or the SIZING layer fails from that date - which is the intended alarm.

BAR CONVENTION (D3): entries are compared only where live's scan read the same 15m bar as the replay
(acceptance.LIVE_CONVENTIONS vs the replay's). The default is the repaired replay's (WILDCARD forming, TREND completed);
declare another with --replay-conventions TREND=forming,WILDCARD=forming.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from futuresbot.replay import acceptance as acc  # noqa: E402

PULL_FILES = ("futures_feature_store.jsonl", "futures_runtime_state.json")
PULL_CMD = "tar czf - -C /data " + " ".join(PULL_FILES) + " | base64 -w0"


def _when(s: str | None, default: float) -> float:
    if not s:
        return default
    try:
        v = float(s)
        return v / 1000.0 if v > 1e11 else v
    except ValueError:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def pull(dest: str, service: str = "Futures-bot", environment: str = "production", cwd: str | None = None) -> list[str]:
    """Read-only pull of the live files into `dest` (a local directory). Returns the paths written."""
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    exe = shutil.which("railway") or "railway"          # railway.CMD on Windows: CreateProcess needs the full name
    proc = subprocess.run([exe, "ssh", "--service", service, "--environment", environment, PULL_CMD],
                          cwd=cwd or str(ROOT), env=env, capture_output=True, text=True, timeout=300)
    blob = "".join(ch for ch in proc.stdout if ch.isalnum() or ch in "+/=")
    if proc.returncode != 0 or not blob:
        raise SystemExit(f"pull failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
    os.makedirs(dest, exist_ok=True)
    written = []
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(blob)), mode="r:gz") as tf:
        for m in tf.getmembers():
            name = os.path.basename(m.name)
            if name not in PULL_FILES or not m.isfile():
                continue                         # never extract anything but the two expected plain files
            data = tf.extractfile(m).read()
            with open(os.path.join(dest, name), "wb") as fh:
                fh.write(data)
            written.append(os.path.join(dest, name))
    return written


def _load_json_list(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return d.get("fills", d) if isinstance(d, dict) else d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pull", metavar="DIR", help="read-only pull of the live files into DIR, then exit")
    ap.add_argument("--pull-cwd", help="directory railway is linked from (default: this repo)")
    ap.add_argument("--feature-store", help="futures_feature_store.jsonl (live fills)")
    ap.add_argument("--runtime-state", help="futures_runtime_state.json (trade_history: contract size, entry time)")
    ap.add_argument("--contracts", help="MEXC contract details JSON list (symbol, contractSize, minVol)")
    ap.add_argument("--replay", help="replay fills JSON")
    ap.add_argument("--exits", help="exit-engine fills on live's own entries (default: the replay's matched fills)")
    ap.add_argument("--flows", help="deposits/withdrawals JSON list of [ts, amount] or {ts, amount, label}")
    ap.add_argument("--since", help="window start (ISO or epoch s); default until - --days")
    ap.add_argument("--until", help="window end (ISO or epoch s); default now")
    ap.add_argument("--days", type=float, default=28.0)
    ap.add_argument("--sleeves", default="WILDCARD,TREND", help="sleeves the replay models")
    ap.add_argument("--replay-conventions", default="",
                    help="SLEEVE=forming|completed,... the 15m bar the replay's entries read (default: "
                         + ",".join(f"{k}={v}" for k, v in acc.REPLAY_CONVENTIONS.items()) + ")")
    ap.add_argument("--start-cash", type=float, help="live cash at --since (default: inferred at the latest flat instant)")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--title", default="")
    ap.add_argument("--json-out", help="also write the full report as JSON")
    a = ap.parse_args(argv)
    if a.pull:
        for p in pull(a.pull, cwd=a.pull_cwd):
            print("pulled", p)
        return 0
    if not (a.feature_store and a.replay):
        ap.error("--feature-store and --replay are required (or --pull DIR)")
    until = _when(a.until, time.time())
    since = _when(a.since, until - a.days * 86400.0)
    th = []
    if a.runtime_state:
        with open(a.runtime_state, encoding="utf-8") as fh:
            th = json.load(fh).get("trade_history") or []
    contracts = None
    if a.contracts:
        contracts = {c["symbol"]: c for c in _load_json_list(a.contracts)}
    live = acc.live_fills_from_feature_store(acc.load_jsonl(a.feature_store), th, contracts)
    replay = acc.replay_fills_from_rows(_load_json_list(a.replay))
    exits = acc.replay_fills_from_rows(_load_json_list(a.exits)) if a.exits else None
    flows = _load_json_list(a.flows) if a.flows else []
    conv = dict(acc.REPLAY_CONVENTIONS)
    for kv in (x.strip() for x in a.replay_conventions.split(",") if x.strip()):
        k, _, v = kv.partition("=")
        if v.strip().lower() not in (acc.FORMING, acc.COMPLETED) or k.strip().upper() not in acc.GRADED_SLEEVES:
            ap.error(f"--replay-conventions: {kv!r} is not SLEEVE={acc.FORMING}|{acc.COMPLETED}")
        conv[k.strip().upper()] = v.strip().lower()
    rep = acc.grade(live, replay, since=since, until=until, exits=exits, flows=flows, start_cash=a.start_cash,
                    sleeves=[s.strip().upper() for s in a.sleeves.split(",") if s.strip()], n_boot=a.n_boot,
                    replay_conventions=conv)
    print(acc.format_report(rep, a.title))
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(rep.as_dict(), fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
