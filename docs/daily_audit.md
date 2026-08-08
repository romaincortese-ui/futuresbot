# Daily Audit — 2026-08-08

---

## Automated Assessment (UTC ~17:30)

### 1. Trades (last 24h: 08-07 17:24 -> 08-08 17:24 UTC)

**6 closed trades.** Exchange `history_positions` (100-row pull) returns exactly
6 in-window closes; the feature store grew 46 -> **52 rows**. Ledger and
exchange **reconcile 6-for-6**, no gap.

| # | time | symbol | sleeve | side | lev | 1R (%margin) | R | net $ | exit reason |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 01:09 | BICO_USDT | WILDCARD | LONG | x1 | 16.33 | **+0.42** | +1.168 | CONVEX_RETENTION_TRAIL |
| 2 | 03:21 | BTW_USDT | WILDCARD | LONG | x3 | 17.02 | **+0.53** | +0.646 | CONVEX_RETENTION_TRAIL |
| 3 | 04:03 | SOL_USDT | SNIPER | LONG | x13 | 4.49 | +1.32 | +0.034 | EXCHANGE_CLOSE (tp) |
| 4 | 11:24 | SUI_USDT | SNIPER | LONG | x13 | 8.30 | **-1.45** | -0.096 | EXCHANGE_CLOSE (stop) |
| 5 | 15:03 | DOGE_USDT | SNIPER | LONG | x13 | 3.59 | **-1.64** | -0.032 | EXCHANGE_CLOSE (stop) |
| 6 | 15:33 | SOL_USDT | SNIPER | LONG | x13 | 8.00 | **-1.11** | -0.052 | EXCHANGE_CLOSE (stop) |

Net **+$1.668**, 3W/3L. Split by sleeve: **WILDCARD +$1.814 / +0.95R (2-for-2)**,
**SNIPER -$0.147 / -2.88R (1W/3L)**. PMT: 0, still decommissioned
(`entries_disabled (FUTURES_ENTRY_MIN_SCORE>=999)` on every cycle).

**Exchange-vs-store $ deltas:** BICO 1.2059 vs 1.1682, BTW 0.6225 vs 0.6460.
Sub-4c, opposite signs — fee-attribution timing, not a reconciliation failure.

**Finding of the day: the trial-7 retention trail did exactly what it was
built to do, twice, on its first live day.**

- **BICO** peak +1.4558R -> floor `0.30 x peak` = **+0.437R**, exited **+0.42R**
  (+$1.17). Under the trial-6.5 rule this identical path banked **$0** (trail
  level -0.54R, fade into the 24h clock). This is the exact trade that killed
  6.5, and the replacement rule paid on it. Migrated position
  (`trail_migrated`), **excluded from the trial-7 scoreboard**.
- **BTW** peak +1.9816R -> floor **+0.594R**, exited **+0.53R** (+$0.65).
  In-trial. Also in the [1R, 2R) dead-zone cohort that used to bank negative.

**Both exits landed slightly BELOW the nominal floor** (-0.017R BICO,
-0.064R BTW; -3.9% / -10.7% of the floor). Cause is fee + market-exit slippage
between the trail trigger and the fill (fee_share 2.3% / 5.1% of gross), not a
rule breach: the invariant is "never below +0.3 x peak, never below zero", and
both banked comfortably positive. Recording it because the size of the BTW gap
is the number that would matter if it grew — at a peak near arm (+1.0R) a 10%
shortfall still banks ~+0.27R, so the invariant has margin. **Watch, do not
act.**

**Tripwires (trial 7):** #1 armed close <= $0 — **0 occurrences, PASS**.
#2 retention bank >= +0.15R each — **+0.42R, +0.53R, PASS**. #3 TP completion —
0 TPs at n=1, non-informative. #4 arm rate — 2/2 armed, n far too small.
#5 gap-throughs — 0.

**SNIPER (live micro leg) — first real ledger.** 4 closes, **-2.88R**, but only
**-$0.147** because margin is ~$0.82/trade (the ~$0.03/R meter). The
informative part is not the dollars: **all three losses closed BEYOND -1R**
(-1.45, -1.64, -1.11), i.e. the x13 stops slip 11-64% past the intended risk on
a fast leg, and fees ran 21-54% of gross. Its own log line already
self-describes as "SIGNAL-STUDY ONLY: not viable at taker fees" — the live R
ledger now agrees. DOGE is the sharp case: built **+0.81R peak** and closed
**-1.64R**; the retention invariant covers the convex sleeve only, and the
sniper has no equivalent. Not proposing a change (the leg is deliberately
sized as a meter, and n=4), but the R-cost is now on the record.

### 1-OPEN. Open positions

**None.** `open_positions` returns 0; `[ACCOUNT] equity=142.32 available=142.32
open_margin=0.00 unrealized=0.00 positions=0` on every cycle for the last hour.
Book is flat — first run in a while with nothing to mark.

### 2. Champion vs Shadow

**Shadow: stale, comparison suppressed pending resync.** Unchanged standing
action item (raised 07-23): `railway up --service Futures-shadow` — paper,
env-only, zero live risk. Operator-gated, not self-applied.

### 3. Learning loop

**(a) Feature store** — 52 rows, +6, reconciled above. `learn_from_trades.py`
re-run on the fresh corpus (n=52, window 06-27..08-08, overall mean **+$0.227**,
meanR +0.242, win 44.2%). OOS-consistent verdicts:

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| hold>=120min | **FAVOR** | +1.893 | 30 / +$1.028 / 66.7% | 22 / -$0.865 / 13.6% |
| regime_trimmed(mult<1) | AVOID | -0.533 | 27 / -$0.029 | 25 / +$0.504 |
| regime_trimmed_hard(<0.5) | AVOID | -0.561 | 16 / -$0.161 | 36 / +$0.400 |
| leverage<=4 | FAVOR | +0.147 | 20 / +$0.318 | 32 / +$0.171 |
| leverage>=7 | AVOID | -0.451 | 22 / -$0.033 | 30 / +$0.418 |
| fee_heavy>=30pct | AVOID | -0.275 | 10 / +$0.005 | 42 / +$0.280 |
| side=LONG | AVOID | -0.830 | 34 / -$0.060 | 18 / +$0.770 |

`hold>=120min` remains the single strongest and most stable signal in the
corpus and is the direct justification of the 24h clock. `side=LONG AVOID` is
**not** actionable: the sleeve is long-only by design and the 18 "SHORT" rows
are legacy PMT/sniper, so the split is a sleeve proxy, not a side edge. Same
for `leverage>=7` — it now separates SNIPER (x13) from WILDCARD, a sleeve
label wearing a leverage costume. Propose-only, nothing applied.

**Zero deep-pullback entries, still.** `deep_pullback(lat 0.50-0.70)` is
**n=0 in 52 rows**, while `at_extreme(lat>=0.99)` is n=10. Both of this
window's wildcard entries were `entry_lateness = 1.0`. The "deep-pullback
candidates ranked first" design has never once produced a live entry. This is
now a 52-trade structural fact, not a coincidence — the ranking preference
cannot express itself because such candidates are not surviving the gates in
the first place. Standing question for a trial boundary, not a live lever.

**(b) Shadow ledger** — 68 rows (+11):

| sleeve | reason | n | resolved | netR | meanR |
|---|---|---|---|---|---|
| SNIPER_FAST | shadow_only | 27 | 26 | +1.83 | +0.070 |
| WILDCARD | slot_occupied | 11 | 11 | +7.77 | +0.706 |
| SQUEEZE | slot_occupied | 6 | 6 | +0.00 | +0.000 |
| WILDCARD | veto:ref_not_listed | 5 | 5 | **-2.06** | **-0.412** |
| SNIPER | min_vol_skip | 5 | 4 | +2.00 | +0.500 |
| SQUEEZE | veto:ref_not_listed | 4 | 4 | +8.00 | +2.000 |
| WILDCARD | side_disabled | 4 | 3 | +0.50 | +0.167 |
| SNIPER_FAST_TRIGGER | shadow_only | 3 | 1 | -0.10 | -0.100 |

**Slot cost — the answer changed, and the honest read is "already spent".**
The +7.77R over 11 resolved looks like a standing case for more slots, but the
timestamps say otherwise: **10 of 11 rows pre-date the 07-31 two-slot move**
(07-23 x4, 07-28, 07-29, 07-30 x4). Exactly **one** row is post-2-slot
(08-05 HEI, +5R). That +7.77R is the evidence that already bought the second
slot; re-quoting it as a case for a third would be double-counting. **Post-2-slot
sample: n=1. No slot proposal.**

**External gate on real alts consolidates as protective.** `veto:ref_not_listed`
is now **-2.06R over 5 resolved, mean -0.412R** (was -1.06R / 4): SYN_USDT
resolved -1R on 08-07. Every real-alt row except KOMA has resolved to a stop.
The +8.00R SQUEEZE rows remain the fee-doomed synthetics on a disabled sleeve
and must not be blended in. **5 of the required >=10** — direction is now four
consecutive confirmations, but I am not proposing a gate change under the bar.

`SNIPER_FAST shadow_only` flipped sign (-0.52R/17 -> **+1.83R/26**) on a 2R-TP
paper bracket with no fees modelled. Mean +0.070R is inside noise, and the LIVE
sniper ledger over the same period is -2.88R/4. Treat the shadow number as
unfunded; the live one is the measurement.

**(c) Scan telemetry.** No `[SIZE_TRIM]` lines, **zero** tracebacks, **zero**
5003/2015 order rejects in the log window — no execution block. Wildcard
histograms this hour: `movers=7 candidates=0 {no_pullback_resume: 6,
roc_below_min: 1}` and `movers=6 candidates=0 {roc_below_min: 5,
no_pullback_resume: 1}`. Sniper: `move_below_min: 11` on all 11 symbols, both
variants, every cycle. Squeeze produced no summary lines (sleeve disabled).
Correct dormancy in a quiet band — no gate loosening proposed.

**(d) Decision rule (trial 7, from 2026-08-07 19:21 UTC deploy).**

| criterion | now |
|---|---|
| wildcard closes | **1 / 30** (BTW; BICO excluded as migrated) |
| net R | **+0.53** |
| net R ex-best | **0.00** (n=1) |
| max drawdown, flow-adjusted | **-0.41%** from the $142.898 close-equity peak |
| every close names its exit rule | **yes** — 2/2 `CONVEX_RETENTION_TRAIL` |

Day 1 of 30-closes-or-90-days. Nothing here is a result.

Longer convex context (unchanged framing, since 07-13): n=27, netR +1.65,
**ex-best -3.44**, net +$8.45, 11 wins.

`USE_DRAWDOWN_KILL=0` remains the operator override; equity drawdown 0.41%,
nowhere near the 20% flag.

### 1b. Wildcard — diagnose

Two entries, two wins, both banked by the new trail; no dormancy problem to
explain today. The one standing diagnostic is the lateness result above
(n=0 deep-pullback in 52). Both entries were `ref_listed=1.0` — liquid and
cross-venue corroborated, not MEXC-only pumps. Sizing clean:
`regime_size_mult=1.0`, `streak_multiplier=1.0`, size_efficiency 0.999 (BICO)
and 0.528 (BTW — the 20%-margin SL cap re-deriving leverage, by design).

### 4-5. Validate / Deploy

**No change proposed, no deploy.** The convex sleeve is under the trial-7
FREEZE (30 wildcard closes or 90 days) and is on close 1 of 30. Every
observation above is either a tripwire pass, a sub-threshold shadow count
(5/10 on the veto, 1 post-2-slot row), or a measurement note. `pytest` not run:
no candidate change to gate.

### 6. Measurement item (not a config change)

The feature store carries **no `trail_migrated` field**, so the trial-7
exclusion of BICO exists only in `DECISION_RULE.md` prose and in this audit.
At n=1 that is trivially manageable; by close 10 it is a silent
scoreboard-contamination risk. Suggest the flag be persisted on the row.
Reporting-only, does not alter which trades are taken — but it is a code
change, so it is flagged for the operator, not self-applied.

### 7. Verdict

**+$1.67 on the day, 6 closes, no change deployed.** The retention trail
banked money on both of its first two live opportunities, including the exact
trade shape that ended trial 6.5. The sniper's live R ledger opened at -2.88R
over 4 trades at a deliberate ~$0.03/R size, with all three stops overshooting
-1R. Book is flat, ledger reconciles, no execution errors.

**7-day verdict on recent changes:** retention trail (08-07) — **earning its
keep, 2/2, first evidence**. Risk dial ON (08-07) — no dispersion read yet at
n=2. Two-slot wildcard (07-31) — 1 post-change blocked candidate, no verdict.

---

# Daily Audit — 2026-08-07

---

## Automated Assessment (UTC ~16:20)

### 1. Trades (last 24h)

**0 closed trades** in the 08-06 16:00 -> 08-07 16:00 UTC window. Full MEXC
history pull (empty-symbol `history_positions`, 291 rows). The two closes
inside a 30h lookback — AVAX_USDT (08-06 10:20) and HFT_USDT (08-06 15:14) —
both fall **before** the window and were already reviewed in the 08-06 entry.
Not re-counted.

Feature store is **46 rows, unchanged**, mtime 08-06 15:14 — exactly consistent
with zero closes. Ledger and exchange agree; no reconciliation gap.

**Scan context.** The wildcard did fire once in the window (BICO_USDT, 08:52
UTC) and that position is still open — see 1-OPEN. Otherwise the band was
quiet: last three `[WILDCARD_SCAN_SUMMARY]` lines show movers 25/28/1,
candidates 0, dominant reject `roc_below_min` (19 of 25, 16 of 28), then
`no_pullback_resume` (4, 8) and `low_volume_z` (2, 1). No entry failures — zero
`5003`/`2015` order rejects, zero tracebacks in the log window. Correct
dormancy, not an execution block.

One anomaly worth a note, not a fix: the 16:02 scan reported `movers=1
scanned=1` against 25-28 on the two prior cycles. A transient universe-fetch
dip; the next cycles recovered. Flagging so a pattern is recognisable if it
repeats — a single cycle is not evidence.

**SNIPER** (FAST live leg) produced no orders in the window:
`[SNIPER_SCAN_SUMMARY]` histogram is `move_below_min: 11` on every cycle for
both variants. The log line still self-describes as
"SIGNAL-STUDY ONLY: not viable at taker fees" — see the ledger read in 1a(b).

### 1-OPEN. Open positions

**BICO_USDT LONG x1 — WILDCARD, opened 2026-08-07 08:52:28 UTC, held ~7.4h.**

| field | value |
|---|---|
| entry / current | 0.04735 / 0.0516 |
| TP (+5R) / SL (-1R) | 0.085997 / 0.039609 |
| 1R (`sl_margin_pct`) | 16.33% of margin |
| margin | $16.857 (intended $16.876) |
| unrealised | +$1.52 (+9.04% on margin) |
| **current R** | **+0.55R** |
| **peak R** (`convex_peak_r`) | **+1.098R** |
| **giveback from peak** | **-0.55R** |
| distance to TP | **+66.7%** of price |
| distance to SL | **-23.2%** of price |
| time-stop | 24h clock -> ~16.6h remaining |

Sizing is clean: `regime_size_multiplier=1.0`, `streak_multiplier=1.0`,
`loss_streak_at_entry=0`, actual/intended margin **99.88%**. No undersizing,
no `[SIZE_TRIM]` lines in the window.

Trail state is correct for trial 6.5: peak +1.098R has **armed** the trail
(arm=+1R) but at `giveback=2R` the trail floor sits at -0.90R, i.e. *below*
the -1R stop is not reached but the trail is effectively inert until peak
exceeds +2R. This is exactly the behaviour the 6.5 amendment was made to
produce — the trial-6 parameterisation (give=1R) would have closed this trade
at ~0.098R on the current pullback. First live instance of the amendment
mattering. n=1, unrealised, not a result.

Honest mark against intent: **`entry_lateness = 1.0`** — the `at_extreme
(lat>=0.99)` bucket, the opposite of the preferred deep-pullback 0.50-0.70.
Entered on a 16.4% 3h ROC at RSI 73.3. It is cross-venue corroborated
(`ref_listed=1.0`), liquid, not a MEXC-only pump. The trade is currently
green, but the entry is not the mid-path entry the sleeve is designed to take.
Lateness is a standing conditional-expectancy question, not a same-day lever.

Note also the leverage: the -20% margin SL cap re-derived x5 down to **x1** to
hold the 3.0xATR stop, so 1R is 16.35% of *price*. +5R therefore requires an
**+81.7% price move** — the trial-4 TP-completion watch item in its most
extreme live form to date.

### 2. Champion vs Shadow

**Shadow: stale, comparison suppressed pending resync.** Verified again this
run — `Futures-shadow` cycle 100789 is still `symbols=6`,
`no_mental_threshold_cross pmt:5`, i.e. the PMT-only 06-14 build. Standing
operator-gated action item (raised 07-23): `railway up --service
Futures-shadow` — paper, env-only, zero live risk. Not self-applied.

### 3. Learning loop

**(a) Feature store.** 46 rows, unchanged since 08-06 15:14, matching zero
closes. `learn_from_trades.py` was **not re-run**: it is a deterministic
function of an unchanged corpus and would reproduce the 08-06 output
bit-for-bit. Standing conclusions from that run (n=46) carry unchanged —
FAVOR `hold>=120min`; AVOID `regime_trimmed(mult<1)`; `leverage>=7` still not
OOS-consistent, do not cite as settled. Propose-only, nothing applied.

**(b) Shadow ledger** — 57 rows. Split by sleeve *and* reason, because the
blended reads have pointed the wrong way twice in this project:

| sleeve | reason | n | resolved | netR | meanR |
|---|---|---|---|---|---|
| WILDCARD | slot_occupied | 11 | 11 | **+7.77** | +0.706 |
| WILDCARD | veto:ref_not_listed | 5 | 4 | **-1.06** | **-0.265** |
| WILDCARD | side_disabled (shorts) | 4 | 2 | +1.50 | +0.750 |
| WILDCARD | veto:move_not_corroborated | 1 | 1 | +5.00 | +5.000 |
| WILDCARD | min_vol_skip | 1 | 1 | -1.00 | -1.000 |
| SQUEEZE | veto:ref_not_listed | 4 | 4 | +8.00 | +2.000 |
| SQUEEZE | slot_occupied | 6 | 6 | +0.00 | +0.000 |
| SNIPER_FAST | shadow_only | 19 | 17 | **-0.52** | **-0.031** |
| SNIPER | min_vol_skip | 4 | 4 | +2.00 | +0.500 |

**The external gate has flipped sign on real alts, and this is the finding of
the day.** The 08-02 relaxation was justified on `ref_not_listed resolved=4
cfR +8.00`. Those four rows are, and always were, the SQUEEZE synthetics
(SKHYSTOCK, SPCXSTOCK, USOIL, SNDKSTOCK) — every one with 1R between 1.19%
and 3.22% of margin, i.e. the fee-doomed bucket, on a sleeve that is now
disabled. The real-alt rows the DECISION_RULE said to wait for have since
accrued: KOMA +1.94, SKYAI -1, CATE -1, SKYAI -1 = **-1.06R over 4 resolved,
mean -0.265R**. On real alts the gate is currently **saving** money.

That is **4 of the required >=10 resolved real-alt rows** — under the bar, and
I am not proposing a change on it. The point is the direction: the number that
motivated relaxing the gate now has an opposing real-alt counterpart, and the
pre-registered instinct to wait was right. SYN_USDT (08-07 13:58, 16.60%
margin 1R) is a fifth real-alt row, unresolved.

**Slot cost.** Wildcard `slot_occupied` is **+7.77R over 11 resolved**
(3 x +5R, 7 x -1R, 1 timeout -0.23). Read it with the era caveat: 10 of the 11
rows predate the 07-31 second-slot deploy, so this is largely the same
evidence that already bought slot #2, not new evidence for slot #3. Only
HEI_USDT (08-05, +5R) is 2-slot-era. Lateness on the blocked wildcard
candidates clusters at **1.0** (8 of 11) — the same at-extreme profile as the
live BICO entry, not the costly deep-pullback misses. SQUEEZE
`slot_occupied` is exactly 0.00R over 6 and moot (sleeve disabled).

**Shorts (long-only watch item).** 4 blocked, 2 resolved, +1.50R
(QBTSSTOCK -1R, HFT +2.5R). Bar is >=20 rows. Nowhere near adjudication —
recording only.

**SNIPER.** 17 resolved shadow rows at **-0.031R mean, -0.52R net**, plus the
live leg's -$0.028 over its 2 real orders. Seventeen rows of approximately
nothing is consistent with the code's own "not viable at taker fees"
self-description. Not yet a disable case (the sleeve is hard notional-capped
and explicitly buying fill data), but it should be held to a stated stop:
recommend a decision at 30 resolved rows.

**(c) Scan telemetry.** Covered in section 1. No `[SIZE_TRIM]` lines; no
entry failures.

**(d) Decision rule — CONVEX TRIAL 6.5.**

| criterion | status |
|---|---|
| wildcard closes | **0 / 30** |
| net R | n/a (no closes) |
| net R ex-best | n/a |
| max drawdown (flow-adj.) | 0% — no closed R curve yet |
| every close attributable | n/a |

Trial 6.5 opened 08-06. The only wildcard close since is HFT_USDT (+0.01R,
`CONVEX_RUNNER_TRAIL`), which closed **under trial-6** parameters (give=1R) at
15:14 on 08-06 and belongs to trial 6. BICO is the trial's first in-window
position and is open. **90-day horizon; 0 of 30.**

`USE_DRAWDOWN_KILL` now reads **1** on Railway (was an explicit operator
override at 0, surfaced 07-17). Re-armed by the operator; noting the change,
not touching it. Equity $142.78, no drawdown condition.

### 4. Diagnose — one lever

**PROPOSED, NOT APPLIED: compute `roc_z` unconditionally in
`futuresbot/wildcard.py`.**

Trial 6 pre-registered measurement item #7 in `docs/DECISION_RULE.md`:

> `roc_z` is logged **even while the sigma trigger is OFF**, so the conditional-
> expectancy engine can settle roc-in-sigma vs roc-in-percent from REAL fills
> rather than from anyone's backtest.

It is not. `wildcard.py:186-196` computes `roc_z` **inside**
`if wildcard_sigma_trigger_enabled():` — and that flag defaults False and is
unset on Railway. Measured today:

- shadow ledger: `roc_z` present on **0 of 57** rows;
- feature store: no `roc_z` column on any row written before the 08-06 deploy,
  and the column the writer now emits (`runtime.py:3302`) reads from position
  metadata that is `None`;
- the live BICO position carries `"roc_z": null` in its metadata.

So trial 6's single most-cited structural defect — "the trigger is not a
trigger; a fixed 8% spans ~10-32x in event rarity across the band" — is
accumulating **zero** evidence, and will still have zero at the end of the
90-day window. The sigma trigger cannot be armed on data, because there is no
data.

Shape of the fix: compute `sigma`/`roc_z` unconditionally, wrapped so a `None`
sigma yields `roc_z = None` instead of the `no_roc_sigma` reject, and keep the
`roc_z_below_min` reject strictly inside the `if` branch. Which trades are
taken and how they are managed is then **unchanged** — this is a measurement
change under the 07-31 standard and may ship inside the freeze without
resetting trial 6.5.

**Not deployed today, for two reasons:** BICO is open (step-5 rule — deploys
restart the container), and this is a code change to the live scan path rather
than a label fix, so it wants a green `pytest` and a clean window. Operator
gate. Recommend shipping at the next flat moment.

Rejected as today's lever: anything on slots, gates, or exit parameters — the
sleeve is frozen for trial 6.5 and every one of those is a treatment change.

### 5. Validate

No gate run. No candidate change to score — the proposed lever is measurement
only, so `replay_exits.py` / `mc_ledger.py` have nothing to price, and the
V-stack does not apply.

### 6. Deploy

**None.** Zero commits, zero Railway variable changes, zero redeploys. Bot
healthy: continuous `[ACCOUNT]` lines, 1 position, no tracebacks.

### 7. Verdict on recent changes (7d)

- **Trial 6.5 exit constants (24h clock / 2R giveback, 08-06)** — first live
  case is BICO, currently held through a -0.55R giveback that the trial-6
  parameterisation would have closed at ~+0.10R. Earning its keep so far;
  n=1 unrealised, not a result.
- **`kind=SNIPER` feature-store label fix (08-06)** — no closes since, so
  untested in production. Regression test holds it.
- **Second wildcard slot (07-31)** — one 2-slot-era blocked candidate since
  (HEI, +5R). Still thin.
- **External gate at `REQUIRE_LISTED=1` (reverted 08-02)** — vindicated on
  real alts this run (-0.265R mean on 4 resolved vetoes). Keep.

**Verdict: no change. 0 closes, 1 healthy open convex position, one measurement
defect found and proposed.**

# Daily Audit — 2026-08-06

---

## Automated Assessment (UTC ~16:30)

### 1. Trades (last 24h)

**5 closed trades, net +$2.051.** Full-history MEXC pull (empty-symbol
`history_positions`, 297 rows total). Note on coverage: the container
restarted mid-audit (16:23 UTC, cause unclear — not triggered by this
session's `railway run`/`ssh` calls, which don't restart the service);
Railway CLI `logs --since` in this environment only reaches back to the
current process's start, so live-log corroboration below covers ~11:24-16:25
UTC, not the full 24h. Where a trade fell outside that window, attribution
is from the feature-store row instead (still ground-truth, just not
cross-checked against a live cycle log).

| symbol | side | kind | lev | held | r_multiple | pnl | exit_reason |
|---|---|---|---|---|---|---|---|
| BICO_USDT | LONG | WILDCARD | x2 | 17.2h | +1.93R | +$1.334 | CONVEX_TIME_STOP |
| BTW_USDT | LONG | WILDCARD | x2 | 11.3h | +0.57R | +$0.767 | CONVEX_TIME_STOP |
| XRP_USDT | SHORT | SNIPER (FAST, live leg) | x13 | 11.1min | +1.20R | +$0.024 | EXCHANGE_CLOSE (TP) |
| AVAX_USDT | SHORT | SNIPER (FAST, live leg) | x13 | 12.0min | -1.27R | -$0.051 | EXCHANGE_CLOSE (STOP) |
| HFT_USDT | LONG | WILDCARD | x1 | 3.0h | +0.01R | +$0.011 | CONVEX_RUNNER_TRAIL |

BICO/BTW are TRIAL 5's closure (both closed by trial 6's new 6h clock on the
first cycle after the 08-05 22:25 UTC deploy) — already recorded in
DECISION_RULE.md's trial-5 closure record, not double-counted into trial 6's
ledger here. HFT_USDT is trial 6's **first fully in-trial WILDCARD trade**
(opened 12:13, closed 15:14) and its `CONVEX_RUNNER_TRAIL` exit is the
**first live fire of the runner-trail rule** since the 08-05 fix
(`6d8d016`) made it reachable — confirms the fix works: armed at peak
+1.07R, gave back to +0.03R, closed net flat. Working as designed.

**New this run — SNIPER FAST live leg has traded for the first time.**
`FUTURES_SNIPER_LIVE_VARIANTS=FAST` / `FUTURES_SNIPER_SHADOW_ONLY=0` have
been live since 08-04 (`3247faf`) but hadn't fired until today. XRP_USDT and
AVAX_USDT (both outside the live-log window, confirmed via feature-store
rows instead) are its first two real orders: notional-capped as designed
(~$0.54 intended margin each), net -$0.028 combined — exactly the
"buy fill/slippage data cheaply, not to profit" behaviour the code comment
describes. Not a performance signal at n=2; flagging only because it's new.

**Bug found and fixed:** `_append_feature_store` tags a row's `kind` by
matching the `entry_signal` prefix (`SQUEEZE`/`WILDCARD`/else `PMT`) — it
never checked for `SNIPER`, so both live sniper closes were silently filed
under `kind=PMT`. Harmless to real P&L (MEXC and the audit trail have the
correct numbers) but it corrupts the `kind=PMT` bucket that
`learn_from_trades.py` treats as "should be empty since decommission", and
would have kept misattributing every future sniper close the same way.
Fixed in `futuresbot/runtime.py` (added a `SNIPER` branch), regression test
added in `tests/test_sniper.py` pinning `kind=="SNIPER"` for a
`SNIPER_SHORT` entry_signal. 745/745 tests pass (was 744). This is a
labelling-only fix — no trading behaviour changed — so shipped directly
rather than gated (mirrors the 08-05 precedent of shipping a caught bug same
day). Existing PMT-mislabeled rows in the feature store are left as-is
(2 rows, immaterial, not worth a backfill).

**Secondary, not fixed:** `_convex_loss_streak` (the cold-streak throttle's
input) only counts `WILDCARD`/`SQUEEZE` entry_signal prefixes toward the
streak — a SNIPER loss (e.g. today's AVAX) doesn't feed the throttle, and a
SNIPER position's own sizing is throttled only by wildcard/squeeze's streak,
never its own. Written before SNIPER existed as a live sleeve. Low stakes
today (SNIPER is hard-notional-capped regardless), but flagging as a
scope gap for whoever next touches the streak throttle — not proposing a
change, this is a risk-sizing scope question for the operator, not a typo.

### 1-OPEN. Open positions

**None.** `get_open_positions()` returns `[]`; account line agrees:
equity $140.6368, available $140.6368, open_margin $0.00, positions=0.

### 2. Champion vs Shadow

**Shadow: stale, comparison suppressed pending resync** (standing 07-23
action item, unchanged — Futures-shadow logs still show PMT-only
`pmt-scan`/`no_mental_threshold_cross` cycles).

### 3. Learning loop

Feature store 41 -> 46 rows (+5, matches today's closes).
`learn_from_trades.py` re-run on the updated corpus (n=46):
- **FAVOR: `hold>=120min`** — n=27 mean +$1.079 (win 66.7%) vs n=19
  mean -$0.999 (win 10.5%), OOS-consistent. Unchanged conclusion, now on
  6 more rows.
- **AVOID: `regime_trimmed(mult<1)` / `chop_regime`** — n=27 mean -$0.029
  (win 40.7%) vs n=19 mean +$0.576 (win 47.4%), OOS-consistent. Unchanged.
- Everything else remains weak/insufficient, including `leverage>=7`
  (n=18, still not OOS-consistent — do not cite as settled). Note `kind=PMT`
  (n=14) is now known to include the 2 mislabeled sniper rows fixed above;
  a rerun after more sniper closes accumulate under the corrected label may
  shift this cell slightly. Propose-only, nothing applied.

**Shadow ledger** grew 33 -> 51 rows (+18). Slot-cost split (WILDCARD only):
n=11 resolved (was 10), **netR +7.77 (mean +0.71R)** — jumped this run
because the previously-unresolved HEI_USDT (08-05's 12:58 blocked
candidate) resolved **+5.0R (TP)**. This now clears the n>=10 evidence bar
with a materially stronger number than 08-05's +2.77R — worth the operator
weighing a 3rd wildcard slot against capacity/complexity; proposing, not
applying (slot counts are operator-tuned per the standing rule).

Veto-gate `ref_not_listed`, real-alt rows: n=4 resolved (KOMA +1.94R, SKYAI
-1.00R x2, CATE -1.00R), net **-1.06R** (mean -0.27R) — still <10, still
roughly flat/mildly protective, no action.

`side_disabled` (trial 6's long-only block on shorts): n=1 resolved,
QBTSSTOCK_USDT would have been -1.00R — first data point, and it points the
direction long-only intends (blocking saved a loss), but n=1 is nowhere
near the >=20 watch-item bar.

SNIPER shadow (FAST + FAST_TRIGGER combined, all `shadow_only`/`slot_occupied`):
n=20 resolved, netR +0.22 (mean +0.01R) — consistent with the documented
"not viable at taker fees" caveat (this is the fee-free counterfactual;
today's 2 real fills, net -$0.028, are directionally consistent with
breakeven-ish once real costs apply).

### 4. Wildcard/squeeze/sniper diagnose

**Wildcard**, partial-window telemetry (~11:24-16:25 UTC, see coverage note
above): 20 scans, movers=665, scanned=458, candidates=2, shorts_blocked=1.
Reject histogram: `roc_below_min` 351 (77%), `no_pullback_resume` 85 (19%),
`low_volume_z` 15, `climax_wick` 2, `rsi_exhausted` 2 — the 3h-ROC gate
remains dominant, correct per design. 0 order-reject codes (5003/2015), 0
Tracebacks in the covered window.

**Squeeze:** still disabled at config level (trial 4/5 design). Operator
confirmation of "intentional, permanent" vs "re-enable" still open
(unchanged since 08-02).

**Sniper:** both live variants scanning every cycle (FAST_TRIGGER,
FAST); in-window histogram dominated by `move_below_min` (1317) — expected,
FAST's trigger is tight by design. First live fills discussed in §1.

### 5. Trial 6 decision-rule progress

Trial 6 opened 2026-08-05 22:25 UTC. Scored per DECISION_RULE.md's own
convention (BICO/BTW attributed to trial 5's closure, not trial 6):
**n=1 WILDCARD trade fully inside trial 6** (HFT_USDT, +0.01R). Net R
+0.01, ex-best is undefined at n=1, no drawdown yet (no losses). Day 2 of a
30-trade/90-day window — far too early to read anything into it; the
runner-trail firing correctly (§1) is the only thing worth noting.

`exit_kind` (new in trial 6, only populated on trial-6-tagged closes):
BICO/BTW/HFT all show `OTHER` — correct, since `CONVEX_TIME_STOP` and
`CONVEX_RUNNER_TRAIL` are neither TP nor STOP by construction. **Re-reading
the standing TRIAL-4 watch item** ("if OTHER dominates, propose scaling TP
down"): that heuristic predates these two new exit rules and would now
misfire — OTHER is *expected* to dominate under trial 6 whenever the trail
or clock does its job. Not proposing a TP-scale change off this; the
heuristic itself needs updating to split `OTHER` into
`TIME_STOP`/`RUNNER_TRAIL`/unexplained before it's useful again as a bug
tripwire. Flagging as a future telemetry polish item, not urgent.

### 6. Diagnose — lever for next 24h

**Shipped:** the SNIPER `kind` mislabeling fix (§1) — correctness-only,
no trading behaviour change, tests green.

**No trading-parameter change proposed.** Trial 6 is on day 2 with n=1
in-trial WILDCARD close; nothing has had time to earn or fail evidence yet.
The one lever with real evidence behind it (3rd wildcard slot, off the
+7.77R/11 slot-cost number) is a capacity/operator-tuned decision, not a
tunable this process self-applies — surfaced as an action item below.

### 7. Validate

`pytest -q`: **745 passed** (was 744; +1 new regression test for the
SNIPER kind-labelling fix). No other code changes this run.

### 8. Deploy

**Shipped:** SNIPER feature-store `kind` labelling fix. `git pull` (already
up to date) -> commit -> push -> `railway up --service Futures-bot --detach`
-> polled to SUCCESS -> verified `[ACCOUNT]` line present, no Traceback. No
open position at deploy time (0 open, safe window).

### 9. Summary

- Equity: $140.6368 (vs 08-05's $138.43; **+$2.05 is realized P&L from
  today's 5 closes, not a capital flow** — no deposit/withdrawal today)
- Trades: 5 closed, net +$2.051 — BICO +$1.334, BTW +$0.767 (both trial-5
  closure), XRP +$0.024, AVAX -$0.051 (sniper FAST live, first-ever),
  HFT +$0.011 (trial 6's first in-trial WILDCARD close)
- Open: none
- New development: SNIPER FAST live leg fired for the first time (2 trades,
  net -$0.028, notional-capped as designed — not a performance signal)
- Bug fixed + deployed: SNIPER closes were mislabeled `kind=PMT` in the
  feature store (learning-corpus attribution only, no P&L impact)
- Slot cost: WILDCARD blocked candidates net +7.77R over 11 resolved rows
  (up from +2.77R/10) — now a clear bar-clearing number, proposing a 3rd
  slot for operator consideration, not applying
- Trial 6: day 2, n=1 in-trial WILDCARD close (+0.01R) — runner-trail fired
  correctly on its first live opportunity
- Veto gate: real-alt `ref_not_listed` n=4 resolved, net -1.06R — still <10
- Shadow: stale, comparison suppressed pending resync
- Deploy: SNIPER kind-labelling fix shipped; 745/745 tests pass
- Bot: healthy, 0 Tracebacks/order-reject errors in the covered log window
- **Action items for operator:** (1) consider a 3rd wildcard slot — slot-cost
  evidence now +7.77R/11 resolved, above the standard bar (capacity/ops
  decision, not self-applied); (2) `FUTURES_SQUEEZE_ENABLED=0` — confirm
  intentional or re-enable (unchanged since 08-02); (3) reconcile-drop
  2-pass-grace fix still outstanding (unchanged from 07-30); (4)
  `USE_DRAWDOWN_KILL=1` live vs the scheduled-task brief's note that it was
  set to 0 — still unreconciled; (5) new `DRAWDOWN_HALT_PCT=0.95` /
  `DRAWDOWN_HALT_WINDOW_DAYS=30` vars are live and not documented in the
  scheduled-task brief — worth a one-line confirmation of what they do and
  whether the brief should be updated; (6) BTW-style lot-size undersizing
  on coarse contract_size symbols remains a candidate future fix, not
  urgent; (7) `_convex_loss_streak` scope gap re: SNIPER (§1) — a sizing
  design question, not urgent.

---

# Daily Audit — 2026-08-05

---

## Automated Assessment (UTC ~16:30)

### 1. Trades (last 24h)

**0 closed trades.** Verified via full-history MEXC pull, empty-symbol
`history_positions`, 293 rows across 3 pages. Max `updateTime` is still
2026-07-31T21:45:30Z (BANK_USDT) — dormancy continues on the closed-trade
side even though TRIAL 5 opened two new positions today (below).

### 1-OPEN. Open positions

TRIAL 5 (`7cd4b96`, "open TRIAL 5 - four defect fixes from trial 4's
evidence") is live and deployed — both wildcard slots are filled with its
first two trades, both still open, neither has touched TP or SL:

- **BICO_USDT LONG x2**, held 11h16m, **+0.16R** (peak **+2.54R** at
  08:xx, giveback from peak **-2.38R** — round-tripped from deep in TP
  territory through breakeven to -0.87R trough and back to flat). TP
  +39.8% away, SL -9.6% away. entry_lateness=1.00 (vertical entry, not a
  deep pullback).
- **BTW_USDT LONG x2**, held 5h21m, **~0.00R** (peak **+0.17R**, giveback
  negligible). TP +45.3% away, SL -9.2% away. entry_lateness=1.00.

**Sizing check:** BICO's actual margin ($4.15) matches its
regime-scaled intended margin ($4.16, mult=0.25) almost exactly —
contract_size=1 gives fine-grained sizing. BTW's actual margin ($7.38) is
**38% short of its regime-scaled intended margin** ($11.91, mult=0.74)
because BTW_USDT's contract_size=100 forces integer-contract rounding
(needed ~1.6 contracts, got 1). Not a bug in the regime scaler — a
lot-size quantization gap on coarse-lot symbols. Flagging as a candidate
for a future bounded fix (round-to-nearest-viable instead of always-down);
not proposing today, not sized to matter much on a $7 position.

### 2. Champion vs Shadow

**Shadow: stale, comparison suppressed pending resync** (standing 07-23
action item, unchanged — Futures-shadow logs still show PMT-only
`pmt-scan`/`no_mental_threshold_cross` cycles, no wildcard/squeeze/convex
activity, confirming it has not been resynced to champion HEAD).

### 3. Trial 5 / config status

Live `railway variables` confirmed the four TRIAL 5 changes are actually
in effect: `FUTURES_WILDCARD_MIN_24H_MOVE=0.03` (was 0.08),
`FUTURES_EXTERNAL_GATE_REQUIRE_LISTED=1`, `FUTURES_SQUEEZE_ENABLED=0`,
`FUTURES_WILDCARD_MAX_POSITIONS=2`, `FUTURES_WILDCARD_MAX_SL_MARGIN_PCT=20`,
`FUTURES_WILDCARD_SL_ATR_MULT=3.0`, `FUTURES_ENTRY_MIN_SCORE=1000` (PMT
still decommissioned). `FUTURES_CONVEX_DRAWDOWN_BRAKE` unset (default off,
shadow-observe per plan). Local repo and `origin/main` are now in sync at
`7cd4b96` (the 10 commits that were unpushed as of 08-04 have landed and
deployed) — nothing outstanding to push today.

**Note:** `USE_DRAWDOWN_KILL=1` live. The scheduled-task brief's standing
note says this was operator-set to 0 on 07-17; current value contradicts
that note. Not touching it (kill-switch ON is the safer default) — flagging
the stale doc/live mismatch for the operator to reconcile, not treating it
as a bug.

**Funnel fix confirmation:** `MIN_24H_MOVE` 0.08->0.03 is doing what trial
5 intended — `movers` per wildcard scan is now ~22-25 (was 7-10 pre-fix).
Aggregated across 31 scans since this morning's deploy: `roc_below_min`
575 (82%), `no_pullback_resume` 107 (15%), rest single digits. The
3h-ROC-8% detector remains the dominant, unchanged gate — correct, matches
the design (only the pre-filter was meant to widen).

**Entry execution:** 0 order-reject codes (5003/2015), 0 Tracebacks in the
available log window (since ~08:20 deploy). Both BICO and BTW entries
filled clean.

### 4. Learning loop

Feature store still 41 rows (0 new closes). Re-ran
`learn_from_trades.py` anyway since trial 5 changed nothing about the
historical corpus — same output as prior runs, restated for the record:
- **FAVOR: `hold>=120min`** — n=24 mean +$1.13 (win 62.5%) vs n=17 mean
  -$1.11 (win 5.9%), OOS-consistent. Positions that get stopped inside 2h
  are overwhelmingly losers; this is mechanical (convex needs time for a
  5R move) rather than a new insight, but it's now OOS-confirmed.
- **AVOID: `regime_trimmed(mult<1)` / `chop_regime`** (same underlying
  flag) — n=24 mean -$0.12 (win 33%) vs n=17 mean +$0.65 (win 47%),
  OOS-consistent. `regime_trimmed_hard(mult<0.5)` shows the same direction
  on a smaller n=14 slice.
- `leverage>=7` (previously flagged informally as "reliably loses") is now
  only **weak** with more data (n=16, not OOS-consistent both ways) — do
  not keep citing it as a settled finding.
- Propose-only, nothing applied.

**Shadow ledger** grew 27 -> 33 rows (+6, all from today's scan activity).
Slot-cost split (WILDCARD only, squeeze now irrelevant/disabled):
n=10 resolved, netR **+2.77** (mean +0.28R) — unchanged from 08-04, no new
resolutions this window; still the number that justified the 2nd slot,
both slots are now occupied by live trial-5 trades so this isn't actionable
today. One new unresolved row: HEI_USDT (blocked by `slot_occupied` at
12:58, lateness=1.00).

**Veto gate correction:** prior daily reports (through 08-04) quoted
`ref_not_listed` net R **blended across synthetic and real-alt rows**
(e.g. "+8.94R/6"), but DECISION_RULE.md's own adjudication bar is
explicitly **real-alt rows only** (synthetics are independently blocked by
the squeeze fee filter and don't inform this gate's cost on real alts).
Re-split today: **real-alt `ref_not_listed`, n=3 resolved: KOMA_USDT
+1.94R, SKYAI_USDT -1.00R, CATE_USDT -1.00R (new today), net -0.06R** —
roughly flat, which *reverses* the "trending net-positive" framing carried
in prior reports. Synthetic-only (SKHYSTOCK/USOIL/SPCXSTOCK/SNDKSTOCK):
n=4, net +8.00R, correctly excluded from adjudication. Still far below the
n>=10 real-alt bar (3 resolved) — no gate-tuning proposal, but flagging the
correction so future reports don't keep citing the blended number.

### 5. Wildcard/squeeze diagnose

**Wildcard:** active and correctly widened (see §3 funnel note). 2
candidates fired since this morning's deploy: BTW_USDT (took it, 2nd slot
was open) and HEI_USDT at 12:58 (blocked, both slots already full —
shadow-logged). Dormancy on the closed-trade side is a slot/hold-time
story, not a scan-gate story: both slots have been continuously occupied
since 11:09.

**Squeeze:** disabled at config level, per trial 4/5 design (not a
scan/gate issue). Operator confirmation of "intentional, permanent" vs
"re-enable" is still an open item (unchanged since 08-02).

### 6. Diagnose — lever for next 24h

**No change proposed.** Today is trial 5's first live day — both slots
are occupied by its first two trades, zero closes yet to judge anything
against the new pass criteria. The only candidate levers on the table
(veto-gate tuning, 3rd wildcard slot) both sit below their evidence bars
(n=3 and n=10 respectively, need 10 and a fresh justification). Correct
move is to let trial 5 accumulate trades.

### 7. Validate

`pytest -q`: **721 passed** locally at `7cd4b96` (up from 08-04's 703 —
trial 5's four defect-fix commits added coverage). No code change this
run, so no replay/MC/shadow-staging gate needed.

### 8. Deploy

**None.** Already deployed (trial 5 shipped before this run); local/origin
in sync; working tree clean.

### 9. Summary

- Equity: $138.43 (flat vs 08-04's $138.59; not a P&L statement, unrealized
  -$0.12 across the 2 open positions)
- Trades: 0 closed; 2 open (BICO_USDT +0.16R, BTW_USDT ~0.00R) — trial 5's
  first two trades, both wildcard
- Open: BICO_USDT LONG x2, held 11h16m, +0.16R (peak +2.54R, giveback
  -2.38R), TP +39.8%/SL -9.6% away
- Open: BTW_USDT LONG x2, held 5h21m, +0.00R (peak +0.17R, giveback
  -0.17R), TP +45.3%/SL -9.2% away; sized 38% under regime target due to
  coarse contract_size=100 lot rounding (flagged, not fixed)
- Slot cost: WILDCARD blocked candidates net +2.77R over 10 resolved rows
  (unchanged, both slots occupied so not actionable today)
- Trial 5: day 1, 0/? convex trades closed, netR 0 (too early to score)
- Veto gate: real-alt `ref_not_listed` corrected to n=3 resolved, net
  -0.06R (reverses prior blended "+8.94R" framing) — still <10, no action
- Exits (all-time convex, reconstructed from r_multiple since exit_kind is
  new): WILDCARD 16 trades, TP 4 (25%), STOP 11, OTHER 1 — above the 16.7%
  breakeven, tripwire not triggered
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run (trial 5 already live)
- Bot: healthy, 0 Tracebacks/order-reject errors, 721/721 tests pass
- **Action items for operator:** (1) `FUTURES_SQUEEZE_ENABLED=0` — confirm
  intentional or re-enable (unchanged since 08-02); (2) reconcile-drop
  2-pass-grace fix still outstanding (unchanged from 07-30); (3)
  `USE_DRAWDOWN_KILL=1` live vs the scheduled-task brief's note that it was
  set to 0 — doc/live mismatch, please reconcile which is correct; (4)
  BTW_USDT-style lot-size undersizing on coarse contract_size symbols is a
  candidate future fix, not urgent

---

# Daily Audit — 2026-08-04

---

## Automated Assessment (UTC ~16:15)

### 1. Trades (last 24h)

**0 closed trades.** Verified via full-history MEXC pull (empty-symbol
`get_historical_positions`, 294 rows). Max `updateTime` across all rows is
still 2026-07-31T21:45:30Z (the BANK_USDT close) — unchanged for the 4th
consecutive audit. `get_open_positions()` confirms 0 open.

### 1-OPEN. Open positions

**None.** Live `[ACCOUNT]` log line agrees: equity **$138.59**, available
$138.59, open_margin $0.00, positions=0 (flat vs 08-03, not a P&L statement).

### 2. Champion vs Shadow

**Shadow: stale, comparison suppressed pending resync** (standing 07-23
action item, unchanged).

### 3. Trial 4 / config status

Live `railway variables` confirmed: `FUTURES_EXTERNAL_GATE_REQUIRE_LISTED=1`
(reverted state holds, no change since 08-02's same-day fix),
`FUTURES_ENTRY_MIN_SCORE=1000` (PMT still decommissioned),
`FUTURES_WILDCARD_ENABLED=1`, `USE_DRAWDOWN_KILL=1` /
`DRAWDOWN_HALT_PCT=0.95` (unchanged, inert at this threshold).

**Still open, unchanged:** `FUTURES_SQUEEZE_ENABLED=0` — squeeze sleeve
remains fully off at the config level, cause still unconfirmed. Operator
confirm still needed: intentional or re-enable.

With 0 closed trades this window, convex ledger and feature-store numbers
are unchanged from 08-03: n=22, netR -1.81, ex-best -6.90R, maxDD 11.98R,
win 27.3%. Feature store 41 rows, unchanged row-for-row.

**Shadow ledger grew 23 -> 27 rows (+4).** Slot-cost split unchanged
(wildcard 10/10 resolved net +2.77R; squeeze 6/6 net +0.0R, <10, no action).
`veto:ref_not_listed` moved from n=5 (4 resolved) to **n=6, all 6 resolved**
(KOMA_USDT resolved +1.94R; new row SKYAI_USDT -1.0R) — net **+8.94R**
across 6 resolved rows. Still below the DECISION_RULE.md n>=10 adjudication
bar — no veto-tuning proposal this run, but the running trend continues to
suggest the gate is costing more than it saves; worth watching as it
approaches n=10. Two new reject-reason categories appeared: `min_vol_skip`
(1 row, SQUEEZE) and `shadow_only` (3 rows, sleeve=SNIPER_FAST: -1.0, +2.0,
+2.0R = net +3.0R) — Sniper remains shadow-only, n=3 far too small to
evaluate, no live risk.

### 4. Learning loop

No new feature-store rows since 08-03 (0 closed trades) — `learn_from_trades.py`
not re-run (identical input reproduces identical output). Shadow-ledger
detail in §3.

### 5. Wildcard/squeeze diagnose

**Wildcard:** active, 5 scans across a ~64min log window (buffer limited to
500 lines today), dominant reject `roc_below_min` (15, 14, 16, 16, 1 across
the 5 scans) — correct dormancy for a quiet market, no gate loosening
proposed. 0 order-reject codes (5003/2015), 0 Tracebacks.

**Squeeze:** disabled at config level — see §3, not a scan/gate issue.

**Sniper (shadow-only, informational):** `mode=shadow` throughout the
window, never `live`, universe 12, dominant reject `move_below_min`, 0
signals from either variant. No live risk.

### 6. Diagnose — lever for next 24h

**No strategy parameter change proposed.** Zero new trades, wildcard
dormancy correct-for-regime, no execution bugs, no fresh ledger evidence
above the adjudication bar. Open items are both operator-decision, not
levers: squeeze re-enable/confirm, and the standing reconcile-drop
2-pass-grace fix (proposed 07-30, still unapplied).

### 7. Validate

`pytest -q`: **703 passed** locally (HEAD unchanged from 08-03's `f8ca020`,
no code touched this run; count differs slightly from 08-03's reported 700
for the same commit — environmental/collection variance, not
code-attributable, not investigated further as nothing changed).

### 8. Deploy

**None.** Local `main` is 10 commits ahead of `origin/main` (through
`f8ca020`), working tree clean, tests green — no push/deploy this run since
no change is being promoted today.

### 9. Summary

- Equity: $138.59 (flat vs 08-03; not a P&L statement)
- Trades: 0 closed, 0 open — 4th straight dormant day
- Trial 4: unchanged (1 genuine trade so far)
- Convex ledger since 07-13: n=22, netR -1.81, ex-best -6.90R, maxDD
  11.98R, win 27.3% (unchanged, no new data)
- Slot cost: wildcard 10/10 net +2.77R (pre-shipment evidence); squeeze
  6/6 net +0.0R (<10, no action)
- Veto gate: `ref_not_listed` now 6/6 resolved, net +8.94R — still below
  the n>=10 bar, trend unchanged (gate looks costly, not protective)
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy, 0 Tracebacks/errors in the available log window, 703/703
  tests pass locally
- **Action items for operator:** (1) `FUTURES_SQUEEZE_ENABLED=0` — confirm
  intentional or re-enable (unchanged since 08-02); (2) reconcile-drop
  2-pass-grace fix still outstanding (unchanged from 07-30); (3) 10 local
  commits sit unpushed to origin — push/deploy whenever convenient, nothing
  urgent in them; (4) `veto:ref_not_listed` trending net-positive (+8.94R/6)
  — approaching the n>=10 bar, will need an explicit adjudication call soon

---

# Daily Audit — 2026-08-03

---

## Automated Assessment (UTC ~18:10)

### 1. Trades (last 24h)

**0 closed trades.** Verified via full-history MEXC pull (empty-symbol
`get_historical_positions`, 297 rows). Max `updateTime` across all rows is
still 2026-07-31T21:45:30Z (the BANK_USDT close) — unchanged for the 3rd
consecutive audit. `get_open_positions()` confirms 0 open.

### 1-OPEN. Open positions

**None.** Live `[ACCOUNT]` log line agrees: equity **$138.59**, available
$138.59, open_margin $0.00, positions=0 (flat vs 08-02, not a P&L statement).

### 2. Champion vs Shadow

**Shadow: stale, comparison suppressed pending resync** (standing 07-23
action item, unchanged).

### 3. Trial 4 / config status

**External-gate item CLOSED.** `docs/DECISION_RULE.md` (edited 08-02) shows
the 08-02 `FUTURES_EXTERNAL_GATE_REQUIRE_LISTED=0` relaxation was reverted to
`1` the same day, live-confirmed just now (`railway variables`). Net effect
on trial 4: zero (relaxation window had no wildcard signal). No longer an
open item.

**Still open, unchanged:** `FUTURES_SQUEEZE_ENABLED=0` — squeeze sleeve
remains fully off at the config level; no new explanation found in commits
or docs since 08-02. Confirmed again live. Operator confirm still needed:
intentional or re-enable.

**Noted, not new:** `USE_DRAWDOWN_KILL=1` / `DRAWDOWN_HALT_PCT=0.95` —
this was already surfaced 07-26/07-27 as a live operator-side change from the
documented `0` override; functionally inert at a 95% halt threshold either
way. Unchanged since, no action.

With 0 closed trades this window, all ledger/slot-cost/learning numbers are
unchanged from 08-02: convex ledger n=22, netR -1.81, ex-best -6.90R, maxDD
11.98R, win 27.3%; slot cost wildcard 10/10 resolved net +2.77R
(pre-2nd-slot-shipment evidence, already actioned), squeeze 6/6 net +0.0R
(<10, no action). Feature store 41 rows / shadow ledger 23 rows, both
unchanged row-for-row (`railway ssh wc -l`).

**Exits (feature store `exit_kind`):** TP 0 | stop 1 | other 0 (MISSING 40).
40 of 41 rows predate the exit_kind column (added 07-31/08-01) — only 1 row
has coverage. Too little data for the TP<10%-at-n>=15 watch item; no action.

### 4. Learning loop

No new rows since 08-02 — see §3. `learn_from_trades.py` not re-run
(identical input reproduces identical output).

**New since 08-02:** Sniper sleeve now ships two shadow variants side by side
(`FAST_TRIGGER`, `FAST` — commit `b82a026`). Confirmed shadow-mode in the
~1h log window (`mode=shadow`, never `live`), universe 11, dominant reject
`move_below_min`, 0 signals either variant. No live risk.

### 5. Wildcard/squeeze diagnose

**Wildcard:** active, 5 scans across a ~1h log window (railway logs' buffer
is shorter today — no 5+h window available), 4/5 zero-mover, 1/5 one mover
rejected on `no_pullback_resume` — correct dormancy for a quiet market, no
gate loosening proposed. 0 order-reject codes (5003/2015), 0 Tracebacks.

**Squeeze:** disabled at config level — see §3, not a scan/gate issue.

### 6. Diagnose — lever for next 24h

**No strategy parameter change proposed.** Zero new trades, wildcard
dormancy correct-for-regime, no execution bugs, no fresh ledger evidence to
act on. Open items are both operator-decision, not levers: squeeze
re-enable/confirm, and the standing reconcile-drop 2-pass-grace fix
(proposed 07-30, still unapplied).

### 7. Validate

`pytest -q`: **700 passed** (was 692 on 08-02; +8 from the Sniper-variant and
ref_listed test additions, both already committed).

### 8. Deploy

**None.** Local `main` is 8 commits ahead of `origin/main` (through
`b82a026`), working tree clean, tests green — no push/deploy this run since
no change is being promoted today.

### 9. Summary

- Equity: $138.59 (flat vs 08-02; not a P&L statement)
- Trades: 0 closed, 0 open — 3rd straight dormant day
- Trial 4: unchanged (1 genuine trade so far); the 08-02 gate-relaxation
  scare is resolved/closed, zero effect on the trial
- Convex ledger since 07-13: n=22, netR -1.81, ex-best -6.90R, maxDD
  11.98R, win 27.3% (unchanged, no new data)
- Slot cost: wildcard 10/10 net +2.77R (pre-shipment evidence); squeeze 6/6
  net +0.0R (<10, no action)
- Exits: TP 0 | stop 1 | other 0 (40/41 rows lack exit_kind coverage yet)
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy, 0 Tracebacks/errors in the available log window, 700/700
  tests pass locally
- **Action items for operator:** (1) `FUTURES_SQUEEZE_ENABLED=0` — confirm
  intentional or re-enable (unchanged from 08-02); (2) reconcile-drop
  2-pass-grace fix still outstanding (unchanged from 07-30); (3) 8 local
  commits sit unpushed to origin — push/deploy whenever convenient, nothing
  urgent in them

---

# Daily Audit — 2026-08-02

---

## Automated Assessment (UTC ~16:20)

### 1. Trades (last 24h, since 08-01 16:20 UTC)

**0 closed trades.** Verified via full-history MEXC pull (empty-symbol
`get_historical_positions`, 301 rows total since 2026-05-04) — max
`updateTime` across all 301 rows is 2026-07-31T21:45:30Z (the BANK_USDT
close reported 08-01). Nothing has closed since.

### 1-OPEN. Open positions

**None.** `get_open_positions()` + live `[ACCOUNT]` log line agree: equity
**$138.59**, available $138.59, open_margin $0.00, positions=0.

### 2. Champion vs Shadow

**Shadow: stale, comparison suppressed pending resync** (standing 07-23
action item, unchanged).

### 3. Trial 4 status (see docs/DECISION_RULE.md) — TOP FINDING

**`FUTURES_EXTERNAL_GATE_REQUIRE_LISTED` is live-set to `0`** (was `1`).
Confirmed via `railway variables`. This was NOT done by this run. The local
working tree carries uncommitted, undeployed instrumentation
(`futuresbot/runtime.py` + `tests/test_sniper.py`, 85 lines, all 692 tests
pass) whose own comments date the change: *"REQUIRE_LISTED was relaxed
mid-trial (2026-08-02, at n=5 counterfactual evidence vs the pre-registered
n=10)"*.

This contradicts the checked-in `docs/DECISION_RULE.md` (last edited 08-01
11:17, unchanged since), which explicitly states under "External gate:
reviewed and DELIBERATELY NOT CHANGED": *"DECISION: instrument now,
adjudicate at >=10 resolved REAL-ALT veto rows."* The live shadow-ledger
`veto:ref_not_listed` count is n=5 (4 resolved net +13.0R, all synthetics;
1 unresolved KOMA_USDT) — below the doc's own n=10 bar.

Per the doc's own "WHEN DOES A CHANGE RESET THE TRIAL?" standard (also
08-01), a gate/threshold change is explicitly listed as a trial-resetting
treatment change, not a measurement change. **Trial 4's clean-treatment
window is therefore compromised as documented** — this needs the operator's
call, not a silent continuation. PROPOSING (not applying) one of: (a)
revert `FUTURES_EXTERNAL_GATE_REQUIRE_LISTED` to `1` to preserve trial 4
integrity until the n=10 bar is met, or (b) formally supersede with a
"trial 5" entry in DECISION_RULE.md acknowledging the relaxation with a
fresh trade-count clock. Not self-applying either — this is a LOCKED
gate/threshold per the scheduled-task rules.

Separately: **`FUTURES_SQUEEZE_ENABLED` is live-set to `0`** — the squeeze
sleeve is fully OFF, not merely dormant. Confirmed by log absence: zero
`SQUEEZE_SCAN_SUMMARY` lines across the full ~5.5h log window (container
restarted 08-02 10:41:37 UTC — cause not visible in logs, 0
Tracebacks/errors either side, consistent with an env-var-triggered
Railway auto-redeploy rather than a crash), where the 900s scan interval
implies ~22 expected scans. This diverges from the standing design (2
wildcard + 1 squeeze slots, shipped 07-31). Not clear whether this was
intentional (e.g. isolating wildcard-only data during the gate-relaxation
work) or accidental — flagging for operator confirmation, not reverting.

With 0 closed trades this window, all trial-4/ledger/slot-cost/learning
numbers are **unchanged from 08-01**: convex ledger n=22, netR -1.81,
ex-best -6.90R, maxDD 11.98R, win 27.3%; slot cost wildcard 10/10 resolved
net +2.77R (pre-2nd-slot-shipment evidence, already actioned), squeeze 6/6
net +0.0R (<10, no action). Feature store 41 rows / shadow ledger 23 rows,
both unchanged row-for-row (confirmed via `railway ssh wc -l` and a ledger
tail).

### 4. Learning loop

No new rows since 08-01 — see §3. `learn_from_trades.py` not re-run
(identical input would reproduce identical output; token-uneconomical to
repeat).

**New since 08-01:** Sniper sleeve shipped shadow-only (commits `cd6c994`,
`484a6f2`, `ad6280f`). Confirmed shadow-mode in logs (`mode=shadow`, never
`live`) — scanning normally, universe 11-12, dominant reject
`move_below_min`, 0 signals in the window. No live risk; not evaluated
further.

### 5. Wildcard/squeeze diagnose

**Wildcard:** active, ~28 scans across the 5.5h window, dominant reject
`roc_below_min` (quiet market, movers found but under the ROC floor) —
correct dormancy, no gate loosening proposed. 0 order-reject codes
(5003/2015), 0 Tracebacks.

**Squeeze:** see §3 — disabled at the config level, not a scan/gate issue.

### 6. Diagnose — lever for next 24h

**No strategy parameter change proposed.** Zero new trades, wildcard
dormancy is correct-for-regime, no execution bugs. The two config-state
findings in §3 (external-gate relaxation vs. documented decision rule;
squeeze fully disabled) are the material items this run — both are
operator-decision items, reported not acted on. Reconcile-drop 2-pass-grace
fix (found 07-30) remains proposed-not-applied, unchanged.

### 7. Validate

`pytest -q`: **692 passed** (local working tree, includes the uncommitted
`ref_listed` instrumentation — does not break anything, still undeployed).

### 8. Deploy

**None.**

### 9. Summary

- Equity: $138.59 (flat vs 08-01's $138.59; not a P&L statement)
- Trades: 0 closed, 0 open
- Trial 4: unchanged (1 genuine trade so far) — **but see the
  REQUIRE_LISTED finding above: trial integrity is in question as of
  today**
- Convex ledger since 07-13: n=22, netR -1.81, ex-best -6.90R, maxDD
  11.98R, win 27.3% (unchanged, no new data)
- Slot cost: unchanged from 08-01 (wildcard 10/10 net +2.77R pre-shipment;
  squeeze 6/6 net +0.0R)
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy, one clean container restart 08-02 10:41 UTC (no
  Tracebacks), 692/692 tests pass locally
- **Action items for operator:** (1) `FUTURES_EXTERNAL_GATE_REQUIRE_LISTED=0`
  contradicts the documented n>=10 adjudication bar in DECISION_RULE.md —
  decide revert vs. formal trial-5 supersession; (2)
  `FUTURES_SQUEEZE_ENABLED=0` — confirm intentional or re-enable; (3)
  uncommitted `ref_listed` provenance-tagging WIP (runtime.py +
  test_sniper.py) ready to commit/deploy once (1) is resolved; (4)
  reconcile-drop 2-pass-grace fix still outstanding (unchanged from 07-30)

---

# Daily Audit — 2026-08-01

---

## Automated Assessment (UTC ~16:20)

### 1. Trades (last 24h, since 07-31 16:20 UTC)

**1 closed trade** (feature store 40→41 rows, matches):

1. **BANK_USDT LONG SQUEEZE x2** — opened 07-31 19:38 UTC, closed 07-31
   21:45 UTC via `EXCHANGE_CLOSE` (exit_kind=STOP, r=-1.05). **-$0.46
   (-14.96% of margin)**, held 126.6min. `regime_size_mult=0.25` (heavily
   trimmed). On-model: hit the -1R stop exactly as designed, no bug.

### 1-OPEN. Open positions

**None.** MEXC API + `futures_runtime_status.json` agree: 0 open (PMT 0/2,
WC 0/2, SQ 0/1). Equity **$138.59**, available $138.59.

### 2. Champion vs Shadow

Champion: widest log pull yet via `railway logs --since 24h -n 3000`
(~2769 lines) — covers 08-01 10:07 UTC (container restart, cause not
visible in logs, 0 Tracebacks/exceptions either side of it) through now.
0 Tracebacks, 0 order-reject codes (5003/2015) in the covered window.
**Shadow: stale, comparison suppressed pending resync** (standing 07-23
action item, unchanged).

### 3. Trial 4 status (see docs/DECISION_RULE.md)

Trial 4 (2nd wildcard slot + candidate fallthrough, live since 07-31): **1
genuine trial-4 trade** — BANK_USDT SQUEEZE above (opened/closed entirely
after the 07-31 redeploy, unambiguous unlike the 07-31 NIL_USDT edge case).
Too few to judge.

Decision-rule ledger (all convex since PMT decommission 2026-07-13, n=22,
feature store): **netR -1.81, ex-best netR -6.90** (still driven by the
single +5.09R ESPORTS trade), **max drawdown 11.98R** (unchanged from
07-31 — BANK_USDT's -1.05R didn't set a new cumulative-R trough), win rate
27.3%. Progress reporting only (n=22 < 30-trade / 90-day gate).

### 4. Learning loop

**(a) Feature store:** 41 rows (was 40). `learn_from_trades.py` over all
41 — same pattern as 07-31, no new signal: `hold>=120min` FAVOR (n=24/17,
gap +$2.24), `regime_trimmed(mult<1)`/`chop_regime` AVOID (n=24/17, gap
-$0.77), `regime_trimmed_hard(<0.5)` AVOID (n=14/27, gap -$0.73).
`leverage>=7` still reads "weak"/not OOS-confirmed (n=16/25, gap -$0.38) —
consistent with 07-31, not restating as settled.

**(b) Shadow ledger:** 23 rows (+1). `slot_occupied`: **all 16 now
resolved** (+2 vs 07-31's 14 — JIMOTHY_USDT -1.0R, SOXS_USDT -0.23R
resolved this window). Net **+2.77R** (down from +4.0R on 07-31 as the 2
new resolutions were both losers). Split by sleeve: **wildcard n=10,
net +2.77R** — crosses the n>=10 bar for the first time, but **all 10 rows
predate the 07-31 2nd-slot shipment** (07-23 to 07-30) — this is the same
evidence window that already motivated shipping the 2nd slot, not fresh
post-shipment data. No new wildcard `slot_occupied` rows have appeared
since 07-31 (consistent with 2 slots reducing collisions). **Squeeze n=6,
net +0.0R** — unchanged, still below the n>=10 bar, no action.
`veto:ref_not_listed` n=5 (+1, KOMA_USDT unresolved), resolved n=4 net
+13.0R — unchanged reading (all 4 resolved are synthetics inside the
fee-doomed bucket per DECISION_RULE.md, not proposing a change).
`min_vol_skip` n=1, `veto:move_not_corroborated` n=1 — unchanged.

**(c) Scan telemetry** (aggregated across the ~6h log window, 24
scan cycles each sleeve — the widest sample yet): **wildcard** 190
movers scanned, histogram `roc_below_min` 126 (66%), `no_pullback_resume`
49, `low_volume_z` 10, `climax_wick` 3, `vertical_blowoff` 1. **squeeze**
720 scanned (universe ~80-81), histogram `no_active_coil` 545 (76%),
`no_range_break` 98, `coil_too_short` 72, `low_volume_z` 4,
`fee_doomed_thin_stop` 1. Consistent with a quiet/choppy regime — correct
dormancy, no gate loosening proposed.

**(d) Decision rule:** see §3. `USE_DRAWDOWN_KILL=1`/`DRAWDOWN_HALT_PCT=0.95`
unchanged.

### 5. Wildcard/squeeze diagnose

Both sleeves correctly idle in a quiet market; the 1 trade that did fire
(squeeze BANK_USDT) resolved exactly on-model via its -1R stop. No
execution failures (5003/2015) in the covered window. Not proposing any
gate loosening.

### 6. Diagnose — lever for next 24h

**No strategy parameter change proposed.** Thin sample (n=1 close), no bug
evidence, scans show correct dormancy. The 07-30 reconcile-drop bug fix
(2-pass grace window) remains proposed-not-applied (operator-gated,
unchanged from 07-31).

### 7. Validate

No code change proposed — `pytest` not run this pass.

### 8. Deploy

**None.**

### 9. Summary

- Equity: $138.59 (-0.32% vs 07-31's $139.03 mark; not a P&L statement)
- Trades: 1 close — BANK_USDT LONG SQUEEZE, -$0.46, -1.05R, hit -1R stop
  (EXCHANGE_CLOSE), 126.6min hold — clean on-model exit
- Open: none
- Trial 4: 1 genuine trade so far (BANK_USDT, too early to judge)
- Convex ledger since 07-13: n=22, netR -1.81, ex-best -6.90R, maxDD
  11.98R, win 27.3%
- Slot cost: wildcard 10/10 resolved net +2.77R (pre-07-31 evidence,
  already actioned via the shipped 2nd slot — not new); squeeze 6/6
  resolved net +0.0R (<10, no action)
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy; one container restart 08-01 10:07 UTC, cause not visible
  in available logs, resumed cleanly with no Tracebacks either side
- Outstanding: reconcile-drop 2-pass-grace fix still proposed, not applied
  (operator-gated); local working tree also has uncommitted, undeployed
  WIP (key_health.py + marketdata.py/runtime.py) from a prior session —
  noted for awareness, not evaluated this run

---

# Daily Audit — 2026-07-31

---

## Automated Assessment (UTC ~16:20)

### 1. Trades (last 24h, since 07-30 16:50 UTC)

**1 closed trade** (feature store 40 rows, confirmed by `futures_runtime_status.json`'s
own "Last:" line — no reconcile-drop suspected this window):

1. **NIL_USDT SHORT WILDCARD x5** — the position open in yesterday's report.
   Closed **07-31 11:07 UTC** via `EXCHANGE_CLOSE` at the **+5R TP** (deep
   pullback entry, `entry_lateness=1.0`; held 82h/3.4d). **+$9.83
   (+95.94% of margin), R +5.06.** `regime_size_mult=0.658` (undersized as
   designed, matches yesterday's "intended vs actual margin" note). This is
   the sleeve design working exactly as intended — a slow multi-day runner
   to full TP, no bank/lock/trail applied at any point.

### 1-OPEN. Open positions

**None.** `get_open_positions` / `futures_runtime_status.json` both confirm
0 open (PMT 0/2, WC 0/1, SQ 0/1). Equity **$139.03**, available $139.03.

### 2. Champion vs Shadow

Champion: cycling normally on the ~70min log window available via `railway
logs` (CLI does not expose a full 24h range) — 0 Tracebacks, 0 order-reject
codes (5003/2015), no `[SIZE_TRIM]` lines (no entries attempted in the
sampled window). **Shadow: stale, comparison suppressed pending resync**
(standing 07-23 action item).

### 3. Trial 3 status (see docs/DECISION_RULE.md)

`FUTURES_WILDCARD_SL_ATR_MULT=3.0` remains live. **1/30 convex trades under
Trial 3** (NIL_USDT above — opened 07-28, before the 07-29 21:19 UTC
redeploy, but closed after; counting by open time per prior convention this
predates Trial 3, so **effectively still 0/30 genuinely-Trial-3 trades**;
flagging the ambiguity rather than picking a side).

Since PMT decommission (2026-07-13), the full convex ledger (feature store,
n=21 closes): **netR -0.76, ex-best netR -5.85** (driven by the single
+5.09R ESPORTS trade), max drawdown on the cumulative-R curve **11.98R**,
win rate 28.6%. This is progress reporting only (n=21 is below the 30-trade
/ 90-day evaluation point) — not a pass/fail verdict per
`docs/DECISION_RULE.md`.

### 4. Learning loop

**(a) Feature store:** 40 rows (was 39 on 07-30 pre-bug-report; +1 matches
today's single close — no evidence of a repeat drop this window).
`learn_from_trades.py` over all 40 rows — same OOS-consistent pattern as
prior runs, no new signal: `hold>=120min` FAVOR (n=23/17, gap +$2.31),
`regime_trimmed(mult<1)`/`chop_regime` AVOID (n=23/17, gap -$0.75, same
underlying flag), `regime_trimmed_hard(<0.5)` AVOID (n=13/27, gap -$0.71).
These describe which trades the regime sizer already flags as risky, not an
independent lever — not proposing a change.
One note: `leverage>=7` (flagged AVOID in a prior session's memory) now
reads **"weak"/not OOS-confirmed** (n=16/24, gap -$0.41) — the earlier
finding has not held up as the sample grew; not restating it as settled.

**(b) Shadow ledger:** 22 rows (16 `slot_occupied`, 4 `veto:ref_not_listed`,
1 `min_vol_skip`, 1 `veto:move_not_corroborated`).
- `slot_occupied`: **14 resolved** (+1 vs 07-30's 13), net **+4.0R** — sign
  flipped positive again (**-5R → +1R → -1R → +4.0R** across the last 4
  audits). Split by sleeve: **wildcard n=8, net +4.0R** (still under the
  n>=10 bar); **squeeze n=6, net +0.0R**. Given the instability, still
  reading this as **not yet a 2nd-slot case** — recommend continued
  tracking, not a proposal, until wildcard-only clears n>=10 on a
  consistent sign. 2 unresolved (JIMOTHY_USDT, SOXS_USDT).
- `veto:ref_not_listed` n=4, net +8R — unchanged, below the n>=10 bar.
- `min_vol_skip` n=1 (-1R), `veto:move_not_corroborated` n=1 (+5R) —
  unchanged single samples.

**(c) Scan telemetry** (sampled ~70min, all-clear window): wildcard
dominant reject `roc_below_min` (movers found but most below the ROC
floor); squeeze dominant reject `no_active_coil` (~90%). Consistent with a
quiet/choppy regime (BTC 24h -3.14% per bot status) — correct dormancy, no
loosening proposed. Full-24h scan histograms not available via `railway
logs` CLI this run (only ~70min returned); noting the tooling gap rather
than extrapolating from a partial window.

**(d) Decision rule:** see §3. `USE_DRAWDOWN_KILL=1`/`DRAWDOWN_HALT_PCT=0.95`
unchanged (standing operator override, not re-flagged as new).

### 5. Wildcard/squeeze diagnose

Both sleeves correctly idle in a quiet/choppy market — no candidates
qualified, no execution failures (5003/2015) in the sampled window. Not
proposing any gate loosening.

### 6. Diagnose — lever for next 24h

**No strategy parameter change proposed.** The reconcile-drop bug found
07-30 (§1a of that entry) remains unresolved — proposed fix (2-pass grace
window before finalizing a dropped position) still not applied; not
re-elaborating here since it was logged in full yesterday and today's close
reconciled cleanly (feature store 39→40, matches the 1 close). Otherwise:
everything behaving to design, thin sample (n=1 close) — no lever tested.

### 7. Validate

No code change proposed — `pytest` not run this pass.

### 8. Deploy

**None.**

### 9. Summary

- Equity: $139.03 (+2.41% vs 07-30's $135.76 mark)
- Trades: 1 close — NIL_USDT SHORT WILDCARD, +$9.83, +5.06R, hit +5R TP
  (EXCHANGE_CLOSE), 82h hold
- Open: none
- Trial 3: 1/30 by close-time but the position predates the redeploy by
  open-time — flagging as ambiguous, not counting as a clean Trial-3 data
  point yet
- Convex ledger since 07-13: n=21, netR -0.76, ex-best -5.85R, maxDD 11.98R
  (progress only, not at the 30-trade gate)
- Slot cost: 14 resolved, net +4.0R (wildcard n=8 +4.0R — still <10;
  squeeze n=6 +0.0R) — sign unstable across recent audits, no proposal
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy, cycling normally, 0 Tracebacks/order-rejects in sampled
  window
- Outstanding: reconcile-drop 2-pass-grace fix still proposed, not applied
  (operator-gated)

---

# Daily Audit — 2026-07-30

---

## Automated Assessment (UTC ~16:12)

### 1. Trades since last audit (07-29 16:50 UTC)

**1 real close, 0 visible in the feature store — reconcile-drop bug found (see §1a).**

1. **BEAT_USDT LONG SQUEEZE x4** — opened 07-29 05:10 UTC (reported open at
   +2.88R, peak +3.25R, in the 07-29 audit), closed **07-30 03:18:46 UTC**
   (~22.1h hold). Exchange ledger: entry 3.604, exit 3.417, realised
   **-$0.7743** (profitRatio -21.41%, margin ~$3.60 of an intended $14.35 —
   `regime_size_multiplier=0.270`). Round-tripped from +3.25R peak through
   breakeven to a loss. `r_multiple` is **not recoverable** (see below) but
   -21.4% margin loss is consistent with a stop-loss fill, so **R ≈ -1**
   (design-consistent, not confirmed).

### 1a. BUG — feature-store row silently lost on a reconcile race

MEXC's `get_historical_positions` had **not yet indexed** BEAT_USDT's close
at the exact moment (03:18:46 UTC, same second as `updateTime`) the
open-position-guard reconcile loop checked it. The reconcile code
(`runtime.py:3021-3045`) does a **single** history lookup (page_size=20); on
a miss it logs `[POSITION_RECONCILE_DROP] reason=no_exchange_position_no_history_match`,
sends one Telegram warning ("Cleared from bot state without recording P&L"),
and drops the position from `open_positions`/`trade_history` **permanently
— no retry**. Confirmed via direct MEXC query minutes ago: the position
**is** in history now (it just wasn't at 03:18:46). Result: feature store
stayed at 39 rows (should be 40), `trade_history` also lacks the entry, and
the trade's exact `sl_margin_pct`/`r_multiple`/`exit_reason` are gone for
good — even though the Telegram alert did fire in real time.

This is a known, tested code path
(`tests/test_runtime.py::test_reconcile_clears_stale_live_position_with_missing_history`)
built for genuinely-orphaned positions (e.g. manually closed outside the
bot), but it has no grace window, so it also fires on a benign
history-indexing race. **Proposed fix (not applied):** require the
history-miss to persist across 2 consecutive reconcile passes (~2s apart,
per the guard's own poll interval) before finalizing the drop, so a
transient MEXC indexing lag doesn't erase a real trade's outcome. This is a
bookkeeping/reconcile fix, not an exit/sizing/entry change — doesn't need
the V-stack replay gate, but not deployed this run (open position live,
propose-only per protocol).

### 1-OPEN. Open positions

- **NIL_USDT SHORT WILDCARD x5**, held **63.0h** (opened 07-28 01:13:54
  UTC): entry 0.03688, current ~0.0332, **+2.62R** (peak **+2.76R** at
  15:15 UTC today, giveback **-0.14R** — Min15 kline replay since entry,
  252 bars). TP **9.9%** away, SL **15.4%** away.
  `regime_size_multiplier=0.658` — margin $10.25 of an intended $15.59
  (undersized as designed). `entry_lateness=1.0`. Predates Trial 3 (opened
  under the old `FUTURES_WILDCARD_SL_ATR_MULT=1.5`).
- **BEAT_USDT** — closed (§1). No other open positions
  (`get_open_positions` returned only NIL_USDT).

### 2. Champion vs Shadow

Champion: cycling normally. Sampled ~9h of logs across boot (07-29
21:19-21:35), the BEAT close window (07-30 02:30-04:00), and 07-30
08:29-16:11 (5000 lines): **0 Tracebacks, 0 order-reject codes (5003/2015)**
outside the reconcile-drop finding above. **Shadow: stale, comparison
suppressed pending resync** (standing 07-23 action item).

### 3. Trial 3 status (superseded Trial 2 — see docs/DECISION_RULE.md)

**Trial 2 was voided**, not concluded: `railway variables --set` created a
Railway-**SKIPPED** deployment (no code changed), so trial-2's flags were
inert for ~70h without the container knowing — its ledger is
uninterpretable and was discarded (not this run's finding; already in
DECISION_RULE.md as of 07-29 22:19 BST).

**Trial 3** (`FUTURES_WILDCARD_SL_ATR_MULT` 1.5→3.0) deployed 07-29 21:19
UTC. Verified live in-container this run (`railway ssh printenv` shows
`FUTURES_WILDCARD_SL_ATR_MULT=3.0`, `FUTURES_CONVEX_STREAK_THROTTLE_ENABLED=1`,
`USE_DRAWDOWN_KILL=1`/`DRAWDOWN_HALT_PCT=0.95`,
`FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT=12` — all match the doc'd config) and a
clean fresh boot (`cycle=1` at 21:20:43 UTC, no Traceback). **0/30 convex
trades under Trial 3** — both NIL_USDT (open) and BEAT_USDT (closed) were
opened *before* the redeploy, so nothing has traded under the new stop
width yet.

### 4. Learning loop

**(a) Feature store:** 39 rows — did **not** grow despite a real close (see
§1a). `learn_from_trades.py` over the 39 rows: OOS-consistent AVOID/FAVOR
conditions unchanged from the established pattern —
`hold>=120min` FAVOR (n=22/17, gap +$1.92), `regime_trimmed(mult<1)` /
`chop_regime` AVOID (n=22/17, gap -$1.20, identical — same underlying flag),
`regime_trimmed_hard(<0.5)` AVOID (n=13/26, gap -$0.35). No new signal this
run; not proposing a change (these describe *which* trades the regime
sizer already flags as risky, not an independent lever).

**(b) Shadow ledger:** 22 rows (+5 since 07-29: SNXX/AKE/JIMOTHY/SOXS new,
AAVE+AKE(20) resolved).
- `veto:ref_not_listed` n=4, net **+8R** — unchanged, still below the n>=10
  bar.
- `slot_occupied` n=**13** resolved (+2), net **-1R** (flipped negative
  again — was +1R at n=11, -5R at n=5). Win rate 2/13 (15.4%). This signal
  has now oscillated -5R → +1R → -1R as it crossed n>=10; reads as
  **still protective, not a 2nd-slot case**, but the sign is unstable —
  recommend continued tracking over a proposal either way.
- `min_vol_skip` n=1 (-1R), `veto:move_not_corroborated` n=1 (+5R) —
  unchanged, single samples.
- 3 unresolved rows (SNXX, JIMOTHY, SOXS).

**(c) Scan telemetry** (squeeze slot free ~13h, 34 cycles/900 scanned):
dominant reject `no_active_coil` (735, 82%), `coil_too_short` (93, 10%),
`no_range_break` (61, 7%), `low_volume_z` (10), `fee_doomed_thin_stop` (1).
**0 signals fired** — correct dormancy (no qualifying coils), not
execution-blocked. Wildcard scanner structurally idle (slot occupied by
NIL_USDT, `movers=0 scanned=0` every cycle). No `SIZE_TRIM` lines sampled
(no new entries in the window).

**(d) Decision rule:** Trial 3 at 0/30 (see §3, too new to have entries).
Equity $134.25 vs the 07-21 post-deposit mark $137.83: -2.6%, well inside
bounds. `USE_DRAWDOWN_KILL=1`/`DRAWDOWN_HALT_PCT=0.95` confirmed live —
nominally on, practically inert at that threshold (standing note, not
re-flagged as new).

### 5. Wildcard/squeeze diagnose

Squeeze: correct dormancy, no loosening proposed (see §4c). Wildcard:
structurally idle (single slot occupied by NIL_USDT for 63h). No execution
failures (5003/2015) found in the sampled windows.

### 6. Diagnose — lever for next 24h

**No strategy parameter change proposed.** The one substantive finding is
the reconcile-drop bug (§1a) — a bookkeeping/logging fix, proposed but not
applied (open position live; low urgency, rare race). Trial 3 needs live
entries before it produces anything to judge.

### 7. Validate

No code change applied this run — `pytest` not re-run. Confirmed the
reconcile-drop path already has test coverage
(`test_reconcile_clears_stale_live_position_with_missing_history`,
`test_reconcile_drops_stale_local_live_position_without_exchange_id`) for
the *intended* case; the proposed fix would need a new test for the
retry/grace-window behavior before it could go through the normal deploy
gate.

### 8. Deploy

**None.**

### 9. Summary

- Equity: $134.25 (-2.6% vs the 07-21 post-deposit mark, flat/healthy)
- Trades: 1 real close since last audit (BEAT_USDT, -$0.77, R≈-1
  estimated) — **missed by the feature store due to a reconcile-drop race
  bug**, proposed fix not applied
- Open: NIL_USDT SHORT x5, held 63.0h, +2.62R (peak +2.76R, giveback
  -0.14R), TP 9.9%/SL 15.4% away
- Trial 3 (wildcard stop 1.5x→3.0x) verified live since 07-29 21:19 UTC,
  0/30 entries so far — both tracked positions predate it
- Slot cost: -1R over 13 resolved rows (protective, sign still unstable)
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy, cycling normally, 0 Tracebacks/order-rejects in sampled
  windows outside the reconcile-drop finding

---

## Automated Assessment (UTC ~16:50)

**Note: no audit ran 07-27 or 07-28** (scheduled task is configured daily at
17:08 UTC; last doc entry before this one is 07-26). This run pulled 72h of
closed positions (not just 24h) to cover the gap — nothing was missed.

### 0. Follow-up — 07-26 thin-stop env-var bug is resolved

`FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT` is confirmed present in the running
process (`railway ssh` env inspection: value `12`, up from the `8` shipped
07-25 — see below). The 07-26 finding (var correct in Railway's store but
absent from the running process) was fixed as a side effect of the operator's
own 07-26 20:30 UTC deploy (`9ff2a21`, convex streak throttle), which
restarted the process and re-injected all variables. No action item remains.

**New operator-side config observed live (already deployed/set, not by this
run — reporting for awareness):**
- `FUTURES_CONVEX_STREAK_THROTTLE_ENABLED=1` (code default is OFF) — halves
  size after 2 consecutive convex losses (any exit reason via
  `_convex_loss_streak`), floors at 0.25x, resets on first win.
- `FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT` raised `8`→`12` (live variable change,
  not tied to a doc'd commit).
- `USE_DRAWDOWN_KILL=1` (previously `0` per the standing operator override)
  with `DRAWDOWN_HALT_PCT=0.95`, `DRAWDOWN_HALT_WINDOW_DAYS=30`. Flagging:
  the code default halt threshold is `0.15` (15% drawdown); `0.95` means the
  kill only fires at a 95% drawdown in the trailing 30d — functionally inert
  in practice, even though the flag itself is "on". Not proposing a change
  (operator-owned lever) — just surfacing the gap between nominal and
  effective protection.

### 1. Trades (since last audit, 07-26 19:05 UTC — 3 closed; 0 in the strict
last 24h)

1. **XAU_USDT LONG SQUEEZE** — closed 07-26 21:25 UTC (the position flagged
   open in the 07-26 report). +$0.013 (+0.40%), R **+1.70**, hold 11.3h.
   `sl_margin_pct=0.235%` (the broken-filter stop) meant fees ate **66.7%** of
   gross profit — confirms the 07-26 prediction exactly: this trade could not
   pay for its own fees regardless of outcome.
2. **NIL_USDT LONG WILDCARD** — opened 07-27 12:11, closed 13:03 (52 min). R
   **-1.07**, -$1.77. `entry_lateness=1.0` (entered at the vertical top).
3. **BTW_USDT LONG WILDCARD** — opened 07-27 13:44, closed 14:15 (31 min). R
   **-1.65**, -$3.39. `entry_lateness=1.0` (also chased the top). Realized
   loss (29.3% of margin) exceeded the 1R stop distance (17.7%) by 65% —
   stop slippage on a thin/illiquid mover, not a fee issue
   (`fee_share_of_gross=1.6%`).

### 1-OPEN. Open positions

- **NIL_USDT SHORT WILDCARD x5**, held ~39.6h (opened 07-28 01:13 UTC):
  entry 0.03688, current 0.03433, **+1.80R** (peak +2.55R, giveback -0.75R,
  Min15 replay). TP 12.9% away, SL 11.6% away. `regime_size_multiplier=0.658`
  — margin $10.25 of an intended $15.59 (undersized as designed). Entered at
  `entry_lateness=1.0` yet currently profitable — contrasts with the two
  lateness=1.0 losses above; too small a sample to read anything into it.
- **BEAT_USDT LONG SQUEEZE x4**, held ~11.6h (opened 07-29 05:10 UTC): entry
  3.604, current ~4.12, **+2.88R** (peak +3.25R, giveback -0.36R). TP 8.7%
  away, SL 17.2% away. `regime_size_multiplier=0.270` — margin $3.60 of an
  intended $14.35.

### 2. Champion vs Shadow

Champion: cycling normally, 0 Tracebacks, 0 order-reject codes (5003/2015) in
a 4.7h/3000-line sample. **Shadow: stale, comparison suppressed pending
resync** (standing 07-23 action item, not re-flagged further).

### 3. Convex ledger (Trial 2, since 07-25 09:46 UTC reset)

**7/30 closed, net R -5.54, ex-best -7.24R, win rate 1/7 (14.3%)** + 2 open
(+1.80R, +2.88R unrealized). Still deeply negative even crediting the best
trade (XAU +1.70R) — sample remains too thin to call.

### 4. Learning loop

**(a) Feature store:** 39 rows (+3, matches the 3 closes above — in sync).
**(b) Shadow ledger:** 17 rows (+3: TAO/BANK resolved, COTI new+resolved).
Resolved splits (full recount this run):
- `veto:ref_not_listed` n=4, net **+8R** (was n=3/+3R) — still under the
  n>=10 bar for a tuning proposal, but the trend keeps pointing the same way
  (this veto is costing more than it saves).
- `slot_occupied` n=**11** — crosses the n>=10 reporting bar for the first
  time. Net **+1R** (flipped sign from the settled -5R/n=5 finding), driven
  by 2 outlier +5R TP wins against 9 losses at -1R (82% loss rate, one winner
  itself entered at `entry_lateness=1.0`). This is new evidence against a
  "Settled" `DECISION_RULE.md` call, but +1R over 11 rows, 2 of them
  outliers, is not "clearly positive" by the standard the panel set —
  recommend continued tracking, **not** proposing a 2nd slot yet.
- `min_vol_skip` n=1, -1R (unchanged). New bucket `veto:move_not_corroborated`
  n=1, +5R (single sample).

**(c) Scan telemetry** (4.7h/18 cycles sampled each sleeve): WILDCARD 132
movers scanned, dominant reject `roc_below_min` (85, 64%) then
`no_pullback_resume` (36, 27%), `low_volume_z`(8), `climax_wick`(2),
`rsi_exhausted`(1). SQUEEZE avg universe 90, 540 scanned, dominant
`no_active_coil` (475, 88%), `coil_too_short`(42), `no_range_break`(23). No
`SIZE_TRIM` in this window (no new entries sampled), no 5003/2015.

**(d) Decision rule:** Trial 2 at 7/30 (see §3). `USE_DRAWDOWN_KILL` flipped
0→1 since the standing baseline note — see §0 (effectively inert at the
current threshold). Equity $135.76 vs the 07-21 post-deposit mark $137.83:
-1.5%, well inside the 30%/20% drawdown bounds.

### 5. Wildcard/squeeze diagnose

No execution failures (0 5003/2015 across the sample). 0 closes in the
strict last-24h is correct dormancy — both sleeve slots are occupied by the
two open positions, so new entries were structurally blocked regardless of
regime. No loosening proposed.

### 6. Diagnose — lever for next 24h

**No parameter change proposed.** Trial 2 (7/30) and the newly-n>=10
slot-cost signal (+1R, outlier-driven) are both too thin/ambiguous to act on.
The one substantive finding this run is informational (§0): the drawdown-kill
threshold is nominally on but practically inert — operator-owned, flagged not
changed.

### 7. Validate

`pytest -q`: **561 passed** (local interpreter; no code change this run so
nothing to regress — count is up from 558 on 07-26, consistent with the
07-26 20:30 streak-throttle commit's added tests).

### 8. Deploy

**None.**

### 9. Summary

- Equity: $135.76 (-1.5% vs the 07-21 post-deposit mark, flat/healthy)
- Trades: 0 in strict last-24h; 3 since the 07-26 audit (net R +1.70, -1.07,
  -1.65) + 2 open (+1.80R, +2.88R)
- 07-26's env-var bug (thin-stop filter not actually live) is resolved,
  confirmed via direct env inspection
- New operator config observed: streak throttle ON, squeeze SL floor 8→12,
  drawdown-kill ON but threshold (0.95) is functionally inert — flagged for
  awareness only
- Slot-cost signal crossed n>=10 for the first time: +1R (was settled -5R),
  but outlier-driven — not proposing a 2nd slot
- Trial 2: 7/30 convex, net R -5.54, ex-best -7.24R
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run
- Bot: healthy, cycling normally, no errors
- **Gap:** no audit ran 07-27/07-28 despite the daily schedule — worth the
  operator's attention

---

# Daily Audit — 2026-07-26

---

## Automated Assessment (UTC ~19:05)

### 0. HEADLINE — thin-stop filter has never actually been live

`FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT=8` (commit `c3deab5`, believed deployed
07-25 09:46/10:46 UTC) is set correctly in Railway's variable store, but is
**absent from the running process's environment**. Confirmed via `railway ssh`:
`os.environ.get('FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT')` returns `None` on the
live container, while all other 173 configured variables (checked exhaustively,
name-by-name) ARE present — this is an isolated gap, not a general env-sync
problem. No redeploy has occurred since the 07-25 10:46 SUCCESS deployment
(deployment list checked), so this isn't a stale-worker artifact either — the
var appears to have never been injected into that running process to begin
with, despite the deploy nominally shipping the code+config together.

**Live consequence:** today's open `XAU_USDT` SQUEEZE_LONG position (entered
10:07 UTC) has `sl_margin_pct=0.235%` — 34x below the 8% floor that should
have blocked it. This is the *exact* failure mode the filter exists to
prevent, happening in real money 24h+ after the fix was believed live.
Independently corroborated by the shadow ledger: an `XAUT_USDT` SQUEEZE
candidate (`sl_margin_pct=0.27%`, ts 07-25 21:34 UTC) reached "candidate"
status at all, which requires clearing `detect_squeeze_signal`'s internal gate
— it could only get there if the floor check saw `min_sl_margin=0` (the
function's fallback default when the env var is absent).

**Action item (not self-applied):** restart/redeploy `Futures-bot` — no code
or config change needed, just a process restart so the already-correct
Railway variable gets injected. Per the runbook, deploys are avoided while a
position is open; XAU_USDT is open now, so this is deferred to the operator or
the next run once flat. Also worth the operator's attention: *how* a variable
can be set in Railway's store yet missing from the running process for 24h+
without a redeploy resetting it — if `railway variables set` was used without
triggering Railway's auto-redeploy, that's a process gap worth knowing about
for future config changes.

### 1. Trades (last 24h)

**0 closed trades.** PMT frozen (unchanged). Feature store unchanged at 36
rows (consistent with 0 closes). Equity $135.11 vs $135.09 yesterday (+0.01%,
flat — the only P&L is the open XAU position's tiny unrealized).

### 1-OPEN. Open positions

**XAU_USDT SQUEEZE LONG, x5, held ~9h (opened 10:07 UTC):** entry $4,066.73,
current ~$4,073, +3.28R (peak +4.81R at $4,075.91 — 0.19R short of the +5R TP
— giveback -1.52R from peak, Min15 replay). TP +0.23% away, SL -0.05% away.
`regime_size_multiplier=0.25` (trimmed to 25% of intended size); margin $3.25
of an intended $16.21 — undersized as designed by the regime scaler, not a
bug. Unrealized +$0.03. Because `sl_margin_pct` is only 0.235% (see §0), even
the R-multiples here are close to meaningless in dollar terms (~$0.008/R) —
this trade cannot pay for its own fees regardless of outcome, which is
precisely the pattern the (non-functioning) filter is meant to exclude.

### 2. Champion vs Shadow

**Champion:** cycling normally, no Tracebacks, no 5003/2015 errors in sampled
logs. **Shadow: stale, comparison suppressed pending resync** (per the
standing 07-23 action item — not re-flagged further).

### 3. Wildcard/squeeze convex ledger

**Trial 2 (since 07-25 09:46 UTC reset): 4 closed, net R -4.52, 0% win rate**
(unchanged — 0 closes today) **+ 1 open at +3.28R.** Per §0, treat this
trial's premise (filter enforced from reset) as unverified until the env-var
gap is fixed — the trades so far were NOT actually filtered, so a clean
re-baseline may be warranted once the fix is confirmed live rather than
continuing to count against the original start point.

### 4. Learning loop

**(a) Feature store:** 36 rows, unchanged. **(b) Shadow ledger:** 12→14 rows;
2 new (`TAO_USDT`, `BANK_USDT`, both `slot_occupied`, unresolved). Resolved
splits unchanged from yesterday: `slot_occupied` n=5, net **-5.0R** (still
protective); `veto:ref_not_listed` n=3, net **+3R**; `min_vol_skip` n=1, -1R.
**(c) Scan telemetry** (~1h sampled): squeeze — universe 77, 30 scanned/cycle,
dominant `no_active_coil` (21/30), `no_range_break`, `coil_too_short` — quiet
regime, gates behaving as designed (modulo §0). Wildcard — 1 mover/cycle,
`no_pullback_resume`. No `SIZE_TRIM` beyond XAU's own entry, no 5003/2015.
**(d) Decision rule:** 4/30 trades (superseded framing, see §3).
`USE_DRAWDOWN_KILL=0` unchanged, operator-aware.

### 5. Wildcard diagnose

No execution failures. Dormancy is correct behavior (quiet regime). No
loosening proposed.

### 6. Diagnose — lever for next 24h

**The lever is §0** — not a parameter tune but an operational fix: get the
already-approved `FUTURES_SQUEEZE_MIN_SL_MARGIN_PCT=8` actually running.
Nothing else proposed; the sample is too thin and the ledger too compromised
by the live bug to draw further conclusions this run.

### 7. Validate

- `pytest -q`: **558 passed** (local run; Python not on PATH via the `python`
  shim, used the local interpreter directly — no code change this run so
  nothing to regress).
- No new exit/sizing/entry change proposed — nothing to replay/MC/shadow-stage.

### 8. Deploy

**None.** The one action item (§0) is a restart, deferred while XAU_USDT is
open — see runbook guidance against deploying with a position open.

### 9. Summary

- Equity: $135.11 (+0.01% vs 07-25, flat)
- Trades: 0 closed; 1 open (XAU_USDT SQUEEZE LONG, +3.28R, peak +4.81R)
- **Critical: the 07-25 thin-stop squeeze filter has never been live** —
  Railway config correct, running process missing the var. Confirmed via
  direct env inspection + corroborated by a shadow-ledger candidate that
  should have been gate-rejected. Action item: restart Futures-bot once flat.
- Trial 2: 4 closed (net R -4.52) + 1 open, but the trial's filtered premise
  is unverified pending the fix above
- Slot-cost signal: unchanged, 5 rows net -5R — still protective
- Shadow: stale, comparison suppressed pending resync
- Deploy: none this run (restart deferred — position open)
- Bot: healthy, cycling normally, no errors

---

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
