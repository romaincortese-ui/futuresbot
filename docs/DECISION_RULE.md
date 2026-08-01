# Pre-registered decision rule — CONVEX TRIAL 4 (from 2026-07-31)

Trial 3 (07-29 -> 07-31) archived. It produced one closed trade (NIL_USDT
+5.06R / +$9.83, full TP after 82h) — too few to judge, so trial 4 supersedes it
rather than extending.

## Changes under test in trial 4
1. **Second wildcard slot** — FUTURES_WILDCARD_MAX_POSITIONS=2 (squeeze stays 1
   via the new independent FUTURES_SQUEEZE_MAX_POSITIONS). Evidence: the
   pre-registered trigger set by the adversarial panel ("blocked candidates net
   clearly positive over >=10 resolved rows") was met — shadow ledger
   slot_occupied n=15, netR +3.00, meanR +0.20. This REVERSES the 07-22 reading
   (n=5, -5.00R, "slot-lock is protective"), which was retracted on more data.
   Slot occupancy was also the dominant cause of the 7d missed movers: ON +198%,
   COTI +161%, MMT +113%, CAP +104%, 1000RATS +121% were all DETECTED and
   blocked by the slot, not by any gate.
   Honest caveat: +0.20R mean is thin (~3 wins at +5R vs 12 losses at -1R), and
   shadow counterfactuals ignore fills/slippage/fees. Worst case 3 concurrent
   convex positions (2 WC + 1 SQ) ~ 5-7% of equity at risk.
2. **Rank-ordered candidate fallthrough** — a vetoed top candidate no longer
   wastes the scan: the bot logs it and tries the next-best (up to
   FUTURES_WILDCARD_MAX_CANDIDATES=3). Two effects: fewer wasted scans, and the
   external gate finally gets MEASURED on real alts.

## WHEN DOES A CHANGE RESET THE TRIAL? (standard, set 2026-07-31)
Test: does the change alter what the bot DOES, or only what it RECORDS?

RESETS the trial (treatment change) — entry logic, exit logic, sizing/leverage,
slot counts, gates/filters/thresholds, or anything that alters which trades are
taken or how they are managed.

DOES NOT reset (measurement change) — feature-store columns, tagger fields,
telemetry, logging, Telegram/report wording, tests, docs, or tooling. These
touch only post-close/observational code paths.

Applied 2026-07-31: TP-completion tracking (exit_kind) and the sizing-telemetry
fix (intended_margin_usdt, streak_multiplier, size_efficiency) landed AFTER
trial 4 began. Both touch only _trade_attribution_tags (post-close),
_classify_exit_kind (pure helper) and learning_digest (reporting). Trial 4
therefore CONTINUES; its treatment (2 wildcard slots + candidate fallthrough)
and pass criteria are unchanged.
KNOWN LIMITATION: trades closed before those deploys lack the new columns, so
trial 4's ledger has partial telemetry coverage on size_efficiency/exit_kind.
This does not affect the R-based pass criteria.
Note also: each deploy restarts the bot (open positions survive on server-side
stops). Batch measurement changes where possible rather than deploying singly.

## WATCH ITEM — TP completion rate (added 2026-07-31)
Widening the stop to 3.0xATR doubled the price move that +5R requires: median 1R
is now ~15.0% of price, so TP needs a ~75% move (it was ~37.6% at 1.5xATR).
Only ~10% of rolling 7d windows in the band produce a 5R-sized move
(unconditional; higher conditional on a signal firing). The grid still favoured
TP5R at this stop width in BOTH windows (+35.8 in-sample, +18.7 OOS), so the
pairing is tested — but the mechanism is stretched.

TRACKING: every closed trade now records `exit_kind` (TP / STOP / OTHER),
classified from realised R (TP >= 4.5R; STOP <= -0.85R; else OTHER) because
exit_reason is usually EXCHANGE_CLOSE and cannot tell the two apart. The weekly
digest reports "Exits: TP n (x%) | stop n | other n".

TRIPWIRE: if TP completions are <10% of closes over >=15 trades AND OTHER
(timeout/mid-flight) dominates, the 3.0xATR stop + 5R target is too demanding.
The fix is then to scale TP DOWN at wide stops (TP3R scored +19.9 in-sample /
+10.9 OOS at 2.0x stop, second-best in both) — NOT to revert the stop, which is
supported independently in both windows and by 13-of-16 live rebounds.

## External gate: reviewed and DELIBERATELY NOT CHANGED
The "+2.00R mean on vetoed candidates" signal does NOT survive inspection. All 4
ref_not_listed vetoes are SYNTHETIC products (SKHYSTOCK, SPCXSTOCK, USOIL,
SNDKSTOCK), all squeeze-sleeve, and ALL have 1R between 1.19% and 3.22% of
margin — i.e. inside the fee-doomed bucket that FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT
=12 now blocks independently. Relaxing the gate would not re-admit them; the fee
filter catches them first. They were logged while that filter was set-but-inert
(the SKIPPED-deploy bug, 07-26..07-29).
Meanwhile the gate's cost on REAL alts is UNMEASURED: KOMA_USDT (+246% in 7d,
$15.5M turnover) fires 4 wildcard signals with a healthy 16.40%-margin 1R and
would be vetoed — but never appeared in the ledger because only the top-ranked
candidate per scan was logged. Change #2 fixes exactly that blind spot.
DECISION: instrument now, adjudicate at >=10 resolved REAL-ALT veto rows.

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
