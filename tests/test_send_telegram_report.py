"""The daily report must render prices and P&L whatever key names the routine used."""
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "send_telegram", pathlib.Path(__file__).resolve().parents[1] / "tools" / "send_telegram.py")
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)


def test_the_09_19_payload_shape_no_longer_prints_none():
    t = {"side": "LONG", "symbol": "ZEC_USDT", "entry": None, "exit": "24h time stop", "pnl": -7.71}
    out = st._render_trade(t)
    assert "None" not in out
    assert "24h time stop" in out and "-7.71" in out and out.startswith("🔴")


def test_raw_trade_record_names_render_fully():
    t = {"side": "LONG", "symbol": "ZEC_USDT", "entry_price": 1581.99, "exit_price": 1529.36,
         "pnl_usdt": -12.13, "exit_reason": "EXCHANGE_CLOSE"}
    out = st._render_trade(t)
    assert "Entry $1,581.99 | Exit $1,529.36" in out
    assert "EXCHANGE_CLOSE" in out and "-12.13" in out
    assert st.missing_fields(t) == []


def test_documented_shape_is_unchanged():
    t = {"side": "LONG", "symbol": "SAGA_USDT", "reason": "WILDCARD retention trail",
         "entry": 0.02274, "exit": 0.0238, "pnl_usd": 8.9, "pnl_pct": 0.6, "acct_pct": 1}
    out = st._render_trade(t)
    assert out.startswith("🟢") and "Entry $0.02274 | Exit $0.0238" in out and "$8.90" in out


def test_missing_fields_are_reported():
    assert st.missing_fields({"symbol": "X", "exit": "trail"}) == ["entry", "exit", "pnl_usd"]
