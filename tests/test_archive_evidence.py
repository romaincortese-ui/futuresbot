"""The daily evidence archive (tools/archive_evidence.py).

It runs against the LIVE container, so the properties that matter are the ones that must never
fail: it only reads /data, no secret crosses the wire, a corrupted transfer is refused rather
than archived, a past day is never filed with today's state, and a re-run changes nothing that
was already proven. The remote script is executed here for real against a fake /data, with a
secret planted in its environment. No network, no railway.
"""
from __future__ import annotations

import ast
import base64
import gzip
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from futuresbot.replay.bars import BarCache
from tests.test_replay_bars import Clock, FakeExchange
from tools import archive_evidence as A

NOW = 1_790_188_230.0                              # 2026-09-23 18:30:30Z
TODAY = "2026-09-23"
SECRET = "sk-live-DO-NOT-LEAK-7f3a"


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _state():
    return {
        "trade_history": [
            {"symbol": "SAGA_USDT", "entry_time": _iso(NOW - 12 * 3600), "exit_time": _iso(NOW - 11 * 3600)},
            {"symbol": "OLD_USDT", "entry_time": _iso(NOW - 40 * 3600), "exit_time": _iso(NOW - 30 * 3600)},
            {"symbol": "SPAN_USDT", "entry_time": _iso(NOW - 26 * 3600), "exit_time": _iso(NOW - 17 * 3600)},
        ],
        "open_positions": {"ZORA_USDT": {"symbol": "ZORA_USDT", "opened_at": _iso(NOW - 3600)}},
    }


def _journal():
    rows = [{"ts": int(NOW - 7200), "n": 2, "rows": [["TAKE_USDT", 2.6, 1.2e7, 2.6], ["AKE_USDT", 0.3, 1e7, 0.3]]},
            {"ts": int(NOW - 30 * 3600), "n": 1, "rows": [["YDAY_USDT", 0.5, 3e6, 0.5]]}]
    return "\n".join(json.dumps(r) for r in rows) + "\n"


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "futures_runtime_state.json").write_text(json.dumps(_state()), encoding="utf-8")
    (d / "futures_ticker_snapshots.jsonl").write_text(_journal(), encoding="utf-8")
    (d / "futures_feature_store.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
    (d / "futures_shadow_ledger.jsonl").write_text('{"b": 2}\n', encoding="utf-8")
    # futures_r_series.jsonl deliberately missing
    return d


def _local_runner(data_dir, calls):
    """Stands in for `railway ssh`: decodes the command exactly as the container shell would and
    runs the script with /data pointed at a temp dir, a secret planted in its environment."""
    def run(cmd):
        calls.append(cmd)
        prefix, suffix = "echo ", " | base64 -d | /opt/venv/bin/python -"
        assert cmd.startswith(prefix) and cmd.endswith(suffix), cmd
        script = base64.b64decode(cmd[len(prefix):-len(suffix)]).decode()
        script = script.replace("'/data/'", repr(str(data_dir).replace("\\", "/") + "/"))
        env = {"PATH": "", "SYSTEMROOT": "C:\\Windows", "MEXC_API_KEY": SECRET, "MEXC_API_SECRET": SECRET,
               "TELEGRAM_BOT_TOKEN": SECRET, "FUTURES_CONVEX_API_SECRET": SECRET,
               "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.50", "FUTURES_WILDCARD_EARLY_STOP_R": "0.5",
               "FUTURES_TREND_SYMBOLS": "ETH_USDT,XRP_USDT,ZEC_USDT,LINK_USDT"}
        out = subprocess.run([sys.executable, "-"], input=script.encode(), capture_output=True, env=env,
                             timeout=60)
        assert out.returncode == 0, out.stderr.decode()
        return "railway banner\n" + out.stdout.decode()
    return run


def _factory(exchange, clock):
    def make(root, rate=5.0):
        return BarCache(root, fetch_json=exchange, clock=clock)
    return make


# --- the container side -------------------------------------------------------------------------

def test_the_remote_script_can_only_read():
    """Whatever this archive grows into, the code sent to the live container opens files 'rb'
    under /data, writes only to stdout, and calls nothing that mutates the filesystem or spawns."""
    tree = ast.parse(A.remote_script())
    banned = {"remove", "unlink", "rename", "replace", "rmdir", "makedirs", "mkdir", "chmod", "system",
              "popen", "truncate", "symlink", "link", "utime", "kill"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert not {a.name for a in node.names} & {"subprocess", "shutil", "socket", "urllib"}
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            assert name not in banned
            if name == "open":
                assert [a.value for a in node.args[1:2]] == ["rb"]
            if name == "write":
                assert ast.unparse(f) == "sys.stdout.write"
    assert set(A.CONTAINER_FILES) == {"futures_feature_store.jsonl", "futures_shadow_ledger.jsonl",
                                      "futures_r_series.jsonl", "futures_ticker_snapshots.jsonl",
                                      "futures_runtime_state.json"}


def test_no_secret_ever_leaves_the_container(data_dir):
    """The env whitelist is applied ON the container; a key outside it (or a whitelisted prefix
    carrying KEY/SECRET/TOKEN) never reaches stdout."""
    calls = []
    run = _local_runner(data_dir, calls)
    raw = run(f"echo {base64.b64encode(A.remote_script().encode()).decode()} | base64 -d | /opt/venv/bin/python -")
    assert SECRET not in raw
    snap = A.pull_container(_local_runner(data_dir, []))
    assert snap["env"] == {"FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.50", "FUTURES_WILDCARD_EARLY_STOP_R": "0.5",
                           "FUTURES_TREND_SYMBOLS": "ETH_USDT,XRP_USDT,ZEC_USDT,LINK_USDT"}
    assert A.env_allowed("FUTURES_CONVEX_TRAIL_ARM_R")
    for bad in ("MEXC_API_KEY", "FUTURES_CONVEX_API_SECRET", "FUTURES_CONVEX_TOKEN", "DATABASE_URL",
                "FUTURES_WILDCARD_RISK_PCT_PASSWORD"):
        assert not A.env_allowed(bad)


def test_pull_verifies_every_file_and_flags_missing_ones(data_dir):
    snap = A.pull_container(_local_runner(data_dir, []))
    assert snap["files"]["futures_runtime_state.json"] == (data_dir / "futures_runtime_state.json").read_bytes()
    assert snap["files"]["futures_r_series.jsonl"] is None
    assert snap["meta"]["futures_r_series.jsonl"] == {"missing": True}


def test_a_corrupted_transfer_is_refused_not_archived(data_dir):
    def tamper(cmd):
        out = _local_runner(data_dir, [])(cmd)
        head, body, tail = out.split(A.MARK)
        doc = json.loads(body)
        f = doc["files"]["futures_feature_store.jsonl"]
        f["gz_b64"] = base64.b64encode(gzip.compress(b'{"a": 2}\n')).decode()
        return head + A.MARK + json.dumps(doc) + A.MARK + tail
    with pytest.raises(RuntimeError, match="verification"):
        A.pull_container(tamper)


# --- the archive --------------------------------------------------------------------------------

def test_symbols_are_what_was_traded_or_scanned_that_day():
    t0, t1 = A.day_bounds(TODAY)
    syms = A.symbols_for_day(TODAY, json.dumps(_state()).encode(), _journal().encode(),
                             {"FUTURES_TREND_SYMBOLS": "ETH_USDT,LINK_USDT"})
    assert syms["traded"] == ["SAGA_USDT", "SPAN_USDT", "ZORA_USDT"]      # SPAN opened yesterday, closed today
    assert syms["scanned"] == ["AKE_USDT", "TAKE_USDT"]
    assert set(syms["always"]) == set(A.ALWAYS_SYMBOLS) | {"LINK_USDT"}
    assert t1 - t0 == 86400


def test_daily_run_writes_everything_dated_and_a_rerun_changes_nothing(tmp_path, data_dir):
    out = tmp_path / "evidence"
    clock = Clock(NOW)
    ex = FakeExchange(clock)
    calls = []
    s1 = A.run_daily(None, out, _local_runner(data_dir, calls), now=NOW, cache_factory=_factory(ex, clock),
                     log=lambda m: None)
    day = out / "archive" / TODAY
    assert s1["day"] == TODAY and len(calls) == 1
    # The fake container runs without FUTURES_WILDCARD_CONVEX_EXIT_ENABLED: the replay timeline no
    # longer describes it, and the run must say so rather than replay a stack that is not live.
    assert "WILDCARD.convex: timeline True != live False" in s1["run"]["exit_timeline_drift"]
    for name in ("futures_runtime_state.json", "futures_ticker_snapshots.jsonl", "futures_feature_store.jsonl"):
        assert gzip.decompress((day / "container" / (name + ".gz")).read_bytes()) == (data_dir / name).read_bytes()
    assert json.loads((day / "container" / "exit_env.json").read_text())["env"]["FUTURES_CONVEX_TRAIL_RETAIN_FRAC"] == "0.50"
    man = json.loads((day / "MANIFEST.json").read_text())
    assert "TAKE_USDT" in man["bars"] and man["bars"]["TAKE_USDT"]["fair"]["bars"] == 1110   # 00:00 -> 18:29
    assert (day / "bars" / "fair" / "Min1" / "TAKE_USDT" / f"{TODAY}.json.gz").exists()
    assert not list(out.rglob("*.tmp"))
    n = len(ex.requests)
    s2 = A.run_daily(None, out, _local_runner(data_dir, []), now=NOW, cache_factory=_factory(ex, clock),
                     log=lambda m: None)
    assert len(ex.requests) == n, "proven bars are never fetched twice"
    assert set(s2["run"]["container"].values()) <= {"unchanged", "missing", "written"}
    assert s2["run"]["container"]["futures_runtime_state.json"] == "unchanged"
    assert s2["run"]["container"]["exit_env.json"] == "unchanged"
    assert len(json.loads((day / "MANIFEST.json").read_text())["runs"]) == 2


def test_the_next_day_finishes_yesterdays_bars(tmp_path, data_dir):
    out = tmp_path / "evidence"
    clock = Clock(NOW)
    ex = FakeExchange(clock)
    A.run_daily(None, out, _local_runner(data_dir, []), now=NOW, cache_factory=_factory(ex, clock), log=lambda m: None)
    clock.t = NOW + 6 * 3600                       # 2026-09-24 00:30Z
    s = A.run_daily(None, out, _local_runner(data_dir, []), now=clock.t, cache_factory=_factory(ex, clock),
                    log=lambda m: None)
    assert s["day"] == "2026-09-24" and s["previous"] == TODAY
    man = json.loads((out / "archive" / TODAY / "MANIFEST.json").read_text())
    assert man["bars"]["TAKE_USDT"]["fair"]["bars"] == 1440 and man["bars"]["TAKE_USDT"]["fair"]["holes"] == []


def test_a_past_day_never_pulls_todays_state_into_it(tmp_path, data_dir):
    """The container only holds NOW. Filing it under an earlier date would fake a snapshot."""
    out = tmp_path / "evidence"
    clock = Clock(NOW)
    ex = FakeExchange(clock)
    A.run_daily(None, out, _local_runner(data_dir, []), now=NOW, cache_factory=_factory(ex, clock), log=lambda m: None)
    calls = []
    s = A.run_daily("2026-09-22", out, _local_runner(data_dir, calls), now=NOW, finish_previous=False,
                    cache_factory=_factory(ex, clock), log=lambda m: None)
    assert calls == [] and s["day"] == "2026-09-22"
    past = out / "archive" / "2026-09-22"
    assert not (past / "container").exists()
    man = json.loads((past / "MANIFEST.json").read_text())
    assert "YDAY_USDT" in man["symbols"]["scanned"] and "OLD_USDT" in man["symbols"]["traded"]
    assert man["bars"]["YDAY_USDT"]["last"]["bars"] == 1440


def test_a_day_the_exchange_no_longer_serves_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        A.run_daily("2026-08-20", tmp_path, None, now=NOW, log=lambda m: None)


def test_backfill_symbol_sets_resolve_from_the_study_tree(tmp_path):
    root = tmp_path / "wc"
    (root / "WCF" / "E" / "data").mkdir(parents=True)
    (root / "WCF" / "E" / "data" / "eligible.json").write_text(json.dumps(["B_USDT", "A_USDT", "A_USDT"]))
    assert A.load_set("E", roots=[tmp_path / "nowhere", root]) == ["A_USDT", "B_USDT"]
    with pytest.raises(FileNotFoundError):
        A.load_set("H", roots=[root])
