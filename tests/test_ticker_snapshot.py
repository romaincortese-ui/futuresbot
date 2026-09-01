"""The ticker recorder must be cheap, bounded, and unable to break a scan.

Added 2026-09-01. The replay could not reproduce the live book - over trials
17-18 it shared 4 trades out of ~38 - and a four-lever ablation showed the
residual is the UNIVERSE: `movers` is built from exchange ticker snapshots
(amount24, the exchange's own 24h high/low, the 7d turnover deflator), none of
which is recoverable from klines afterwards. Recording it is the only route to a
replay that sees what live saw.

Because it runs inside the live scan loop, the property that matters most is
NEGATIVE: it must never raise, whatever the disk or the data does. A diagnostic
that can halt trading is worse than no diagnostic.
"""
from __future__ import annotations

import json

from tests.test_trail_ratchet import rt  # noqa: F401  (shared fixture)


def test_snapshot_writes_one_compact_line_per_scan(rt, tmp_path, monkeypatch):
    path = tmp_path / "snap.jsonl"
    monkeypatch.setattr(rt, "_ticker_snapshot_path", lambda: str(path))
    rt._wildcard_attribution = {
        "AAA_USDT": {"turnover_24h_usdt": 5_000_000.0, "range_24h": 0.12},
        "BBB_USDT": {"turnover_24h_usdt": 2_500_000.0, "range_24h": 0.09},
    }
    rt._record_ticker_snapshot([(0.12, "AAA_USDT"), (0.09, "BBB_USDT")])

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1, "one line per scan"
    row = json.loads(lines[0])
    assert row["n"] == 2
    assert row["rows"][0][0] == "AAA_USDT"
    assert row["rows"][0][2] == 5_000_000.0, "turnover must survive"
    assert row["rows"][0][3] == 0.12, "24h range must survive"
    # rows are ARRAYS: with objects the key names would outweigh the values
    assert isinstance(row["rows"][0], list)


def test_two_scans_append_rather_than_overwrite(rt, tmp_path, monkeypatch):
    path = tmp_path / "snap.jsonl"
    monkeypatch.setattr(rt, "_ticker_snapshot_path", lambda: str(path))
    rt._wildcard_attribution = {"AAA_USDT": {"turnover_24h_usdt": 1.0, "range_24h": 0.1}}
    rt._record_ticker_snapshot([(0.1, "AAA_USDT")])
    rt._record_ticker_snapshot([(0.1, "AAA_USDT")])
    assert len(path.read_text(encoding="utf-8").strip().split("\n")) == 2


def test_missing_attribution_does_not_lose_the_row(rt, tmp_path, monkeypatch):
    """A symbol with no attribution entry must still be recorded - knowing it
    was in the movers list is the point, even without its turnover."""
    path = tmp_path / "snap.jsonl"
    monkeypatch.setattr(rt, "_ticker_snapshot_path", lambda: str(path))
    rt._wildcard_attribution = {}
    rt._record_ticker_snapshot([(0.15, "GHOST_USDT")])
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["rows"] == [["GHOST_USDT", 0.15, 0.0, 0.0]]


def test_disabled_by_flag_writes_nothing(rt, tmp_path, monkeypatch):
    path = tmp_path / "snap.jsonl"
    monkeypatch.setattr(rt, "_ticker_snapshot_path", lambda: str(path))
    monkeypatch.setenv("FUTURES_TICKER_SNAPSHOT_ENABLED", "0")
    rt._wildcard_attribution = {"A_USDT": {}}
    rt._record_ticker_snapshot([(0.1, "A_USDT")])
    assert not path.exists()


def test_an_unwritable_path_never_raises(rt, monkeypatch):
    """THE SAFETY PROPERTY. This runs inside the live scan; a disk problem must
    degrade to no diagnostics, never to a failed scan."""
    monkeypatch.setattr(rt, "_ticker_snapshot_path",
                        lambda: "/nonexistent-dir-xyz/snap.jsonl")
    rt._wildcard_attribution = {"A_USDT": {}}
    rt._record_ticker_snapshot([(0.1, "A_USDT")])   # must not raise


def test_garbage_movers_never_raise(rt, tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_ticker_snapshot_path", lambda: str(tmp_path / "s.jsonl"))
    rt._wildcard_attribution = {"A_USDT": {"turnover_24h_usdt": "not-a-number"}}
    rt._record_ticker_snapshot([(None, "A_USDT")])  # must not raise


def test_the_scan_calls_it(rt):
    """Pins the call site: a recorder nothing invokes records nothing."""
    import inspect

    from futuresbot.runtime import FuturesRuntime
    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    assert "self._record_ticker_snapshot(movers)" in src
