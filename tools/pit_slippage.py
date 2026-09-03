"""What does execution actually COST, and does it get worse with size?

    railway ssh -> /opt/venv/bin/python tools/pit_slippage.py

THE QUESTION THIS EXISTS FOR. The account goes from ~$170 to ~$1078 on
2026-09-04, a 6.3x step. Every previously-rejected finding was priced in dollars
at $170, so re-pricing them linearly at the new size un-rejects three of them.
That linear step is only valid if the EDGE SCALES - and the one cost that does
not scale linearly is execution. Six times the notional into a thin alt book is
worse fills, and this project has never measured a convex fill: every capacity
estimate it has produced rests on an ASSUMED impact coefficient
(REALISTIC_SLIPPAGE_BPS_PER_LEV=0.5) rather than a measured one.

WHY THIS RECONSTRUCTS RATHER THAN WAITS. Entry slippage began recording only on
2026-09-03, so the pre-deposit sample will be one or two fills - useless as a
control. But EXIT slippage on a stop-out is recoverable from data already in
hand: the designed stop price is entry x (1 -/+ sl_frac_designed), the actual
fill is exit_price, and the gap is slippage. That gives a $170-scale baseline
across the whole history TODAY, which is the control group the funded week needs.

WHAT IT CANNOT DO, stated so the number is not over-read:
- EXCHANGE_CLOSE (75 of 119) does not say whether TP or SL fired. Only fills
  landing near -1R are treated as stop-outs; a trade stopped after the retention
  trail moved the level is NOT comparable to the designed stop and is excluded.
- Slippage and gap risk are not separable here. A stop that fills 40bps through
  its level on an illiquid alt may be paying impact, or the market may simply
  have gapped. Both are real costs of trading that symbol at that size, which is
  the decision-relevant quantity, but neither is "market impact" in isolation.
- The size regression is observational. Bigger positions are not randomly
  assigned - they are the ones sizing let through, which correlates with the
  calm filter and therefore with liquidity. Read it as an upper bound on how
  benign the scaling is, not as a causal impact estimate.

READ-ONLY.
"""
from __future__ import annotations

import json
import math
import os
import statistics as st

STATE = os.environ.get("PJ_STATE", "/data/futures_runtime_state.json")
STOP_BAND = (-1.60, -0.55)      # realised R that plausibly means "the stop fired"


def _f(x, d=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else d
    except (TypeError, ValueError):
        return d


def main() -> int:
    trades = json.load(open(STATE))["trade_history"]
    conv = [t for t in trades
            if str(t.get("entry_signal") or "").startswith(("WILDCARD", "TREND", "SQUEEZE"))]

    rows = []
    for t in conv:
        e = _f(t.get("entry_price"))
        x = _f(t.get("exit_price"))
        slf = _f(t.get("sl_frac_designed"))
        risk = _f(t.get("risk_usdt"))
        pnl = _f(t.get("pnl_usdt"))
        if e <= 0 or x <= 0 or slf <= 0 or risk <= 0:
            continue
        r_mult = pnl / risk
        if not (STOP_BAND[0] <= r_mult <= STOP_BAND[1]):
            continue
        # The trail only ever moves a stop toward profit, so a fill at roughly
        # -1R means the ORIGINAL designed level is the one that fired.
        sgn = 1.0 if str(t.get("side")) == "LONG" else -1.0
        designed = e * (1.0 - sgn * slf)
        if designed <= 0:
            continue
        # positive = filled BEYOND the stop = adverse
        slip_bps = sgn * (designed - x) / e * 10000.0
        # margin x leverage, NOT contracts x contract_size x price: the trade
        # record does not carry contract_size, so that form silently defaulted
        # to 1.0 and produced $0.11 notionals on a $170 account - and a mean
        # "notional" of $1872, which should have been caught by looking at it.
        notional = _f(t.get("margin_usdt")) * _f(t.get("leverage"), 1.0)
        if notional <= 0:
            continue
        rows.append({"symbol": t.get("symbol"),
                     "sleeve": str(t.get("entry_signal") or "").split("_")[0],
                     "side": t.get("side"), "r": r_mult, "bps": slip_bps,
                     "notional": notional,
                     "usd": abs(slip_bps) / 10000.0 * notional,
                     "fees": _f(t.get("fees_usdt"))})

    print("=" * 78)
    print("EXIT SLIPPAGE ON STOP-OUTS  (reconstructed, $170-scale baseline)")
    print("=" * 78)
    print("convex trades: %d | usable stop-outs: %d" % (len(conv), len(rows)))
    if len(rows) < 5:
        print()
        print("TOO FEW to say anything. Not a finding - an absence of one.")
        return 0

    b = [r["bps"] for r in rows]
    print()
    print("  slippage bps beyond the designed stop (positive = adverse)")
    print("    mean %+.1f | median %+.1f | p90 %+.1f | min %+.1f | max %+.1f"
          % (st.mean(b), st.median(b), sorted(b)[max(0, int(.9 * len(b)) - 1)],
             min(b), max(b)))
    if len(b) > 1:
        se = st.pstdev(b) / math.sqrt(len(b))
        print("    SE %.1f -> mean sits %.1f SE from zero"
              % (se, abs(st.mean(b)) / se if se else 0.0))

    tot_slip = sum(r["usd"] for r in rows)
    tot_fee = sum(r["fees"] for r in rows)
    print()
    print("  cost on these %d stop-outs: slippage $%.2f | fees $%.2f"
          % (len(rows), tot_slip, tot_fee))
    if tot_fee:
        print("  slippage is %.0f%% of what fees cost on the same trades"
              % (100.0 * tot_slip / tot_fee))
    print("  per stop-out: mean $%.3f | MEDIAN $%.3f on median notional $%.2f"
          % (tot_slip / len(rows), st.median([r["usd"] for r in rows]),
             st.median([r["notional"] for r in rows])))
    print("  (the mean is not the number to use - the bps distribution runs")
    print("   %+.0f to %+.0f, so one fill dominates it. Median is the estimate.)"
          % (min(b), max(b)))

    print()
    print("-" * 78)
    print("DOES IT GET WORSE WITH SIZE?  the whole funded-week question")
    print("-" * 78)
    srt = sorted(rows, key=lambda r: r["notional"])
    half = len(srt) // 2
    lo, hi = srt[:half], srt[half:]
    print("  %-22s %5s %12s %12s" % ("notional bucket", "n", "mean bps", "mean $"))
    for nm, grp in (("smaller half", lo), ("larger half", hi)):
        if grp:
            print("  %-22s %5d %+12.1f %12.3f"
                  % (nm, len(grp), st.mean([g["bps"] for g in grp]),
                     st.mean([g["usd"] for g in grp])))
    if len(lo) >= 3 and len(hi) >= 3:
        d = st.mean([g["bps"] for g in hi]) - st.mean([g["bps"] for g in lo])
        pool = math.sqrt(st.pstdev([g["bps"] for g in hi]) ** 2 / len(hi)
                         + st.pstdev([g["bps"] for g in lo]) ** 2 / len(lo))
        print()
        print("  larger-minus-smaller: %+.1f bps, %.2f SE"
              % (d, abs(d) / pool if pool else 0.0))
        print("  (needs ~2 SE to mean anything. Below that this says NOTHING")
        print("   about whether 6.3x notional costs more - which is itself the")
        print("   answer: the linear re-pricing is UNVERIFIED, not verified.)")

    print()
    print("-" * 78)
    print("BY SLEEVE")
    print("-" * 78)
    print("  %-12s %5s %12s %12s" % ("sleeve", "n", "mean bps", "total $"))
    for k in sorted({r["sleeve"] for r in rows}):
        g = [r for r in rows if r["sleeve"] == k]
        print("  %-12s %5d %+12.1f %12.2f"
              % (k, len(g), st.mean([q["bps"] for q in g]),
                 sum(q["usd"] for q in g)))

    print()
    print("-" * 78)
    print("WORST FILLS")
    print("-" * 78)
    print("  %-16s %-6s %8s %9s %10s %8s"
          % ("symbol", "side", "R", "bps", "notional", "cost $"))
    for r in sorted(rows, key=lambda z: -z["bps"])[:8]:
        print("  %-16s %-6s %8.2f %+9.1f %10.2f %8.3f"
              % (str(r["symbol"]).replace("_USDT", ""), r["side"], r["r"],
                 r["bps"], r["notional"], r["usd"]))

    print()
    print("=" * 78)
    print("WHAT THIS DOES AND DOES NOT LICENCE")
    print("=" * 78)
    per = st.median([r["usd"] for r in rows])
    print("  MEDIAN stop-out slippage costs $%.3f per stop-out at ~$170." % per)
    print("  If bps hold CONSTANT at 6.3x notional that becomes $%.2f each."
          % (per * 6.3))
    print("  If bps instead grow with size the cost grows superlinearly and the")
    print("  linear re-pricing of the rejected list is WRONG in the expensive")
    print("  direction. The size split above is the only evidence either way,")
    print("  and at this n it cannot separate the two. Entry slippage began")
    print("  recording 2026-09-03; the funded week produces a real distribution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
