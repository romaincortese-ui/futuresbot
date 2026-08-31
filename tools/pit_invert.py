"""Would SHORTING the trades that stopped out have paid? Measured on the real paths.

    railway run --service Futures-bot python tools/pit_invert.py

The owner asked whether the losing entries could be identified and inverted. All
six trades that hit their stop in trials 17-18 were LONG. This resolves the
MIRROR of each one against the same klines: same entry price and moment, same
stop fraction, same target multiple, opposite side.

WHY INVERTING A LOSER IS NOT AUTOMATICALLY A WINNER. Costs are paid in both
directions. A long that loses -1R does not imply a short that gains +1R: the
short has its own stop above the entry, and price that fell far enough to hit
the long's stop must first not have risen far enough to hit the short's. The
only way to know is to walk the bars.

READ-ONLY.
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

HORIZON = 24 * 3600
SRC = os.environ.get("INVERT_TRADES") or "sl_analysis.json"


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    sl = [x for x in d if x.get("exit_reason") == "EXCHANGE_CLOSE"]
    print("*** MIRROR of the %d stopped-out trades, trials 17-18 ***\n" % len(sl))
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    now = int(time.time())
    import datetime as dt

    def ets(x):
        return dt.datetime.fromisoformat(str(x.get("entry_time"))).timestamp()

    syms = sorted({x["symbol"] for x in sl})
    span = (now - min(ets(x) for x in sl)) / 86400.0 + 2.0
    frames, rep = fetch_frames(cl, syms, days=span, workers=5, min_bars=100, now_ts=now)
    print(rep)
    BARS = {s: list(zip([float(b.timestamp()) for b in df.index],
                        [float(v) for v in df["high"]], [float(v) for v in df["low"]],
                        [float(v) for v in df["close"]])) for s, df in frames.items()}
    fn = ratchet(3.0, 0.75, base=0.50, arm=1.0)
    print("\n%-11s %-6s %8s | %10s | %10s" % ("symbol", "sleeve", "actual R", "MIRROR R", "mirror exit"))
    tot_a = tot_m = 0.0
    unres = 0
    for x in sl:
        bars = BARS.get(x["symbol"])
        if not bars:
            continue
        e0 = ets(x)
        i0 = None
        for k, b in enumerate(bars):
            if b[0] <= e0:
                i0 = k
            else:
                break
        if i0 is None:
            print("%-11s  entry precedes history" % x["symbol"]); continue
        entry = float(x["entry_price"]); slf = float(x["sl_frac_designed"])
        tp_r = 3.0 if str(x.get("entry_signal", "")).startswith("TREND") else 5.0
        aR = float(x["pnl_usdt"]) / float(x["risk_usdt"]) if x.get("risk_usdt") else 0.0
        tot_a += aR
        # MIRROR: short at the same price, stop above, target below
        m_sl = entry * (1 + slf)
        m_tp = entry * (1 - slf * tp_r)
        row = {"entry": entry, "sl": m_sl, "tp": m_tp, "side": "SHORT"}
        g = resolve(bars, i0, entry, m_sl, m_tp, tp_r, "SHORT", HORIZON,
                    shadow.cost_r(row), fn, 0.0, now)
        if g is None:
            print("%-11s %-6s %+8.2f | %10s | %s"
                  % (x["symbol"], str(x.get("entry_signal"))[:6], aR, "unresolved", "-"))
            unres += 1
            continue
        tot_m += float(g[0])
        print("%-11s %-6s %+8.2f | %+10.2f | %s"
              % (x["symbol"], str(x.get("entry_signal"))[:6], aR, float(g[0]), str(g[2])))
    print("\n%-11s %-6s %+8.2f | %+10.2f" % ("TOTAL netR", "", tot_a, tot_m))
    if unres:
        print("%d unresolved (still inside the 24h clock) - excluded from the mirror total" % unres)
    print("\nA mirror total near +N does NOT mean shorting is an edge: these six were")
    print("SELECTED for having lost. The unbiased question is what shorting does to")
    print("ALL entries, which trend.py already answers (-$14 to -$34 over 63d x 8")
    print("windows) and the 90-day drift-controlled study answers (+0.244R long vs")
    print("-0.225R short).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
