import json

from futuresbot.shadow_ledger import append_row, candidate_row, ledger_path, load_rows, resolve_outcome, rewrite


class _Sig:
    symbol = "FOO_USDT"; side = "LONG"; entry_price = 100.0; sl_price = 95.0; tp_price = 125.0
    leverage = 4; sl_margin_pct = 20.0; roc_pct = 0.10; rsi = 55.0


def _row(**over):
    row = candidate_row(_Sig(), sleeve="WILDCARD", reject_reason="veto:crowded_longs", lateness=0.9)
    row.update(over)
    return row


def test_candidate_row_shape():
    r = _row()
    assert r["symbol"] == "FOO_USDT" and r["reject_reason"].startswith("veto:")
    assert r["entry_lateness"] == 0.9 and r["outcome"] is None


def test_resolver_stop_wins_adverse_first():
    r = _row(ts=1000)
    # one bar hits BOTH stop (95) and tp (125): adverse-first -> stop
    out = resolve_outcome(r, [(2000, 130.0, 90.0)], now_ts=3000)
    assert out["outcome"] == -1.0 and out["outcome_kind"] == "stop"


def test_resolver_tp():
    r = _row(ts=1000)
    out = resolve_outcome(r, [(2000, 101.0, 99.0), (3000, 126.0, 100.0)], now_ts=4000)
    assert out["outcome"] == 5.0 and out["outcome_kind"] == "tp"


def test_resolver_timeout_marks_r():
    r = _row(ts=1000)
    # never hits either level; horizon passed -> timeout marked at last mid R
    bars = [(2000, 111.0, 109.0)]  # mid 110 -> +10 / 5 = +2R
    out = resolve_outcome(r, bars, now_ts=1000 + 49 * 3600)
    assert out["outcome_kind"] == "timeout" and abs(out["outcome"] - 2.0) < 0.01


def test_resolver_pending_when_no_data_and_young():
    r = _row(ts=1000)
    assert resolve_outcome(r, [], now_ts=2000) is None


def test_short_side_resolution():
    r = _row(ts=1000, side="SHORT", entry=100.0, sl=105.0, tp=75.0)
    out = resolve_outcome(r, [(2000, 104.0, 74.0)], now_ts=3000)
    assert out["outcome"] == 5.0 and out["outcome_kind"] == "tp"
    out2 = resolve_outcome(dict(r), [(2000, 106.0, 74.0)], now_ts=3000)
    assert out2["outcome"] == -1.0  # adverse-first


def test_append_load_rewrite_roundtrip(tmp_path):
    p = str(tmp_path / "shadow.jsonl")
    # Two DISTINCT candidates. This previously appended the same row twice 1s
    # apart, which load_rows now collapses as a double-write of one signal —
    # that pattern is the real bug it dedupes (sniper wrote each blocked signal
    # twice), not something the roundtrip is meant to assert.
    append_row(p, _row(ts=1))
    append_row(p, _row(ts=2, symbol="BAR_USDT"))
    rows = load_rows(p)
    assert len(rows) == 2
    rows[0]["outcome"] = -1.0
    rewrite(p, rows)
    rows2 = load_rows(p)
    assert rows2[0]["outcome"] == -1.0 and rows2[1]["outcome"] is None


def test_ledger_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FUTURES_SHADOW_LEDGER_FILE", str(tmp_path / "x.jsonl"))
    assert ledger_path("/ignored") == str(tmp_path / "x.jsonl")


def test_detectors_emit_reasons():
    import pandas as pd
    from futuresbot.wildcard import detect_wildcard_signal
    from futuresbot.squeeze import detect_squeeze_signal
    flat = pd.DataFrame({"open": [1.0] * 50, "high": [1.01] * 50, "low": [0.99] * 50,
                         "close": [1.0] * 50, "volume": [100.0] * 50})
    reasons: list[str] = []
    assert detect_wildcard_signal(flat, "FOO_USDT", reasons) is None
    assert reasons == ["roc_below_min"]
    reasons2: list[str] = []
    assert detect_squeeze_signal(flat, "FOO_USDT", reasons2) is None
    assert len(reasons2) == 1  # exactly one bucket per rejection


def test_entry_lateness_metric():
    import pandas as pd
    from futuresbot.runtime import FuturesRuntime
    closes = [100.0] + [100.0 + i for i in range(1, 13)]  # rises to 112, entry at top
    df = pd.DataFrame({"close": closes})
    assert abs(FuturesRuntime._entry_lateness(df, "LONG") - 1.0) < 1e-9
    # short entered at the low of a falling move = maximally late too
    df2 = pd.DataFrame({"close": [112.0 - i for i in range(13)]})
    assert abs(FuturesRuntime._entry_lateness(df2, "SHORT") - 1.0) < 1e-9
