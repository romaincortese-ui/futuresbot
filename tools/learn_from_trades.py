"""Stage-2 'learn from trades' report. Reads the persistent feature store
(/data/futures_feature_store.jsonl) when available; otherwise reconstructs a
corpus from MEXC closed-trade history (cheap features) so the engine can run
immediately. Runs the conditional-expectancy engine and prints AVOID/FAVOR
proposals. PROPOSE only — nothing here trades or changes config.

Usage: python tools/learn_from_trades.py [feature_store.jsonl]
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

from futuresbot.conditional_expectancy import default_conditions, rank_conditions, summarize

PMT = {"BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "SEI_USDT", "ZEC_USDT"}


def load_store(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def reconstruct_from_mexc(days: int = 60) -> list[dict]:
    from futuresbot.config import FuturesConfig
    from futuresbot.marketdata import MexcFuturesClient
    c = MexcFuturesClient(FuturesConfig.from_env())
    cutoff = time.time() - days * 86400
    raw = []
    for pg in (1, 2, 3):
        r = c.private_get("/api/v1/private/position/list/history_positions", {"page_num": pg, "page_size": 100})
        d = r.get("data") if isinstance(r, dict) else r
        if not d:
            break
        raw += d
    rows = []
    for p in raw:
        if p.get("updateTime", 0) / 1000 < cutoff:
            continue
        sym = p.get("symbol"); side = int(p.get("positionType", 0))
        op = float(p.get("openAvgPrice") or 0); cp = float(p.get("closeAvgPrice") or 0)
        lev = float(p.get("leverage") or 0); pnl = float(p.get("realised") or 0)
        sgn = 1 if side == 1 else -1
        pnl_pct = ((cp / op - 1) * sgn * lev * 100) if op > 0 else 0.0
        kind = "PMT" if sym in PMT else "CONVEX"
        ot = p.get("createTime", 0) / 1000; ct = p.get("updateTime", 0) / 1000
        rows.append({
            "ts": round(ct), "symbol": sym, "side": "LONG" if side == 1 else "SHORT", "kind": kind,
            "leverage": lev, "pnl_usdt": round(pnl, 4), "pnl_pct": round(pnl_pct, 2),
            "r_multiple": round(pnl_pct / 20.0, 2) if kind == "CONVEX" else None,  # convex 1R≈20% margin cap
            "hold_min": round((ct - ot) / 60.0, 1), "is_win": pnl > 0,
            "is_wildcard": kind == "CONVEX",
        })
    return rows


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FUTURES_FEATURE_STORE_FILE", "")
    rows, src = [], ""
    if path and os.path.exists(path):
        rows = load_store(path); src = f"feature store {path}"
    if not rows:
        rows = reconstruct_from_mexc(); src = "reconstructed from MEXC history (cheap features only)"
    print(f"corpus: {len(rows)} closed trades | source: {src}")
    if rows:
        span = sorted(r.get("ts", 0) for r in rows)
        print(f"window: {datetime.fromtimestamp(span[0], timezone.utc):%Y-%m-%d} .. {datetime.fromtimestamp(span[-1], timezone.utc):%Y-%m-%d}")
    o = summarize(rows)
    print(f"OVERALL: n={o['n']} mean=${o['mean_usd']:+.3f} sum=${o['sum_usd']:+.2f} win%={o['winrate']} meanR={o['mean_R']}")
    print(f"\n{'condition':24}{'verdict':12}{'gap$':>8}  with(n/mean$/win%)        without(n/mean$/win%)     oos")
    for p in rank_conditions(rows, default_conditions(), min_n=6):
        w, wo, oos = p["with"], p["without"], p["oos"]
        print(f"{p['condition']:24}{p['verdict']:12}{p['gap_usd']:>+8.3f}  "
              f"{w['n']:>3}/{w['mean_usd']:>+6.3f}/{w['winrate']:>4}   "
              f"{wo['n']:>3}/{wo['mean_usd']:>+6.3f}/{wo['winrate']:>4}   "
              f"e={oos['early_gap']} l={oos['late_gap']} {'OK' if oos['consistent'] else '-'}")
    print("\nAVOID = presence reliably hurts (OOS-consistent) -> propose a veto/filter."
          "\nFAVOR = presence reliably helps -> propose tilting toward it."
          "\nPROPOSE ONLY -- validate before acting; small samples = treat as hypotheses.")


if __name__ == "__main__":
    main()
