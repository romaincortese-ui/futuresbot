"""Entry slippage must reach BOTH stores, and the bug class must stay dead.

2026-09-03. `_open_wildcard_position` has stamped `entry_slippage_bps` on the
position since 2026-09-01, and 119 convex trades carried it to no store at all,
because BOTH the trade record and the feature-store row are built field by field
and neither listed it. The identical bug hit the trial-6 columns earlier, and
`_append_feature_store` carries a comment about it.

Why it matters more than a missing column usually would: slippage is the only
cost that scales with position size, so it is the central unknown for a funded
week at 6x notional - and it is the one field that CANNOT be reconstructed
afterwards, because the actual fill price is recorded nowhere else.
"""
from __future__ import annotations

import inspect

from futuresbot.runtime import FuturesRuntime

# Columns that exist to be ANALYSED. Each must appear on both write surfaces.
# Add to this list whenever a new measurement is stamped at entry.
ANALYSIS_COLUMNS = (
    "entry_slippage_bps",
    "roc_z",
    "sl_frac_designed",
    "peak_r",
    "mae_r",
    "hold_hours",
)


def _close_record_source() -> str:
    """The method that builds the trade-history record on close."""
    for name in dir(FuturesRuntime):
        try:
            src = inspect.getsource(getattr(FuturesRuntime, name))
        except Exception:
            continue
        if "trade_history.append" in src:
            return src
    raise AssertionError("could not find the close-record builder")


def test_the_convex_entry_still_measures_slippage():
    """If this stamp goes away the measurement dies silently - nothing else
    records the actual fill price."""
    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert "entry_slippage_bps" in src
    assert "signal_price" in src


def test_slippage_reaches_the_feature_store():
    """The corpus Stage-2 actually reads."""
    src = inspect.getsource(FuturesRuntime._append_feature_store)
    assert '"entry_slippage_bps"' in src
    assert '"entry_notional_usdt"' in src, "bps without notional cannot become dollars"


def test_slippage_reaches_the_trade_record():
    assert '"entry_slippage_bps"' in _close_record_source()


def test_every_analysis_column_is_on_BOTH_write_surfaces():
    """THE BUG CLASS. Three separate times a column was added to one surface and
    not the other, and each time the absence was discovered only when an
    analysis came up empty months later. Both rows are built field by field, so
    nothing but this test couples them."""
    feature_src = inspect.getsource(FuturesRuntime._append_feature_store)
    close_src = _close_record_source()
    missing = []
    for col in ANALYSIS_COLUMNS:
        in_feature = f'"{col}"' in feature_src
        in_close = f'"{col}"' in close_src
        if not (in_feature and in_close):
            where = "feature store" if in_close else "close record"
            missing.append(f"{col} (absent from the {where})")
    assert not missing, "columns on only one write surface: " + "; ".join(missing)


def test_slippage_sign_convention_is_documented_as_adverse():
    """A signed cost with an undocumented sign is worse than no cost: the funded
    week's verdict turns on whether the number means better or worse."""
    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert "WORSE" in src, "the sign convention must stay stated at the stamp"


def test_notional_is_computed_not_back_solved():
    """margin_used x leverage is None whenever the sizing-audit fields did not
    populate, which is exactly when a fill is unusual enough to care about."""
    src = inspect.getsource(FuturesRuntime._append_feature_store)
    assert 'getattr(position, "contracts"' in src
    assert 'getattr(position, "contract_size"' in src
    assert "margin_used" not in src.split("_entry_notional")[1].split("row = {")[0],         "notional must not be back-solved from margin x leverage"


def test_a_bad_position_object_cannot_kill_the_whole_feature_row():
    """THE NEAR MISS. The first version of the notional computation used bare
    attribute access. `_append_feature_store` wraps its whole body in
    `except Exception`, so one AttributeError dropped the ENTIRE row - a missing
    cost column silently became a missing corpus. Caught by two sniper tests
    that pass a SimpleNamespace position."""
    import json
    from datetime import datetime, timezone
    from types import SimpleNamespace

    src = inspect.getsource(FuturesRuntime._append_feature_store)
    assert "position.contracts" not in src, "bare attribute access is back"
    assert 'getattr(position, "contracts"' in src

    class _Rt:
        _append_feature_store = FuturesRuntime._append_feature_store
        account = SimpleNamespace(id="test")

    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        rt = _Rt()
        rt._feature_store_path = Path(d) / "fs.jsonl"
        # a position with NONE of the notional attributes
        pos = SimpleNamespace(entry_signal="WILDCARD_LONG", metadata={})
        trade = {"symbol": "X_USDT", "side": "LONG", "leverage": 5,
                 "pnl_usdt": -1.0, "pnl_pct": -1.0, "setup_regime": "OTHER_LONG",
                 "exit_time": datetime.now(timezone.utc).isoformat()}
        rt._append_feature_store(trade, pos)
        assert rt._feature_store_path.exists(), "the row was dropped entirely"
        row = json.loads(rt._feature_store_path.read_text(encoding="utf-8").strip())
        assert row["symbol"] == "X_USDT"
        assert row["entry_notional_usdt"] is None
