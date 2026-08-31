"""What would trial 18's actual trades have done with NO retention trail?

    railway run --service Futures-bot python tools/pit_notrail.py

Not a replay of signals - a counterfactual on the TEN REAL TRADES. Each one's
entry, side, stop fraction and sleeve come from the live ledger; the price path
comes from the exchange. Only the exit policy changes.

WHY IT IS WORTH ASKING. Every one of the six retention-trail exits in trial 18
banked between +0.48R and +0.63R, and every one of them had peaked between
+1.19R and +1.37R - they arm at 1R and fade immediately. Nothing in the trial has
exceeded +0.63R, so the +5R target and the 3R ratchet have never been touched.
That raises a fair question: is the trail collecting small change from trades
that would otherwise have run?

ARMS TESTED, all on the identical price paths:
    no trail        stop / target / 24h clock only - the pre-trial-7 behaviour
    retain 0.30     the trial-17 setting
    retain 0.50     LIVE (trial 18), with the 3R -> 0.75 ratchet
    retain 0.70     the arm that scored best on ex-top-5% in the replay

HONEST LIMIT. Ten trades. This measures what DID happen on ten specific paths,
which is a real fact and a tiny sample - it is evidence about this trial, not
about the policy. The 220-day replay in pit_exits_sized.py is the population
estimate; this is the audit trail behind one trial's numbers.

READ-ONLY.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import make_floor, resolve  # noqa: E402

BAR, HORIZON = 900, 24 * 3600
TRADES = os.environ.get("NOTRAIL_TRADES") or "trial18_trades.json"

ARMS = [
    ("no trail",        make_floor("none", 0.0, 1.0)),
    ("retain 0.30",     make_floor("flat", 0.30, 1.0)),
    ("retain 0.50 LIVE", ratchet(3.0, 0.75, base=0.50, arm=1.0)),
    ("retain 0.70",     make_floor("flat", 0.70, 1.0)),
]


def main() -> int:
    print("*** COUNTERFACTUAL on trial 18's ten REAL trades. ***")
    trades = json.load(open(TRADES, encoding="utf-8"))
    print("trades: %d\n" % len(trades))
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    now = int(time.time())
    syms = sorted({t["symbol"] for t in trades})
    # enough history to cover the oldest entry plus its 24h clock
    span_d = (now - min(t["entry_ts"] for t in trades)) / 86400.0 + 2.0
    frames, rep = fetch_frames(cl, syms, days=span_d, workers=5,
                               min_bars=100, now_ts=now)
    print(rep)

    BARS = {}
    for s, df in frames.items():
        BARS[s] = list(zip([float(x.timestamp()) for x in df.index],
                           [float(x) for x in df["high"]],
                           [float(x) for x in df["low"]],
                           [float(x) for x in df["close"]]))

    print("\n%-11s %-5s %7s %8s | %s" % ("symbol", "side", "peak_r", "ACTUAL",
                                         " ".join("%14s" % a for a, _ in ARMS)))
    totals = {a: 0.0 for a, _ in ARMS}
    tot_actual = 0.0
    unresolved = 0
    for t in trades:
        bars = BARS.get(t["symbol"])
        if not bars:
            print("%-11s  no klines" % t["symbol"])
            continue
        # index of the last bar at or before entry
        i0 = None
        for k, b in enumerate(bars):
            if b[0] <= t["entry_ts"]:
                i0 = k
            else:
                break
        if i0 is None:
            print("%-11s  entry precedes fetched history" % t["symbol"])
            continue
        entry = t["entry"]
        sgn = 1.0 if t["side"] == "LONG" else -1.0
        sl_frac = t["sl_frac"]
        sl = entry * (1 - sgn * sl_frac)
        tp_r = 3.0 if t["signal"].startswith("TREND") else 5.0
        tp = entry * (1 + sgn * sl_frac * tp_r)
        row = {"entry": entry, "sl": sl, "tp": tp, "side": t["side"]}
        cr = shadow.cost_r(row)
        actual_r = (t["pnl"] / t["risk"]) if t["risk"] else 0.0
        tot_actual += actual_r
        cells = []
        for name, fn in ARMS:
            g = resolve(bars, i0, entry, sl, tp, tp_r, t["side"],
                        HORIZON, cr, fn, 0.0, now)
            if g is None:
                cells.append("      unresolved")
                unresolved += 1
            else:
                totals[name] += float(g[0])
                cells.append("%+9.2f %-4s" % (float(g[0]), str(g[2])[:4]))
        print("%-11s %-5s %+7.3f %+8.2f | %s"
              % (t["symbol"], t["side"], t["peak_r"], actual_r, " ".join(cells)))

    print("\n%-11s %-5s %7s %+8.2f | %s"
          % ("TOTAL netR", "", "", tot_actual,
             " ".join("%+14.2f" % totals[a] for a, _ in ARMS)))
    r1 = trades[0]["risk"] if trades else 0
    print("\nnetR is per-trade R summed. At the trial's ~$3.0 mean risk that is")
    print("roughly $3 per 1.0R. Actual netR came to %+.2f." % tot_actual)
    if unresolved:
        print("%d arm-trades unresolved (still inside their 24h clock) - excluded"
              % unresolved)
    _ = r1
    print("\nTEN TRADES. This is what happened on these paths, not what the policy")
    print("is worth. pit_exits_sized.py over 220 days is the population estimate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
