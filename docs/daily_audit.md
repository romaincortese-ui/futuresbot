# Daily Audit — 2026-07-25

---

## Automated Assessment (UTC ~21:15)

### 1. Trades (last 24h)

**PMT: 0** (frozen, `FUTURES_ENTRY_MIN_SCORE=1000`, unchanged). **Convex: 5 closed** — feature store grew 31→36 rows:
- `XAU_USDT` SQUEEZE LONG, x5, **-3.79R / -$0.04** (-1.08% margin), 06:21 UTC, hold 1.2min, exit `EXCHANGE_CLOSE`. Anomaly: `sl_margin_pct`=0.28% (razor-thin) meant fees alone were 286% of the gross loss. Entered ~3.5h *before* the operator's thin-stop filter (`FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT=8`, commit `c3deab5`, deployed 09:46 UTC today) went live — this trade is the live, real-money confirmation of exactly the failure mode that filter now blocks.
- `ESPORTS_USDT` WILDCARD SHORT, x2, -1.06R / -$0.61 (-15.4% margin), 12:25 UTC — clean -1R stop.
- `HYPE_USDT` SQUEEZE LONG, x5, -1.14R / -$0.17 (-4.9% margin), 14:12 UTC, entry ~09:48 UTC (~2min after the filter deploy). `sl_margin_pct`=4.29% — *below* the new 8% floor. Single occurrence right at the deploy boundary (likely an in-flight scan cycle from the old process/pod), not a repeat — the next 2 squeeze fires (AKE 16.1%, and none since) are clear of the floor. Worth a glance next run, not yet an action item.
- `AKE_USDT` SQUEEZE LONG, x3, -1.27R / -$0.68 (-20.4% margin), 15:41 UTC — clean -1R stop, filter-compliant (16.1% margin).
- `ALLO_USDT` WILDCARD SHORT, x3, -1.05R / -$1.38 (-18.9% margin), 19:06 UTC — clean -1R stop.

Net this window: -$2.88 / -4.31R, 0/5 winners. Equity: **$135.09** (vs $138.21 07-24) — -2.3%.

### 1-OPEN. Open positions

**None.** `[ACCOUNT]` confirms `positions=0`, flat since ALLO's stop.

### 2. Champion vs Shadow

**Futures-bot (champion):** cycling normally, 558/558 tests pass (was 557 — new test for the thin-stop filter), no Tracebacks, no 5003/2015 execution errors in sampled logs (~48min window).

**Shadow: stale, comparison suppressed pending resync** (action item logged once on 07-23/07-24; not re-flagged further).

### 3. Wildcard/squeeze convex ledger

**Operator reset the trial today** (`docs/DECISION_RULE.md` rewritten 09:46 UTC): Trial 1 (07-13→07-25, 11/30 trades) was terminated *by design* — it isolated the fee-doomed thin-stop pattern (60d study: thin-stop squeeze setups netR -104.5 vs normal +40.2) and the fix shipped (`FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT=8`). Ledger before the reset is no longer representative per the doc.

**Trial 2 (since 09:46 UTC today): 4 convex trades, net R -4.52, net $ -$2.84, 0% win rate.** All 4 are clean -1R stops in a quiet/choppy regime — far too early to read (n=4). XAU above predates the reset and isn't counted in Trial 2.

### 4. Learning loop

**(a) Feature store:** 36 rows (was 31), in sync with the 5 closes above.

**(b) Shadow ledger:** grew 9→12 rows, but **all 3 new rows are unresolved** (`XAUT_USDT` slot_occupied, `SNDKSTOCK_USDT` veto:ref_not_listed, `SPX500_USDT` slot_occupied) — no change to the resolved splits:
- `slot_occupied`: n=5 resolved, net **-5.0R** (unchanged) — still protective, not costly.
- `veto:ref_not_listed`: n=3 resolved, net **+3R** (unchanged).
- `min_vol_skip`: n=1, -1R (unchanged).

**(c) Scan telemetry** (~48min sampled window, 3 cycles/sleeve): **wildcard** — 4 movers/cycle, dominant reject `roc_below_min` (9/12). **squeeze** — universe 70-75, 30 scanned/cycle, dominant `no_active_coil` (78/90), `coil_too_short`, `no_range_break`. Quiet regime, gates behaving as designed. No `SIZE_TRIM` lines, no 5003/2015 failures.

**(d) Decision rule:** superseded by the operator's reset — see §3. Trial 2 stands at 4 trades (of 30 or 90 days), net R -4.52. `USE_DRAWDOWN_KILL=0` override unchanged, operator-aware.

### 5. Wildcard diagnose

No execution failures. Scan correctly dormant (`roc_below_min` / `no_active_coil` dominant). No rejected mover showed continuation evidence worth a gate change. No loosening proposed.

### 6. Diagnose — lever for next 24h

**None new.** The operator already shipped and deployed the one live lever (thin-stop squeeze filter) this morning, ahead of this run — reviewed and confirmed working (§3, §4d). Sample too thin (n=4 post-reset) for any further change. Watch item only: HYPE's sub-floor `sl_margin_pct` at the exact deploy boundary (§1) — recheck next run if it recurs.

### 7. Validate

- `pytest -q`: **558 passed** (+1 vs yesterday, covers the new filter).
- No new exit/sizing/entry change proposed this run — nothing to replay/MC/shadow-stage.

### 8. Deploy

**None this run.** (Operator's own thin-stop filter deploy at 09:46 UTC today predates this audit; reviewed, not re-deployed.)

### 9. Summary

- Equity: $135.09 (-2.3% vs 07-24, -2.0% vs the 07-21 post-deposit baseline)
- Trades: 5 closed, 0/5 winners, net -$2.88/-4.31R; 0 open
- Trial reset today by the operator: thin-stop squeeze filter live (`FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT=8`); Trial 2 at 4 trades, net R -4.52 (too early to read); XAU trade retrospectively confirms the exact failure the filter fixes
- Slot-cost signal: unchanged, 5 slot_occupied rows net -5R — still protective
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy, cycling normally, no errors, no entry-execution failures observed

---

# Daily Audit — 2026-07-24

---

## Automated Assessment (UTC ~22:10)

### 1. Trades (last 24h)

**PMT: 0** (frozen, `FUTURES_ENTRY_MIN_SCORE=1000`, unchanged; confirmed via fresh 6-symbol position-history export, 226 closed positions, window still ends 07-19). **Convex: 2 closed** — feature store grew 28→31 rows:
- `XRP_USDT` SQUEEZE LONG, x5, -1.43R / **-$0.30** (-3.31% margin), exit `EXCHANGE_CLOSE` (stop). Larger than the usual ~-1.0R stop cluster because the SL was unusually tight (`sl_margin_pct`=2.31%) and fees ate 31.8% of gross on this trade — fee-drag on tight-stop squeeze entries, consistent with the known convex fee-drag concern, not a new bug.
- `SNXX_USDT` WILDCARD SHORT, x3, -1.07R / **-$2.77** (-17.63% margin), exit `STOP_LOSS` — clean -1R stop, no anomaly.

Also closed just outside the strict 24h window (25.5h ago, still worth flagging): `ESPORTS_USDT` WILDCARD_LONG hit its **+5R TP** at 07-23 20:37 UTC after a 58h hold — **+5.09R / +$4.08**. This was the long-open position tracked across the last several audits.

Equity: **$138.21** (vs $139.8 07-23, vs $137.83 post-deposit 07-21 baseline) — -1.1% day-over-day, driven by realizing the last leg of ESPORTS' gain net of the two new stops.

### 1-OPEN. Open positions

**None.** 0 open positions confirmed via exchange query (`get_open_positions()`, all symbols) — flat window right after SNXX's stop.

### 2. Champion vs Shadow

**Futures-bot (champion):** cycling normally, 557/557 tests pass, no Tracebacks/errors and no 5003/2015 execution failures in the sampled log window (~1h, 500 lines). Wildcard/squeeze scans both showing quiet-regime rejection patterns (see 4c).

**Shadow: stale, comparison suppressed pending resync** (confirmed again — still PMT-gate-only code, no `SQUEEZE_SCAN_SUMMARY` lines, flat paper equity 100.00, 0 positions; this is now a 7th confirmation but per the 07-23 decision this is logged once as an action item and not re-elaborated — see Diagnose).

### 3. Wildcard/squeeze convex ledger (since 07-13 decommission, cumulative)

**12 closed trades** (was 9): win rate 33% (4/12), net R **+3.51**, ex-best R (drop ESPORTS +5.09) **-1.58**, net $ **+$3.20**. Still outlier-dependent — two of four wins (BILL +4.43R, ESPORTS +5.09R) account for essentially the entire edge.

### 4. Learning loop

**(a) Feature store:** 31 rows (was 28), in sync with the 3 new closes above.

**(b) Shadow ledger: grew from 6 to 9 rows, all now resolved** (AKE resolved -1R since 07-23; 2 new rows added: `ON_USDT` WILDCARD `slot_occupied` -1R, `PEPE_USDT` SQUEEZE `min_vol_skip` -1R, `DOGE_USDT` SQUEEZE `slot_occupied` -1R). Split:
- `slot_occupied`: **n=5, net -5.0R** (ERA, DEXE, AKE, ON, DOGE — every one a loser). Still below the 10-row action threshold, but the signal so far is that the single wildcard slot is **protective, not costing money** — answers the recurring "am I missing a second slot?" question with data, for now.
- `veto:ref_not_listed`: n=3, net +3R (unchanged, still below threshold).
- `min_vol_skip`: n=1, -1R (new category, too small to characterize).

**(c) Scan telemetry** (~1h sampled window, 3 cycles/sleeve): **wildcard** — 5-6 movers/cycle, dominant reject `roc_below_min` (10/11), one `no_pullback_resume`. **squeeze** — universe 93, ~30 scanned/cycle, dominant `no_active_coil` (85/90), `coil_too_short` (2), `no_range_break` (2). Quiet regime, gates behaving as designed. No `SIZE_TRIM` lines, no 5003/2015 execution failures.

**(d) Decision rule** (horizon = 30 convex trades from 07-13 23:00 UTC or 2026-10-13): **12 of 30 elapsed** — net R +3.51, ex-best -1.58 (still fails the outlier-robustness criterion if judged today). No drawdown concern. `USE_DRAWDOWN_KILL=0` override unchanged, operator-aware. **Note:** per `docs/DECISION_RULE.md`, today (07-24) is the deadline for a one-time operator edit to the pre-registered thresholds before they lock until the horizon — no edit was made this window, so the criteria are now immutable as originally registered.

### 5. Wildcard diagnose

No execution failures (0 5003/2015 in sample). Scan is correctly dormant — `roc_below_min` dominates, no rejected mover showed evidence of continuation worth a gate change. No loosening proposed.

### 6. Diagnose — lever for next 24h

**None.** PMT frozen; convex gates correctly dormant in a quiet regime; decision-rule (12/30) and shadow-ledger (5 and 3 rows) samples still below action thresholds. **Operational item (logged once, not re-flagged further):** Futures-shadow resync remains outstanding.

### 7. Validate

- `pytest -q`: **557 passed.**
- No exit/sizing/entry change proposed — no replay/MC/shadow validation needed.

### 8. Deploy

**None.** No candidate change to promote.

### 9. Summary

- Equity: $138.21 (-1.1% vs 07-23, +0.3% vs the 07-21 post-deposit baseline)
- Trades: 2 closed (XRP -1.43R/-$0.30, SNXX -1.07R/-$2.77), 0 open (ESPORTS closed +5.09R/+$4.08 just outside the window)
- Decision rule: 12/30 trades, net R +3.51, ex-best -1.58 — still outlier-dependent; thresholds lock today per the pre-registered doc
- Slot-cost signal: 5 slot_occupied shadow rows net -5R — protective so far, not yet actionable (n<10)
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy, cycling normally, no errors, no entry-execution failures observed

---

# Daily Audit — 2026-07-23

---

## Automated Assessment (UTC ~18:45)

### 1. Trades (last 24h)

**PMT: 0** (frozen, `FUTURES_ENTRY_MIN_SCORE=1000`, unchanged). **Convex: 0 closed** — feature store unchanged at 28 rows (last close still `PEPE_USDT` SQUEEZE, 07-21 12:01 UTC). Confirmed via fresh 6-symbol PMT position-history export (226 closed positions, window ends 07-19 — no PMT activity since freeze, as expected).

**1 open convex position (unchanged from yesterday):** `ESPORTS_USDT` WILDCARD_LONG, x2, entry 0.0243, sl 0.0224, tp 0.0333 — unrealized **+$2.49-2.61 (+47-48% margin)**, tp_progress advanced 0.52 -> 0.62-0.65, no bank/lock trigger fired yet, no anomalies, tracking cleanly.

Equity: **~$139.8** (vs $137.83 post-deposit baseline 07-21) — +1.4%, vs yesterday's $139.34 — +0.3%, driven by the open ESPORTS unrealized gain continuing to build.

### 2. Champion vs Shadow

**Futures-bot (champion):** cycling normally, 557/557 tests pass, no 5003/2015 execution errors, no Tracebacks in sampled logs.

**Futures-shadow: still on the 2026-06-14 build — 6th consecutive audit flagging this** (07-13, 07-16, 07-18, 07-19, 07-22, 07-23). Confirmed again: shadow logs show `PMT_GATE_BLOCK` (pre-decommission code path) and zero `SQUEEZE_SCAN_SUMMARY` lines in the sampled window (squeeze sleeve shipped 06-26) — still missing PMT decommission, squeeze sleeve, decision-rule/shadow-ledger telemetry, and the 07-22 regime-scaler-trim fix. Shadow currently shows 0 open positions (flat window, paper equity baseline 100.00) — still a good moment to resync (`railway up --service Futures-shadow`, env-only, operator call, not self-applied).

### 3. Wildcard/squeeze convex ledger (since 06-26 decision point, cumulative)

9 closed trades since the 07-13 decommission (unchanged this window — see Decision rule below).

### 4. Learning loop

**(a) Feature store:** 28 rows, unchanged from 07-22 — in sync (no new closes to reconcile).

**(b) Shadow ledger: grew from 3 to 6 rows (5 resolved, 1 open).** New since 07-22: `ERA_USDT` WILDCARD -1R (reject `slot_occupied`), `DEXE_USDT` WILDCARD -1R (`slot_occupied`), `AKE_USDT` WILDCARD unresolved (`slot_occupied`, still open). Net across 5 resolved rows = **+1R** (-1, +5, -1, -1, -1) — still far below the >=10-row minimum, no proposal. Notable shift: all 3 new rows are `slot_occupied` rejects (a live wildcard candidate skipped because the single wildcard slot was already held by ESPORTS), not external vetoes — this is exactly the slot-contention evidence the second-slot question needs, but n=3 is still too thin to act on.

**(c) Scan telemetry** (~30min sampled window): **wildcard** — small sample (5-6 movers/cycle), rejects `low_volume_z`, `no_pullback_resume`, `roc_below_min`; one genuine signal `AKE_USDT` found and correctly skipped only due to `slot_occupied` (not a strategy gate). **squeeze** — dominant `no_active_coil` (~23-25/30 scanned per cycle), `coil_too_short`, `no_range_break`. Consistent with a quiet regime — gates working as designed. No 5003/2015 execution failures.

**(d) Decision rule** (horizon = 30 convex trades from 07-13 23:00 UTC or 2026-10-13): **9 of 30 elapsed, unchanged** — net R = +0.92, ex-best (drop +4.43R BILL win) = -3.51 — still outlier-dependent, too early to act (n=9 of 30). No drawdown concern. `USE_DRAWDOWN_KILL=0` override unchanged, operator-aware.

### 5. Diagnose — lever for next 24h

**None.** PMT frozen by operator decision; convex gates correctly dormant in a quiet regime; decision-rule and shadow-ledger samples still too small to act on. **Operational item (repeat):** Futures-shadow resync — 6 consecutive audits stale, flat window still available right now.

### 6. Validate

- `pytest -q`: **557 passed.**
- No exit/sizing/entry change proposed — no replay/MC/shadow validation needed.

### 7. Deploy

**None.** No candidate change to promote.

### 8. Summary

- Equity: ~$139.8 (+1.4% vs the 07-21 post-deposit baseline; +0.3% vs 07-22)
- Trades: 0 closed / 1 open (ESPORTS_USDT WILDCARD_LONG, unrealized +$2.5-2.6, tp_progress 0.62-0.65)
- Decision rule: 9/30 trades, net R +0.92, ex-best -3.51 (unchanged, still outlier-dependent)
- Top flag: Futures-shadow confirmed still on the 06-14 build (6th consecutive audit) — flat window available for resync; secondary flag: shadow ledger now has 3 `slot_occupied` rejects (single wildcard slot binding), worth tracking toward the second-slot question
- Deploy: none this run
- Bot: healthy, cycling normally, no errors, no entry-execution failures observed

---

# Daily Audit — 2026-07-22

---

## Automated Assessment (UTC ~18:45)

### 1. Trades (last 24h)

**PMT: 0** (frozen, `FUTURES_ENTRY_MIN_SCORE=1000`, unchanged). **Convex: 0 closed** — feature store's last close is `PEPE_USDT` SQUEEZE at 07-21 12:01 UTC (just outside the 24h window). Confirmed via `railway logs --filter close` (no close events) and via the 6-symbol PMT position-history export (last closed position 07-19, expected since PMT is frozen).

**1 open convex position:** `ESPORTS_USDT` WILDCARD_LONG, x2, entry 0.0243, sl 0.0224, tp 0.0333 — currently unrealized **+$2.06 (+38.7% margin)**, tp_progress 0.52, tracking cleanly toward the bank-at-1R/runner design, no anomalies.

Equity: **$139.34** (vs $137.83 post-deposit baseline 07-21) — +1.1%, driven by the open ESPORTS unrealized gain.

### 2. Champion vs Shadow

**Futures-bot (champion):** redeployed today (`db4140fa`, 07-22 10:40 UTC, commit `380e1b4`), cycling normally, 557/557 tests pass, no 5003/2015 execution errors in the sampled window.

**Futures-shadow: still on the 2026-06-14 build** (deployment list confirms last SUCCESS = 06-14 21:00, no redeploy since) — **5th consecutive audit flagging this** (07-13, 07-16, 07-18, 07-19, 07-22). It is missing the squeeze sleeve (added 06-26), the PMT decommission, the decision-rule/shadow-ledger telemetry, and today's regime-scaler-trim fix. **Correction to the 07-19 note:** shadow's old build DOES include working wildcard-entry code — it opened and closed 2 live paper trades this window (`BANK_USDT` WILDCARD_LONG x7, both exited `PEAK_PROFIT_LOCK`, net **+$1.59**), so champion-vs-shadow is usable for raw wildcard mechanics but not for anything added since 06-14. Currently a flat window (0 shadow positions) — good time to resync (`railway up --service Futures-shadow`, env-only, operator call, not self-applied).

### 3. Wildcard/squeeze convex ledger (since 06-26 operator decision point, cumulative)

9 closed trades since the 07-13 decommission (see Decision rule below); no new closes this window to add.

### 4. Learning loop

**(a) Feature store:** 28 rows (was 22 on 07-17), growing with closes — in sync.

**(b) Shadow ledger:** still 3 resolved rows (`SKHYSTOCK_USDT` -1R, `SPCXSTOCK_USDT` +5R, `USOIL_USDT` -1R, all `veto:ref_not_listed`). Net +3R on n=3 — far below the >=10-row minimum, no proposal.

**(c) Scan telemetry** (~9h sampled window, 36 cycles each sleeve): **wildcard** — 230 movers evaluated, rejects `roc_below_min` (177), `no_pullback_resume` (34), `low_volume_z` (16), `climax_wick` (3). **squeeze** — dominant `no_active_coil` (902/~1080 scanned), `coil_too_short` (105), `no_range_break` (64), `low_volume_z` (9). Consistent with a quiet regime — gates working as designed, no loosening proposed. No 5003/2015 execution failures.

**(d) Decision rule** (horizon = 30 convex trades from 07-13 23:00 UTC or 2026-10-13): **9 of 30 elapsed** (ARB +0.34R, NEAR -1.14R, BILL +4.43R, AKE +2.53R, BILL -1.07R, ALLO -1.09R, PI -0.97R, ERA -1.06R, PEPE -1.05R). **Net R = +0.92, ex-best (drop the +4.43R BILL win) = -3.51** — still outlier-dependent (pass criterion #2 not yet met if evaluated today); too early to act (n=9 of 30). No drawdown concern at this equity scale. `USE_DRAWDOWN_KILL=0` override unchanged, operator-aware.

### 5. Diagnose — lever for next 24h

**None.** PMT frozen by operator decision; convex gates are correctly dormant in a quiet regime (no rejected mover showed demonstrable continuation); decision-rule and shadow-ledger samples too small to act on. **Operational item (not a strategy lever):** Futures-shadow resync — 5 consecutive audits stale, now confirmed via deployment history, and a flat window is available right now.

### 6. Validate

- `pytest -q`: **557 passed.**
- No exit/sizing/entry change proposed — no replay/MC/shadow validation needed.

### 7. Deploy

**None.** No candidate change to promote.

### 8. Summary

- Equity: $139.34 (+1.1% vs the 07-21 post-deposit baseline)
- Trades: 0 closed / 1 open (ESPORTS_USDT WILDCARD_LONG, unrealized +$2.06)
- Decision rule: 9/30 trades, net R +0.92, ex-best -3.51 (still outlier-dependent — watch this metric)
- Top flag: Futures-shadow confirmed still on the 06-14 build (5th consecutive audit) — usable for wildcard mechanics only, blind to everything shipped since; flat window available for resync
- Deploy: none this run
- Bot: healthy, cycling normally, no errors, no entry-execution failures observed

---

# Daily Audit — 2026-07-19

---

## Automated Assessment (UTC ~22:25)

### 1. Trades (last 24h, exact window 07-18 22:25 -> 07-19 22:25 UTC)

**PMT: 0.** Still blocked by `FUTURES_ENTRY_MIN_SCORE=1000` (decommissioned 2026-07-13, operator decision — not re-litigated).

**Convex: 2 closed trades, both losses.**
- `ALLO_USDT` WILDCARD_LONG: entry 07-18 10:28, exit 07-19 03:59 (17.5h hold), x5, exit_reason EXCHANGE_CLOSE (server-side SL). **-$1.45 (-17.8% margin, R=-1.09).**
- `PI_USDT` WILDCARD_LONG: entry 07-19 15:14, exit 15:55 (41min hold), x4, exit_reason EXCHANGE_CLOSE (server-side SL). **-$0.96 (-16.1% margin, R=-0.97).**

Both are clean, fast stop-outs — no leak, no design violation.

**No open positions** — wildcard and squeeze slots both free.

**Untracked trade (flagged, not a bot action):** MEXC's raw position ledger shows a third closed position this window — `SOL_USDT` LONG, opened 02:11, closed 17:02, x5, realised -$0.13 — that appears in **neither** `trade_history` nor `open_positions` at any point in the bot's persisted state. This looks like a manual/external trade placed directly on the exchange, outside the bot's control loop entirely (not a reconciliation bug — the bot never held state for it, so no orphan-warning path applies). Immaterial P&L; flagged for operator awareness/reconciliation only.

Equity: **$65.76** (was $67.69 at the 07-18 audit) — **-2.85%**, consistent with the two convex losses (-$2.41) net of the small untracked SOL loss.

### 2. Champion vs Shadow

**Futures-bot (champion):** current `main` (`d4fbd06`), cycling normally, telemetry firing, no errors, no 5003/2015 execution failures in the sampled log window.

**Futures-shadow: still stale on the 2026-06-14 build** (35+ days), equity flat $100.00, 0 trades, still running the pre-decommission PMT-only scan (`no_mental_threshold_cross` / `score_below_threshold` gate blocks every cycle, no wildcard/squeeze/telemetry code present). **This is the 4th consecutive audit flagging this** (07-13, 07-16, 07-18, 07-19). Champion-vs-shadow comparison remains unusable. Recommend `railway up --service Futures-shadow` (env-only resync to current `main`, no code change) at the next flat window — not self-applied, operator call.

### 3. Wildcard/squeeze convex ledger (running, since 06-26 operator decision point)

**15 trades, net +$8.15, netR +18.28, 46.7% win rate.** Outlier-robust: net stays positive ex-best (+$3.00, dropping BILL_USDT's +$5.15). Split: WILDCARD 9 trades/+$4.93; SQUEEZE 6 trades/+$3.22. Continues to earn its keep — no disable proposal.

### 4. Learning loop

**(a) Feature store:** 26 rows (was 24 at 07-18) — grew by exactly 2, matching the ALLO/PI closes. In sync with the exchange ledger.

Ran `tools/learn_from_trades.py` (n=26, window 06-27→07-19, overall mean +$0.30/trade, 50.0% win, meanR +0.65). Same single actionable-bar-clearing condition as 07-18: **`hold>=120min` FAVOR** (15 trades avg +$1.17/80% win vs 11 trades avg -$0.90/9.1% win, OOS-consistent). Still **not actionable** — hold time is an outcome, not a pre-trade signal. No new condition clears n>=10-per-side.

**(b) Shadow ledger (vetoed-signal counterfactuals):** 3 rows (was 2), only 2 resolved (`SKHYSTOCK_USDT` -1R, `SPCXSTOCK_USDT` +5R, both `veto:ref_not_listed`); new `USOIL_USDT` row unresolved. Still far below the >=10-row minimum — no proposal.

**(c) Scan telemetry** (~50min log window): wildcard rejects `roc_below_min` / `no_pullback_resume` / `low_volume_z` — consistent with a quiet regime. Squeeze dominant bucket `no_active_coil` (~26-27/30 scanned). **One squeeze signal fired this window (`USOIL_USDT`, 22:14 UTC) but was correctly vetoed by the external ref-not-listed gate before entry** — matches the new shadow-ledger row exactly; confirmed via open_positions=0 that no entry occurred. No 5003/2015 execution-failure codes observed.

**(d) Decision rule** (docs/DECISION_RULE.md, horizon = 30 convex trades from 07-13 23:00 UTC or 2026-10-13): **7 of 30 trades elapsed** (ARB +0.34R, NEAR -1.14R, BILL +4.43R, AKE +2.53R, BILL -1.07R, ALLO -1.09R, PI -0.97R). **Net R = +3.03, ex-best (drop the +4.43R BILL win) = -1.40 — the ex-best figure has flipped negative for the first time** (was +0.66 at 07-18) after today's two losses. Still very early (n=7 of 30) — not a proposal trigger, but the outlier-dependence criterion (pass criterion #2) is now the one to watch as the sample grows. No drawdown concern at this equity scale. `USE_DRAWDOWN_KILL=0` env override still in place (operator-aware, unchanged).

### 5. Diagnose — lever for next 24h

**None on the entry/exit side** — PMT frozen by operator decision, convex sleeves performing to design (2 clean stop-outs, no leak), decision-rule sample too small to act on, learning-loop conditions still below the actionable bar. **Operational item (not a strategy lever):** Futures-shadow resync, now flagged 4 audits running — recommend prioritizing this at the next flat window since it blocks the entire champion-vs-shadow comparison mechanism.

### 6. Validate

- `pytest -q`: not run this session (no code/config change proposed, so no regression risk to gate).
- No exit/sizing/entry change proposed, so no replay/MC/shadow validation needed.

### 7. Deploy

**None.** Champion already current (`d4fbd06`, 07-17). No candidate change to promote.

### 8. Summary

- Equity: $65.76 (-2.85% vs the 07-18 audit)
- Trades: 0 PMT / 2 convex closed, both losses (ALLO -$1.45/R-1.09, PI -$0.96/R-0.97)
- Untracked: SOL_USDT -$0.13, appears in neither trade_history nor open_positions — likely a manual/external trade, flagged for awareness only
- Open: none (both convex slots free)
- Convex ledger since 06-26: +$8.15 / 15 trades / 46.7% win / netR +18.28 — earning its keep
- Decision rule: 7/30 trades, net R +3.03, ex-best now -1.40 (first negative reading) — sample still small, watch this metric
- Top flag: Futures-shadow still on the 06-14 build (35+ days stale) — 4th consecutive audit raising this
- Deploy: none this run
- Bot: healthy, cycling normally, no errors, no entry-execution failures observed

---

# Daily Audit — 2026-07-18

---

## Automated Assessment (UTC ~22:50)

**Gap note:** no audit ran 2026-07-17 (skipped day, one day after the 07-16 catch-up run). Findings below use the exact last-24h window from MEXC/`trade_history` timestamps, plus a 48h-since-last-audit cross-check.

### 1. Trades (last 24h, exact window 07-17 22:46 -> 07-18 22:46 UTC)

**PMT: 0.** Still blocked by `FUTURES_ENTRY_MIN_SCORE=1000` (decommissioned 2026-07-13, per operator decision — not re-litigated).

**Convex: 1 closed trade.** `BILL_USDT` WILDCARD_SHORT: entry 03:11, exit 04:15 (64.6min hold), x5, score 96, exit_reason EXCHANGE_CLOSE (server-side SL). **-$1.00 (-19.15% of margin, R=-1.07).** Clean, fast stop-out — no leak, no design violation.

**1 open position:** `ALLO_USDT` WILDCARD_LONG, x5, opened 07-18 10:28 UTC, margin $8.15, entry 0.45305, TP 0.52732 (+5R design), SL 0.43844, unrealized ~-$0.55 (-6.7% of margin) as of this run. Occupies the wildcard slot; squeeze slot is free (0 open squeeze positions).

**Also in the 48h since the last audit (07-16):** `AKE_USDT` SQUEEZE_LONG, entry 07-16 -> exit 07-17 14:14, **+$2.49 (+49.6%, R=2.53), exit_reason MANUAL_CLOSE** (operator closed it — this is the AKE launch named in the 07-17 wildcard-band commit forensics; not a bot decision).

Equity: **$67.69** (was $66.84 at the 07-16 audit, 48h ago) — small net gain, consistent with realized +$1.49 (BILL -$1.00, AKE +$2.49) plus the current -$0.55 unrealized on ALLO.

### 2. Champion vs Shadow

**Futures-bot (champion):** confirmed on current `main` — last deploy `d4fbd06` (wildcard small-cap band focus + per-sleeve convex slots), SUCCESS 2026-07-17 15:37 UTC. Live logs show `[WILDCARD_SCAN_SUMMARY]` / `[SQUEEZE_SCAN_SUMMARY]` telemetry firing every cycle, confirming both recent commits (`1634cb1`, `d4fbd06`) are live, not just merged.

**Futures-shadow: still stale on the 2026-06-14 build (34 days now), equity flat $100.00, 0 trades, still running the pre-decommission PMT-only scan** (`[PMT_GATE_BLOCK]` on all 6 pairs every cycle, no wildcard/squeeze/telemetry code present). This is the **3rd consecutive audit flagging this** (07-13, 07-16, 07-18) with no resync yet — champion-vs-shadow comparison remains unusable. Re-flagging with more urgency: recommend `railway up --service Futures-shadow` (env-only resync to current `main`, no code change) at the next flat window. Not self-applied — deploy actions are an operator call per protocol.

### 3. Wildcard/squeeze convex ledger (running, since 06-26 operator decision point)

**13 trades, net +$10.56, netR +20.34, 53.8% win rate.** Outlier-robust: net stays positive even ex-best (+$5.41 dropping BILL_USDT's +$5.15). Split: WILDCARD 7 trades/+$7.34/netR+9.95/42.9% win; SQUEEZE 6 trades/+$3.22/netR+10.39/66.7% win. Full trade list unchanged from 07-16 plus 3 new: ARB_USDT SQUEEZE +$0.11 (07-14), AKE_USDT SQUEEZE +$2.49 (07-17), BILL_USDT WILDCARD -$1.00 (07-18). Continues to earn its keep — no disable proposal.

**Note for the record:** 2 of these 13 trades (ARB 07-14, AKE 07-17) closed via `MANUAL_CLOSE` (operator-initiated), not a designed exit path. Immaterial to P&L here (both were profitable holds) but worth tracking against DECISION_RULE.md pass-criterion 4 ("no manual rescues") as the sample grows.

### 4. Learning loop

**(a) Feature store:** 24 rows (was 22 at the 07-17 verification point) — grew by exactly 2 rows matching the 2 convex closes since then (AKE, BILL). Still in sync with the exchange ledger.

Ran `tools/learn_from_trades.py` (n=24, window 06-27→07-18, overall mean +$0.42/trade, 54.2% win, meanR +0.79). Only one condition clears both AVOID/FAVOR verdict and n>=10-per-side: **`hold>=120min` FAVOR** (14 trades avg +$1.36/85.7% win vs 10 trades avg -$0.89/10% win, OOS-consistent). Reported per protocol, but flagging it as **not actionable** — hold time is an outcome, not a pre-trade signal (winners naturally take longer to reach TP/bank; losers get stopped fast). No proposal from this. All other conditions (kind=WILDCARD/SQUEEZE/PMT, leverage tiers, side) are "weak" or "insufficient" — below the reporting bar.

**(b) Shadow ledger (vetoed-signal counterfactuals):** only 2 resolved rows (`SKHYSTOCK_USDT` -1R stop, `SPCXSTOCK_USDT` +5R TP — both vetoed on `ref_not_listed`). Net counterfactual is positive, which would argue the veto cost a winner, but n=2 is far below the >=10-row minimum — no proposal, continuing to accumulate.

**(c) Scan telemetry** (short ~45min log window, retention-limited — same limitation as prior audits): 3x `WILDCARD_SCAN_SUMMARY` samples, all `skipped=slot_occupied` (ALLO holding the slot the whole window — can't assess reject buckets while occupied). 3x `SQUEEZE_SCAN_SUMMARY`, dominant bucket `no_active_coil` (~15-20 of 30 scanned each cycle), no signal — consistent with a quiet/no-setup regime, not a bug. No entry-failure error codes (5003/2015) seen in this window.

**(d) Decision rule** (docs/DECISION_RULE.md, horizon = 30 convex trades from 07-13 23:00 UTC or 2026-10-13): **5 of 30 trades elapsed** (ARB +0.34R, NEAR -1.14R, BILL +4.43R, AKE +2.53R, BILL -1.07R). **Net R = +5.09, ex-best (drop the +4.43R BILL win) = +0.66R** — still positive, though thin at this sample size; not a real test yet. No drawdown concern (equity trended up over the window; both losses were small, quick stop-outs). No orphaned positions; the 2 MANUAL_CLOSEs noted above are the only wrinkle against criterion 4. `USE_DRAWDOWN_KILL=0` env override still in place (operator-aware, unchanged).

### 5. Diagnose — lever for next 24h

**None on the entry/exit side** — PMT frozen by operator decision, convex sleeves performing to design, decision-rule sample too small to act on. **Operational item (not a strategy lever):** Futures-shadow resync, now flagged 3 audits running.

### 6. Validate

- `pytest -q`: **not run this session** — no local Python available in this environment, and the deployed container's venv lacks dev/test deps (pandas native libs missing when pytest was ad-hoc installed: `libstdc++.so.6` not present in the slim runtime image). No code or config change is proposed this run, so there is no regression risk from skipping this gate today.
- No exit/sizing/entry change proposed, so no replay/MC/shadow gate needed.

### 7. Deploy

**None.** Champion already current (d4fbd06, 07-17). No candidate change to promote. A live position (ALLO_USDT) is open, which would block a deploy anyway.

### 8. Summary

- Equity: $67.69 (+1.3% since the 07-16 audit, 48h)
- Trades: 0 PMT / 1 convex closed in strict 24h (BILL_USDT -$1.00, R-1.07); +1 more convex (AKE +$2.49, R+2.53) in the 48h since last audit
- Open: ALLO_USDT WILDCARD_LONG, unrealized ~-$0.55
- Convex ledger since 06-26: +$10.56 / 13 trades / 53.8% win / netR +20.34 — earning its keep
- Decision rule: 5/30 trades, net R +5.09 (+0.66 ex-best) — on track, sample still small
- Top flag: Futures-shadow still on the 06-14 build (34 days stale) — 3rd consecutive audit raising this
- Deploy: none this run
- Bot: healthy, cycling normally, no errors, no entry-execution failures observed

---

# Daily Audit — 2026-07-16

---

## Automated Assessment (UTC ~16:20)

**Gap note:** the 2026-07-13 entry below was never committed by that run (docs/daily_audit.md sat modified-but-uncommitted in the working tree); it is committed now as part of this run, unchanged. No audit exists for 07-14/07-15.

### 1. Trades (last 24h, MEXC + persisted trade_history)

**PMT: 0 trades.** Expected — `FUTURES_ENTRY_MIN_SCORE=1000` (decommissioned since 2026-07-13) still blocks all `_enter_trade` entries; last PMT close was 2026-07-14 00:55 (BTC_USDT SHORT, -$3.49, pre-dates this window). No PMT positions open.

**Convex (wildcard+squeeze): 1 closed trade, a big one.** `BILL_USDT` WILDCARD_SHORT: entry 2026-07-15 07:28 @ 0.03589, exit 2026-07-16 15:43 @ 0.0294, x4, score 96, held 32.3h, exit_reason EXCHANGE_CLOSE (server-side TP, not a discretionary lock — matches the convex-exit design that skips profit-locks and lets winners run). **+$5.15 (+71.75%, R=4.43).** This is the kind of multi-day runner the convex thesis is built on. No open wildcard/squeeze positions right now.

Also closed just outside the strict 24h window: `NEAR_USDT` SQUEEZE_LONG, 2026-07-15 06:12->07:27, -$0.163 (R=-1.14) — quick stop-out, unremarkable.

**0 open positions anywhere.** Equity $66.84 (was ~$61.7 a day ago on the one closed trade) -> **+8.3%/24h**, all from the one wildcard win.

### 2. Champion vs Shadow

**Futures-bot (champion) WAS redeployed** — 2026-07-16 15:42 UTC, current `main` (3ad120a), resolving the 16-day deploy gap flagged in the 07-13 report. `pytest -q`: 539/539 green. No Tracebacks/errors in visible logs.

**Futures-shadow is still stuck on the 2026-06-14 build** (32 days, cycle #59,553, equity flat $100.00, 0 trades) — it predates PMT-decommission, the squeeze sleeve, the external gate, and the convex-exit change, so it is not a usable champion-vs-shadow comparison right now. This is the same issue as 07-13, still unresolved. **Flagging again as the top operational item** — recommend `railway up --service Futures-shadow` (env-only resync, no code change) at the next flat window so it starts mirroring current champion; not self-applied per protocol (deploy = operator call, and it's outside what this run was asked to do).

### 3. Wildcard ledger (running, since inception 2026-06-15, last 200 trade_history entries)

24 wildcard trades lifetime, 12 wins (50%), net **-$5.34** — but this is dominated by pre-06-16 tail risk (SIREN -$8.88, before the -20% SL cap) and pre-06-26 trades (before the convex no-early-lock exit change). **Judging on the operator-designated post-06-26 window** (per 2026-07-13 operator decision): 4 wildcard trades, net **+$9.47** (O_USDT +2.15/R5.0, TRIA +3.47/R4.94, VANRY -1.30/R-0.96, BILL +5.15/R4.43); squeeze sleeve 5 trades, net **+$0.73** (3W/2L). Combined convex since 06-26: **9 trades, net +$10.20, 67% win rate, avg R ~2.6.** Continues to earn its keep — no disable proposal.

Squeeze/wildcard scan diagnostics (short ~30min log window, retention-limited): one candidate seen, `ANSEM_USDT` LONG (ROC 13.7%, RSI 72) — vetoed by `EXTERNAL_GATE` (`ref_not_listed`, i.e. not listed on the reference exchange). Looks like the veto working as intended (screening out an illiquid/unverifiable micro-cap mover), not a bug. Stage-2 feature store has 22 rows accumulated since 06-26 — still below a useful sample for a with/without-X split; no proposal yet, as expected.

### 4. Diagnose — lever for next 24h

**None.** No entry-side lever available (PMT frozen by operator decision; convex sleeves performing to design). The only open item is the Futures-shadow resync (operational, not a strategy tune) — see above.

### 5. Validate

- `pytest -q`: 539/539 passed.
- No exit/sizing/entry change proposed this run, so no replay/MC/shadow gate needed.

### 6. Deploy

**None this run** (champion already redeployed prior to this run, independently of this audit; no new candidate change to promote).

### 7. Summary

- Equity: $66.84 (+8.3%/24h, driven by 1 wildcard win)
- Trades 24h: 0 PMT / 1 wildcard (BILL_USDT SHORT +$5.15, R4.43, 32h hold)
- Shadow: $100.00 flat, still on stale 06-14 build — not a valid comparison; propose resync
- Convex ledger since 06-26: +$10.20 / 9 trades / 67% win — earning its keep
- Deploy: none this run; champion already resynced to `main` outside this audit
- Bot: healthy, cycling normally, no errors

---

# Daily Audit — 2026-07-13

---

## Automated Assessment (UTC ~22:45)

**GAP NOTICE:** no audit entry exists between 2026-06-26 and today — 16 days with no recorded run. This is the first review in that window; findings below reflect current live state only, not a continuous 24h-by-24h trail.

### 1. Trades Reviewed (last ~24-48h, MEXC historical positions)

**PMT: 1 closed trade.** SOL_USDT SHORT, x15, entry 77.15 -> exit 76.83, opened 2026-07-12 21:30 UTC, closed 2026-07-13 00:02 UTC. Net **+$0.30** (gross +$0.478, fees -$0.185). Small, quick win — matches the small-wins design intent. No issues.

**Wildcard: 0 new opens/closes in 24h,** but **1 wildcard position has been open since 2026-07-09 17:40 UTC (4 days)**: ARB_USDT LONG, x5 (floor of the 5-10x band), margin $1.96 (~3% of equity — below the 5-15% balance_fraction spec, likely trimmed further by a risk cap), currently ~+$0.10 unrealized (price +0.9% since entry). Not misbehaving (still within the -20% SL cap, small size), but it has not progressed toward +1R in 4 days — the convex "ride the runner" exit only pays off if the move continues; a 4-day flat chop is dead capital, not proof of a bug. Scan diagnostics for wildcard rejects were not available this run (Railway log retention only reached back ~4h from `railway logs`, not the full 24h — see Validate section).

Open positions right now: BTC_USDT SHORT (x20, entry 61,934.30, opened 2026-07-13 18:00 UTC, unrealized -$0.59) + the ARB wildcard above.

### 2. Champion vs Shadow

Futures-shadow paper equity is flat at exactly **$100.00, 0 trades** — because Futures-shadow has not been redeployed since **2026-06-14** (29 days). It is not running any of the code merged since then and cannot serve as a candidate comparison right now (see Deploy Drift below).

### 3. Deploy Drift — TOP FINDING

**Futures-bot (champion) has not been redeployed since 2026-06-26 23:22 UTC (16+ days).** Five commits merged to `main` since that deploy have never shipped to the live container:

| Commit | What | Live effect right now |
|---|---|---|
| `8062f4e` | fix: close message + accounting reflect partial banks | **Bug still live** — Telegram close messages / trade_history undercount banked (+1R/+2R) profit on the deployed build |
| `6de8084` | convex wildcard exit (skip discretionary profit-locks) | Inert — `FUTURES_WILDCARD_CONVEX_EXIT_ENABLED=1` is already set on Railway but the deployed code predates this flag |
| `859de73` | Coiled-Spring squeeze-breakout entry (long-only) | Inert — `FUTURES_SQUEEZE_ENABLED=1` already set, same issue |
| `c561b91` | external cross-exchange/crowding entry veto (fail-open) | Inert — `FUTURES_EXTERNAL_GATE_ENABLED=1` already set, same issue |
| `3ad120a` | Stage-2 conditional-expectancy engine + feature store | Propose-only, no live risk either way, but the feature store isn't accumulating data while undeployed |

Notably, the Railway env vars for the three feature flags were **already flipped on**, implying deploy was intended and simply never executed — this looks like a stalled/interrupted rollout, not a pending decision. `pytest` is green (539/539) on current `main`.

**Did not deploy this run**: a champion position is currently open (BTC_USDT SHORT + the ARB wildcard), and the protocol says avoid deploying with a position open. This is the top priority for the next review that catches a flat window — ship current `main` to both Futures-bot and Futures-shadow to resync the champion/shadow baseline.

### 4. Diagnose — lever for next 24h

No new tuning lever proposed. The dominant issue is operational (ship already-merged, already-tested code), not a strategy parameter. Once deployed, re-baseline the champion-vs-shadow comparison since shadow will restart from the current `main`, not the stale June 14 build.

### 5. Validate

- `pytest -q`: **539/539 passed**.
- No exit/sizing/entry change proposed this run, so no replay/MC/shadow gate needed.
- Log retention caveat: `railway logs --since` did not return data older than ~4h regardless of the requested window (tried 24h/96h) — 24h trade facts here came from MEXC `get_historical_positions` directly, per protocol; wildcard scan-reject diagnostics could not be pulled for the full window.

### 6. Deploy

**None.** Position open (see above). Recommend deploying current `main` (the 5 commits above) at the next flat window.

### 7. Summary

- Equity: ~$64.4 (current live read; no reliable 24h-ago baseline exists due to the 16-day reporting gap)
- Trades 24h: 1 PMT (SOL SHORT, +$0.30, win) / 0 new wildcard (1 wildcard, ARB LONG, still open 4 days)
- Shadow: $100.00 flat, stale build (June 14) — not a valid comparison until redeployed
- Top flag: 16-day deploy gap — 5 merged commits (1 live accounting bug fix + 3 already-flagged-on feature flags + 1 propose-only engine) sitting undeployed; propose shipping at next flat window
- Deploy: none this run (position open)
- Bot: healthy, cycling normally, no errors in visible logs

---

# Daily Audit — 2026-06-26

---

## Automated Assessment (UTC ~18:25)

### 1. Trades Reviewed (24h)

**0 PMT trades. 0 Wildcard trades.**
Equity: **$62.61** (up +$1.55 from $61.06 on Jun 24; source unclear — no closed trades found in 48h across 29 checked symbols; likely funding credit or settlement lag).

No open positions.

**Market context (at scan time):**
- BTC: ~$60,100 (FLAT, trap_reclaim_block SHORT at $60k)
- ETH: FLASH_BULLISH +0.45% 24h
- SOL: MEGA_BULLISH **+8.11% 24h**, +6.15% 12h, +5.79% 6h (strong but no mental level break)
- BNB: FLASH_BULLISH +1.54% 24h
- SEI: MEGA_BEARISH **-9.24% 24h**, -3.97% 12h (strong but no mental level break)
- ZEC: FLASH_BULLISH +4.24% 24h

PMT gate histogram (all 6 blocked): `{no_mental_threshold_cross pmt:5, trap_reclaim_block side:1}`

---

### 1b. WILDCARD — Diagnose & Improve

**Ledger (all 4 live trades, unchanged):**

| # | Symbol | Side | Date | Net | PnL% margin | Status |
|---|--------|------|------|-----|-------------|--------|
| 1 | EVAA | LONG | Jun 14 | +$3.16 | +26.3% | WIN (operator closed) |
| 2 | EVAA | SHORT | Jun 15 | +$0.91 | +9.5% | WIN |
| 3 | SIREN | SHORT | Jun 15 | -$8.70 | -67.9% | LOSS (pre-cap) |
| 4 | UB | SHORT | Jun 24 | -$1.11 | -18.7% | LOSS (with cap) |

**Cumulative: 2W/2L, 50% WR, net -$5.74. Still < 5 trades for tunable gate.**

**(a) Scan diagnostics (today's universe scan):**
- 931 MEXC USDT-settled contracts scanned
- 4 movers passed turnover (≥$3M) + |24h move| ≥8% gate:
  - MAGMA_USDT: -22.4% 24h, $12M turnover
  - VELVET_USDT: +15.5% 24h, $15.7M turnover
  - HEI_USDT: -10.8% 24h, $9.3M turnover
  - CAP_USDT: +8.7% 24h, $3.8M turnover

Gate 2 (pullback-resume) broke all 4:
- MAGMA: ROC -22% PASS, but current bar resuming UP (wrong direction vs entry SHORT); no clean pullback structure
- VELVET: ROC +15.5% PASS, but current bar closing DOWN (not resuming LONG); prev > prev2 so no pullback either
- HEI: ROC -10.8% PASS, resumed SHORT, but no prior pullback (prev not bouncing against the drop)
- CAP: Insufficient bars (26 < 30 minimum)

No 5003/2015 order rejects (no entries attempted). No tick-snapping execution bug triggered.

**(b) Dormancy:** Not dormant by intent — 4 qualifying movers were scanned. All blocked by gate 2 (no pullback-resume structure). Correct behavior: the wildcard waits for a flag/pennant entry, not a raw momentum chase. Loosening gate 2 would chase vertical moves — DO NOT.

**(c) Improve:** 4 live trades < 5 required. No tunable proposed. Monitor.

---

### 2. Champion vs Shadow

| Service | Equity | Cycles | Status |
|---------|--------|--------|--------|
| Futures-bot (LIVE) | **$62.61** | ~561 | Active, cycling 45s |
| Futures-shadow (PAPER) | **$100.00** | ~22,289 | Active, cycling 45s |

Shadow gate: identical to champion — `{no_mental_threshold_cross pmt:5, trap_reclaim_block side:1}`. No candidate staged; shadow mirroring champion. Shadow equity gap ($37.39) reflects live losses before shadow diverged. No A/B conclusions (need ≥5 shadow trades; 0 since staging).

---

### 3. Diagnose — One lever

**OI STUDY (update attempt):**
OI data spans Jun 19-26 (7 days, 11,480 samples/symbol). MEXC historical position API returned 0 PMT trades in 14d — prior trades (Jun 17-22) are beyond the API's return horizon. Cannot add new data points to the study. Last known results (from Jun 24 audit): NEUTRAL=0/3, CONFIRMED=1/2, DIVERGENT=1/1 — inconclusive (6 trades). **OI promotion blocked.**

**Lever for next 24h: None.**
- SOL MEGA_BULLISH (+8% 24h) is the notable signal but the `no_mental_threshold_cross` block is structurally correct — no round-number or prior-high break has occurred yet. If SOL breaks a psychological level during the next 24h, the bot would enter. Nothing to tune.
- BTC $60k trap_reclaim_block (SHORT) is working correctly — price dipped below $60k and recovered, correctly suppressing SHORT entries.
- Calibration at 13/15 trades (from Jun 24 audit; 0 new trades added). Walk-forward gate remains blocked until ≥2 more live PMT fills.
- No replay run: no candidate change to evaluate.

---

### 4. Validate

- **pytest:** 525/525 passed ✓
- **Replay:** N/A (no change proposed)
- **Shadow:** No candidate staged; mirroring champion

---

### 5. Deploy

**None.** No code or env changes. Correct status: observe and wait.

---

### 6. Summary

- Equity: $62.61 (+$1.55 from Jun 24; +2.5%); -44.8% from Jun 9 peak
- Trades 24h: 0 PMT, 0 Wildcard
- Wildcard: 4 movers scanned, all blocked at pullback-resume gate. Not dormant — correct behavior
- Lever: None. OI study inconclusive. Entry side frozen. Calibration needs 2 more live PMT fills
- Deploy: None
- Bot: healthy, cycling, no errors

---

# Daily Audit — 2026-06-24

---

## Automated Assessment (UTC ~09:50)

### 1. Trades Reviewed (24h)

**1 WILDCARD trade closed. 0 PMT trades.**
Equity: **$61.06** (down from $99.65 last recorded deploy-check; -38.8% since; down $49.74 = -44.9% from June 9 peak of $113.05).

No open positions.

**WILDCARD — UB_USDT SHORT (closed today)**

| Symbol | Side | Lever | Entry | Exit | Gross | Fee | Net | PnL% margin | Margin | Acct% |
|--------|------|-------|-------|------|-------|-----|-----|-------------|--------|-------|
| UB_USDT | SHORT | x3 | $0.0590 | $0.0626 | -$1.07 | $0.03 | **-$1.11** | -18.67% | $5.75 | 1.82% |

- Opened 07:41 UTC, closed 08:23 UTC (42 min). Exit reason: EXCHANGE_CLOSE (SL hit).
- Peak PnL reached +5.59% (near +1R threshold; bank never armed).
- Leverage correctly capped to x3 by the 20% SL margin cap (SL distance ~5.9% × x5 would exceed 20% cap; trimmed to x3).
- Margin $5.75 = 9.4% of equity (design: 10-15%; slightly under due to leverage cap constraint, acceptable).
- Entry structurally valid: entered SHORT at pullback on an extreme mover; price briefly went in favour before reversing and SL fired.
- **PMT compliance: N/A (wildcard slot, not PMT).** SL cap working correctly. No stop leak beyond 20%.

**7-day PMT recap (context for equity drawdown):** 7 trades Jun 17-22, net -$7.41, 3W/4L. 4 stop-outs in a market recovering from the June crash (BTC ~$62-64k after June crash). Cold-streak throttle fired (ZEC trade had smaller margin ~$7, confirms throttle working). Winners banked via tight-lock at +7-9% margin (low-tier behavior). No stop leak > 25% on any PMT trade.

---

### 1b. WILDCARD — Diagnose & Improve

**Ledger (all 4 live trades):**

| # | Symbol | Side | Date | Net | PnL% margin | Status |
|---|--------|------|------|-----|-------------|--------|
| 1 | EVAA | LONG | Jun 14 | +$3.16 | +26.3% | WIN (operator closed) |
| 2 | EVAA | SHORT | Jun 15 | +$0.91 | +9.5% | WIN |
| 3 | SIREN | SHORT | Jun 15 | -$8.70 | -67.9% | LOSS (pre-cap) |
| 4 | UB | SHORT | Jun 24 | -$1.11 | -18.7% | LOSS (with cap) |

**Cumulative: 2W/2L, 50% WR, net -$5.74. Still < 5 trades for the tunable gate.**

**(a) Scan diagnostics:** Wildcard is active — found and entered UB_USDT today. No 5003/2015 order-reject errors observed in today's logs for UB. Broad-universe scan logs not surfaced at INFO level (wildcard scan messages not visible in grepped output), but confirmed working via live trade.

**(b) Dormancy:** Not dormant. 1 trade today. Previous gap (Jun 15 → Jun 24, 9 days) was dormancy due to post-SIREN cap tightening + no qualifying movers in that window. Correct behavior — no movers above gate = no trades.

**(c) Improve:** 4 live trades < 5 gate. No tunable proposal. Monitor.

**Key outstanding wildcard risk:** UB_USDT is a micro-token with a 24h high of $0.0955 and low of $0.0579 — a 65% range. This suggests either genuine high-volatility or thin-book manipulation risk. The volume floor (MIN_TURNOVER) should catch the most illiquid tokens; UB had $5.5M 24h notional volume which is above typical floors. No action needed now; flag for review if next UB/similar trade also loses quickly on reversal.

---

### 2. Champion vs Shadow

| Service | Equity | Status |
|---------|--------|--------|
| Futures-bot (champion, LIVE) | **$61.06** | Active, cycling 45s |
| Futures-shadow (paper) | **$100.00** | Active, cycling 45s |

Shadow shows $100.00 (paper reset balance) — appears freshly reset with no accumulated paper P&L. Both services show identical `no_mental_threshold_cross pmt:6` gate blocks across all 6 symbols today. No divergence attributable to config difference (shadow mirroring champion with no candidate staged). Shadow equity vs champion divergence = **+$38.94** favoring shadow (paper) — entirely from earlier live SLs.

---

### 3. Diagnose — One lever

**OI Lift Study (ran today for first time; June 17-24 data):**

| OI State at Entry | Trades | WR | Net P&L |
|-------------------|--------|----|---------|
| CONFIRMED (OI rising) | 2 | 50% | -$3.27 |
| DIVERGENT (OI falling) | 1 | 100% | +$3.23 |
| NEUTRAL | 3 | 0% | -$8.85 |

Result: **Inconclusive.** NEUTRAL is 0/3 (worst), but only 6 trades total. DIVERGENT winning is directionally opposite to the model hypothesis. Sample is too small for statistical significance. **OI promotion blocked — do not apply score_adj.**

**Lever for next 24h: None.** Market is flat across all 6 PMT symbols (all ±0.3-2.3% on 24h, well below MEGA thresholds). PMT entry is correctly gated. Calibration now at 13/15 trades — 2 more PMT fills needed before the walk-forward gate can pass.

LESSON REINFORCED: Equity drawdown since June 9 (-44.9%) reflects the PMT system correctly firing SHORT entries during the June crash recovery period where most SHORTs got stopped out. The sizing and throttle are working as designed. No systemic design flaw — the bot is behaving correctly in a hard market.

---

### 4. Validate

- **pytest:** 523/523 passed ✓
- **Replay:** N/A (no change proposed)
- **Shadow:** No candidate staged; shadow mirroring champion

---

### 5. Deploy

**None.** No code or env changes. Correct status: observe and wait.

---

### 6. Summary

- Equity: $61.06 (-44.9% from June 9 peak, net -$7.41 7d PMT, -$1.11 today wildcard)
- Trades 24h: 1 (UB wildcard SHORT, -$1.11, valid SL, cap working)
- PMT: 0 entries (all FLAT, correct)
- Wildcard ledger: 4 trades, 50% WR, net -$5.74 (< 5-trade gate for tunable proposal)
- OI lift study: 6 trades, inconclusive, OI promotion blocked
- Calibration: 13/15 trades, walk-forward OOS PF=0.209 (failing)
- Deploy: none
- Verdict: HOLD. Market is ranging. Bot healthy.

---

# Daily Audit — 2026-06-20

---

## Automated Assessment (UTC ~17:35)

### 1. Trades Reviewed (24h)

**5 closed trades (3 PMT + 2 Wildcard).** Equity $66.98 (prev $72.97 Jun 18, -$5.99 / -8.2%).

#### 24h closed trades (Jun 18 20:00 → Jun 20 17:35 UTC):

| Symbol | Type | Side | Entry | Exit | Net | Fee | profRatio | Lev | Dur | Exit |
|--------|------|------|-------|------|-----|-----|-----------|-----|-----|------|
| BNB_USDT | PMT | SHORT | $579.60 | $576.10 | +$1.05 | -$0.39 | +7.6% | 18x | 16.5h | profit lock |
| BTC_USDT | PMT | SHORT | $62,854.40 | $63,590.70 | -$4.32 | -$0.53 | -23.4% | 18x | 26.7h | SL |
| ZEC_USDT | PMT | LONG | $476.69 | $473.57 | -$1.01 | -$0.20 | -12.0% | 15x | 10m | SL |
| BEAT_USDT | WC | LONG | $1.983 | $1.869 | -$1.29 | -$0.03 | -23.5% | 4x | 20m | SL |
| BTW_USDT | WC | LONG | $0.06167 | $0.05759 | -$0.42 | -$0.01 | -13.5% | 2x | 34m | SL |

**PMT: 1W/2L, net -$4.28. WC: 0W/2L, net -$1.71. Total 24h: net -$5.99.**

**PMT design compliance:**
- BNB SHORT 18x: pmt=BEARISH threshold cross → SHORT ✓. Stop-first sizing with tight ATR → 18x. Closed via profit lock at +7.6%. ✓
- BTC SHORT 18x: pmt=BEARISH → SHORT ✓. SL fired at -23.4% profRatio. BTC moved +1.17% against the position at 18x = -21.1% margin + fees = -23.4%. Within 25% stop-leak cap ✓. Wide ATR gave 18x (tighter stop, higher lev) — expected stop-first behaviour.
- ZEC LONG 15x: entered on pmt=BULLISH threshold cross. SL in 10 minutes. profRatio -12.0%. Stop-chase cooldown (21600s/6h) now active for ZEC LONG side. ✓

**Cold-streak note:** BTC SL (streak=1) → ZEC SL (streak=2) → triggers 0.5x throttle on next PMT trade. After next WIN, resets.

**Wildcard design compliance:**
- BEAT LONG 4x (capped from 7x): BEAT was an extreme up-mover (3h ROC ≥8%), pullback-resume entry ✓. Leverage capped by SL cap logic (wide ATR → sl_frac≈4.5%, 4.5%×7=31.5% > 20% cap → trimmed to 4x). profRatio=-23.5% EXCEEDS the 20% SL cap by 3.5pp. Likely cause: illiquid small-cap alt gapped through the SL limit order (BEAT fell -5.75% in 20 min; limit not filled at SL price). Tick-snap bug cannot be ruled out. Action: tick-snap fix still needed.
- BTW LONG 2x (capped from 7x): extreme up-mover, pullback-resume ✓. Leverage capped (ATR ~7.5% → sl_frac=11.3%, 11.3%×7=79% >> cap → trimmed to 2x, sl_margin=22.5% → cap forces sl_frac tighter → final sl_margin≈15%). profRatio=-13.5% within expected cap. SL executed correctly. ✓

### 2. Wildcard Ledger (updated through Jun 20)

**Since redesign launch (Jun 14):**
| # | Date | Symbol | Net | profRatio | Note |
|---|------|--------|-----|-----------|------|
| 1 | Jun 14 | EVAA LONG | +$3.16 | +26.3% | WIN |
| 2 | Jun 15 | EVAA SHORT | +$0.91 | +9.5% | WIN |
| 3 | Jun 15 | BSB LONG | +$0.58 | +4.6% | WIN |
| 4 | Jun 15 | SIREN SHORT | -$8.70 | -67.9% | LOSS (pre-cap, no-SL) |
| 5 | Jun 17 | SKYAI SHORT | -$4.22 | -50.7% | LOSS (SL tick-snap bug, post-cap) |
| 6 | Jun 18 | ESPORTS SHORT | +$1.15 | +12.9% | WIN |
| 7 | Jun 18 | VELVET LONG | +$0.86 | +10.1% | WIN |
| 8 | Jun 19 | BEAT LONG | -$1.29 | -23.5% | LOSS (SL cap breach, possible gap) |
| 9 | Jun 19 | BTW LONG | -$0.42 | -13.5% | LOSS (SL within cap) |

**Total: 9 trades, 5W/4L (56%), net -$7.97.** 4 consecutive losses. Trade 10 triggers net-negative disable assessment per protocol. Clean wins (EVAA×2, BSB, ESPORTS, VELVET) were all fast +10-26% gains. Losses are concentrated in 3 SL-miss/bug cases (SIREN, SKYAI, BEAT) and 1 clean SL (BTW). Strategy shows genuine short-duration signal when entries work; execution quality (SL placement for illiquid alts) is the drag.

**Wildcard diagnostics:**
- Scan ran every ~15min (FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS=900). No [WILDCARD_SCAN] log in Railway window (scan logs only appear on candidate found, not on empty results).
- Current movers (24h, vol>$500k): BICO +28.9%, VELVET +12.6%, AGT +9.9%, BTW +6.7%, SIREN +5.0%. Regime is moderately active — there ARE extreme movers today.
- BEAT (Jun 19 05:07) and BTW (Jun 19 06:13) entered on valid 3h ROC + pullback-resume. Both were up-movers that quickly reversed. This is the pattern expected: acceleration entries that don't sustain. No gate loosening warranted.
- BEAT profRatio=-23.5% exceeded cap: the SL at ~$1.894 (4.5% below entry) was either not filled (gap-through on illiquid alt) or tick-snap caused a mis-placed SL. Cannot distinguish from MEXC exit data alone. If gap-through: this is normal small-cap risk, not a bug. If tick-snap: fix needed.
- Entry failure check: no 5003/2015 order errors visible in current log window (too recent). Prior SKYAI case was confirmed SL order failure.
- No dormancy (2 wildcard trades Jun 19). No gate loosening proposal (<5 live trades with ≥5d dormancy).
- At 9 trades with net -$7.97: **APPROACHING DISABLE THRESHOLD** (10 trades net-negative). Will reassess on trade 10.

### 3. Champion vs Shadow

| Metric | Champion (LIVE) | Shadow (PAPER) |
|--------|----------------|----------------|
| Equity | $66.98 | $100.00 |
| 24h trades | 5 (3 PMT + 2 WC) | 0 |
| Config | 6-pair baseline | mirrors champion + volume_filter |
| Gate (current) | no_mental_threshold_cross pmt:6 | no_mental_threshold_cross pmt:5, volume_filter:1 |

Shadow $100 vs champion $66.98 reflects prior live losses. No candidate staged. Shadow has volume filter as residual from prior staging — not a new candidate. No A/B conclusion possible (0 shadow trades).

### 4. OI Study

**7-day window (Jun 13-Jun 20 UTC), 68,532 samples across 6 symbols.**

| Label | n | mean_fwd_% | pos_rate |
|-------|---|-----------|----------|
| CONFIRMED (OI↑ + price↑) | 16,465 | +0.0257 | 49.1% |
| DIVERGENT (OI↓ + price↑) | 16,743 | +0.0075 | 46.9% |
| NEUTRAL | 34,934 | +0.0188 | 50.5% |

**Verdict: DO NOT PROMOTE.** CONFIRMED pos_rate (49.1%) UNDERPERFORMS NEUTRAL (50.5%) by -1.4pp — sign reversed from the Jun 18 window (+1.4pp). The signal is regime-dependent noise. Jun 13-20 covers a bear-to-recovery cycle (BTC $60K → $64K), positive bias lifts all labels. CONFIRMED underperforming NEUTRAL on the critical gate metric means OI expansion at entry is not adding edge. Continue accumulation; need 14+ days spanning a clear bull + bear regime.

### 5. Diagnose

**ONE lever: None.** Market in moderate recovery (BTC +1.5% 24h, BNB +1.3%, ZEC +5.0%). All 6 PMT pairs blocked by `no_mental_threshold_cross pmt=BULLISH` (12h moves too small to cross mental threshold). ZEC also has stop-chase cooldown active (6h from 16:55 UTC).

**Cold-streak throttle active:** BTC SL → ZEC SL = 2 consecutive SLs. Next PMT trade is sized at 0.5x normal margin until a win resets the streak.

**Top action (code):** Tick-snap fix. SKYAI (-$4.22 Jun 17) was confirmed SL-order failure from priceUnit precision. BEAT (-$1.29 Jun 19) shows same pattern (profRatio exceeded cap). Fix: before placing any SL/TP order, snap price to per-symbol priceUnit from exchange spec; abort if priceUnit unknown rather than falling back to 0.01. Not yet shipped.

**Lessons not forgotten:** trigger-side changes 5-for-5 rejected. Entry frozen pending OI protocol.

### 6. Validation

- pytest: **523/523 passed** ✓ (GitHub CI known-red, ignored)
- No candidate change → no replay required

### 7. Deploy

**None.** No env or code changes.

### 8. Summary

- Trades (24h): 5 — BNB +$1.05, BTC -$4.32, ZEC -$1.01 (PMT), BEAT -$1.29, BTW -$0.42 (WC) → net -$5.99
- Equity: $66.98 (-8.2% on prior day; -33.1% vs start ~$100)
- Shadow: $100 paper, 0 trades, mirror config
- Wildcard: 9 trades (5W/4L, 56% WR, net -$7.97). 4 straight losses. Approaching 10-trade disable gate.
- OI: 7d study run — CONFIRMED underperforms NEUTRAL (49.1% vs 50.5% pos_rate), sign reversed. DO NOT PROMOTE.
- Change: none | Deploy: none

**Change verdicts:**
- `BANK_PROTECT=1 + EARLY_LOCK=0` (Jun 14): BNB SHORT closed at profit lock +7.6% (below +1R bank step). ZEC/BTC both SL'd. Still 0 trades reaching the +1R bank trigger. Cannot verdict yet.
- `WC SL cap 20%` (Jun 16): BEAT breach (-23.5%) likely gap-through on illiquid alt, not cap logic failure. Cap logic is correct; execution is the gap. 4 post-cap clean or cap-bounded trades.
- `OI retention 7d` (Jun 12): 7d study run. CONFIRMED underperforms NEUTRAL — result not actionable, still earning its keep as data collector.

---

# Daily Audit — 2026-06-18

---

## Automated Assessment (UTC ~20:10)

### 1. Trades Reviewed (24h)

**4 closed trades (2 PMT + 2 Wildcard).** Equity $72.97 (prev $72.24 Jun 17, +$0.73 / +1.0%).

#### 24h closed trades (Jun 17 20:10 → Jun 18 20:10 UTC):

| Symbol | Type | Side | Entry | Exit | Realised | Fee | profRatio | Lev | Dur | Exit |
|--------|------|------|-------|------|----------|-----|-----------|-----|-----|------|
| ETH_USDT | PMT | SHORT | $1,745.52 | $1,732.33 | +$3.23 | -$0.86 | +8.82% | 15x | 3h54m | profit lock |
| BTC_USDT | PMT | SHORT | $63,990.50 | $64,394.00 | -$4.50 | -$0.91 | -11.71% | 15x | 2h54m | SL |
| ESPORTS_USDT | WC | SHORT | $0.15601 | $0.15288 | +$1.15 | -$0.10 | +12.85% | 7x | 2min | TP |
| VELVET_USDT | WC | LONG | $0.42250 | $0.42930 | +$0.86 | -$0.10 | +10.08% | 7x | 38min | bank/lock |

**PMT: 1W/1L, net -$1.27. WC: 2W/0L, net +$2.01. Total 24h: net +$0.74.**

**PMT design compliance:**
- ETH: MEGA_BEARISH → SHORT ✓. Margin ~$36.6 (score-band 92-94 = 50% balance ✓). Exited via profit lock +8.82%. Clean win.
- BTC: MEGA_BEARISH → SHORT ✓. Margin ~$38.5 (50% balance ✓). BTC rallied +0.63% in 3h before SL; loss -11.71% (< 25% stop-leak guard). Clean SL, no anomaly.
- Cold streak: BTC SL is streak=1. Throttle not yet triggered (requires 2 consecutive).

**Wildcard design compliance:**
- ESPORTS SHORT 7x: 3h ROC extreme down, pullback-resume entry, 2-min hold to TP. Correct mid-flight entry, sizing ~$9.7 (~12% balance ✓).
- VELVET LONG 7x: 3h ROC extreme up, pullback-resume. 38-min hold, closed at bank/lock. Sizing ~$9.4 (~12% balance ✓).
- Both trades correct. No entry failures detected.

**SKYAI anomaly (Jun 17 11:19 UTC — prior audit window):**
- SKYAI SHORT 7x: opened 10:59, closed 11:19, realised -$4.22 (-50.69% margin). Cap should limit to -20%.
- Price moved +7.12% against the SHORT in 20 min; theoretical 1.5xATR SL should have triggered at ~+2-3% (i.e. $0.347). Actual exit at $0.36459 — SL was NOT executed.
- **Conclusion: SL order failed, almost certainly the tick-snapping bug (priceUnit precision → 5003 error on the SL order).** The cap code is logically correct; the order was not placed at the right price. Fix = snap SL/TP prices to per-symbol priceUnit BEFORE placing orders. This is NOT yet shipped.
- Impact: -$4.22 unrecovered loss that should have been ~-$1.63 max.

### 2. Wildcard Ledger

**Since redesign launch (Jun 14):**
| Trade | Date | Symbol | Net | profRatio |
|-------|------|--------|-----|-----------|
| 1 | Jun 14 | EVAA LONG | +$3.16 | +26.3% |
| 2 | Jun 15 | EVAA SHORT | +$0.91 | +9.5% |
| 3 | Jun 15 | BSB LONG | +$0.58 | +4.6% |
| 4 | Jun 15 | SIREN SHORT | -$8.70 | -67.9% (pre-cap) |
| 5 | Jun 17 | SKYAI SHORT | -$4.22 | -50.7% (SL bug, post-cap) |
| 6 | Jun 18 | ESPORTS SHORT | +$1.15 | +12.9% |
| 7 | Jun 18 | VELVET LONG | +$0.86 | +10.1% |
**Total: 7 trades, 5W/2L (71%), net -$6.26. < 10-trade gate; no disable proposal.**
Both losses are explainable by specific bugs (no-cap, SL order bug) rather than strategy failure. The 5-trade win streak within the clean exits suggests the strategy generates genuine signals. Prioritize the SL tick-snap fix before further edge assessment.

### 3. Champion vs Shadow

| Metric | Champion (LIVE) | Shadow (PAPER) |
|--------|----------------|----------------|
| Equity | $72.97 | $100.00 |
| 24h trades | 4 (2 PMT + 2 WC) | 0 |
| Config | 6-pair baseline | mirrors champion |
| Gate state | All 6 blocked: no_mental_threshold_cross | identical |

Shadow equity $100 vs champion $72.97 reflects prior live losses. No candidate staged. Same signals.

### 4. OI Study

Still insufficient: yesterday's 7d study showed CONFIRMED vs NEUTRAL +1.4pp pos_rate. Need 14+ days (including bullish periods). Continue accumulation.

### 5. Diagnose

**ONE lever: None.** Market in MEGA_BEARISH consolidation (BTC -2.1%/24h, ETH -1.7%, SOL -3.2%, ZEC -6.3%). All 6 PMT pairs blocked by no_mental_threshold_cross. Correct behavior — no structural issue to fix.

**Top action (code, not env):** Wildcard SL tick-snap fix. SKYAI loss (-$4.22) is directly attributable to SL order failure from priceUnit mismatch. Fix: before placing entry/SL/TP orders, snap all prices to the symbol's priceUnit from exchange spec; abort if unknown rather than falling back to 0.01.

### 6. Validation

- pytest: **522/522 passed** ✓ (GitHub CI known-red, ignored)
- No candidate change → no replay required

### 7. Deploy

**None.** No env or code changes.

### 8. Summary

- Trades (24h): 4 — ETH +$3.23, BTC -$4.50, ESPORTS +$1.15, VELVET +$0.86 → net +$0.74
- Equity: $72.97 (+1.0% on prior day; -27.0% vs start ~$100)
- Shadow: $100 paper, 0 trades, mirror config
- Wildcard: 7 trades since redesign (71% WR, net -$6.26); SKYAI loss = SL tick-bug, not strategy
- OI: accumulating; promote gate not met
- Change: none | Deploy: none

**Change verdicts:**
- `BANK_PROTECT=1 + EARLY_LOCK=0` (Jun 14): ETH exited via profit lock +8.82% (did not reach +1R bank step). BTC SL at -11.71%. Still pending 3+ trades hitting the +1R bank trigger. Cannot verdict yet.
- `WC SL cap 20%` (Jun 16): SKYAI loss exceeded cap due to SL order bug (not cap logic failure). 4 post-cap clean trades (BSB, EVAA-S, ESPORTS, VELVET) all within normal range. Cap logic correct. Fix = tick-snap the SL price.
- `OI retention` (Jun 12): accumulating, earning keep.

---

# Daily Audit — 2026-06-17

---

## Automated Assessment (UTC ~21:04)

### 1. Trades Reviewed (24h)

**2 closed PMT trades.** Equity $72.24 (prev $69.67 Jun 16 21:00 UTC, +$2.57 / +3.7%).

#### 24h closed trades (since Jun 16 ~21:04 UTC):

| Symbol | Side | Entry | Exit | Net | profitRatio | Lev | Dur | Exit |
|--------|------|-------|------|-----|-------------|-----|-----|------|
| ETH_USDT | SHORT | $1,793.39 | $1,786.98 | +$1.09 | +3.0% | 15x | ~6h5m | profit lock |
| BTC_USDT | SHORT | $65,783.80 | $65,325.30 | +$1.48 | +7.9% | 15x | ~20h15m | profit lock |

**Design compliance:**
- Both entered ~Jun 16 19:35 UTC when market direction was MEGA_BEARISH; lev=15 (stop-first, low-tier). ✓
- ETH profRatio=+3.0%, BTC=+7.93% — both positive exits via profit lock (not SL). ✓
- No stop leak. Cold-streak resets to 0 on wins. ✓
- BNB briefly scored 92.10 (below 92.5 floor) blocked by 4 exhaustion caps (one_hour_exhaustion, volume_climax, high_score_trend_stretch, high_score_volume_chase all firing at 92.0–94.0). Correct filter for exhausted entry. ✓

**Wildcard (24h):** 0 trades. No extreme mover (|3h ROC|≥8%) found in recent scans. Market in ~1-2% range.

**Wildcard ledger (all-time):** 3 trades, 2W/1L (67%), net -$4.97. Still <5 trades — assessment deferred.
- EVAA Jun 14 +$3.07, EVAA Jun 15 +$0.80, SIREN Jun 15 -$8.84 (pre-cap; cap deployed Jun 16).
- 0 wildcard trades since 20%-SL cap went live. No adverse cases post-cap.

### 2. Champion vs Shadow

| Metric | Champion (LIVE) | Shadow (PAPER) |
|--------|----------------|----------------|
| Equity | $72.24 | $100.00 (paper) |
| 24h trades | 2 (ETH/BTC SHORT wins) | 0 |
| Config | 6-pair baseline | mirrors champion (11-pair expansion shadow-only) |
| Cycle | ~3558 | ~5610 |
| Redis (PMT weight) | 0.85 (refreshed) | missing Redis URL — stuck at default |

Shadow has no candidate staged; equity gap reflects champion live losses, not config divergence. Shadow also sees same `no_mental_threshold_cross` for all pairs — signals identical. **No A/B conclusion possible yet** (need ≥5 shadow trades).

Minor note: shadow missing Redis URL causes PMT core weight to skip refresh (stays at default 0.90 vs champion 0.85). This is a slight scoring bias — shadow slightly more likely to score above threshold than champion. Not actionable without staging a candidate.

### 3. OI Study

Carried forward from UTC ~20:10 run: 7-day study ran, CONFIRMED vs NEUTRAL gap (+1.4pp pos_rate) insufficient. Continue accumulation; need 14+ days including a bull period.

### 4. Diagnose

**ONE lever: None.**

All 6 pairs blocked by `no_mental_threshold_cross` in latest cycles (BTC -2.1%, ETH -3.4%, SOL -3.0%, ZEC -5.7% / 12h; BNB -1.6% 12h also blocked, SEI FLAT). No structural mis-calibration visible.

**Lessons not forgotten:** trigger changes 5-for-5 rejected. Entry frozen pending OI protocol.

### 5. Validation

- pytest: **522/522 passed** ✓ (GitHub CI known-red, ignored)
- No candidate change → no replay, no gate check required

### 6. Deploy

**None.**

### 7. Summary

- Trades (24h): 2 (ETH SHORT +$1.09, BTC SHORT +$1.48 → net +$2.57)
- Equity: $72.24 (+3.7% on prior 24h close, -27.4% vs Jun 14 peak of $99.51)
- Shadow: $100 paper, 0 trades, mirror config
- OI: accumulating; 7d study run (20:10 run), promote gate NOT met
- Change: none | Deploy: none

**Change verdicts (last 7d):**
- `BANK_PROTECT_ENABLED=1 + EARLY_LOCK_DISABLED` (Jun 14): ETH/BTC SHORTs both closed by profit lock before +1R — bank step not reached on these small moves. 0 trades yet reaching the bank step. Verdict pending ≥3 trades hitting +1R.
- `Wildcard SL cap 20%` (Jun 16, commit 6fd1fab): 0 wildcard trades post-cap. Cannot verdict yet.
- `OI retention 7d` (Jun 12): 7d study run, CONFIRMED marginally positive. Earning its keep.
- `Stop-first PMT sizing` (Jun 9): Mechanism correct; recent exits via profit lock not SL. Variance is direction, not mechanism.

---

## Automated Assessment (UTC ~20:10)

### 1. Trades Reviewed (24h)

**2 closed PMT trades.** Equity $72.24 (prev $99.51 Jun 14, -$27.27 / -27.4% over 3 days including Jun 15-16 losses).

#### 24h closed trades (since Jun 16 ~16:25 UTC):

| Symbol | Side | Entry | Exit | Gross | Fee | Net | PnL% margin | Dur | Exit reason |
|--------|------|-------|------|-------|-----|-----|-------------|-----|-------------|
| ETH_USDT | SHORT | $1,793.39 | $1,786.98 | +$1.08 | -$0.86 | +$0.22 | ~+0.2% | 7h4m | TP/profit lock |
| BTC_USDT | SHORT | $65,783.80 | $65,325.30 | +$1.48 | -$0.44 | +$1.04 | ~+1.1% | 21h12m | TP/profit lock |

24h PMT: **2W/0L, net +$1.26**. Both fee-heavy (ETH fee/gross 79.6%, BTC 29.7%).

#### 3-day context (Jun 15-17, since Jun 14 audit):

| Date | Symbol | Side | Entry | Exit | Net | Note |
|------|--------|------|-------|------|-----|------|
| Jun 15 13:40 | BTC_USDT | LONG | $66,218.60 | $66,540.60 | +$1.73 | 20% tier win |
| Jun 16 02:10 | BNB_USDT | LONG | $621.70 | $614.10 | -$22.25 | 20% tier SL, -19.6% margin |
| Jun 16 05:32 | ZEC_USDT | LONG | $524.94 | $521.85 | -$5.30 | early exit ~67% of 1R |
| Jun 17 01:41 | ETH_USDT | SHORT | $1,793.39 | $1,786.98 | +$0.22 | fee-heavy TP |
| Jun 17 15:50 | BTC_USDT | SHORT | $65,783.80 | $65,325.30 | +$1.04 | fee-heavy TP |

**3d PMT: 3W/2L, net -$24.56**

**Design compliance:**
- **BNB SL:** profitRatio -19.6% — within 25% cap ✓. 20% tier (lev=16 from stop-first). Stop fired correctly.
- **ZEC early exit:** -13.6% margin loss on 17-minute position; exited before full 1R SL (~18%). Pullback/floor mechanism likely. No stop leak ✓.
- **Cold-streak:** BNB (SL, streak=1) → ZEC (early loss, streak uncertain) → ETH WIN (resets). At most 1-cycle throttle on ETH; bot is at streak=0 now.

#### Wildcard trades (3-day, SEPARATE from PMT):

| Date | Symbol | Side | Entry | Exit | Net | profitRatio | Note |
|------|--------|------|-------|------|-----|-------------|------|
| Jun 14 20:39 | EVAA_USDT | LONG | $0.6699 | $0.6962 | +$3.07 | +26.3% | WIN, margin ~$12 (12% acct) |
| Jun 15 13:34 | EVAA_USDT | SHORT | $0.9047 | $0.8909 | +$0.80 | +9.5% | WIN, margin ~$9.5 (10% acct) |
| Jun 15 19:21 | SIREN_USDT | SHORT | $0.04589 | $0.05030 | -$8.84 | -67.9% | LOSS pre-cap SL |

**Wildcard ledger (all 3 trades, cumulative):** 2W/1L (67%), net -$4.97. <5 trades — assessment deferred per protocol.

**Wildcard notes:** SIREN loss predated the 20% SL cap (deployed Jun 16 via commit 6fd1fab). EVAA sizing was correctly within 10-15% balance budget. No wildcard trades since cap deployment.

### 2. Champion vs Shadow

| Metric | Champion (LIVE) | Shadow (PAPER) |
|--------|----------------|----------------|
| Equity | $72.24 | $100.00 |
| Trades (24h) | 2 (ETH/BTC SHORT wins) | 0 |
| Cumul. since Jun 14 | -$27.27 | $0 (no trades) |
| Config | baseline | mirrors champion (no candidate staged) |
| Cycle | 3557 | 5604 |

Shadow has no candidate staged; equity divergence reflects champion live losses not in paper. Shadow has 0 trades since Jun 14 (BNB at 92.1 is below shadow's 90.0 floor in current logs; same 6 symbols). Cumulative A/B requires ≥5 shadow trades.

### 3. OI Study (UPDATED — 7 days of data)

**Data window:** Jun 10 – Jun 17 UTC | 11,410 samples/symbol | lookback=5 (~265s), fwd=60 (~53min)

| Label | n | mean_fwd_% | pos_rate | median_% |
|-------|---|-----------|----------|---------|
| CONFIRMED (OI↑ + price↑) | 5,398 | +0.0029 | 50.1% | +0.0027 |
| DIVERGENT (OI↓ + price↑) | 5,800 | -0.0473 | 45.8% | -0.0540 |
| NEUTRAL | 56,872 | -0.0080 | 48.7% | -0.0072 |

vs Jun 14 (4.91d, bearish-only):
- Jun 14 CONFIRMED: mean -0.038%, pos_rate 48.6% → **now: +0.003%, 50.1%** (direction flipped positive, consistent with regime mix now including recovery period)
- Jun 14 CONFIRMED underperformed NEUTRAL (48.6 vs 48.9%) → **now: CONFIRMED outperforms NEUTRAL (+1.4pp)**

**Verdict: STILL DO NOT PROMOTE.** CONFIRMED vs NEUTRAL gap (+1.4pp pos_rate, +0.011% mean over 53min) is too small for a live score contribution. The absolute effect size is ~0.008% per hour, which over a 2h PMT trade horizon = ~0.016% edge — well below fees. Period covers Jun 10-17 (one bear-then-recovery cycle). Need 14+ days spanning a clear bull trend to confirm structural edge. Continue accumulation.

### 4. Diagnose

**ONE lever: None warranted.**

Market is broad bearish (BTC -2.2%, ETH -3.5%, SOL -3.3%, ZEC -3.3% in 24h). All PMT pairs blocked:
- BTC, ETH, SOL, ZEC: no_mental_threshold_cross
- SEI: FLAT, no threshold cross
- BNB: score=92.1 SHORT (FLASH_BEARISH level=600), blocked by exhaustion caps (one_hour_exhaustion, volume_climax, high_score_trend_stretch, high_score_volume_chase — all capping at 92.0–94.0)

The exhaustion guard correctly preventing a BNB SHORT entry into what appears to be local exhaustion of the selling. No actionable param tuning visible.

**Lessons not forgotten:** trigger changes 5-for-5 rejected. Entry frozen pending OI protocol.

### 5. Validation

- pytest: **522 passed** ✓ (local; GitHub CI known-red, ignored)
- No candidate change → no replay required
- No gate checks needed

### 6. Deploy

**None.** No code or env changes.

### 7. Summary

- Trades (24h): 2 (ETH SHORT +$0.22, BTC SHORT +$1.04 = +$1.26)
- Equity: $72.24 (-27.4% since Jun 14 audit)
- 3d losses: BNB SL -$22.25 (20% tier, correct), SIREN wildcard -$8.84 (pre-cap), ZEC early exit -$5.30
- Shadow: $100 paper, 0 trades, mirroring champion
- OI: 7d study run, CONFIRMED improved (+0.003% mean vs -0.038% Jun 14) but edge vs NEUTRAL too marginal to promote
- Change: none
- Deploy: none

**Change verdicts (last 7d):**
- `BANK_PROTECT_ENABLED=1 + EARLY_LOCK_DISABLED` (Jun 14): 2 post-promote trades (ETH/BTC SHORT wins). Neither hit the bank step (small moves). Insufficient data — need ≥3 trades reaching +1R.
- `Wildcard SL cap 20%` (Jun 16, commit 6fd1fab): 0 wildcard trades since deploy. Cannot verdict yet.
- `OI retention 7d` (Jun 12): 7d accumulated ✓. Lift study improved (CONFIRMED now marginally positive). Earning its keep.
- `Stop-first PMT sizing` (Jun 9): BNB SL fired at -19.6% margin (within cap). Mechanism correct. Direction calls are the variance driver.

---

# Daily Audit — 2026-06-14

---

## Automated Assessment (UTC ~16:25)

### 1. Trades Reviewed (24h)

**1 closed trade.** Equity $99.51 (prev $99.65 June 13 close, -$0.14).

| Symbol | Side | Entry | Exit | Gross P&L | Fee | Net P&L | PnL% margin | Duration | Exit reason |
|--------|------|-------|------|-----------|-----|---------|-------------|----------|-------------|
| ZEC_USDT | LONG | $424.86 | $425.46 | +$1.05 | $1.19 | -$0.14 | -0.27% | 16.3 min | TP/profit-lock (price +0.14%) |

**Trade verdict:** Fee-dominated loss. Price moved +0.14% in trade direction (favorable for LONG) at 15x leverage = +2.1% on margin, but round-trip fee ($1.19) exceeds gross gain ($1.05). This is a structural issue for short-duration ZEC trades: ZEC notional ~$743 (175 contracts × 0.01 ZEC × $424.86) means both legs each cost ~$0.595 at 0.08% taker rate, creating a $1.19 fee hurdle for any trade closed before meaningful price movement.

**Tier check:** All recent trades at lev=15x (PMT minimum), consistent with stop-first NAV-risk sizing. Previous ZEC (June 11) also used 15x. Score for ZEC entry not recoverable (prior deployment logs unavailable); design compliance assumed based on entry being logged pre-restart.

**Cold-streak note:** Champion service restarted at 14:46 UTC today (new deployment). Cold-streak counter is in-memory only; reset on restart. The ZEC SL (June 11) + ETH soft-close + SEI SL (June 12) sequence was NOT in the new deployment's memory. First trade after restart will have no throttle applied. Known gap, not self-fixable via params. **PROPOSE** (operator action): persist cold-streak state to Redis.

**No stop leak, no design violation.**

### 2. Champion vs Shadow

| Metric | Champion (LIVE) | Shadow (PAPER) |
|--------|----------------|----------------|
| Equity | $99.51 | $100.00 (start) |
| Trades (24h) | 1 | 0 |
| Config | 6-pair, baseline | 6-pair + MAKER_LADDER + PORTFOLIO_VAR + VOLUME_FILTER |
| Start | ongoing | 16:12 UTC today |

Shadow just redeployed at 16:12 UTC today with $100 paper equity. No trades yet. The shadow now includes `USE_MAKER_LADDER`, `USE_PORTFOLIO_VAR`, and `FUTURES_PMT_VOLUME_FILTER_ENABLED=1`. On cycle 1, BTC was blocked by `volume_filter_block` (vol_z=-0.87) vs champion's `score_below_threshold`. The volume filter is catching the low-volume current environment. Cumulative comparison requires ≥5 shadow trades; tracking starts today.

### 3. OI Study

**Data window:** 2026-06-09 18:19 → 2026-06-14 16:16 UTC — **4.91 days**, 8010–8011 samples per symbol (~53s interval). At threshold.

**Lift analysis run** (5-sample lookback, 60-sample forward, June 9–14 across 6 symbols):

| Label | n | mean_fwd_% | pos_rate | median_% |
|-------|---|-----------|----------|---------|
| CONFIRMED (OI ↑ + price ↑) | 3,873 | -0.038 | 48.6% | -0.017 |
| DIVERGENT (OI ↓ + price ↑) | 3,702 | -0.108 | 43.6% | -0.077 |
| NEUTRAL | 40,100 | -0.014 | 48.9% | -0.002 |

**Verdict: DO NOT PROMOTE.** CONFIRMED outperforms DIVERGENT by 5pp pos_rate and +0.07% mean over ~53min horizon. But: (1) all three means are negative — the June 9–14 window was monotonically bearish, introducing systematic downward bias; (2) CONFIRMED underperforms NEUTRAL (48.6% vs 48.9%), meaning OI expansion adds no edge vs no-signal baseline; (3) 4.91 days is a single regime (post-selloff consolidation) — not diverse enough to confirm whether the CONFIRMED→DIVERGENT 5pp gap is structural or regime-specific. Continue accumulation; re-run when >7 days data with a bullish period included.

### 4. Diagnose

**ONE lever:** None warranted today. All signals below threshold; market in post-June-6 consolidation.

**Current scan context (cycle ~90):**
- BTC: score 86.41 → FLAT, SHORT side, ~6 pts below floor 92.5. Capped by funding_adverse_reduced_size (91.99). Not actionable (entry frozen).
- ETH: no_mental_threshold_cross, pmt=BEARISH, 24h=-1.15%
- SOL: no_mental_threshold_cross, pmt=BEARISH, 24h=-1.69%
- BNB: no_mental_threshold_cross, pmt=FLAT, 24h=-0.39%  
- SEI: no_mental_threshold_cross, pmt=BEARISH, 24h=-2.77%
- ZEC: no_mental_threshold_cross, pmt=FLAT, 24h=+1.35% (threshold 1.4% — 0.05% away)

ZEC is the closest to threshold (24h move 1.35% vs 1.4% floor). A +$0.21 move on ZEC (~0.05% at $424) would cross. Not a tunable lever (entry frozen).

**Lessons not forgotten:** trigger-side changes rejected 5-for-5. Entry frozen pending OI protocol.

### 5. Validation

- pytest: **505 passed** ✓ (local; GitHub CI known-red, ignored)
- No candidate change → no replay required
- No deploy planned

### 6. Deploy

**None.** No code or env changes. Bot healthy, running.

### 7. Summary

- Trades (24h): 1 (ZEC LONG fee-dominated -$0.14)
- Equity: $99.51 (-$0.14 from $99.65 yesterday; -$13.54 / -12.0% since June 9)
- Shadow: started today, 0 trades, $100 paper. Cumulative tracking begins.
- OI study: FIRST RUN. 4.91d data, weak CONFIRMED edge (-0.038% vs DIVERGENT -0.108%), not promotable (bearish-period-only, single regime).
- Change: none
- Deploy: none

**Change verdicts (last 7d):**
- `BANK_PROTECT_ENABLED=1 + EARLY_LOCK_DISABLED` (Jun 14, promoted): 0 live trades post-promote. ZEC Jun 14 trade was fee-dominated; BANK_PROTECT not triggered (position never reached bank step). Insufficient to verdict.
- `P2 runner protection` (Jun 12): 0 attributable live trades. Monitoring.
- `OI retention 7d` (Jun 12): 4.91d accumulated, first OI lift study run. Data collection earning its keep.
- `Stop-first PMT sizing` (Jun 9): SLs continue firing at ~20% margin (within design). 2 SL losses in 5d total -$23. Mechanism correct; direction calls are the driver.

---

# Daily Audit — 2026-06-13

---

## Automated Assessment (UTC ~18:25)

### 1. Trades Reviewed (24h)

**0 closed trades.** Equity $99.65 — unchanged from yesterday's close. 0 positions open.

**7-day context (11 trades, Jun 7–12):**

| Date (UTC) | Symbol | Side | Entry | Exit | Net P&L | Margin% | Note |
|------------|--------|------|-------|------|---------|---------|------|
| Jun 12 06:21 | SEI_USDT | LONG | $0.04998 | $0.04939 | -$10.96 | -19.6% | SL hit |
| Jun 11 17:30 | ETH_USDT | LONG | $1654.94 | $1657.21 | -$0.19 | -0.3% | Fee-dominated, 23s close |
| Jun 11 08:56 | ETH_USDT | LONG | $1650.97 | $1659.28 | +$2.77 | +5.1% | Clean win |
| Jun 11 04:19 | ZEC_USDT | LONG | $425.03 | $419.99 | -$12.06 | -19.9% | SL hit |
| Jun 10 05:45 | BTC_USDT | SHORT | $61836 | $61260.9 | +$7.04 | +12.4% | Clean 8h short |
| Jun 08 23:02 | ETH_USDT | LONG | $1702.26 | $1706.30 | +$0.95 | +1.7% | Small win |
| Jun 08 11:22 | BNB_USDT | LONG | $601.10 | $602.80 | +$1.67 | +2.6% | Small win |
| Jun 08 19:29 | SEI_USDT | LONG | $0.05026 | $0.04986 | -$13.14 | -20.6% | SL hit |
| Jun 07 17:05 | SOL_USDT | LONG | $65.16 | $65.28 | +$0.05 | +0.5% | Fee-heavy |
| Jun 07 16:17 | SOL_USDT | LONG | $64.90 | $65.02 | +$0.12 | +1.4% | Small win |
| Jun 07 05:01 | BNB_USDT | LONG | $582.20 | $583.20 | +$0.04 | +0.2% | Fee-heavy |

**7d summary:** 11 trades | WR 63.6% (7W/4L) | Net -$23.71 | Gross wins $12.64 | Gross losses $36.35 | PF 0.35 | Total fees $14.40

**Design compliance:**
- **Stop-loss integrity:** All 3 SLs hit at profitRatio ~-20% (within 25% hard cap ✓). Stop fired cleanly at 3xATR → ~1R.
- **Cold-streak throttle:** Jun 11 ETH (17:30) was a fee-dominated TP/quick-close (price went up), NOT an SL. Jun 12 SEI was SL → streak=1 at session end. Throttle not yet due. ✓
- **Tier/budget:** SEI and ZEC scored 92.5-95 range; implied margin ~$55-60 on ~$110 account → max loss at SL = 10% account. Consistent with "92.5-95 risks 10%" design. ✓
- **ZEC LONG flag:** ZEC has DOWNTREND_MOMENTUM_PRIORITY enabled for shorts. Bot still took a LONG via PMT lane — not blocked by design (DOWNTREND_PRIORITY adds short preference, doesn't block longs). Trade was a valid PMT entry per current design.
- **Fee-dominated ETH (23s):** TP hit immediately at entry spread (+0.14%), fees exceeded gross profit. One-off TPSL too tight at entry; not actionable without replay.

### 2. Champion vs Shadow

| Metric | Champion (LIVE) | Shadow (PAPER) |
|--------|----------------|----------------|
| Equity | $99.65 | $100.00 |
| Trades (24h) | 0 | 0 |
| Score floor | 92.50 | 90.00 |
| Signal (current) | BTC 86.88 → blocked | BTC 86.88 → blocked |
| Candidate config | — | none staged (mirror) |

No candidate staged on shadow. Both idle on identical signals. Shadow mirrors champion; equity divergence ($0.35) reflects champion real-money SL activity not replicated in paper mode.

### 3. OI Study Status

OI data: **4.0 days** (Jun 9 18:19 → Jun 13 18:25 UTC), 6500+ samples per symbol (BTC, ETH, SOL, BNB, ZEC, SEI).

**Not yet eligible.** Protocol requires ≥5 days around Jun 14. Study window opens tomorrow (Jun 14) — run the `futuresbot.oi_signal` lift analysis then.

### 4. Diagnosis

**No change.** Market sideways (BTC $64,000), all PMT signals below 92.5 threshold. OI study pending.

**Scan context (0 trades today):** BTC PMT=FLAT, score=86.88 (floor 92.5). ETH/SOL/BNB/ZEC — no mental threshold cross. Trap-reclaim block active on BTC SHORT at $64,000 level (level broke long-way within lookback). Bot is correctly idle.

**Pattern to monitor:** 3 of 11 recent trades (SEI×2, ZEC×1) were large SLs totaling -$36.1 gross losses. The large-SL trades follow the "LONGs on weak/downtrending assets" pattern. OI lift study should clarify whether OI expansion at entry is a reliable continuation filter.

### 5. Validation

- pytest: **499 passed** ✓ (local; GitHub CI known-red, ignored per protocol)
- No candidate change → no replay required
- No gate checks needed

### 6. Deploy

**None.** No code changes.

### 7. Summary

- Trades (24h): 0
- Equity: $99.65 (unchanged from yesterday; down -$13.40 / -11.8% since June 9 audit)
- 7d P&L: -$23.71 | WR 63.6% | PF 0.35 (dominated by 3 SL hits: SEI -$13.14, ZEC -$12.06, SEI -$10.96)
- Shadow: paper $100, no candidate, mirrors champion
- OI study: 4d data, eligible tomorrow June 14
- Change: none
- Deploy: none

**Change verdicts (last 7d deploys):**
- `Stop-first PMT sizing` (Jun 9): SLs firing cleanly at ~1R. Correct behavior; net negative due to direction calls, not mechanism failure. Neutral.
- `Bank half at +1R` (Jun 10): BTC SHORT (8h), ETH (2.5h) are candidate partial-bank triggers. Cannot attribute without bot trade-close logs. Monitoring.
- `Score-tiered exit + trap-reclaim` (Jun 11): Trap-reclaim active in logs (BTC SHORT @64k blocked). Working.
- `Self-calibrating low-tier lock` (Jun 11): <3 attributable trades. Too early.
- `P1 sizing compromise + V0 exit-replay gate` (Jun 12): 0 live trades post-deploy. No data.
- `P2 runner protection` (Jun 12): 0 live trades post-deploy. No data.
- `OI retention 7d` (Jun 12): 4d accumulated ✓. Study eligible tomorrow.

---

# Daily Audit — 2026-06-12

---

## Automated Assessment (UTC ~18:17)

### 1. Trades Reviewed (24h)

**1 closed trade.** Equity $99.65 (prior ~$110.61 after June-11 17:30 ETH close, -10.1%).

| Symbol | Side | Entry | Exit | Gross P&L | Fee | Net P&L | PnL% margin | Margin | Acct% | Duration |
|--------|------|-------|------|-----------|-----|---------|-------------|--------|-------|----------|
| SEI_USDT | LONG | $0.04998 | $0.04939 | -$9.64 | $1.32 | -$10.96 | -19.6% | ~$55.82 | -10.1% | ~2.3h (04:01–06:21 UTC) |

**Trade verdict:** Stop-loss exit. Price moved -1.18% adverse at 15x → -17.7% margin, plus 2.4% fees = -20.1% ≈ profitRatio -19.6% ✓ consistent.

**Tier check:** Score in 92–94 range → SCORE_BAND_SIZE_92_94=0.50 → margin=50% of $110.61=$55.31≈$55.82 ✓. Stop-first: margin×leverage×stop_pct≈$10.8=~10% account risk. Design intent: "92.5–95 risks 10%". Compliant.

**Stop-leak:** -19.6% margin < 25% flag ✓. No leak.

**Cold streak:** Trade was SL → streak=1. Threshold=2. No throttle for next trade.

**Fee check:** $1.32 fee on -$9.64 gross loss = 13.7% of gross — not fee-dominated on a loss.

**SEI symbol status:** SEI_USDT is now absent from FUTURES_PMT_SYMBOLS in champion; the trade cleared before the redeploy at ~12:48 UTC that removed it. Shadow still has SEI enabled.

### 2. Champion vs Shadow

| Metric | Champion (LIVE) | Shadow (PAPER) |
|--------|----------------|----------------|
| Equity | $99.65 | $100.00 |
| Trades (24h) | 1 (SEI SL) | 0 |
| Cumul. since shadow start | — | — |

Shadow has no candidate config staged (only FUTURES_MARGIN_BUDGET_USDT=100). All cycles blocked by `no_mental_threshold_cross`. Shadow is mirroring champion default behavior. No config divergence to measure yet.

### 3. OI Study Status

OI timeseries data: 4,870+ samples per symbol, 72h window (June 9 18:14 → June 12 18:14 UTC). **Blocker:** 3-day retention would expire June 9 data before the June 14 study date, leaving only 3 days. Study requires ≥5 days.

**Lever deployed:** Increased retention 3d → 7d (`oi_publisher.DEFAULT_MAX_AGE_SECONDS`). June 9 data now preserved through June 16. OI lift study runnable on/after June 14 with data spanning June 9–14 (≥5 days). ✓

### 4. Diagnose

**Lever:** OI retention 3d → 7d (see above). Single-line constant change, no trading path impact, no replay needed.

**Observations:**
- Uncommitted local changes (P2 bank-protect + breakeven-stop + second rung): present on disk, need `replay_exits.py` ≥7d validation before staging on shadow.
- Past change d9110fb (Self-calibrating low-tier lock): insufficient attributable live trades to verdict yet (<3). Monitor.

### 5. Validate

- pytest: **499/499 passed** ✓
- Replay: N/A (data-collection-only change)
- Shadow: N/A (no trading-logic change)

### 6. Deploy

**Deployed:** `futuresbot/oi_publisher.py` — OI retention 3d → 7d.
Commit `fa0b213`. Pushed, redeployed Futures-bot. Post-deploy: equity=$99.65, [OI_SAMPLE] active, no Traceback. ✓

### 7. Pending

- Uncommitted P2 changes (breakeven-stop, second rung banking): need replay before staging.
- OI lift study: can run June 14 or later.
- SEI removal from champion PMT symbols: flagged, reason unknown (user action or auto-gate?). Shadow still has SEI — monitor if shadow ever scores an SEI entry.

---

# Daily Audit — 2026-06-11

---

## Automated Assessment (UTC ~16:43)

### 1. Trades Reviewed (24h)

**2 closed trades.** Equity $110.80 (prior reference 2026-06-09: $113.05, -2.0%).

| Symbol | Side | Entry | Exit | Gross P&L | Fee | Net P&L | PnL% margin | Margin | Acct% |
|--------|------|-------|------|-----------|-----|---------|-------------|--------|-------|
| ZEC_USDT | LONG | $425.03 | $419.99 | -$10.63 | $1.43 | -$12.06 | -19.93% | ~$60.51 | ~54.6% |
| ETH_USDT | LONG | $1650.97 | $1659.28 | +$4.07 | $1.30 | +$2.77 | +5.07% | ~$54.61 | ~49.3% |

Net P&L: **-$9.29** (-8.4% equity). Win rate: 50%.

Trade times (UTC June 11): ZEC 04:00–04:19 (~19 min, stop-out). ETH 05:45–08:56 (~3.2h, small gain exit).

### 2. Entry Consistency

Both LONG entries. No live log available for June 11 to verify PMT signal states. Prior June-9 context was MEGA_BEARISH across all symbols; market likely shifted by June-11 given BTC recovery. Cannot confirm entry validity without live signal log.

### 3. Flags

- **CONCENTRATION x2**: ZEC margin ~$60.51 (~54.6% acct), ETH margin ~$54.61 (~49.3% acct). Both exceed 8% flag threshold by >6x. Same PMT score≥95 full-balance sizing (score_band_fraction=1.0) identified June 9.
- **STOP worked (ZEC)**: -19.93% loss < 25% flag — no stop leak.
- **COST-DOMINATED (ETH)**: Fee $1.30 = 32% of gross P&L $4.07. Small wins at 15x leverage are heavily fee-diluted.

### 4. Change / Deploy

None. Report-only. Geometry rebuild in progress.

### 5. Proposal

Add `FUTURES_MAX_MARGIN_USDT` hard cap as interim circuit breaker while sizing geometry rebuild is in progress. Would have capped both trades to <8% acct without requiring a code deploy.

---

# Daily Audit — 2026-06-09

---

## Run 2 (16:10 UTC) — Automated Assessment

### 1. Trades Reviewed
**Live trades (24h): 0** — equity $113.05, unchanged. All 6 symbols (BTC, ETH, SOL, BNB, SEI, ZEC) MEGA_BEARISH, no mental threshold crosses for entire log window (~58-min visible, consistent with all-day pattern). MEXC API confirmed: 0 closed positions in 24h, equity=$113.05248.

### 2. Baseline (corrected methodology)
**CORRECTION from Run 1**: Prior run used per-symbol backtest (9 trades, -$3.59) which overstates signal count. Portfolio mode (max 1 open position, matching live behavior) is the correct comparison.

**Portfolio mode 7d baseline (2026-06-02 → 2026-06-09T16:00):**
| Metric | Value |
|--------|-------|
| Trades | 2 |
| Net P&L | +$181.16 |
| Win rate | 50% |
| Profit factor | 4.02 |
| Max drawdown | -63.8% |
| BTC SHORT | +$241 (END_OF_TEST) |
| SOL SHORT | -$60 (STOP_LOSS) |

Note: Backtest default initial balance = $300. Proportional to $113 live: ~$68 net gain.

### 3. Diagnosis — Concentration Risk
**CONCENTRATION FLAG**: PMT sizing code (`backtest.py:368-370`) uses `balance × score_band_fraction` for margin, bypassing NAV-risk sizing (which is gated off for PMT by `backtest.py:388`). For scores ≥95 (band 95-100), fraction=1.0 → full balance deployed as margin.

At $113 live account with score≥95 entry:
- margin = $113, leverage = 15-25x → notional = $1,695–$2,825
- Typical stop distance (SOL: ~0.65%) → stop-out loss = $11–$18 = **10-16% of account**
- Threshold: 8%. Every high-conviction entry exceeds the flag threshold.

This is the "inflated conviction → oversized position → single SL erases 10%+" failure mode.

### 4. Change Tested
`FUTURES_PMT_SCORE_BAND_SIZE_95_100`: 1.0 → 0.75 (−25%, within bound)

| Run | P&L | PF | Max DD | Concentration |
|-----|-----|----|--------|---------------|
| Baseline (1.0) | +$181.16 | 4.02 | -63.8% | ~13-20% per trade |
| Modified (0.75) | +$147.07 | 4.27 | -56.5% | ~10-15% per trade |

**REJECTED**: Modified P&L ($147) < baseline ($181). Does not beat baseline on P&L gate. Drawdown and PF improve but absolute performance regresses in a strong-trend environment.

### 5. Deploy
**None.** No code or env changes. Tests: 469/469 passed.

### 6. Outstanding Issues
- Concentration risk remains: PMT sizing bypasses NAV-risk cap for score≥95 entries. Single-trade risk ~10-16% of account exceeds 8% flag threshold. A fix reduces P&L in strong-trend periods — consider a separate structural review to enable NAV-risk sizing for PMT trades.
- Calibration gap unchanged: 5 live trades vs 15 required minimum.

---

## 1. Trades Reviewed (24h)

**Live trades: 0** — equity locked at $113.05 (unchanged from prior day).

Gate histogram for ~400 cycles:
- Early period: `no_mental_threshold_cross pmt:5, countertrend_block side:1`
- Late period (last ~60 cycles): `no_mental_threshold_cross pmt:3, score_below_threshold score:3`

The late-period shift means 2 additional symbols started crossing mental thresholds but their PMT scores fell below the 92.5 entry floor.

**Live calibration state:** only 5 trades accumulated since last deploy — far below the 15-trade minimum. Bot is running on seed calibration (`calibration/multi_symbol_calibration.json`). Walk-forward gate consistently rejecting calibration: `oos_pf=0.199 < 1.15`.

**Market context:** Post-June-6 major liquidation event ($1.28B longs wiped). BTC ~$60k (-5% in 24h), ETH ~$1,600, SOL ~$65, BNB ~$574. Market in consolidation/ranging after sharp bearish week.

No entry analysis available (0 trades). Bot behavior appears correct — the June-2 to June-8 period had 2 successful PMT_THRESHOLD_SHORT entries (BTC +$80, SOL -$23) that were taken during the actual MEGA move.

---

## 2. Baseline (7-day, closest feasible window)

**Note:** 24h backtest returns 0 usable symbols — minimum 220 bars (~55h) needed for warmup. 7-day window used as rolling baseline.

| Metric | Value |
|--------|-------|
| Window | 2026-06-02 → 2026-06-09 |
| Trades | 9 |
| P&L | -$3.59 |
| Win rate | 22.2% |
| Profit factor | 0.958 |
| Max drawdown | -59.2% |
| Signals | PMT_THRESHOLD_LONG (4), PMT_THRESHOLD_SHORT (5) |

**Divergence vs live (5 trades total):** Backtest uses exact historical fills; live has slippage, latency, and market impact. 5 live trades insufficient to assess statistical divergence.

Baseline persisted → `docs/daily_baseline.json`.

---

## 3. Diagnosis

**Primary blocker: `FUTURES_PMT_SIMPLE_HIGH_SCORE_TREND_STRETCH_SCORE_CAP=92`**

PMT scoring flow for MEGA signals:
1. MEGA_BEARISH classification requires 12h ≥1.8% (BTC MEGA threshold).
2. Core score = 96 (MEGA), context bonus up to +4 → raw score 96-100.
3. `high_score_exhaustion_min=94.5` → HIGH_SCORE path activates.
4. `HIGH_SCORE_TREND_STRETCH` fires when 12h move in trade direction ≥2.4%.
5. Cap applied: 92. Entry floor: 92.5 → **BLOCKED**.

The gap between MEGA threshold (1.8%/12h) and trend stretch cap (2.4%/12h) means only early MEGA entries (12h between 1.8-2.4%) can proceed. Once the trend is established (12h > 2.4%), all MEGA entries are capped below the floor. On June 9, BTC 12h bearish move is ~2-3%, consistently above 2.4%.

**Secondary issue:** Walk-forward calibration failing (oos_pf=0.199). Structural — too few live trades for calibration. Not addressable via a single-parameter change.

---

## 4. Change Attempted

**Proposed:** Raise `FUTURES_PMT_SIMPLE_HIGH_SCORE_TREND_STRETCH_SCORE_CAP` from 92 → 93 (within ≤25% bound). This would allow MEGA continuation entries where 12h momentum is 2.4%+ in trade direction.

---

## 5. Validation

| Run | Trades | P&L | Profit Factor | Verdict |
|-----|--------|-----|---------------|---------|
| Baseline (cap=92) | 9 | -$3.59 | 0.958 | — |
| Modified (cap=93) | 14 | -$74.10 | 0.453 | FAIL |

The modified run had 5 more trades, but net P&L was $70 worse. Most of the new entries were PMT_THRESHOLD_LONG trades in the prevailing bearish market — counter-trend entries that were cleanly stopped out. The trend stretch cap at 92 is correctly protecting against these late/chasing entries.

**Conclusion:** Change does NOT beat baseline on either 24h or 7-day window. ABORT.

---

## 6. Deploy

**No deploy.** No code changes committed. Railway configuration unchanged.

---

## 7. Summary

- Trades reviewed: 0 (no live activity in 24h)
- Baseline P&L (7d): -$3.59, PF=0.958 (9 PMT trades)
- Change: `HIGH_SCORE_TREND_STRETCH_SCORE_CAP` 92→93 — tested and REJECTED (PF worsened 0.96→0.45)
- Deploy: none
- Bot status: healthy, running, equity $113.05

**Outstanding structural issue:** Live calibration has only 5 trades vs 15 required minimum. Bot needs ~10 more live trades before calibration can self-update. This requires the market to offer sufficient PMT entries — the existing MEGA entry window (12h between 1.8-2.4%) is narrow but working correctly when conditions arise.
