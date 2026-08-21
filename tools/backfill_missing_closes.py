"""Backfill closed trades the history-lag race erased from the feature store.

    railway run --service Futures-bot python tools/backfill_missing_closes.py            # dry run
    railway run --service Futures-bot python tools/backfill_missing_closes.py --apply    # write

The race (fixed 2026-08-21, see tests/test_reconcile_history_lag.py) cleared
positions "without recording P&L" whenever MEXC dropped a closed position from
open_positions before publishing its closed row. Six real closes were erased.
The trades happened; only the record is gone.

WHAT THIS RECONSTRUCTS, and what it refuses to. Everything written comes from
the exchange: symbol, side, leverage, entry/exit, realised P&L, profit ratio and
timestamps from the position record, and the stop distance from the position's
own resting STOP ORDER where one survives. Fields the exchange cannot know —
peak_r, entry_lateness, regime_size_mult, streak_multiplier, roc_z — are written
as null. They are NOT guessed. `sl_margin_pct` and `r_multiple` are derived only
when a real stop price is recoverable; otherwise null.

Every row carries reconstructed=1 so no analysis can mistake it for a
first-class observation, and `kind`/`sleeve` are marked inferred because the
exchange does not record which sleeve opened a trade — they are derived from
whether the symbol is one of the six PMT pairs.

Idempotent: a position already present (matched on symbol + close time) is
skipped. Backs the store up before writing.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime

PMT_PAIRS = {"BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "SEI_USDT", "ZEC_USDT"}
MATCH_WINDOW_S = 180


def _stop_price(client, symbol: str, position_id: str) -> float | None:
    """The position's own resting stop price, if MEXC still holds the order."""
    for page in range(1, 4):
        try:
            payload = client.private_get("/api/v1/private/stoporder/list/orders",
                                         {"symbol": symbol, "page_num": page, "page_size": 50})
        except Exception:
            return None
        data = payload.get("data")
        rows = data if isinstance(data, list) else (data or {}).get("resultList", [])
        if not rows:
            return None
        for row in rows:
            if str(row.get("positionId") or "") != str(position_id):
                continue
            try:
                sl = float(row.get("stopLossPrice") or 0.0)
                return sl if sl > 0 else None
            except (TypeError, ValueError):
                return None
        time.sleep(0.2)
    return None


def main() -> int:
    apply = "--apply" in sys.argv
    cfg = FuturesConfig.from_env()
    client = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, client)
    store = rt._feature_store_path

    existing = []
    if store.exists():
        for line in store.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    existing.append(json.loads(line))
                except Exception:
                    pass
    print(f"feature store: {store} ({len(existing)} rows)")
    have = {(str(r.get("symbol")), float(r.get("ts") or 0)) for r in existing}

    # Every closed position MEXC knows about, newest first.
    ex_rows, seen = [], set()
    for page in range(1, 8):
        payload = client.private_get("/api/v1/private/position/list/history_positions",
                                     {"page_num": page, "page_size": 100})
        data = payload.get("data")
        rows = data if isinstance(data, list) else (data or {}).get("resultList", [])
        if not rows:
            break
        for r in rows:
            pid = r.get("positionId")
            if pid in seen:
                continue
            seen.add(pid)
            ex_rows.append(r)
        if len(rows) < 100:
            break
        time.sleep(0.25)
    first_ts = min((float(r.get("ts") or 0) for r in existing), default=0.0)
    ex_rows = [r for r in ex_rows if float(r.get("updateTime") or 0) / 1000.0 >= first_ts - 120]
    ex_rows.sort(key=lambda r: int(r.get("updateTime") or 0))
    print(f"exchange closes in the store's window: {len(ex_rows)}")

    missing = []
    for r in ex_rows:
        sym = str(r.get("symbol") or "")
        ts = float(r.get("updateTime") or 0) / 1000.0
        if any(s == sym and abs(t - ts) <= MATCH_WINDOW_S for s, t in have):
            continue
        missing.append(r)

    built = []
    for r in missing:
        sym = str(r.get("symbol") or "")
        pid = str(r.get("positionId") or "")
        ts = float(r.get("updateTime") or 0) / 1000.0
        opened = float(r.get("createTime") or 0) / 1000.0
        pnl = float(r.get("realised") or 0.0)
        ratio = float(r.get("profitRatio") or 0.0)
        entry = float(r.get("openAvgPrice") or 0.0)
        exit_px = float(r.get("closeAvgPrice") or 0.0)
        lev = int(r.get("leverage") or 0)
        side = "SHORT" if int(r.get("positionType") or 1) == 2 else "LONG"
        margin = (abs(pnl) / abs(ratio)) if ratio else None
        sl = _stop_price(client, sym, pid)
        sl_margin_pct = None
        r_mult = None
        if sl and entry > 0:
            sl_frac = abs(entry - sl) / entry
            if sl_frac > 0 and lev > 0:
                sl_margin_pct = round(sl_frac * lev * 100.0, 4)
                if sl_margin_pct > 0:
                    r_mult = round(ratio * 100.0 / sl_margin_pct, 2)
        kind = "PMT" if sym in PMT_PAIRS else "WILDCARD"
        built.append({
            "account": rt.account.id, "ts": round(ts), "symbol": sym, "side": side,
            "kind": kind, "leverage": lev,
            "pnl_usdt": pnl, "pnl_pct": round(ratio * 100.0, 6),
            "sl_margin_pct": sl_margin_pct, "setup_regime": None,
            "entry_lateness": None, "ref_listed": None, "roc_z": None,
            "sleeve": kind, "legacy_major": None, "legacy_prefilter_ok": None,
            "balance_fraction": None, "equity_at_entry": None,
            "margin_wanted": None, "margin_used": (round(margin, 4) if margin else None),
            "risk_pct_actual": None, "risk_cap_bound": None,
            "exit_rule": "EXCHANGE_CLOSE_RECONSTRUCTED", "risk_usdt": None,
            "sl_frac_designed": None, "peak_r": None,
            "equity_at_open_usdt": None, "equity_at_close_usdt": None,
            "hold_hours": round((ts - opened) / 3600.0, 3) if opened else None,
            "is_win": pnl > 0, "r_multiple": r_mult,
            "hold_min": round((ts - opened) / 60.0, 1) if opened else None,
            "is_wildcard": kind == "WILDCARD",
            "entry_3h_roc_pct": None, "regime_size_mult": None,
            "intended_margin_usdt": None, "streak_multiplier": None,
            "loss_streak_at_entry": None, "size_efficiency": None,
            "fee_share_of_gross": None,
            "exit_reason": "EXCHANGE_CLOSE_RECONSTRUCTED",
            "exit_kind": ("STOP" if r_mult is not None and r_mult <= -0.85 else None),
            # Provenance. Without these a later reader cannot tell a
            # reconstruction from an observation, and would trust nulls as data.
            "reconstructed": 1,
            "reconstructed_at": round(time.time()),
            "reconstructed_from": f"mexc_position:{pid}",
            "reconstructed_note": ("sleeve inferred from symbol (PMT pair or not); "
                                   "sizing/telemetry fields unknowable and left null"),
            "entry_price": entry, "exit_price": exit_px, "position_id": pid,
        })

    print(f"\nMISSING CLOSES TO BACKFILL: {len(built)}")
    total = 0.0
    for b in built:
        total += b["pnl_usdt"]
        print(f"  {time.strftime('%m-%d %H:%M', time.gmtime(b['ts']))} {b['symbol']:<12} "
              f"{b['side']:<5} x{b['leverage']:<3} ${b['pnl_usdt']:+8.4f} "
              f"({b['pnl_pct']:+6.2f}%)  sl%={b['sl_margin_pct']}  R={b['r_multiple']}  "
              f"kind={b['kind']}")
    print(f"  net ${total:+.4f}")

    if not built:
        print("\nnothing to do — the store already reconciles")
        return 0
    if not apply:
        print("\nDRY RUN. Re-run with --apply to write.")
        return 0

    backup = store.with_suffix(store.suffix + f".bak-{int(time.time())}")
    shutil.copy2(store, backup)
    print(f"\nbacked up -> {backup}")
    with open(store, "a", encoding="utf-8") as fh:
        for b in built:
            fh.write(json.dumps(b, default=str) + "\n")
    after = len(store.read_text(encoding="utf-8").splitlines())
    print(f"appended {len(built)} rows: {len(existing)} -> {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
