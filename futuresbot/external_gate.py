"""External entry veto ('reality check') for the convex sleeves (wildcard +
squeeze), which fire on MEXC data ALONE and bleed on MEXC-only manipulated /
illiquid microcap pumps.

Before opening, corroborate against a SECOND venue (Bybit primary, OKX fallback):
  1. CROSS-EXCHANGE: does the pair even trade there with liquidity, and (for a
     big mover) is the move real cross-exchange — or a MEXC-only pump?
  2. CROWDING: don't enter the heavily-crowded side (extreme funding = cascade
     risk against us).

FAIL-OPEN by contract: any error/timeout/unreachable venue -> ALLOW. The gate
only ever SUBTRACTS bad trades; an infra problem must never block (or force) one.
Pure decision functions are unit-tested; the fetch is best-effort.
"""
from __future__ import annotations

import json
import urllib.request


def perp_symbol(mexc_sym: str) -> str:
    """MEXC 'BTC_USDT' -> Bybit/Binance 'BTCUSDT'."""
    return mexc_sym.replace("_", "").upper()


def okx_inst(mexc_sym: str) -> str:
    """MEXC 'BTC_USDT' -> OKX 'BTC-USDT-SWAP'."""
    base = mexc_sym.upper().replace("_USDT", "")
    return f"{base}-USDT-SWAP"


def decide_cross_exchange(mexc_move_pct: float, ref_move_pct: float, ref_listed: bool, *,
                          require_listed: bool = True, big_move: float = 0.05,
                          min_corroboration: float = 0.4) -> tuple[bool, str]:
    """Allow/veto on cross-exchange reality. Veto a pair that doesn't trade on the
    reference venue (MEXC-only) and, for a BIG mover, one whose move the reference
    venue does not corroborate (same sign, >= min_corroboration of the magnitude)."""
    if not ref_listed:
        return (not require_listed, "ref_not_listed")
    if abs(mexc_move_pct) >= big_move:
        same_dir = (mexc_move_pct > 0) == (ref_move_pct > 0)
        if not (same_dir and abs(ref_move_pct) >= min_corroboration * abs(mexc_move_pct)):
            return (False, f"move_not_corroborated(mexc={mexc_move_pct*100:.1f}%,ref={ref_move_pct*100:.1f}%)")
    return (True, "ok")


def decide_funding_crowding(side: str, funding_rate: float | None, *, max_abs: float = 0.001) -> tuple[bool, str]:
    """Veto entering the crowded side: don't LONG when funding is very positive
    (crowded longs -> long-liquidation cascade risk), nor SHORT when very negative."""
    if funding_rate is None or max_abs <= 0:
        return (True, "no_funding")
    if side == "LONG" and funding_rate >= max_abs:
        return (False, f"crowded_longs(funding={funding_rate*100:.3f}%)")
    if side == "SHORT" and funding_rate <= -max_abs:
        return (False, f"crowded_shorts(funding={funding_rate*100:.3f}%)")
    return (True, "ok")


def _http_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (trusted hosts)
        return json.loads(r.read().decode())


def _bybit(sym: str, timeout: float, bars: int) -> tuple[bool, float, float | None, float]:
    psym = perp_symbol(sym)
    k = _http_json(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={psym}&interval=15&limit={bars}", timeout)
    lst = ((k.get("result") or {}).get("list")) or []
    if not lst:
        return (False, 0.0, None, 0.0)
    closes = [float(x[4]) for x in lst][::-1]  # bybit returns newest-first
    roc = (closes[-1] / closes[0] - 1.0) if closes and closes[0] > 0 else 0.0
    funding: float | None = None; turn = 0.0
    try:
        t = _http_json(f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={psym}", timeout)
        row = (((t.get("result") or {}).get("list")) or [{}])[0]
        fr = row.get("fundingRate")
        funding = float(fr) if fr not in (None, "") else None
        turn = float(row.get("turnover24h") or 0.0)
    except Exception:  # ticker is best-effort; kline already proved existence
        pass
    return (True, roc, funding, turn)


def _okx(sym: str, timeout: float, bars: int) -> tuple[bool, float, float | None, float]:
    c = _http_json(f"https://www.okx.com/api/v5/market/candles?instId={okx_inst(sym)}&bar=15m&limit={bars}", timeout)
    data = c.get("data") or []
    if not data:
        return (False, 0.0, None, 0.0)
    closes = [float(x[4]) for x in data][::-1]  # okx newest-first
    roc = (closes[-1] / closes[0] - 1.0) if closes and closes[0] > 0 else 0.0
    return (True, roc, None, 0.0)  # OKX funding/turnover skipped (fallback only)


def fetch_reference(sym: str, *, timeout: float = 0.6, bars: int = 13) -> tuple[bool, float, float | None, float]:
    """(listed, ref_3h_roc, funding_rate, turnover24h) from Bybit, OKX fallback for
    existence. Raises on total failure so the caller fails OPEN."""
    listed, roc, funding, turn = _bybit(sym, timeout, bars)
    if listed:
        return (True, roc, funding, turn)
    # not on Bybit -> try OKX (existence + roc only)
    try:
        return _okx(sym, timeout, bars)
    except Exception:
        return (False, 0.0, None, 0.0)
