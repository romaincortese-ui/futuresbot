# Pre-registered decision rule — convex-only trial

**Registered:** 2026-07-17 (operator-approved plan, adversarial-panel item 5).
**Status:** PROPOSED thresholds — operator may edit ONCE before 2026-07-24; after
that the criteria are immutable until the horizon.

## The question
Does the convex-only futures bot (wildcard + squeeze entries, convex exit,
external veto, -20% SL cap, 5% risk cap) have a positive, non-outlier-dependent
edge worth funding with real capital?

## Horizon
Whichever comes FIRST:
- **30 closed convex trades** counted from 2026-07-13 23:00 UTC (the PMT
  decommission), or
- **2026-10-13** (90 days).

## Pass criteria (ALL must hold at the horizon)
1. **Net R > 0 after fees** across the window (feature-store rows, `r_multiple`).
2. **Outlier-robust:** net R still > 0 after dropping the single best trade.
3. **Max drawdown** from the window's equity peak **< 30%**.
4. **No unexplained behavior:** every close attributable to a designed exit
   (stop/TP/exchange close) — no orphaned positions or manual rescues.

## Outcomes (pre-committed)
- **PASS → graduate:** fund the account to a size where the edge pays for the
  effort (operator decides amount; the point is the *decision* is forced).
- **FAIL → kill or paper:** disable live entries (convex flags off) and either
  shut down or continue paper-only. No "one more tweak" extension on live money.
- **AMBIGUOUS** (e.g. net R > 0 but outlier-dependent): extend ONCE by 30 trades
  paper-or-live at operator's choice, then the rule is binding.

## Discipline
- Strategy changes during the window are allowed only if risk-reducing or
  telemetry-only (the standing evidence-first gates apply). Entry-gate changes
  reset the trade counter.
- The daily assessment reports progress against this rule (trades elapsed,
  net R, ex-best R, drawdown).
- The rolling ledger, not 24h P&L, is the only scoreboard.

## Capital-flow annotations (deposits/withdrawals)

- 2026-07-21: operator DEPOSIT of ~+$72 (equity $65.76 -> $137.83). Not P&L.
- Drawdown for criterion 3 must be computed on a FLOW-ADJUSTED equity curve
  (subtract deposits from post-deposit equity; add back withdrawals) or,
  equivalently, from the cumulative R curve. Raw equity deltas across a flow
  boundary are not P&L. Net R / ex-best R criteria are unaffected (R is
  scale-invariant); the engine compares conditions in R for the same reason.
