# Pre-registered decision rule — CONVEX TRIAL 7 (from 2026-08-07)

Trial 6.5 CLOSED at **n=0 in-trial closes** after ~20h. Not a performance
verdict: a DESIGN defect was identified in its own trail rule by the live
BICO_USDT trade, the owner ruled ("giving back more than 100% of the built
profit is not a good design"), and the fix is a treatment change. One position
(BICO_USDT LONG, opened 08-07 08:52, peak +1.46R) migrates into trial 7 tagged
`trail_migrated=1` and is EXCLUDED from trial-7 scoreboard statistics.

## The trial-6.5 lesson (why the giveback rule died)

`exit = peak - 2R` puts the exit BELOW ZERO for every peak under 2R. Measured on
the replay panel, 20.7% of armed trades peak in [1R, 2R) — that entire cohort
could build profit and hand back >100% of it (mean banked: **-0.20R**). The live
BICO trade is the exact shape: peak +1.46R (~+$4), trail level -0.54R, a fade to
the 24h clock banks $0.

## AMENDMENT 2026-08-09 — sleeve tagging (NOT a reset)

A defect, not a treatment change: sniper positions were indistinguishable from
wildcard ones. `_open_wildcard_position` (the shared entry primitive) stamped
`wildcard: 1.0` on every convex entry with a branch only for SQUEEZE, so a
SNIPER entry (a) consumed one of trial 7's two wildcard slots, (b) inherited
the 24h clock and retention trail, and (c) announced itself on Telegram as
"WILDCARD ... Meteorite: 3h move -0.6%" — the wildcard's own trigger language
on a move that could never pass the wildcard's 8% bar.

Live consequence, AVAX_USDT SHORT, closed 2026-08-09: peaked **+1.6767R**,
closed **-0.01R / -$0.0005**. The retention floor did exactly what it promised
in R (0.30 x 1.68 = +0.50R) and still banked a loss, because the sniper's stop
is ~0.37% wide, so `cost_drag = 0.190% / 0.368% = 0.52R` per round trip. The
retention invariant is stated in GROSS R; below a ~1.7R peak the sniper's floor
sits under its own breakeven. The invariant was not violated — it was applied
to a sleeve it was never priced for.

Fix (three separations, no parameter moved):
- `_sleeve_kind()` resolves SQUEEZE > SNIPER > WILDCARD > PMT from specific
  markers instead of the shared flag; `metadata["sniper"]=1.0` is now stamped
  at open. Slot counting, the entry message and the feature-store `sleeve`
  column all read it.
- Convex exits (24h clock, retention trail) apply to WILDCARD and SQUEEZE only.
- SNIPER is exit-governed by its exchange-side SL/TP alone: it opts out of the
  PMT profit-lock/micro-lock stack too, whose triggers are also margin-percent
  denominated (micro-lock arms at 2.0% margin = +0.42R on a 4.8% sniper stop —
  still under its 0.52R cost). Excluding it from convex without this would have
  moved the defect, not removed it.
- Cost floor added to `_convex_runner_trail_exit` regardless of sleeve: the
  retention floor is raised to `1.5 x cost_R` and suppressed entirely when that
  exceeds the peak. Inert on wildcard geometry (16% stop -> cost 0.012R).

**Scoring impact.** Trial 7's counter is 30 WILDCARD closes; no wildcard close
is invalidated. The sniper study restarts its 25-fill count from this deploy —
its 5 prior fills (SOL +$0.034, SUI -$0.096, DOGE -$0.032, SOL -$0.052, AVAX
-$0.0005) ran under exits the sleeve was not designed for and are VOID as
fill-quality evidence. Slot contention is a live confound on the wildcard arm
for the pre-amendment window: whenever a sniper was open, capacity was 1/2 not
2/2. Recorded, not corrected.

## Changes under test in trial 7

**Treatment (the reset):**

1. **Retention trail** replaces the giveback: arm at +1R (unchanged), exit floor
   = `FUTURES_CONVEX_TRAIL_RETAIN_FRAC x peak_R` (default **0.30**), ratchet-
   only. Exit reason `CONVEX_RETENTION_TRAIL`. Legacy giveback reachable for
   rollback via `FUTURES_CONVEX_TRAIL_RETAIN_FRAC=0`.
   INVARIANT, by construction: once armed, an exit is never below +0.3R —
   a trade can never give back more than 70% of its best profit.
   Measured price of the invariant (444 identical entries, adversarially
   re-simulated to 4 decimals; independent Min60 proxy agrees): **zero** —
   +0.030R/trade vs giveback (t_day 0.83, family-wise p 0.55 = noise), TP
   completion 7.4% -> 7.0%, dead-zone banking -0.20R -> +0.43R,
   P(armed exit <= 0) 35.6% -> 0.5% (residual = gap-throughs).
   0.30 is PRE-REGISTERED, not measured-optimal: 0.25-0.50 is one statistical
   plateau (one panel picks 0.30, another 0.50). Fallback 0.25 ONLY if
   tripwire 3 fires at n>=100. Every retain >= 0.35 measured monotonically
   worse (0.70 collapses TP completion to 0.9%): runners outnumber dead-zoners
   1.4:1, so "keep more" measurably backfires. DO NOT RAISE RETAIN ON A FADE.
2. **`FUTURES_WILDCARD_RISK_TARGETED` default ON** (was default OFF, shipped
   2026-08-07): every wildcard trade risks ~1.87% of balance, making $ = R x
   ~$2.66. Median-neutral dispersion fix (CV 19.5% -> 4.8%); bundled so the
   owner's dollar framing and the R machinery become the same number. The exit
   rule is R-denominated, so trail attribution is unaffected by this bundling.

**Rejected in the same investigation (do not resurrect without new evidence):**

- Record lock ("best 3 in history"): harmful at every window (N=10: -62R,
  t -2.32); at the real history size (~9-16 closes) the 3rd-best threshold is
  <= 0 with 37% probability. The de-noised +3R bank FLIPPED NEGATIVE cross-panel
  (-0.058R, t -1.42) — a sweep-max artifact. Retest only past ~100 same-regime
  closes; peak_r/exit_rule/pnl are already logged per close for exactly that.
- Average-arm: trailing form death-spirals (the rule's own scratches drag the
  average down); fixed arm=2R breaks the invariant on the BICO shape itself.
- Market-trend / time-ramp overlays: 20 pre-registered cells, all between
  -0.045 and +0.007R; the three trend definitions disagree on SIGN; fourth
  consecutive regime-conditioning null in this project (prior fw p 0.988).
  The 23h59 fade nightmare is already fixed by the floor.

**Carried forward unchanged:** long-only, 2 slots, 3.0xATR stop capped at 20%
of margin, +5R TP, 24h convex time stop (trail checks before clock), crypto-only
band, sigma trigger OFF.

## Pass criteria (30 WILDCARD closes or 90 days; migrated positions excluded)

1. **Net R > 0** after fees. 2. **Still > 0 after dropping the best trade.**
3. **Max drawdown < 30%**, flow-adjusted. 4. **Every close names its exit rule.**

## Watch items / tripwires (error rates stated, per the trial-6.5 critique)

| # | metric | expect | tripwire | false-alarm | miss |
|---|---|---|---|---|---|
| 1 | armed close <= $0 net, no gap flag | ~0 by construction | any single occurrence -> bug, halt | ~0% | ~0% (tests code, not edge) |
| 2 | retention-exit net bank | >= +0.15R each | any below without gap flag -> fill quality | ~0% | ~0% |
| 3 | TP completion | ~7% | 0 TPs in 30 closes -> NOTE only; decisive at n~100 | 11% | ~45% vs true 2% — weak, indicative |
| 4 | arm rate | 40-50% of closes | < 25% at n=30 -> entry stream differs from replay | ~1.5% | ~25% vs true 20% |
| 5 | gap-through share of armed exits | 0.5-8% | > 3 of first 20 -> move floor server-side |
| 6 | retain | 0.30 fixed | no retuning before 50 closes; 0.25 only via tripwire 3 at n>=100 |

## Honest limits

- Nothing here is an edge claim. The retention rule's +0.030R is family-wise
  noise; it ships because the INVARIANT is owner-specified and measured free.
- Replay panels run 6-10x live signal density on a survivorship-biased
  universe: only DIFFERENCES and path-shape properties transfer, never levels.
- BICO at deploy: floor becomes 0.30 x 1.4558 = +0.437R (~+$1.2-1.4 banked on
  a full fade vs $0 under trial 6.5). No instant close unless price is already
  below +0.44R at deploy. Tagged migrated; excluded from the scoreboard.

---

# ARCHIVED — Pre-registered decision rule, CONVEX TRIAL 6.5 (from 2026-08-06)

Trial 6 amended on day 2 at n=1. Same treatment structure, two exit VALUES
corrected: `FUTURES_CONVEX_TIME_STOP_HOURS` 6 -> **24** and
`FUTURES_CONVEX_TRAIL_GIVEBACK_R` 1.0 -> **2.0**. Everything else unchanged
(long-only, trail arm +1R, short-TP clamp, crypto-only scan, sigma trigger
still default-OFF). Called 6.5 rather than 7: the treatment is the same
mechanism set with different constants, and the amendment happened before the
trial accumulated a scoreable sample.

## Why the amendment — recorded meticulously

**The 6h clock was sized on the wrong policy.** The justification written into
`_convex_time_stop_exit` was the decay-curve result "-0.26R at 48-72h, t_day
-2.07". That figure is real and reproduces to 3 decimal places — but it scores a
STOP-ONLY, NO-TAKE-PROFIT position, which this bot has never held. Scoring the
IDENTICAL signals with the live +5R bracket attached flips the same 72h horizon
to **+0.123R**. Both prior "opposing facts" were true; they measured different
policies.

**Measured on the live stack** (598 LONG full-stack signals, 346d PIT band,
detector validated 7022/7022 bar-for-bar against `detect_wildcard_signal`,
trail on): mean net R by clock — 6h +0.139, 24h +0.214, 48h +0.223, 72h +0.242.
The 72h-6h difference is +0.103R at day-clustered t **+2.00** (family-wise
p 0.059 — the strongest inferential result this project has produced), with
0/12 leave-one-month-out sign flips, 0/126 leave-one-symbol-out, surviving a
top-3-trade haircut, and LARGER with June 2026 removed.

**Tail destruction as shipped:** TP completion 19.6% (hold-to-stop) -> 1.8%
(trial-6 stack). Of 121 eventual +5R completions the shipped stack booked 11.
The 6h clock captured 23% of +5R completions; 24h captures 54%.

**Why 24h and not 48h/72h/none:** R keeps improving with horizon but DOLLARS do
not — on the realistic 2-slot book with the streak throttle live, 48h is -$5.1
and 72h +$3.4 vs 24h +$24.0, because the throttle downsizes exactly the
clustered trades a longer hold rescues. 24h is the middle of a broad R plateau
where the dollar reading is least hostile. A finite clock is retained as the
backstop against stale positions / dropped stops / halts, which replay cannot
model.

**The giveback was the bigger lever and the instinctive fix was backwards.** At
arm=1R/give=1R, a trade arming at exactly +1R trails at exactly 0R by
construction — the live HFT trade (+1.07R peak -> +0.03R exit) was that floor
case, not an anomaly. Tightening to 0.5R HALVES mean R (0.185 -> 0.096);
widening is monotone-better across a 221-cell surface (0.25R $93.5 / 1.0R
$152.7 / 2.0R $228.7, throttled). The trail, not the clock, was the dominant
tail-truncator: it cut +5R completions from 121/598 to 50/598 (59% of the tail)
vs the clock's 23%. At give=2R the trail is inert below a +2R peak — protects a
genuine runner, never scratches a marginal one.

**The two levers are SUBSTITUTES** (clock alone +$15.8, giveback alone +$19.3,
both +$24.7 — sub-additive). Expected joint effect ~+$25/346d at $140.64, CI
[-$106, +$159]. **NOT AN EDGE CLAIM** — family-wise p for the chosen cells is
0.29-0.49. This retires an unsupported number; it does not establish its
replacement.

**Corrections to trial-6 claims, recorded:** "0 of 100 +5R captured at 6h" did
NOT replicate (three independent replays: 19-24% captured; earliest touch
1.0-1.5h, not 8h). "85% of +5R in June 2026" did NOT replicate (14-31%).
The trail is NOT a scratch machine in general (median trail exit +0.68 to
+0.84R net; only 1-12% at/below zero) — the HFT case was the parameterisation's
floor, now removed.

## Pre-registered expectations for trial 6.5 (write-down before looking)

- Exit mix near **7-11% TP / 49-60% stop / ~30% trail-or-clock**; mean hold
  ~8.4h; slot blocking ~11%.
- If live TP completion stays under ~4% over 20+ closes, the trail is firing far
  more aggressively than replay models and the giveback change did not take.
- If the exit mix shows >70% CONVEX_TIME_STOP, 24h is too tight for the fills
  actually taken.

## FREEZE

This is the FOURTH treatment change in six days (trial 5 -> 6 -> 6.5). The
convex sleeve is now **frozen for the full trial window** — 30 wildcard closes
or 90 days, whichever first, per the unchanged pass criteria below. Known
remaining defects (SOXS/EWY in the band via the blocklist gap; the $75
margin-budget fallback; hard dollar loss-limits parsed but unenforced) are
measurement/correctness items that may ship WITHOUT resetting the trial only if
they do not alter which trades are taken or how they are managed; the SOXS/EWY
universe fix DOES alter the tradeable set and therefore WAITS for the trial
boundary unless a position in an affected symbol actually opens.

## Open data-integrity item (gating future horizon work, not this trial)

Two replays of the identical no-TP policy return -0.266R (n=277, 70 symbols)
and +0.389R (n=598, 144 symbols) — 0.65R apart on the same claimed detector.
Density checks favour the larger panel, arrival-rate checks favour the smaller.
Until one signal stream is rebuilt and reconciled against the live entry log,
every horizon-level number above is provisional; the DIRECTION of the 6.5
changes does not depend on which stream is right (the ordering 6h-worst holds
in both), but the magnitudes do.

---

# ARCHIVED — Pre-registered decision rule, CONVEX TRIAL 6 (from 2026-08-05)

Trial 5 CLOSED the same day it opened, at **n=0 closed trades**. Not a
performance verdict — a structural one. Five defects were measured during it
that make its premise untestable, so continuing would have spent weeks
generating data about a mis-specified sleeve. See the closure record below.

## Trial 5 closure record

**Result: n=2, both LONG, both profitable. Net +$2.101.**

Both positions were still open when the trial was called; both were then closed
by the bot's own new 6h clock on the first monitor cycle after the trial-6
deploy (2026-08-05 22:25 UTC). No position was closed by hand.

| symbol | lev | entry | exit | held | gross | fees | **net** | on margin |
|--------|-----|-------|------|------|-------|------|---------|-----------|
| BICO_USDT | x2 | 0.02352 | 0.02734 | 17.2h | +$1.348 | $0.014 | **+$1.334** | +32.14% |
| BTW_USDT | x2 | 0.1475 | 0.15541 | 11.3h | +$0.791 | $0.024 | **+$0.767** | +10.40% |
| | | | | | **+$2.139** | **$0.038** | **+$2.101** | |

Account after: equity **$140.65**, available $140.65, open margin $0.00,
positions 0. Both closes recorded `exit_reason=CONVEX_TIME_STOP`.

Two things this tiny sample illustrates rather than proves. **(a)** Both winners
were on symbols where the fixed 8% trigger is near-noise (BTW is the band's most
extreme case at ~1.0 sigma), so trial 5's two profitable trades are not evidence
the trigger works — they are evidence the sleeve can profit *despite* it.
**(b)** BTW was +7.76% when the trial was called and +5.36% when the clock
closed it ~2h later; the giveback is exactly the behaviour the 6h clock exists
to bound. n=2 either way — do not read either as a result.

**Why it was closed early — measured, in order of severity:**

1. **The trigger is not a trigger.** `|3h ROC| >= 8%` is a FIXED percent, so it
   spans **~10-32x in event rarity** across turnover rank 30-90 (1.04 sigma on
   BTW, 33.6 sigma on SPY; ~10.1x crypto-only). **24% of band symbols never
   breached 8% in 83 days** — they cannot fire. **5 symbols supply 50% of all
   band signal**, and on those 8% is 1.0-1.3 sigma, i.e. routine: BTW breached
   8%/3h on **19.2% of ALL its 3h bars**. Both trial-5 positions were opened on
   such symbols. The sleeve believes it applies one rule; it samples a different
   population per symbol.
2. **21% of short signals had a mathematically unreachable target.** At the
   deployed 3.0xATR stop, `tp = entry*(1 - sl_frac*5)` with `sl_frac >= 0.20`
   puts the short's take-profit at or below **price zero**, silently converting
   those trades to stop-or-nothing.
3. **The clock was wrong.** Edge half-life ~4h, zero-crossing ~8h, and
   **-0.263R at 72h (day-clustered t -2.07)** — the ONLY result in the whole
   programme that survived era-split, leave-one-symbol-out AND a top-3-trade
   haircut. Live median hold was ~11h, so the sleeve routinely paid to hold
   positions whose edge had expired. Both open positions were past it.
4. **Slot starvation was a hold problem, not a slot problem.** Hold-to-stop
   blocked **39%** of incoming signals; a 6h cap blocks ~10%, at zero capital.
5. **The ledger could not identify its own trades.** No sleeve tag, and **0 of
   226 rows** recorded which exit rule fired. Every per-sleeve attribution in
   this project has been an inference from six symbol names.

**Corrections recorded (things this project believed that are false):**

- `1/(1+k)` is the WRONG null for this bracket. Arithmetic barriers are
  asymmetric in log space and a finite horizon truncates far-target hits: the
  true driftless null at +5R is **8.25%**, not 16.7%. Measured hit rate 14.9%.
  Every "below fair value" statement scored against 16.7% was scored against a
  null roughly double the correct one.
- Break-even at +5R is **16.98%** with the corrected cost, not 16.7%.
- `contract/detail` reports `takerFeeRate = 0` on 56/73 band symbols. **False** —
  realised fills pay 1.00x listed, **0.0672%/side**. `cost_drag = 0.190%/sl_frac`.
- "0 of 65 wildcard shorts ever completed +5R" — **false**. `daily_audit.md:597`
  NIL_USDT +5.06R; `daily_audit.md:1472` BILL_USDT +4.43R.
- "A random entry beats the wildcard signal" — **false**, a look-ahead artifact.
  Controls drawn from bars BEFORE the signal bar beat it by +1.624R (t +15.66);
  controls drawn AFTER it are a dead heat (-0.025R, t -0.26).
- "Cap leverage at 6 to cut fees" — **withdrawn**. `fee/margin == 2*rate*lev` is
  an identity (R^2 = 1.0000), not a finding, and capping 20->6 would silently
  TRIPLE every margin-%-denominated exit threshold. If less risk is wanted, cut
  `balance_fraction` and say so.

## Changes under test in trial 6

**Treatment changes (these are why the trial resets):**

1. **`FUTURES_WILDCARD_LONG_ONLY=1` (new, default ON).** Shorts are still
   DETECTED and shadow-logged as `side_disabled`; they are simply not taken.
   Filtered AFTER the candidate list is built, never inside the detector —
   `_shadow_log_untaken` only fires on objects that reached that list, so a
   detector-level reject would produce zero shadow rows and destroy the question
   permanently. Rationale: a short's payoff is bounded at `1/sl_frac` (price
   cannot go below zero) so the convex +5R design is structurally a LONG-side
   design; the measured target ladder is monotone UP in k for longs
   (+0.021 -> +0.250) and monotone DOWN for shorts (+0.077 -> +0.020). The
   shadow ledger accrues ~3.8x faster than the book, cutting the horizon to
   settle the short question from ~6.7 years to ~1.8.
2. **`FUTURES_CONVEX_TIME_STOP_HOURS=6` (new).** Hard clock on convex positions,
   per defect 3. Pre-registered as **removal of a measured negative tail and a
   throughput gain, NOT as an edge claim** — expected value ~$38/yr.
3. **`FUTURES_CONVEX_RUNNER_TRAIL=1` (new, default ON), arm +1R / give back 1R.**
   A CAPACITY change: measured expectancy-neutral (paired -0.035R, t -0.35) but
   win rate 22.8% -> 51.6%, median trade -1.02R -> +0.05R, mean hold 27.3h ->
   8.5h, ~2.5x return per slot-day after a top-3 haircut. It does not bank early
   and does not cap the runner.
4. **Short take-profit clamped** (`FUTURES_WILDCARD_MAX_SHORT_TP_DIST=0.50`), per
   defect 2. Inert while long-only is on; correctness fix regardless.

**Available but DEFAULT OFF (arm only with a shadow comparison in hand):**

5. **`FUTURES_WILDCARD_SIGMA_TRIGGER=0`** — replaces the fixed 8% with
   `|ln(1+roc)| / EWMA(0.94) sigma_3h >= FUTURES_WILDCARD_MIN_ROC_Z` (4.0),
   sigma floored at 1.0% and computed STRICTLY TRAILING (the final 12 returns
   are dropped so the move cannot inflate its own yardstick).
6. **`FUTURES_WILDCARD_TP_FROM_DESIGNED_STOP=0`** — anchors the target to the
   pre-margin-cap stop distance. Off by default because it breaks the identity
   `target == tp_r x realised-R` that every R-based report assumes.

**Measurement only (does NOT reset a trial, per the 2026-07-31 standard):**

7. `sleeve`, `exit_rule`, `hold_hours`, `equity_at_close_usdt`, `roc_z`,
   `sl_frac_designed` and `peak_r` recorded on every close; `roc_z`,
   `sl_frac_designed` and `equity_at_open_usdt` recorded at open. `roc_z` is
   logged **even while the sigma trigger is OFF**, so the conditional-expectancy
   engine can settle roc-in-sigma vs roc-in-percent from REAL fills rather than
   from anyone's backtest.
8. Wildcard scan fetches 7d of 15m bars instead of 15h (`FUTURES_WILDCARD_SCAN_BARS=672`).
   The detector reads only the tail, so the SIGNAL is unchanged — but the sigma
   estimator needs >=96 trailing 3h returns and 60 bars can never supply them.

## Pass criteria (evaluated at 30 WILDCARD trades or 90 days)

Scored per sleeve, never blended.

1. **Net R > 0** after fees.
2. **Outlier-robust:** net R still > 0 after dropping the single best trade.
3. **Max drawdown** from the window's peak **< 30%**, flow-adjusted.
4. **Every close attributable to a named exit rule** — now actually checkable,
   because `exit_rule` is recorded.

Pass -> fund to a size where the edge pays for the effort.
Fail -> shut the sleeve down. No extending the window to chase a verdict.

## Watch items for trial 6

- **Shorts blocked**: `shorts_blocked` in `[WILDCARD_SCAN_SUMMARY]` and
  `side_disabled` rows in the shadow ledger. If blocked shorts resolve clearly
  positive over >=20 rows, long-only is wrong and must be revisited.
- **Time-stop bite rate**: what fraction of closes are `CONVEX_TIME_STOP`. If it
  is >70%, 6h is too tight for the fills actually being taken.
- **Trail vs stop**: `CONVEX_RUNNER_TRAIL` closes should REPLACE stop-outs, not
  take-profits. If TP completion falls, the trail is capping runners and the
  giveback must widen.
- **`roc_z` distribution at entry**: if live entries cluster below z=4, the fixed
  trigger is admitting near-noise and the sigma trigger should be armed.

## HONEST LIMITS OF THIS TRIAL (recorded up front)

- **Nothing here is an edge claim.** Wildcard LONG is +0.224R at day-clustered
  t **+1.67**; its best searched cell fails a family-wise null at p=0.144. Across
  ~517 cells searched this session the largest |t| found anywhere was **2.24**
  against a null E[max|t|] of **3.25** — the whole search produced less apparent
  signal than chance would on random data.
- **Validatability is the binding constraint.** Establishing the live
  configuration's own +0.179R at t=2.8 needs ~2,100 trades ≈ **7.2 years** at
  0.8 closes/day. Trial 6 is expected to make the sleeve CHEAPER and its records
  READABLE. It is not expected to prove anything.
- **Unresolved and gating:** what actually closes live wildcard positions has
  never been reconciled (one study measured a 0.2h median live hold against the
  ~11h established elsewhere). Until `exit_rule` accumulates, the SIGN of the
  sleeve's replay expectancy is not established.

---

# ARCHIVED — Pre-registered decision rule, CONVEX TRIAL 5 (from 2026-08-05)

Trial 4 (07-13 -> 08-05) CLOSED at n=22. Not extended: the wildcard sleeve was
structurally unable to fire for its final ~106 hours (see defect #1 below), so
further waiting would have added time without adding evidence.

## Trial 4 result and what it taught

n=22, netR **-1.81**, $+4.53. Split by sleeve, which is the whole lesson:

| sleeve   | n  | netR  | win | TP completion | verdict |
|----------|----|-------|-----|---------------|---------|
| WILDCARD | 12 | +4.49 | 25% | 25% (3/12)    | keep    |
| SQUEEZE  | 10 | -6.30 | 30% | 0% (0/10)     | DISABLED |

1. **The TP watch item fired on a blended number and the blend was misleading.**
   Trial 4 pre-registered "<10% TP completion over >=15 trades -> scale TP down".
   Measured 9.1% and it triggered. But that is 25% for wildcard (above the 16.7%
   break-even at +5R/-1R) and 0% for squeeze. The correct response was to remove
   the squeeze sleeve, NOT to lower the wildcard's target. **The wildcard's +5R
   TP is retained for trial 5.** A watch item computed across heterogeneous
   sleeves can point the wrong way; trial 5 scores per sleeve.
2. **Squeeze was anti-convex**: 3 wins of +0.34/+2.53/+1.70R against losses to
   -3.79R. It won small and lost large, the inverse of the design. Disabled.
3. **Dollar P&L and netR disagreed in sign** (+$4.53 vs -1.81R). Size scaling put
   more capital behind winners. Encouraging but n=22 with two dominant trades.
4. **Process failure, recorded honestly**: the external gate was relaxed mid-trial
   on re-presented evidence and reverted the same day (see 2026-08-02 below). Net
   effect on trial 4 was zero — it was live ~8h during a drought with no signal —
   but the discipline lapse is the more important finding.

## Changes under test in trial 5

**Defect fixes (not strategy changes) — these close gaps trial 4 exposed:**

1. **`FUTURES_WILDCARD_MIN_24H_MOVE` 0.08 -> 0.03.** The pre-filter admitted a
   symbol only if its 24-HOUR change exceeded 8%, then handed it to a detector
   that triggers on a 3-HOUR ROC of 8%. A coin that runs +8% in 3h and retraces
   to +3% on the day never reached the detector. Measured live over ~45 scans:
   948 USDT pairs -> 917 in band -> ~72 pass turnover -> **7-10 pass this gate**
   -> 0 candidates, with `roc_below_min` the DOMINANT detector reject — i.e. the
   gate was admitting the wrong symbols. An independent 92h replay of the same
   detector over the same band found **48 full signals** while the live scan
   produced zero. The detector's 8%/3h trigger and all pattern gates are
   UNCHANGED; only the pre-filter widens.
2. **Atomic `_save_state`.** Was a bare `write_text` on the authoritative
   open-positions ledger, rewritten every cycle. A container kill mid-write
   truncated it, and `_load_state` cannot tell "empty" from "wrong" — the bot
   would boot with zero positions against real ones on MEXC.
3. **`_record_fill` wired into the convex entry path.** It existed since Sprint 3
   but was only ever called from the decommissioned PMT path, so the convex
   sleeves have NEVER measured a fill. This is why every capacity and cost-drag
   figure in this project rests on an assumed impact coefficient. Write-only.
4. **Equity-drawdown brake wired to the convex path**, behind
   `FUTURES_CONVEX_DRAWDOWN_BRAKE` (**default OFF**). `_drawdown_size_multiplier`
   was likewise PMT-only, so the convex sleeves ran all of trial 4 with no
   drawdown protection — the streak throttle counts consecutive losses, which is
   not the same thing as being deep in an equity hole. Observe first, arm later.

**Carried forward unchanged from trial 4:** 2 wildcard slots, 3.0xATR stop, +5R
TP, -20% margin cap, external gate at `REQUIRE_LISTED=1` (the pre-registered
state), squeeze disabled.

## Pass criteria (evaluated at 30 WILDCARD trades or 90 days)

Scored **per sleeve**, never blended — see lesson 1.

1. **Net R > 0** after fees.
2. **Outlier-robust:** net R still > 0 after dropping the single best trade.
3. **Max drawdown** from the window's peak **< 30%**, flow-adjusted.
4. **No unexplained behaviour:** every close attributable to a designed exit.

Pass -> fund to a size where the edge pays for the effort.
Fail -> shut the sleeve down. No extending the window to chase a verdict.

## Watch items for trial 5

- **Fill slippage** (newly measurable): if realised slippage exceeds ~10bp per
  side, the cost model behind every capacity estimate needs re-deriving.
- **Funnel counts**: `move24h_ok` should rise materially from 7-10. If candidates
  remain 0 at the looser gate, the leak is downstream and this fix was wrong.
- **Drawdown brake**: shadow-observe for 2 weeks before arming.

---

# ARCHIVED — Pre-registered decision rule, CONVEX TRIAL 4 (from 2026-07-31)

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

### 2026-08-02 — the gate WAS relaxed, contradicting the decision above
`FUTURES_EXTERNAL_GATE_REQUIRE_LISTED=0` was set on Railway and deployed. The
justification given at the time was a shadow-ledger read-out showing
`veto:ref_not_listed  resolved=4  cfR +8.00`.

That is the SAME +2.00R-mean signal this section had already inspected and
rejected, recomputed and re-presented as if new. The four rows are the synthetic
products named above — the fee-doomed bucket the squeeze filter blocks
independently. Adjudication threshold at the moment of the change: **>=10
resolved real-alt rows required, 1 logged (KOMA_USDT, still unresolved), 0
resolved.** The change was made at effectively zero of the evidence its own
pre-registered rule demanded.

Mitigation shipped the same day: every convex entry now carries a `ref_listed`
tag (1.0 corroborated / 0.0 MEXC-only / absent = gate off or fetch failed),
written to position metadata and to the feature-store row. Trial 4 can therefore
be scored **with and without** the population the relaxation admits, so the
window is recoverable rather than contaminated. Zero affected trades had
occurred when the tag shipped — the entire trial-4 population to date predates
the change.

RESOLVED same day: **reverted to `REQUIRE_LISTED=1`** and verified inside the
running container. Net effect on trial 4: **zero** — the relaxation was live for
roughly 8 hours during a market drought in which no wildcard signal fired, so no
trade was taken under the altered rules and the trial-4 population is entirely
pre-change. The `ref_listed` tag stays: it is useful telemetry regardless, and it
is what made the revert a free choice rather than a judgement call.

Standing rule reaffirmed: a pre-registered threshold is not satisfied by
recomputing evidence the same document already inspected and rejected. The
adjudication bar for this gate remains **>=10 resolved REAL-ALT veto rows**
(currently 1 logged — KOMA_USDT — 0 resolved). The instrumentation fix that
logs every candidate rather than only the top-ranked one is working and will
accumulate those rows on its own.

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
