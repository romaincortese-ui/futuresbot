"""Daily evidence archive: container journals + MEXC last/fair 1m bars, dated, idempotent, read-only.

WHY (assessment 2026-09-23, "The Outsider"): the whole evidence base lived in %TEMP%; eight cited
study folders were already gone; MEXC serves 1m klines for only ~30 days and 15m for ~361, both
sliding forward daily; and the bot's own journals are ring-buffered or rewritten in place. Every
test the assessment ranked (forming-bar vs completed-bar entries, TREND without the trail, the
acceptance scorer) depends on data that disappears a day at a time. The owner approved a daily
archive; this is it.

WHAT ONE RUN DOES (default: today, UTC)
  1. Pulls, READ-ONLY, one snapshot of the container's journals over `railway ssh`:
       futures_feature_store.jsonl   conditional-expectancy feature rows
       futures_shadow_ledger.jsonl   refused / shadow candidates
       futures_r_series.jsonl        per-position R paths
       futures_ticker_snapshots.jsonl  the WILDCARD scan journal (one line per scan: ts + movers)
       futures_runtime_state.json    trade_history, open positions, trial marker
     plus the exit/risk env values (a fixed whitelist of non-secret FUTURES_* names, filtered ON
     THE CONTAINER so nothing else ever crosses the wire) and the deployed commit when Railway
     exposes it (RAILWAY_GIT_COMMIT_SHA; absent on 2026-09-23). Each file is
     read once into memory on the container, hashed and gzipped there, and verified by hash here.
     Nothing on the container is written: the remote side is a read-only Python script piped to
     the interpreter on stdin.
  2. Caches MEXC LAST and FAIR 1m bars (futuresbot.replay.bars) for every symbol the bot traded
     (open or closed positions overlapping the day) or scanned (the journal's movers that day),
     plus the TREND universe and the majors its gates read.
  3. Finishes the PREVIOUS day's bars too (their tail was still forming at the last run), so a
     job run at any hour leaves every past day complete.

LAYOUT  <out>/archive/YYYY-MM-DD/
            container/<file>.gz        snapshot taken that UTC day (latest run wins, hash-checked)
            bars/<feed>/Min1/<SYM>/YYYY-MM-DD.json.gz   (a futuresbot.replay.bars cache root)
            MANIFEST.json              every run: what was pulled, hashes, symbols, holes
IDEMPOTENT: an unchanged container file is not rewritten; bars already proven are not refetched.

BACKFILL (one-off, the assessment's "cache fair and last 15m for the E and H symbol sets"):
    python tools/archive_evidence.py backfill-15m --sets E,H
writes <out>/bars/<feed>/Min15/<SYM>/YYYY-MM.json.gz from as far back as MEXC still serves.

Never prints a secret, never writes /data, never places an order, never deploys.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from futuresbot.replay.bars import BarCache, HISTORY_DAYS  # noqa: E402
from futuresbot.replay.exits import timeline_drift  # noqa: E402

DEFAULT_OUT = Path(os.environ.get("FUTURESBOT_EVIDENCE_DIR", "C:/Users/Rocot/futuresbot-evidence"))
SERVICE = "Futures-bot"
ENVIRONMENT = "production"
# The owner-approved list. Read-only on the container.
CONTAINER_FILES = (
    "futures_feature_store.jsonl",
    "futures_shadow_ledger.jsonl",
    "futures_r_series.jsonl",
    "futures_ticker_snapshots.jsonl",
    "futures_runtime_state.json",
)
# Exit / sizing parameters a replay needs to know were live that day. A WHITELIST of names,
# matched on the container: a key outside it never leaves the process. The deny pattern is a
# second lock in case a whitelisted prefix ever grows a secret.
ENV_WHITELIST = re.compile(
    r"^(FUTURES_CONVEX_[A-Z0-9_]+|FUTURES_(WILDCARD|TREND)_EARLY_STOP_[A-Z_]+"
    r"|FUTURES_TREND_(TRAIL_ENABLED|TRAIL_ARM_R|BREAKEVEN_ARM_R)"   # EXP/T: else a live flip escapes drift
    r"|FUTURES_WILDCARD_CONVEX_EXIT_ENABLED|FUTURES_(WILDCARD|TREND)_RISK_PCT|FUTURES_TREND_TP_R"
    r"|FUTURES_TREND_SYMBOLS|FUTURES_OPEN_POSITION_MONITOR_SECONDS|USE_FUTURES_FAIR_PRICE_WS"
    r"|FUTURES_WILDCARD_(COMPLETED_BARS|MAX_BAR_AGE_SECONDS)"
    r"|RAILWAY_GIT_COMMIT_SHA)$")
ENV_DENY = re.compile(r"KEY|SECRET|TOKEN|PASS|AUTH|COOKIE|PRIVATE|CREDENTIAL|SESSION", re.I)
# TREND scans these every cycle and its gates read BTC/SOL; they are "scanned" every day.
ALWAYS_SYMBOLS = ("BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "ZEC_USDT")
MARK = "<<ARCHIVE_EVIDENCE>>"


def env_allowed(name: str) -> bool:
    return bool(ENV_WHITELIST.match(name)) and not ENV_DENY.search(name)


def remote_script(files: Iterable[str] = CONTAINER_FILES) -> str:
    """The Python the container runs. Opens files 'rb' only; prints one JSON document between
    markers. Kept free of any write call - tests/test_archive_evidence.py asserts that."""
    return (
        "import base64,gzip,hashlib,json,os,re,sys,time\n"
        f"F={list(files)!r}\n"
        f"W=re.compile({ENV_WHITELIST.pattern!r})\n"
        f"D=re.compile({ENV_DENY.pattern!r},re.I)\n"
        "o={'pulled_at':time.time(),'files':{},'env':{}}\n"
        "for f in F:\n"
        "    p='/data/'+f\n"
        "    try:\n"
        "        st=os.stat(p)\n"
        "        with open(p,'rb') as h: raw=h.read()\n"
        "        o['files'][f]={'size':len(raw),'mtime':st.st_mtime,'sha256':hashlib.sha256(raw).hexdigest(),"
        "'gz_b64':base64.b64encode(gzip.compress(raw,6)).decode()}\n"
        "    except FileNotFoundError:\n"
        "        o['files'][f]={'missing':True}\n"
        "o['env']={k:v for k,v in os.environ.items() if W.match(k) and not D.search(k)}\n"
        f"sys.stdout.write({MARK!r}+json.dumps(o)+{MARK!r})\n"
    )


def railway_runner(cwd: str | os.PathLike) -> Callable[[str], str]:
    """Runs one read-only shell command on the container; returns stdout."""
    exe = shutil.which("railway") or shutil.which("railway.cmd") or "railway"

    def run(cmd: str) -> str:
        env = dict(os.environ, MSYS_NO_PATHCONV="1")
        res = subprocess.run([exe, "ssh", "--service", SERVICE, "--environment", ENVIRONMENT, cmd],
                             cwd=str(cwd), env=env, capture_output=True, timeout=600)
        if res.returncode != 0:
            # stderr can carry CLI noise but never the payload; truncate anyway.
            raise RuntimeError("railway ssh failed (%d): %s" % (res.returncode,
                                                               res.stderr.decode("utf-8", "replace")[:300]))
        return res.stdout.decode("utf-8", "replace")
    return run


def pull_container(run: Callable[[str], str], files: Iterable[str] = CONTAINER_FILES) -> dict:
    """One snapshot of the approved files. Returns {'pulled_at', 'env', 'files': {name: bytes|None},
    'meta': {name: {size, mtime, sha256}}}; raises if any payload fails its hash."""
    script = base64.b64encode(remote_script(files).encode()).decode()
    out = run(f"echo {script} | base64 -d | /opt/venv/bin/python -")
    parts = out.split(MARK)
    if len(parts) < 3:
        raise RuntimeError("container answer carried no archive payload")
    doc = json.loads(parts[1])
    res = {"pulled_at": float(doc["pulled_at"]), "files": {}, "meta": {},
           "env": {k: v for k, v in (doc.get("env") or {}).items() if env_allowed(k)}}
    for name, m in doc["files"].items():
        if m.get("missing"):
            res["files"][name] = None
            res["meta"][name] = {"missing": True}
            continue
        raw = gzip.decompress(base64.b64decode(m["gz_b64"]))
        sha = hashlib.sha256(raw).hexdigest()
        if sha != m["sha256"] or len(raw) != int(m["size"]):
            raise RuntimeError(f"{name}: payload failed verification (sha/size mismatch)")
        res["files"][name] = raw
        res["meta"][name] = {"size": len(raw), "mtime": m["mtime"], "sha256": sha}
    return res


# ---------------------------------------------------------------------------------------------
# symbol selection
# ---------------------------------------------------------------------------------------------
def _ts(x: Any) -> float | None:
    if x in (None, ""):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except ValueError:
        return None


def traded_symbols(state: dict, t0: float, t1: float) -> set[str]:
    """Symbols with a position overlapping [t0, t1): closed trades plus whatever is open."""
    out: set[str] = set()
    for r in state.get("trade_history") or []:
        a, b = _ts(r.get("entry_time")), _ts(r.get("exit_time"))
        if a is not None and a < t1 and (b is None or b >= t0) and r.get("symbol"):
            out.add(str(r["symbol"]))
    ops = state.get("open_positions") or {}
    for p in (ops.values() if isinstance(ops, dict) else ops):
        if isinstance(p, dict) and p.get("symbol"):
            a = _ts(p.get("opened_at"))
            if a is None or a < t1:
                out.add(str(p["symbol"]))
    return out


def scanned_symbols(journal_lines: Iterable[str], t0: float, t1: float) -> set[str]:
    """Movers the WILDCARD scan journal says were scanned in [t0, t1)."""
    out: set[str] = set()
    for line in journal_lines:
        try:
            d = json.loads(line)
            ts = float(d["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        if t0 <= ts < t1:
            out.update(str(r[0]) for r in d.get("rows") or [] if r)
    return out


def day_bounds(day: str) -> tuple[int, int]:
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    t0 = int(d.timestamp())
    return t0, t0 + 86400


# ---------------------------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------------------------
def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _load_manifest(day_dir: Path) -> dict:
    p = day_dir / "MANIFEST.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"day": day_dir.name, "container": {}, "bars": {}, "runs": []}


def _save_manifest(day_dir: Path, man: dict) -> None:
    _atomic_write(day_dir / "MANIFEST.json", json.dumps(man, indent=1, sort_keys=True).encode("utf-8"))


def store_container(day_dir: Path, snap: dict, man: dict) -> dict:
    """Write each verified file as <name>.gz unless the stored copy has the same hash."""
    written = {}
    for name, raw in snap["files"].items():
        meta = snap["meta"][name]
        prev = man["container"].get(name) or {}
        target = day_dir / "container" / (name + ".gz")
        if raw is None:
            written[name] = "missing"
            continue
        if prev.get("sha256") == meta["sha256"] and target.exists():
            written[name] = "unchanged"
            continue
        _atomic_write(target, gzip.compress(raw, 6))
        man["container"][name] = dict(meta, pulled_at=snap["pulled_at"])
        written[name] = "written"
    if snap.get("env"):
        target = day_dir / "container" / "exit_env.json"
        prev_env = json.loads(target.read_text(encoding="utf-8")).get("env") if target.exists() else None
        if prev_env == snap["env"]:
            written["exit_env.json"] = "unchanged"
        else:
            env_doc = json.dumps({"pulled_at": snap["pulled_at"], "env": snap["env"]}, indent=1, sort_keys=True)
            _atomic_write(target, env_doc.encode("utf-8"))
            written["exit_env.json"] = "written"
    return written


def archive_bars(day: str, symbols: Iterable[str], out: Path, *, cache_factory=BarCache,
                 workers: int = 6, now: float | None = None, rate: float = 5.0) -> dict:
    """LAST and FAIR Min1 bars of `day` for every symbol, into <out>/archive/<day>/bars."""
    t0, t1 = day_bounds(day)
    now = time.time() if now is None else now
    cache = cache_factory(str(out / "archive" / day / "bars"), rate=rate)
    syms = sorted(set(symbols))
    jobs = [(s, f) for s in syms for f in ("last", "fair")]

    end = min(t1, int(now // 60 * 60))            # completed minutes only; the rest is next run's

    def one(job):
        s, f = job
        b = cache.load(s, f, "Min1", t0, end)
        return s, f, len(b), [list(u) for u in b.unavailable]

    res: dict = {}
    with ThreadPoolExecutor(max(1, workers)) as pool:
        for s, f, n, holes in pool.map(one, jobs):
            res.setdefault(s, {})[f] = {"bars": n, "holes": holes}
    return res


def _latest_snapshot(out: Path, name: str, before_or_on: str) -> bytes | None:
    root = out / "archive"
    if not root.is_dir():
        return None
    for d in sorted((p for p in root.iterdir() if p.is_dir() and p.name <= before_or_on), reverse=True):
        f = d / "container" / (name + ".gz")
        if f.exists():
            return gzip.decompress(f.read_bytes())
    return None


def symbols_for_day(day: str, state_raw: bytes | None, journal_raw: bytes | None,
                    env: dict | None = None) -> dict[str, list[str]]:
    t0, t1 = day_bounds(day)
    state = json.loads(state_raw.decode("utf-8")) if state_raw else {}
    lines = io.StringIO(journal_raw.decode("utf-8", "replace")) if journal_raw else []
    trend = [s.strip().upper() for s in ((env or {}).get("FUTURES_TREND_SYMBOLS") or "").split(",") if s.strip()]
    return {"traded": sorted(traded_symbols(state, t0, t1)),
            "scanned": sorted(scanned_symbols(lines, t0, t1)),
            "always": sorted(set(ALWAYS_SYMBOLS) | set(trend))}


def run_daily(day: str | None, out: Path, run: Callable[[str], str] | None, *, now: float | None = None,
              workers: int = 6, finish_previous: bool = True, cache_factory=BarCache, rate: float = 5.0,
              log: Callable[[str], None] = print) -> dict:
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    day = day or today
    t0, _ = day_bounds(day)
    if now - t0 > (HISTORY_DAYS["Min1"] - 1) * 86400:
        raise SystemExit(f"{day}: MEXC no longer serves its 1m bars (~{HISTORY_DAYS['Min1']:.0f}-day window)")
    day_dir = out / "archive" / day
    man = _load_manifest(day_dir)
    run_rec: dict = {"at": round(now, 1)}
    env: dict = {}
    if day == today and run is not None:
        snap = pull_container(run)
        run_rec["container"] = store_container(day_dir, snap, man)
        env = snap.get("env") or {}
        state_raw = snap["files"].get("futures_runtime_state.json")
        journal_raw = snap["files"].get("futures_ticker_snapshots.jsonl")
        log("container: " + ", ".join(f"{k}={v}" for k, v in sorted(run_rec["container"].items())))
        # The replay's deployed-exit timeline must end where live is. A difference means an exit
        # dial moved and futuresbot/replay/exits.LIVE_TIMELINE needs a row.
        drift = timeline_drift(env)
        run_rec["exit_timeline_drift"] = drift
        if drift:
            log("WARNING exits.LIVE_TIMELINE is stale: " + "; ".join(drift))
    else:
        # A past day: the container holds today's state, which must not be filed under that day.
        # Symbols come from the newest archived snapshot on or after it (the journals are cumulative).
        state_raw = _latest_snapshot(out, "futures_runtime_state.json", "9999-12-31")
        journal_raw = _latest_snapshot(out, "futures_ticker_snapshots.jsonl", "9999-12-31")
    syms = symbols_for_day(day, state_raw, journal_raw, env)
    allsyms = set().union(*syms.values())
    man["symbols"] = syms
    log(f"{day}: {len(syms['traded'])} traded, {len(syms['scanned'])} scanned, {len(allsyms)} symbols")
    res = archive_bars(day, allsyms, out, cache_factory=cache_factory, workers=workers, now=now, rate=rate)
    man["bars"] = res
    holes = sum(1 for s in res.values() for f in s.values() if any(h[2] != "not_closed" for h in f["holes"]))
    run_rec["bars"] = {"symbols": len(res), "series_with_holes": holes,
                       "bars": sum(f["bars"] for s in res.values() for f in s.values())}
    man["runs"] = (man.get("runs") or [])[-49:] + [run_rec]
    _save_manifest(day_dir, man)
    log(f"{day}: bars {run_rec['bars']}")
    summary = {"day": day, "run": run_rec}
    if finish_previous:
        prev = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        pdir = out / "archive" / prev
        if (pdir / "MANIFEST.json").exists():
            pman = _load_manifest(pdir)
            psyms = set().union(*(pman.get("symbols") or {}).values()) if pman.get("symbols") else set()
            if psyms:
                pres = archive_bars(prev, psyms, out, cache_factory=cache_factory, workers=workers, now=now,
                                    rate=rate)
                pman["bars"] = pres
                pman["runs"] = (pman.get("runs") or [])[-49:] + [{"at": round(now, 1), "finished_by": day}]
                _save_manifest(pdir, pman)
                summary["previous"] = prev
    return summary


# ---------------------------------------------------------------------------------------------
# one-off 15m backfill
# ---------------------------------------------------------------------------------------------
SET_SOURCES = {
    # replay E (wc/WCF/E): the 601-symbol point-in-time pool, 2026-01-27 ->
    "E": ("WCF/E/data/eligible.json",),
    # replay H (wc/WCR/H): the 529-symbol pool, 2025-10-01 -> 2026-02-04 - the one rolling off.
    "H": ("WCR/H/data/eligible.json",),
}
# The %TEMP% working copy first (the permanent copy under futuresbot-evidence/wc may still be
# mid-copy), then the archive.
WC_ROOTS = (Path(tempfile.gettempdir()) / "wc", Path("C:/Users/Rocot/futuresbot-evidence/wc"))


def load_set(name: str, roots: Iterable[Path] = WC_ROOTS) -> list[str]:
    for root in roots:
        for rel in SET_SOURCES[name]:
            p = Path(root) / rel
            if p.exists():
                syms = json.loads(p.read_text(encoding="utf-8"))
                return sorted({str(s) for s in (syms.keys() if isinstance(syms, dict) else syms)})
    raise FileNotFoundError(f"symbol set {name}: none of {SET_SOURCES[name]} under {list(roots)}")


def backfill_15m(sets: Iterable[str], out: Path, *, workers: int = 6, rate: float = 6.0,
                 now: float | None = None, log: Callable[[str], None] = print,
                 cache: BarCache | None = None) -> dict:
    now = time.time() if now is None else now
    root = out / "bars"
    members: dict[str, list[str]] = {s: load_set(s) for s in sets}
    for s, syms in members.items():
        _atomic_write(root / "sets" / f"{s}.json", json.dumps(syms).encode("utf-8"))
    universe = sorted(set().union(*members.values()))
    cache = cache or BarCache(str(root), rate=rate)
    start = now - (HISTORY_DAYS["Min15"] + 2) * 86400
    report: dict = {}
    done = [0]

    def one(sym):
        r = {}
        for feed in ("fair", "last"):
            try:
                b = cache.load(sym, feed, "Min15", start, now)
            except Exception as exc:               # one bad symbol must not end a 2-hour run
                r[feed] = {"bars": 0, "first": None, "last": None, "holes": ["error"],
                           "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                continue
            kinds = sorted({u[2] for u in b.unavailable})
            r[feed] = {"bars": len(b), "first": b.time[0] if b.time else None,
                       "last": b.time[-1] if b.time else None, "holes": kinds}
        done[0] += 1
        if done[0] % 25 == 0:
            log(f"backfill {done[0]}/{len(universe)} {sym} {cache.stats}")
        return sym, r

    with ThreadPoolExecutor(max(1, workers)) as pool:
        for sym, r in pool.map(one, universe):
            report[sym] = r
    summary = {"at": round(now, 1), "sets": {s: len(v) for s, v in members.items()}, "symbols": len(universe),
               "requests": cache.stats["requests"], "failed": cache.stats["failed"]}
    for feed in ("fair", "last"):
        rows = [v[feed] for v in report.values()]
        summary[feed] = {"bars": sum(r["bars"] for r in rows),
                         "symbols_with_bars": sum(1 for r in rows if r["bars"]),
                         "unknown_symbol": sorted(k for k, v in report.items() if "unknown_symbol" in v[feed]["holes"]),
                         "fetch_failed": sorted(k for k, v in report.items() if "fetch_failed" in v[feed]["holes"]),
                         "errors": sorted(k for k, v in report.items() if "error" in v[feed]["holes"]),
                         "earliest": min((r["first"] for r in rows if r["first"]), default=None)}
    _atomic_write(root / "BACKFILL_15M.json", json.dumps({"summary": summary, "symbols": report},
                                                           indent=1, sort_keys=True).encode("utf-8"))
    return summary


def dir_size(p: Path) -> tuple[int, int]:
    n = b = 0
    for dp, _dn, fn in os.walk(p):
        for f in fn:
            n += 1
            b += os.path.getsize(os.path.join(dp, f))
    return n, b


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("daily", help="container journals + that day's 1m bars (default command)")
    d.add_argument("--day", help="YYYY-MM-DD (UTC); default today. Past days archive bars only.")
    d.add_argument("--no-container", action="store_true", help="skip the railway pull")
    d.add_argument("--railway-cwd", default=str(REPO), help="a directory linked to the railway project")
    d.add_argument("--workers", type=int, default=6)
    d.add_argument("--rate", type=float, default=5.0, help="MEXC requests per second")
    b = sub.add_parser("backfill-15m", help="one-off: 15m last+fair bars for replay symbol sets")
    b.add_argument("--sets", default="E,H")
    b.add_argument("--workers", type=int, default=6)
    b.add_argument("--rate", type=float, default=6.0)
    for p in (d, b):
        p.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    if args.cmd == "backfill-15m":
        s = backfill_15m([x.strip() for x in args.sets.split(",") if x.strip()], out,
                         workers=args.workers, rate=args.rate)
        n, sz = dir_size(out / "bars")
        print(json.dumps(dict(s, files=n, bytes=sz), indent=1))
        return 0
    if args.cmd is None:
        args = ap.parse_args(["daily"] + (argv or sys.argv[1:]))
    run = None if args.no_container else railway_runner(args.railway_cwd)
    s = run_daily(args.day, out, run, workers=args.workers, rate=args.rate)
    n, sz = dir_size(out / "archive" / s["day"])
    print(json.dumps(dict(s, files=n, bytes=sz), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
