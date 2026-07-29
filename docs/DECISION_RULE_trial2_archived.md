# Pre-registered decision rule — CONVEX TRIAL 2 (from 2026-07-25)

Trial 1 (2026-07-13 -> 07-25) was **terminated early at 11/30 trades — by design,
not by drift**: it produced exactly the finding it existed to produce (see
`DECISION_RULE_trial1_archived.md`). Thin-1R squeeze fires were identified as a
structural, fee-driven loss source and filtered out; the ledger from before that
change is no longer representative, so the counter resets.

## The change under test (shipped at trial 2 start)
`FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT=8` — squeeze setups whose 1R is below 8% of
margin are SKIPPED (logged `fee_doomed_thin_stop` + shadow ledger), not widened.
Evidence: 60d/316 fires — thin(<8%) netR **-104.5** (avgR -0.53, 15% win, fees
**24.1% of 1R**) vs normal(>=8%) netR **+40.2** (avgR +0.34, fees 4.4%).
Removing them takes the sleeve from -64R to +40R. Corroborated independently by
19 live trades (thin: 16.3% fee drag, net -$0.22) and 9 shadow rows (thin
candidates DOGE/PEPE resolved -1R). Widening was REJECTED: the floor sweep only
moved -64R -> -56R because a wider stop drags the +5R TP proportionally further.

## Pass criteria (unchanged, evaluated at 30 convex trades or 90 days)
1. **Net R > 0** after fees across the window (feature-store `r_multiple`).
2. **Outlier-robust:** net R still > 0 after dropping the single best trade.
3. **Max drawdown** from the window's peak **< 30%**, flow-adjusted (deposits are
   not P&L; see the capital-flow annotations below).
4. **No unexplained behavior:** every close attributable to a designed exit
   (-1R stop / +5R TP / exchange close) — no orphaned positions, no manual
   rescues (operator committed 2026-07-19 to no manual closes).

Pass -> fund the account to a size where the edge pays for the effort.
Fail -> shut down or go paper-only. No extending the window to chase a verdict.

## Settled — do NOT re-propose without NEW evidence
- **2nd wildcard slot: REJECTED.** Shadow ledger: 5 slot-blocked candidates
  resolved **5-for-5 at -1R (net -5R)**. The single per-sleeve slot is
  protective, not costly. (Supersedes the 07-17 slot-contention rationale.)
- **Synthetics veto exemption: REJECTED.** The SPCXSTOCK +5R counterfactual that
  motivated it came from a 1.19%-margin stop — inside the proven fee-doomed
  bucket; the other two synthetics resolved -1R. They fail the fee test
  independently of the listing test.
- **Wider ATR stops (1.5 -> 2.0/2.5x): RETRACTED**, pending out-of-regime and
  contracts-space validation (adversarial panel, 07-21).
- No MIN_ROC raise, no lateness VETO, no ratchet/trail (+1R ratchet costs -12.3R
  across the 7 trades reaching +2R), no funding-hold policy.

## Capital-flow annotations
- 2026-07-21: operator DEPOSIT ~+$72 (equity $65.76 -> $137.83). Not P&L.
- Drawdown must be computed flow-adjusted (or from the cumulative R curve).
  Net R / ex-best R are scale-invariant and unaffected; the conditional-
  expectancy engine compares conditions in R for the same reason.
