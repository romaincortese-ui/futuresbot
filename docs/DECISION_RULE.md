# STANDING OBJECTIVE (owner directive, 2026-08-10)

**Every change is justified by expected $ P&L.** Not R, not coverage, not
signal count, not elegance. Before proposing a change, state: the $ per trade,
the trades per month, and the edge assumed. If the answer is "under $10/month
either way", say so and drop it.

The arithmetic that governs it, at the time of writing:

| | |
|---|---|
| 1R | **$4.09** (2026-08-29: `risk_pct x equity` = 2.41% x $169.6; $11.30 at the gated $469 funded size). Was $2.66 at 1.87% x $142. The risk dial makes this identical on EVERY symbol, so "that market is too small to be worth trading" is not a valid objection in this design |
| entries | ~2.6/day in replay at 3 slots; live slower. Slot-capped by `FUTURES_WILDCARD_MAX_POSITIONS=3` x the 24h clock |
| monthly envelope | **-$11 to +$22** at 21 trades; **-$32 to +$64** at 60, for edges of -0.2R to +0.4R |

**The uncomfortable consequence:** at this account size no change moves
materially more dollars. More trades widens the envelope in BOTH directions —
it does not tilt it. Only a positive per-trade edge tilts it, and after seven
trials that edge has never been scored.

Therefore the highest-$ work is whatever shortens **time-to-verdict**, because
a proven +0.4R/trade is +$64/mo at $142 and +$450/mo at $1,000. Widening the
funnel on an unmeasured edge is not a P&L improvement; it is a variance
increase wearing one's clothes.

---

# PRE-REGISTERED DECISION RULE — CONVEX TRIAL 19

**Opens AFTER the funded week closes and the withdrawal completes**, not before.
Written 2026-09-03, while trial 18 is still running, so the rule exists before
its data does.

## The change: ONE env var

    FUTURES_TREND_MAX_POSITIONS=2  ->  3

Nothing else. Not the universe, not the trigger, not the clock, not the stop,
and nothing on WILDCARD.

## Why this and not something better

Because after a week of measurement there is nothing better, and this is the
only candidate that clears the screen without diluting per-fill quality.

**Everything else was tested and refuted**, most of it this week:

| refuted | measurement |
|---|---|
| TREND universe expansion | `$/fill` collapses 0.999 -> 0.215 adding 8 majors |
| TREND trigger 4% -> 5% | -$2.24; the band effect is real but reshuffling eats it |
| TREND trigger -> 3% / 48h | ex-top-5% -$12.59; supersedes the 2026-08-27 cell |
| TREND stop width, 0.25x-2.0x | live 3.0x is the peak on all three axes |
| lower trail arm 0.9R-0.4R | winners cut short outnumber losers rescued 2-3x |
| 17 regime formulations | all fail the placebo control |
| convex -> squeeze switch | squeeze marginal contribution -$1.15 |
| entry price-context scoring | 13 features, two sleeves, nothing at 2 SE |
| WILDCARD trigger 8% -> 7% | +$5.54/month, mechanism unexplained, still OPEN |
| TREND 0.5x risk on re-entry | as proposed (depth>=1) -$18.79; depth>=2 variant is 8 ZEC trades, tuned window |
## TRIAL 19F — PRE-REGISTERED 2026-09-08 18:18 UTC, BEFORE THE FLAG WAS SET

**Written before the env var was changed. If any line below is edited after a result
is seen, the trial is void.**

### The change, in full

    FUTURES_WILDCARD_EARLY_STOP_R        0.0  ->  0.5
    FUTURES_WILDCARD_EARLY_STOP_MINUTES  (unset, default 30)  ->  30
    FUTURES_TREND_EARLY_STOP_R           (unset)  ->  0.0     explicit, belt and braces
    FUTURES_TRIAL_LABEL                  18F -> 19F
    FUTURES_TRIAL_START_TS               1788519433 -> 1788891501

Nothing else. Not the arm, not the retention, not the ratchet, not the universe,
not the slots, not the risk.

### What it does

On WILDCARD positions only: exit at market if the trade reaches -0.5R within the
first 30 minutes. After 30 minutes the ordinary -1R stop applies unchanged.

### The baseline it is measured against

Trial 18F closed at **9 closes, -$47.56**: TREND +$35.72 over 5 fills, WILDCARD
**-$83.27 over 4 fills (MAGMA -26.45, FORM -25.76, PONS -19.41, MARSCOIN -11.65)**,
every one a stop-out. Trial 18F's primary criterion (mean realised risk per trade
in [1.6%, 2.2%]) was **PASSING at 2.018%** when it closed.

### THE PRE-REGISTERED KILL. Either condition, immediately, no discussion.

1. **Two cut trades whose peak before the cut was >= 1.0R.** `/report` prints this
   as "cut above 1R". A fire on a trade that had already been meaningfully positive
   is the failure mode; two of them is not bad luck.
2. **After 20 fires, the running dollar delta against the logged counterfactual is
   negative.** The rule needs a **>=33% save rate** to break even and delivered 78%
   in sample (12 helped, 2 harmed). Below 50% over 20 fires it is dead.

Rollback is `FUTURES_WILDCARD_EARLY_STOP_R=0`, one variable, seconds.

### Pass criteria (30 WILDCARD closes, or 45 days, whichever first)

1. **PRIMARY: the running delta against the counterfactual is positive at n>=20
   fires.** Not "the sleeve made money" — the sleeve's own edge is a coin flip and
   this trial is not testing it. It is testing whether cutting early beats not
   cutting.
2. Cuts above 1R peak: **zero or one** across the whole trial.
3. Mean realised risk per trade stays in [1.6%, 2.2%] — the standing sizing
   criterion, unchanged and independent of this rule.
4. TREND is untouched: zero `CONVEX_EARLY_STOP` exits on a TREND position. Any
   single one is a defect, not a result.

### What would make me call it a false positive even if it passes

The result rests on **X = 0.5 having been a prior**, chosen from the shape of four
trades before any grid was swept. Walk-forward refitting X **loses** (-$32 to
-$54/mo). **X MUST NEVER BE REFIT.** If this trial passes and the temptation
arises to tune X from its own fires, that is the exact move the evidence forbids.
Only T may be tuned, and only after n>=30.

### The honest odds going in

Bootstrap 95% CI **[-$47.81, +$218.93]**, **P(delta <= 0) = 0.095**, grid-corrected
permutation **p = 0.042**. The candidate's own 5x6 grid is 24 of 30 cells negative.
6 of the 25 trades that touch -0.5R inside 45 minutes went on to peak >= 2R, so
cutting a runner is a **1-in-7 recurrence**, not a freak event.

**This is a bounded bet with a positive expectation, not an established edge.**
Expected +$115/month, floor +$56/month under every pessimistic assumption stacked,
cost if wrong about **-$55/month**, and one runner cut inside the window costs
**-$138** — 1.3 months of the rule's own edge.

### Running alongside, at zero behavioural cost

The shadow diagnostic (`t_adverse_25/50/75`) records time-to-depth on **every**
convex position regardless of this flag, and is promoted into the closed record and
the feature row. It already produced its first row within minutes of deploying:
ZEC_USDT 09-08 reached -0.25R and -0.50R at **minute 95.24** — far outside a
30-minute window, and TREND, where the rule is off. That series is what will let X
be set from live fills instead of from the historical rows it was read off.

## 2026-09-08: PEAK CAPTURE — the prize is ONE TRADE, and my PONS numbers were wrong

Owner's question: PONS reached +$20.25 and closed -$19.41; how could we have banked it? Seven
agents on the feed gap, the arm x retain corner re-tested clean, and a genuine reversal detector.

### CORRECTION: BOTH PONS FIGURES I REPORTED WERE PRODUCED BY AN ARM THE BOT NEVER SAW

`runtime.py:2101-2113`: the arm is tested against `convex_peak_r`, which is **only ever written
from a poll of the live price**. PONS's `convex_peak_r` topped out at **0.9653R**. It never
reached 1.00.

**So on PONS, `arm 1.00` with retain 0.50, 0.90 or 0.95, and every ratchet variant, are
BYTE-IDENTICAL: -$19.41 in every case.** The **+$9.70** (live rule) and **+$17.80** (owner's 10%
cell) both came from arming on the Min1 traded tape at 1.0969R. **The owner's cell would not have
saved PONS.**

Re-run capped at the peak the bot actually saw:

    LIVE arm 1.00 / retain 0.50           tape +$9.70    bot **-$18.88**
    OWNER'S arm 1.00 / retain 0.90        tape +$17.80   bot **-$18.88**   <- does not save it
    arm 0.95 / retain 0.90                tape +$17.80   bot +$15.61
    arm 0.90 / retain 0.90                tape +$17.80   bot +$15.61
    $15 fixed arm / retain 0.90           tape +$17.80   bot +$15.61

**RETENTION IS NOT WHAT SAVES PONS. LOWERING THE ARM BELOW 0.96R IS.** Every cell with arm >=
1.00R banks nothing, whatever the retention.

### THE PRIZE IS ONE TRADE

From the 09-07 snapshot, 80 trades, 30 days, counted directly with no simulator:

    peaked >= $20 and closed <= 0 :  0 trades
    peaked >= $15 and closed <= 0 :  0 trades
    peaked >= $10 and closed <= 0 :  0 trades  (PONS excepted)
    peaked >=  $5 and closed <= 0 :  1 trade — ZEC 09-07, peak $9.48 at **0.4855R**, closed
                                     -$20.38. Its peak is below ANY arm >= 0.75R, so no
                                     arm-based mechanism reaches it.

**PONS is the only trade in the book's recorded history that peaked above $10 and closed at or
below zero. $37.23 in 31 days — one event.**

**AND THE REASSURING HALF, which is the real answer to "we're missing it right now."** Of the 16
trades that peaked above $5, the exit stack banked essentially all of it:

    ZEC  $75.61 -> $75.37  100%      ZEC  $9.60 -> $9.50   99%
    TUT  $18.03 -> $17.94  100%      XRP  $7.08 -> $6.79   96%
    ENA  $11.12 -> $11.11  100%      ZEC  $5.74 -> $5.72  100%
    SOL   $5.70 ->  $5.52   97%      XRP  $5.71 -> $5.84  102%

Total giveback across all 16 is $65, of which two ZEC trades are $47.

**44 trades armed. NONE closed at or below zero. Worst armed outcome: -0.0149R (AVAX, two cents).**
The 2026-08-07 retention invariant is holding perfectly. **Above the arm, the failure mode the
owner describes has never occurred.**

### THE MECHANISM THE OWNER NEEDS — his goal is right, his instrument is wrong

**The arm sets where the rule starts WATCHING. It does not set where the rule FIRES.** The floor
is `retain x peak`, re-evaluated every time the peak rises. Raising the arm to 1.0R does not make
the trail wait for a genuinely significant peak — it makes it start watching at 1.0R and then fire
at the **first 10% wobble after that**, which on the median trade is around 1.0-1.1R.

PONS only looked like a counter-example because on that one path the first 10% retrace after 1.0R
happened to land at the real top. **That is path luck**, and the base rate prices it:

**AFTER A 10% GIVEBACK, THE TRADE MAKES A NEW HIGH 93% OF THE TIME (41 of 44).**

A 10% giveback carries no information about reversal. 30 detectors tested, 27 lose money (-$90 to
-$210/mo), and the 3 positives all have ex-top-5%-by-delta of exactly **0.000** — their whole
effect is 1-4 trades.

What the owner's cell costs, named: **-$225/mo on WILDCARD, -$301/mo on the book.** On the 11
trades with peak >= 2R it banks +11.59R against the live +20.83R:

    ENA      peak 5.02R  live +4.93R : +4.96 TP    -> +0.94 TRAIL   **-$101.17**
    MAGMA    peak 5.14R  live +2.93R : +3.42 TRAIL -> +1.18 TRAIL    -$56.41
    USELESS  peak 3.52R  live +2.58R : +2.62 TRAIL -> +0.89 TRAIL    -$43.69
    TUT      peak 4.11R  live +2.71R : +2.58 TRAIL -> +0.89 TRAIL    -$42.75
    TUT      peak 5.12R  live +5.53R : +2.74 TRAIL -> +1.42 TRAIL    -$33.13

Honest counter-evidence: **one** trade would have paid — ZEC 09-06 05:55, peak $29.28, trailed out
at $11.88 (41% capture), where a 0.90 floor plausibly banks ~$26. **One for, five against.**

### TWO CONFIG TRAPS IN THE FORM I PROPOSED

1. **`runtime.py:2048-2051`: `if trigger <= 0 or high <= base: return base`.** Setting
   `RETAIN_FRAC=0.90` makes `0.75 <= 0.90` true and **SILENTLY DISABLES THE 3R RATCHET** —
   stripping the only protection the genuine runners have.
2. **Any `RATCHET_R <= ARM_R` degenerates.** "Ratchet 0.75R/0.90", "ratchet 1.0R/0.90" and "base
   retain 0.90" are **one rule with three names** and price identically. Only `RATCHET_R` strictly
   above `ARM_R` is a new shape, and the best such cell (2.0R/0.90) still loses $133-145/mo.

### THE FIXED DOLLAR ARM IS A TRAIL-DISABLE IN A DOLLAR COSTUME

A $15 arm scores **+$269/mo** on the historical book — because book risk spans $0.53 to $28.33
against a **$2.25 median**, so $15 is a **6.7R median arm**. It arms 3-5 trades of 77 instead of
36, and prices **to the cent** the same as switching the trail off entirely. Then the scale trap
closes: at the funded 1R of $25.16 the identical rule is **arm 0.60R** and prices **-$361/mo**.
**The sign inverts between the book you measured on and the account you would run it on.** On PONS
it "worked" only because PONS's 1R happened to be $18.46.

### THE ONE REAL DEFECT FOUND — and it is not the one I expected

**The exchange stop triggers and fills on LAST price while the trail measures FAIR.**
`marketdata.py` sends `/stoporder/place` with **no `priceType`/`triggerType`**, so the stop
triggers on a feed the bot never sets and never reads back. Measured: **7 of 38 stop-outs filled
at a price the fair index never printed, and 4 stopped where fair never reached -1.00R at all.**
Read the MEXC account setting before acting; this study's dollar evidence for it is one ambiguous
row.

Separately, PONS's $2.43 peak shortfall decomposes into **$1.60 feed choice** (fair vs last) and
**$0.83 sampling** (an instantaneous poll missing a one-minute wick). The sampling half was
decisive: **on the bot's OWN fair feed the wick reached 1.0100R, above the arm.** The peak existed
for under a minute and **no minute CLOSE in the entire 23.6h hold reached even 0.9653R.**

### RULING: SHIP NOTHING. Change no env var.

Keep `ARM_R=1.0`, `RETAIN_FRAC=0.50`, `RATCHET_R=3.0`, `RATCHET_RETAIN=0.75`.

**Queued for the 18F boundary, as a defect fix and not an edge:** evaluate the arm test against the
fair feed's 1-minute high/low rather than a point sample. It would have armed PONS (~+$9) and
costs ~$0 by construction. **But the population is n=2** — PONS ($29) and ONG_USDT ($1.46) — and
ex-top-5%-by-delta is **$0.00**. It is a real defect fitted to two observations; it ships because
it is monotone-safe, not because it is measured.

**CHEAPEST THING ON THE PAGE — persist the per-position `r_now` poll series.** The entire
retention axis above 0.50 is currently **unanswerable**: there is no live ground truth anywhere
above the live setting, so every number in the 0.70-0.95 region is unanchored simulation, and
**three independent engines disagreed by $85-$220/mo on it.** One log line makes the axis
measurable in 30 days.

**What would have to be true before any retention change ships:** (1) with the trail disabled the
engine must score WORSE than the live setting — today one engine scores **+5.69R better**; and (2)
the residual against live trail exits must minimise **at** retain 0.50, not at 0.30. Until both
hold, do not re-run the arm x retain grid — it will return a confident mechanical negative by
construction.

**The failure the owner watched is not a pattern. It is one trade whose $20.25 lasted under sixty
seconds, never printed as a minute close, and sat $0.64 below an arm the bot's own price feed was
too slow to see.**

## 2026-09-08: THE EARLY STOP — SURVIVES WEAKLY. The first candidate in ~140 to reach ship.

**RULE: on WILDCARD only, exit at market if the trade touches -0.5R within the first 30 minutes.
After 30 minutes the normal -1R stop applies. Equivalently: a tight stop that widens.**

Found by comparing the shapes of the four 18F WILDCARD trades at the owner's request ("how can we
identify this early and cut the losses"). Four agents attacked it from independent angles.

### Verdict: NOT REFUTED, NOT PROVEN

It is not the previously-refuted rule, it is not tail-driven, it is not one trade, and no honest
fill model turns it negative. **But the corrected statistics are p ~ 0.04-0.13, not 0.0003, and
the confidence interval crosses zero.** A bounded bet with positive expectation, not an edge.

### The mechanism, and it passes a sign control

    early touchers reach 1R     33%   |  non-touchers  64%
    mean max excursion        1.34R   |               2.61R
    ROC sign control: +$69.89/mo on HIGH |3h ROC| entries vs +$37.43 on low, with fewer cuts

The sign control is the important one: the effect is stronger where the mechanism predicts it
should be. Exit-stack coupling also passes — the rule stays +$75 to +$130/mo against seven
alternative arm/retain baselines including one with a positive base sumR, so it is not an
artefact of today's trail.

### Scope is decided by the data

    WILDCARD  50 trades, 14 fires,  2 harmed   +3.853R   **+$114.90/mo**
    TREND     27 trades,  4 fires,  2 harmed   -0.254R     -$7.57/mo   <- EXCLUDE
    LONG      67 trades, 18 fires,  4 harmed   +3.599R    +$107.33/mo
    SHORT     10 trades,  0 fires,  0 harmed    0.000R      $0.00      <- no evidence either way

TREND's touched trades are its runners: SOL t50=m7 peaked +7.93R, ZEC t50=m42 peaked +6.32R. On
liquid majors an early adverse move carries no information; on microcaps an early failure is a
real failure. That is the whole finding, and it is why the parameter must be per-sleeve.

### The fill: no resting order needed, and one agent was wrong

    resting order filling exactly at -0.5R    +$107.33/mo
    in-process market at touch-bar CLOSE      **+$87.79/mo**
    in-process market at NEXT-bar close        +$73.41/mo
    close-only trigger (poll blind to wicks)   +$38.17/mo

A market exit costs **18-32%, not half**. Angle 3's claim that the market fill beats the resting
fill ($90.90 vs $90.55) **does not reproduce** — on one engine it is $74.07 vs $90.55. Its
conclusion survives anyway: the in-process version clears the bar by 9x while eliminating the
cancel/replace failure mode, worth more than the ~$20/mo it gives up.

**FLOOR ACROSS EVERY PESSIMISTIC ASSUMPTION STACKED** (WILDCARD-only, market fill, poll blind to
wicks): **+$56.35/mo. Five times the bar.**

Slippage ladder, WILDCARD-only, market fill: 0bps +$95.6 | 25bps +$81.2 | 40bps +$72.6 |
100bps +$38.1. Breakeven is far outside any plausible cost.

### Compounding AMPLIFIES it

Path-dependent terminal equity from $1,126 over 26 days: baseline $1,438.28 -> book-wide
$1,527.13 -> **WILDCARD-only $1,549.06 (+$110.78 over 26 days = +$131/mo)**. The savings land
early, so the compounding case is BETTER than the flat case — and compounding is the case that
matters under fund-once-and-compound.

### THE THREE THINGS THAT KEEP IT AT "WEAKLY"

**1. THE CANDIDATE'S OWN GRID REPRODUCES THE FAILURE SIGNATURE THAT KILLED ITS PREDECESSOR.**
On the refuted rule's own 5x6 axes, live-scored: the CANDIDATE is **24 of 30 cells negative, mean
-9.53R**; the reproduced SNAPSHOT grid is only 12 of 30 negative, mean -2.00R. DECISION_RULE
killed the snapshot rule for being 24/30 negative at mean -3.29R. **The candidate reproduces that
signature three times deeper.** And the snapshot rule's own X=0.5/T=30 cell is **+$19.90/mo, not
negative** — the prior refutation was a grid-level verdict, not a cell-level one.

**2. YOU CANNOT REJECT ZERO.** Bootstrap over trades, 20,000 draws: point +$90.55, **95% CI
[-$47.81, +$218.93], P(delta<=0) = 0.095, t = 1.32.** Market fill: P = 0.131. Grid-corrected
permutation **p = 0.042**; entry-shift grid-max **p = 0.083**. **The headline p = 0.0003 is a
single-cell number and must never be quoted again.**

**3. THE MECHANISM IS WRONG ONE TIME IN FOUR AMONG THE TRADES THAT CARRY THE SLEEVE.**
**6 of the 25 trades that touch -0.5R within 45 minutes went on to peak >= 2R.** SOL retraced at
minute 6.7 and then made 3R. So the ENA-class cost is not a one-off tail event — it is a
**1-in-7 recurrence** that a 25-day window happened to see only four times.

### Walk-forward: X MUST NEVER BE REFIT

    frozen (0.5, 30), no fitting                    +$102 to +$123/mo
    X pinned a priori, T refit, rolling origin      +$102/mo
    X pinned, T refit, coarse folds       +$52 halves / +$22 thirds / **+$9 quarters**
    both refit, per-trade expanding window           +$31 to +$95/mo
    both refit, 2-4 coarse folds                    **-$32 to -$54/mo**

The sign flips on one thing: whether the selector lands on X=0.4, a **-$86 cliff cell**. Under
per-trade refit it picks X=0.5 twenty-three times and X=0.4 eighteen times and still nets
positive; under a 2-fold split it picks X=0.4 once and loses -$318/mo blind. **T is forgiving; X
is a ridge.** ENA itself survives every fragility probe (t50 = 36.11 min, stable under Min1, Min5,
Min15, close-basis and +/-3min jitter) — the cliff is not knife-edge, but X is.

### THE SHIP SPEC

- **X = 0.5R, T = 30 min, FROZEN. Never refit X.** All the fragility lives there.
- **WILDCARD only.** `FUTURES_TREND_EARLY_STOP_R = 0.0` explicitly.
- **In-process market exit, NOT a resting order.** Hook into `_maybe_convex_trail` in
  runtime.py — already gated by `_is_wildcard_convex`, already computes `r_now` from the live
  stop distance every poll, already persists `convex_trough_r`. Guard: if elapsed <= 30 min and
  `r_now <= -0.5`, route to `_close_position_for_exit`. **Behind a default-off env flag.**
- **DO NOT place a second resting stop.** MEXC exposes a singular `stopLossPrice` and
  `cancel_all_tpsl` is all-or-nothing, so a -0.5R resting stop must REPLACE the -1R stop and be
  re-placed at T+30. A silently failed replace leaves a position running 23.5 hours with the wrong
  stop or none. That risk exceeds the ~$20/mo the resting fill adds.
- **THE REAL IMPLEMENTATION RISK IS THE DENOMINATOR, NOT THE ORDER.** If
  `_position_stop_risk_pct_of_margin` returns a too-small value, `|r_now|` inflates and the rule
  cuts everything inside 30 minutes. **Floor it: skip if risk_pct is below half the metadata
  `sl_margin_pct`.** Log every fire with `r_now`, `risk_pct` and elapsed minutes.
- **Log the counterfactual on every fire**, or the rule is unfalsifiable in production.

**PRE-REGISTERED KILL, before enabling:** kill the flag if either (a) two cut trades whose
unmanaged path would have reached +1.5R occur, or (b) after 20 fires the running $ delta against
the logged counterfactual is negative. The rule needs a **>=33% save rate** to break even and
delivered **78% in-sample** (12 helped, 2 harmed on WILDCARD); below 50% over 20 fires it is dead.

**Cost if wrong:** CI lower bound ~ **-$55/mo**. One runner cut inside the window costs about
**-$138**, i.e. 1.3 months of the rule's own edge. Bounded, and dominated by a 1-in-7 event.

**Do not wait for the 18F boundary** — default-off, WILDCARD-only, in-process, reversible in one
env var. Waiting costs a month of measurement and buys nothing.

**Take no variant.** The ramp is dominated. Breakeven-if-ever-positive is -$481/mo, refuted. ROC
conditioning is backwards. Shorts cannot be tested (0 of 10 fire), so scope to longs explicitly if
zero unmeasured exposure is wanted; on this data it costs nothing.

### WHAT IT DOES TO THE FOUR 18F TRADES — and what it does NOT do

    trade      side   t50    live      with the rule          delta
    MAGMA      LONG   m7    -1.06R    CUT at m7 -> -0.52R    +0.54R = +$13.6
    FORM       LONG   m13   -1.06R    CUT at m13 -> -0.52R   +0.54R = +$13.6
    PONS       SHORT  m142  -1.08R    untouched                    0
    MARSCOIN   SHORT  m267  -1.03R    untouched                    0

Two saved, zero harmed, two untouched: **+$27.2 across the four.**

**THE TWO TRADES THE OWNER MINDED MOST ARE THE TWO THIS RULE NEVER TOUCHES.** PONS held 23.6
hours, peaked +0.97R and bled to -1.08R; MARSCOIN is the same shape. Both are SHORTS, where the
rule has zero evidence (0 of 10 fire). **It is a fast-failure rule for longs. It is not a fix for
the slow bleed** — that remains open, and it is what the peak-capture study was built to answer.

## 2026-09-08: THE COMPOUNDING GAP — real, now closed, changes no verdict, and kills retain 0.40

Owner's observation: every study priced additively (sum R, multiply by a constant 1R) while the
bot sizes off available_balance, so the process is multiplicative. **He was right. The gap was
real and it had been in every study in this project.** Seven agents closed it.

### WHAT THE FRAME ACTUALLY ADDS — one real number

Peak-exit and retain-0.40 have **statistically identical netR** (+3.251R vs +3.272R against live;
additively **$15.54 vs $15.64/mo — indistinguishable**). Compounded through the real sizing chain
they diverge by **$16/month**:

    retain-0.40   +$11.96/mo
    peak-exit     **-$4.15/mo**

Same sum of R, **opposite dollar sign**. Mechanism: peak-exit's rescues land on **$2.12-risk**
rows while its truncations land on **$2.44-risk** rows — a risk-weighted delta of **-$0.85**
against retain-0.40's **+$8.55**. **The additive model literally cannot see this**, and it is the
single thing the compounding frame adds. The owner's methodological point is vindicated.

### AND IT RUNS AGAINST HIS OWN PROPOSAL

Terminal equity, E0 = $190, f = 2.183%, WILDCARD 50 rows, realised order, 26 days:

    no-trail control        $214.95   (+$26.54/mo)
    retain-0.40             $202.32   (+$11.96/mo)
    live arm1.0/retain0.50  $191.95   (baseline)
    peak-exit arm0/ret0.98  **$188.35**  (**-$4.15/mo**)

**Peak-exit is the only cell that ends BELOW where it started, and the only one with a negative
geometric mean** (g = -0.000174/trade).

### THE VARIANCE SAVING IS REAL AND WORTH $2.24/MONTH

g ~= f*mu_R - f^2*sigma_R^2/2. The drag budget at f = 1.3876%:

    cell                  meanR      sd R    geometric g    drag/trade
    LIVE arm1.0 ret0.50  -0.0237    1.223     -0.00047       0.01421%
    R040 arm1.0 ret0.40  +0.0593    1.368     +0.00064       0.01784%
    R030 arm1.0 ret0.30  +0.0817    1.429     +0.00094       0.01930%
    PEAK arm0.0 ret0.98  +0.0255    0.302     +0.00035       0.00089%
    LIVE-RECORDED        +0.1986    1.537     +0.00253       0.02264%

Peak-exit's **4x variance reduction buys 0.01332%/trade = 1.18% of equity/month = $2.24/month at
$190**, against a $10 bar. At f = 2.18% the variance term is 9% of the mean term for peak-exit
versus 23% for live — **the saving exists but the mean it is bought with is negative, so Jensen
makes it worse rather than better.**

**Critical risk fractions where low variance finally wins on geometric growth:** peak-exit
overtakes retain-0.40 at **f = 3.97% (2.9x today's risk)**, retain-0.30 at f = 6.23% (4.5x), and
the live ledger at **f = 18.77% (13.5x)**. Live f is 1.39%, funded 2.18%. **Nothing crosses.**

Objection (2) does NOT bite: the arithmetic mean is **POSITIVE** on the ledger (+0.1986R/trade
all-book, +0.0774R WILDCARD), so compounding does not flip a sign.

### ORDER-DEPENDENCE IS A MATHEMATICAL IDENTITY, NOT AN EFFECT

With sizing strictly proportional to equity, terminal = E0 * PROD(1 + f*R_i) — **a product of
commuting scalars, so ORDER CANNOT MATTER.** The owner's "one close at a time" compounding is
real but order-independent. The entire order-dependence budget comes from integer-contract
truncation, the streak throttle and the ruin floor. With truncation live and the throttle OFF,
2000 shuffles give a coefficient of variation of only **0.19-1.11%**, and pairwise on the same
shuffle **retain-0.40 beats live in 2000 of 2000 shuffles** (+$10.35 median) while **peak-exit
loses in 2000 of 2000** (-$4.47 median). Neither result is a path artefact.

### THE WITHDRAWAL POLICY CHANGES WEALTH, NOT THE RANKING

Terminal equity from $190, 21 fills/week, 3,000 block-bootstrap paths, median:

    cell            3mo sweep  12mo sweep | 3mo no-wd  12mo no-wd | 12mo maxDD
    LIVE ret0.50       $172       $133    |   $166        $114    |    58%
    R040 ret0.40       $228       $337    |   $222        $372    |    40%
    R030 ret0.30       $243       $398    |   $243        $523    |    39%
    PEAK arm0          $208       $261    |   $208        $274    |     7%
    LIVE-RECORDED      $327       $740    |   $372      $2,739    |    27%

**The ranking is IDENTICAL under all three withdrawal policies at 3, 6 and 12 months:
R030 > R040 > PEAK > LIVE.** Policy changes WEALTH (3.7x over 12 months on the ledger book) but
not the ORDERING of exit rules. **The finding we were open to — a low-variance rule winning under
compounding and losing under the sweep — did not occur. Exit rule and withdrawal policy can be
chosen separately.**

### RETAIN 0.40 IS REFUTED, AND THE REASON RETIRES THIS MORNING'S LADDER

It reproduces at +3.272R = +$98.9/mo and then fails every control: 4 gaining trades against 12
losing ones; **all 4 gainers are unfaithful engine rows** while 9 of the 12 losers are faithful;
the faithful-subset delta **SIGN-FLIPS to -$33.9/mo** and ex-top-3-by-delta to -$38.7/mo;
sign-flip permutation p=0.425; entry-shift placebo p=0.130 and **family-wise p=0.870** against the
grid-max null, where on jittered entries the median best-of-14 retention cell beats 0.50 by
**+$236/mo, nearly twice the observed best cell**. The era split is -$6.1/mo in the first half and
+$204/mo in the second. The boundary sweep is a **sawtooth, not a plateau**: 0.45 +$130.6, 0.40
+$98.9, 0.35 +$68.5, 0.30 +$41.7, 0.25 +$12.3, 0.20 +$58.1 — adjacent 0.05 steps swing by $50/mo.

**THE DECISIVE FINDING IS ENGINE REPAIR, NOT EDGE.** Mean |sim - live-recorded| is **0.241R at
retain 0.50 and 0.162R at 0.40**. MAGMA (live +2.932R), USELESS 09-04 (+2.584R), USELESS 09-01
(+1.237R) and GALA (+0.715R) **ALL ran live under retain 0.50 and exited via
CONVEX_RETENTION_TRAIL at the value the sim only produces at 0.40.** Those four rows carry +4.55R
of the +3.27R delta. The Min1 replay closes them early on a wick the live 1-second poll never
acted on; lowering the trail below that wick cancels the simulator's own error.

**The retention ladder is measuring how far the level must be moved to stop the replay misfiring,
not a property of the rule.** The 2026-09-08 entry reporting retain 0.40 at +$97.6/mo is
RETIRED on this basis.

### THE ONE GENUINE FINDING FROM THE OWNER'S LINE OF THINKING

**Re-enable the streak throttle.** With `FUTURES_CONVEX_STREAK_THROTTLE_ENABLED` ON,
order-dependence jumps to CV 5-8% and **peak-exit flips to +$6.21 median with P(delta>0) =
0.752** — because **a 92% win rate never trips a loss-streak throttle.** That is the only
mechanism found in which the low-variance instinct actually pays. It is worth ~$7/month, it is
below the bar on its own, and it requires re-enabling a dial that **live fills already priced as
net-positive in its own right** and that has been OFF since 2026-08-27. It also connects to the
2026-09-08 finding that the shrink dials were preferentially catching losers (-0.298R on
sub-half-size rows against +0.431R full-size), worth 1.66x in the dollar record.

**This is the item to take forward from the compounding line — not an exit change.**

### Standing addition to the conversion rule

6. For any comparison between configurations with materially different variance, report the
   PATH-DEPENDENT terminal equity alongside sumR. Two cells with identical sumR can differ in
   dollars by the risk-weighting of where their gains and losses land — measured here at $16/month
   on cells whose additive figures differ by $0.10.

## 2026-09-08 (AMENDMENT): THE WITHDRAWAL POLICY WAS MISREAD — run-equity is FUNDED, not $190

**Correcting an error of mine that propagated into a pre-registered rule and struck a live
proposal.**

### What the owner actually intends

> "I never said I would do that for each funded week. This funded week is a test, but the idea is
> that I'm going to fund the bot with a certain amount of money, let the bot trade and compound,
> and withdraw only profits when I feel like it. It will not go back to $190 every week."

The "$190" figure came from a **single statement about THIS test week**. I generalised it into a
standing weekly sweep and built on it. The actual policy is: **fund once, compound, withdraw
profits opportunistically.**

### What that voids

**1. THE BAR RULING'S WORKED EXAMPLE IS WRONG.** The 2026-09-08 absolute-bar entry says "price at
the equity it will RUN at" and then uses **$190** as that equity, with a table showing a +$57/mo
item earning ~$10/mo. **The PRINCIPLE STANDS and is unchanged. The FACT is wrong.** Run-equity is
the funded level and RISING, not $190. Delete the $190 row and the "one sixth of its measured
dollars" conclusion.

**2. `FUTURES_EXTERNAL_GATE_MIN_REF_TURNOVER` 500k -> 12M IS UN-STRUCK.** The rescale audit's
FLIP 1 killed it because 2.266 R/month prices at $9.40/mo **at $190**. At funded equity it is
**+$57/mo**, comfortably above the absolute bar. It still fails condition (2) of the standing test
— family-wise p=0.092 across the five continuous variables searched, walk-forward p=0.076 — so it
remains UNPROVEN and does not ship on magnitude alone. But **it is no longer disqualified on
dollars**, and it returns to the "consider at the 18F boundary" line.

**3. TRIAL 19's PRICING NEEDS RESTATING.** It was priced at "$190 equity where 1R is ~$2.60".
If trial 19 opens on a compounding funded account, its +$1.91/mo restates at the funded 1R. That
does not rescue it — it fails on controls and its drawdown kill trips on the baseline (30.3% of
equity) — but the dollar figure on file is wrong and should not be cited.

**4. THE COMPOUNDING ARGUMENT IS LIVE, NOT INERT.** The owner's hypothesis — that many small
positive closes compound the allocatable balance and make each subsequent win larger — was about
to be answered with "your own weekly sweep defeats it." **That objection was my invention, not his
policy.** Under fund-once-and-compound the geometric frame is the CORRECT objective and the
additive model every prior study used is the wrong one. The running study prices all three
policies, so read it against the no-withdrawal and partial-withdrawal rows, not the weekly-sweep
row.

### What still stands

- **The bar is ABSOLUTE** (owner's ruling, pre-registered). Unchanged.
- **Price at the equity the change will RUN at, not the equity it was MEASURED at.** Unchanged as
  a principle — it is simply that run-equity is now the funded, compounding level. This still
  matters: a change measured during a $1,100 test week and deployed on a differently-sized account
  must be restated.
- **Magnitude is a floor, not a criterion.** Unchanged, and it is what still holds
  MIN_REF_TURNOVER back.

### The lesson worth recording

A one-off operational statement ("I'll withdraw down to $190 this week") was promoted to a
standing constraint and then pre-registered, where it killed a live proposal and reframed a valid
methodological argument as self-defeating. **Operational statements about a specific week are not
policy. Confirm the standing version before building on it.**

## 2026-09-08: THE RESCALE AUDIT — nothing revives, two things fall, and my own correction was overstated

Owner instructed a re-run of every study affected by the corrected risk fraction. Five agents.
Scoped by DEATH CAUSE, because only magnitude-deaths are scale-sensitive.

### THE R RECORD IS VALID — but my stated mechanism was WRONG

**Conclusion right, reason wrong.** I attributed the pre/post risk-fraction gap (1.171% ->
2.183%) to integer-contract truncation and argued R survives because truncation scales P&L and
risk together. **The truncation premise is REFUTED and runs the WRONG WAY**: the pre-era fill
ratio is **0.896** against a post-era **0.829** — truncation was LESS severe before the deposit,
not more. It explains only **5-7%** of the gap. **~63-69% is COMPOSITION** — six wide-stop
ZEC/MAGMA fills that happened to land post-deposit.

R survives anyway, for a better reason: **`risk_usdt` is recomputed from the contracts ACTUALLY
FILLED** (`nav_risk_sizing.py:52` floors qty, `:82` returns `risk_usdt = qty x loss_per_contract`;
`_stamp_realised_risk` re-stamps from realised qty; `runtime.py:4938` recomputes at close from
`position.margin_usdt` x realised stop%). So R is a **realised-over-realised ratio, invariant to
every size mechanism**. Verified: R is uncorrelated with the truncation factor (Pearson
**+0.0087, t=+0.08, n=92**); `risk_usdt` reconciles to margin_USED (median relative error 4.9%)
not margin_WANTED (33.0%); `r_multiple = pnl_usdt / risk_usdt` to a median error of 0.013R across
84 rows. The pre/post meanR gap (+0.174 vs +0.019) has permutation **p=0.816**.

### AND THE 1R CORRECTION ITSELF IS OVERSTATED

**The funded 1R of $25.16 rests on n=6, with a bootstrap 95% CI of [$15.86, $26.45] — which
CONTAINS the old $15.49.** The 1.62x multiplier I applied across four studies is not established.
Use $25.16 as the point estimate for forward pricing, but stop treating the rescale as a fact:
**the two figures are not distinguishable at n=6.**

### THE TRIAGE — ~80% of the refuted record needed no re-run

122 refutation lines matched; 87 classified (35 were headers or cross-references):

    (d) MECHANISM / STRUCTURAL   28  (32%)   not scale-sensitive
    (b) CONTROL FAILURE          27  (31%)   not scale-sensitive
    (a) MAGNITUDE                15  (17%)   SCALE-SENSITIVE
    (e) CONSTRUCTION ERROR        9  (10%)   not scale-sensitive
    (c) TAIL DAMAGE               8   (9%)   not scale-sensitive

Scale-sensitive exposure is **~15-27 items of ~130, i.e. 12-21%** — and the second agent puts the
clean count at **5**, because most magnitude-class items carry a second, non-scale-sensitive death
alongside the dollar figure. Either way **roughly 80% of the record needed no re-run and was not
re-run.** This corroborates the standing claim that the CONTROL STACK, not the dollar bar, has
been doing the work.

### NO VERDICT FLIPS UPWARD. NOT ONE.

Two items cross the bar at funded scale and both carry a second death scale cannot cure:
- WILDCARD trigger 7%: +$35.85/mo, but no explained mechanism and it fails the both-halves
  35-65% screen.
- WILDCARD trigger 6%: +$42/mo, but ex-top-5% worsens monotonically (-$80 -> -$127) while $/fill
  falls 0.449 -> 0.372. **That is dilution, not edge.**

### TWO VERDICTS FLIP DOWNWARD, AND BOTH MATTER

**FLIP 1 — `MIN_REF_TURNOVER` 500k -> 12M, the only proposal standing, FALLS BELOW THE BAR.**
Published +$57/mo at funded scale = **2.266 R/month**. Priced at the **$190 it will actually run
at** after the withdrawal, that is **$9.40/mo — under the absolute $10 bar**, and it stays under
at every risk anchor tested ($5.04 at the 1.171% whole-pre-era fraction, $7.47 at the 1.734%
trailing fraction, $9.40 at the 2.183% funded fraction). Its downside restates to -$4.62/mo so
the 2:1 ratio holds exactly — ratios are scale-invariant — but the absolute clearance does not.
It was already failing condition (2) of the standing test (family-wise p=0.092, walk-forward
p=0.076), so it now fails **(1) and (2) together**. **Struck from the "consider at the 18F
boundary" line unless the account stays funded.**

This is the owner's own absolute-bar ruling doing exactly what it was written to do, one commit
after it was written.

**FLIP 2 — trial 19's pre-registered 20%-of-equity drawdown kill NOW TRIPS ON THE BASELINE.**
maxDD in R is unchanged (-13.9R for the live book, -14.4 to -15.9R with the third TREND slot), but
at the funded risk fraction that is **30.3% of equity**. The kill fires on doing nothing. The
trial as pre-registered **cannot be run without amending that condition** — and per the
2026-09-08 conflict ruling, the amendment must NOT be a relaxation justified by a bad baseline
figure; it must be re-expressed in R (-16R) with the arithmetic stated.

### THE QUIET FINDING, AND IT IS THE MOST ACTIONABLE THING HERE

**The historical DOLLAR record is flattered by 1.66x relative to flat-R conversion.** Pre-deposit
dollar sum **+$48.97** against sumR +14.59 x mean 1R $2.02 = **+$29.44**.

The mechanism: **the shrink dials were preferentially applied to LOSERS.** Trades scaled below
half size average **-0.298R**; full-size trades average **+0.431R**. The regime scaler and streak
throttle were, in effect, catching bad trades — which is a real protection the dollar record
benefited from and the R record does not show.

**`FUTURES_CONVEX_STREAK_THROTTLE_ENABLED` has been OFF since 2026-08-27.** So the funded bot no
longer reproduces that protection, and **every dollar-weighted historical figure is optimistic by
up to 1.66x until restated in R.** This deserves its own study: the shrink dials may have been
worth more than the "shrink dials pay" record credits, and one of them is currently switched off.

### STANDING CONVERSION RULE — for every future study

1. Compute the effect in **R**. Never sum historical dollars across a cash-flow boundary: the
   dollar record is loser-weighted by the shrink dials and is optimistic by up to 1.66x.
2. Convert **once**, at the end, using the 1R of the equity the change **will run at** — not the
   equity it was measured at. Post-withdrawal that is ~$4.35, not $25.16.
3. Report maxDD **both** in R and as a % of the equity it will run at. R-denominated drawdown is
   invariant; the percentage is not, and the kill conditions are written in percentages.
4. State the 1R used and its interval. The funded 1R is n=6 and its CI contains the pre-funding
   figure.
5. Magnitude is a **floor, not a criterion** — see the absolute-bar ruling.

## 2026-09-08: EXIT-AT-PEAK — REFUTED, and it decapitates 11 of 11

Owner's proposal: WILDCARD only, "let it run until it reaches a peak and then close the trade
right away. No more chances." Five agents. The corner WAS genuinely unswept (prior grids capped
retention at 0.75); it is also genuinely empty.

### The counter-test the brief said would decide it. It decided it.

All 11 trades with peak >= 2R, under arm 0 / retain 0.98:

    symbol            peak R   peak at   live R   OWNER exit    given up   clears 0.10R
    HNT_USDT LONG      5.55     m1124    +0.71   +0.296 @ m1     -$10.3        m0
    HNT_USDT LONG      5.51     m536     +0.58   +0.022 @ m6     -$14.0        m12
    MAGMA_USDT LONG    5.14     m745     +0.71   +0.095 @ m48    -$15.5        m47
    TUT_USDT LONG      5.12     m446     +2.74   +0.057 @ m3     -$67.6        m9
    ENA_USDT LONG      5.02     m791     +4.96   +0.056 @ m61   -$123.4        m101
    SKR_USDT LONG      4.65     m414     +0.62   +0.067 @ m1     -$13.8        m1
    TUT_USDT SHORT     4.11     m1355    +2.58   +0.016 @ m5     -$64.6        m207
    USELESS_USDT LONG  3.52     m461     +1.05   +0.016 @ m1     -$25.9        m74
    GALA_USDT LONG     2.57     m1006    +0.52   +0.015 @ m28    -$12.7        m34
    USELESS_USDT LONG  2.56     m441     +0.72   +0.035 @ m1     -$17.3        m109
    ACE_USDT LONG      2.06     m1037    +0.74   +0.015 @ m0     -$18.3        m1

**It decapitates 11 of 11.** Largest exit +0.296R, **median +0.035R = $0.88**. Median exit minute
**5**; the true peaks arrive at minutes **414 to 1355**. Cost on this cohort alone: -15.24R =
**-$454/month**. Across all 22 trades with live peak >= 1R: **-$887.5/month**.

### The owner is right about the cost centre and wrong about the instrument

**He is right:** 26 of 50 rows stop out at -1.03R each = **-26.8R = -$674 over 25 days**. That IS
the problem.

**The instrument does not reach it.** Decomposed on deltas vs the live baseline:

    RESCUES      24 trades  +26.02R  +$776/mo    (-1R stops converted to scratches)
    TRUNCATIONS  22 trades  -22.77R  -$679/mo
    NET                      +3.25R   +$96.9/mo   <- a 96% cancellation

**What the rescues actually BANK is +1.255R in total = $31.58: mean $1.44, median $0.31 per
trade.** The "+26R rescue" is almost entirely the -1.02R stop avoided, not profit captured.
Stated plainly: **the rule buys 22 avoided stops for the price of 21 decapitated winners.**

Two ~25R streams cancelling to 2R — any 8% error on either arm flips the sign. Bootstrap 95% CI
**[-$446, +$582]**, P(delta<=0) = 0.345, removing three trades reverses it, the era split
disagrees, leave-one-symbol-out flips it, and **placebo matches or beats it in 18 of 20 draws.**
Against the LIVE book rather than the sim it is **-5.780R = -$167.8/mo**.

### The cosmetic transformation, stated for the record

    exit mix   LIVE:  26 stop / 18 trail / 5 clock24 / 1 TP
               OWNER:  4 stop / 46 trail / 0 clock24 / 0 TP
    win rate   44% -> 92%      maxDD 8.12R -> 1.69R      netR -3.84R -> -0.59R

The 24h clock and the 5R TP cap both become **structurally unreachable** — the trail pre-empts
them on 92% of the book. **The sleeve still loses; it just loses in a way that looks like
winning.**

### THE OWNER READ A REAL FEATURE — the monotone claim is FALSE as written

The `_convex_runner_trail_exit` docstring says retention above 0.30 is "monotonically worse". It
is not. At the live arm 1.0R, $/month by retention:

    0.20 +57.3 | 0.30 +41.1 | 0.40 +97.6 | 0.50 0.0 (live) | 0.60 +13.4 | 0.70 -109.7
    0.75 -81.9 | 0.80 -126.9 | 0.85 -123.3 | 0.90 -109.5 | 0.95 -74.8 | 0.98 -54.0 | 0.995 -43.6

Local maximum at **0.40**, collapse at 0.70, trough at **0.80**, then a steady **+$83 recovery
from 0.80 to 0.995**. There IS a second-optimum direction at the high end and the owner was
reading it correctly — the recovery just tops out at **-$43.6/mo**, still below the incumbent, and
only crosses zero when arm is driven to exactly 0.

The TP-completion half of the docstring IS confirmed: completion is 2.0% at retain <= 0.60 and
**0.0% at every retain >= 0.70**.

**Note for follow-up: retain 0.40 prices at +$97.6/mo against the live 0.50.** Same noisy grid, so
not a recommendation — but it is the one cell here pointing at the incumbent being mis-set, and it
points the OPPOSITE way to the proposal.

### The maximum is a ridge one row wide

The 81-cell maximum sits at arm 0.00 / retain 0.98 at +$96.9/mo and fails every screen:
ex-top-5%-by-delta is **NEGATIVE** (-$20.9/mo, -$115.5 under the honest engine); the entry-shift
placebo grid-max null has median **+$202.2** against an observed best of +$96.9, i.e. **family-wise
p = 0.850 — random entry timing beats the best cell of the real search in 85% of placebo worlds**.
Along retain at arm 0 it is a smooth plateau (+$37.6 -> +$96.9), but **one step in arm (0 -> 0.05)
costs $168**. Arm must be exactly zero. That is the definition of a spike.

### MY HYBRID SUGGESTION WAS STRUCTURALLY DEGENERATE

I proposed a two-regime exit: tight peak-exit below 1R, live trail above. **Bound 0.50R and bound
1.50R produce BIT-IDENTICAL results**, as do all five bounds x three tight-retains. Reason:
**every trade's peak starts at zero and passes THROUGH the tight regime on its way up, so the
tight rule always fires first and no trade ever reaches the loose regime.** A peak-bounded
two-regime exit is not a two-regime exit — it collapses to the tight rule exactly. It cannot
protect runners by construction. The record showing it untested was right: it was untested because
it is not a distinct rule.

The time-gated repair ("if peak < 1R by minute 60, switch to tight") looked like a live candidate
at **+$277.8/mo** and is an engine artefact: every gated exit fires at minute 60-61 and books
0.98x the prior 60-minute high while price is far below it. Under the honest resting-stop engine
the same cell is **-$225.8/mo**.

### CORRECTION TO THE ENGINE-FIDELITY RULE SET YESTERDAY

The standing rule says report the faithful subset (trades the Min1 engine reproduces within
0.15R). **For this class of question that subset is LOSS-ENRICHED BY CONSTRUCTION and must not be
credited.** The 11 unfaithful rows are almost exactly the sleeve's winners — TUT +5.09 (sim
+2.74), MAGMA +2.98 (sim +0.71), USELESS +2.55 (sim +1.05), BLESS +0.73 (sim -1.04) — carrying
**+13.41R** of the live book. The engine understates winners by 8.566R, and **8 of 21 sim-peak>=1R
trades are unfaithful against only 3 of 29 sim-peak<1R trades.**

**So any rule that truncates winners scores well on the faithful subset for a mechanical reason.**
The owner's cell is +$96.9/mo on the full pool and **+$256.6/mo on the faithful subset** — that
subset figure is an artefact of the selection, not corroboration.

**AMENDED STANDING RULE: report the faithful subset, and ALSO report whether faithfulness is
correlated with the outcome the rule acts on. Where it is, the faithful-subset figure is an upper
or lower bound, not a cleaner estimate.**

### The sign is not determined by the data

Five defensible constructions of the same cell, full pool $/month: favour_first/wick **+96.9** |
adverse_first/wick +81.0 | favour_first/close-probe **-43.1** | adverse_first/close-probe -1.5 |
resting-stop with market fill -2.4. **At retain >= 0.90 the exit rule lives entirely inside a
1-minute bar, so 1-minute bars cannot resolve it in principle.** The verifier adds: 33 of 50
owner-rule exits fire at minute <= 2, carrying +$350.9/mo of the delta — in exactly the region the
engine models worst.

**Verdict: REFUTED. Do not ship.** Refuted count ~135.

## 2026-09-08: THE SHIP BAR IS ABSOLUTE — owner's ruling, pre-registered

**Recorded BEFORE the rescale audit returned, deliberately.** The audit is re-pricing every
magnitude-death at the corrected 1R, and a threshold chosen after seeing which items clear it is
not a threshold. This is the pre-registration.

### The ruling

**The "$10/month does not ship" bar is ABSOLUTE, not relative.** It stays denominated in dollars.

The bar prices an operational cost — a deploy, a restart with live positions, a trial reset, and
the added complexity of one more branch — and that cost does not scale with the account. It is the
same deploy at $190 equity as at $1,100.

The rejected alternative: a RELATIVE bar in R. $10/month when 1R was ~$2.66 is **3.76 R/month**,
which at 1R=$25.16 would be **$94.60/month**. Almost nothing in the project's history clears that,
and it would make the bar rise every time the account grows, which is not what the bar is for.

### THE CONSEQUENCE THAT MATTERS MOST — price at the equity it will RUN at

An absolute bar only works if the dollars are the dollars the change will actually earn. So:

**Price every proposal at the equity it will RUN at, not the equity it was MEASURED at.**

This is not academic. The owner withdraws to **$190** at week end, so:

    equity      1R (at the funded 2.18% risk fraction)    a "+$57/mo" item earns
    $1,100      ~$25.16                                    $57/mo
    $190        ~$4.35                                     ~$10/mo

**A change measured at funded scale earns roughly one sixth of its measured dollars once the
withdrawal lands.** Trial 19 is the standing example: it is pre-registered to open AFTER the
withdrawal, so its +$1.91/mo must be priced at $190 equity, where it is worth cents — the
"rescaling makes it clear the bar" argument is backwards for that specific change.

### The standing test

A change ships when, at the equity it will run at over the horizon it will run for:

1. expected P&L exceeds **$10/month**, AND
2. it survives the control stack (permutation, entry-shift placebo, family-wise multiplicity,
   leave-one-out and leave-one-symbol-out, era split), AND
3. its ex-top-5% delta, **screened by delta and not by baseline outcome**, is not materially
   negative, AND
4. it does not raise maxDD as a % of equity into the 45% margin kill line or the trial's own
   drawdown kill.

Magnitude alone was never sufficient and is not now. The bar is a floor, not a criterion.

### The guard against bar erosion

An absolute bar does get easier to clear as the account grows, which eventually admits noise.
The guard is condition (2): **a change that clears $10/month but fails a control still does not
ship.** Across ~130 refuted items the overwhelming majority died on controls rather than on
magnitude, so the control stack — not the dollar bar — is what has actually been doing the work.
Revisit the bar's level only if equity changes by another order of magnitude.

## 2026-09-08: THE WILDCARD REBUILD — 1R IS $25.16 NOT $15.49, and one env var survives

Eleven agents, five lines of attack, adversarial verification on every proposal. **15 proposals
raised, 11 killed, 4 survived — and 3 of the 4 survivors are worth $0.** Triggered by a second
funded-week WILDCARD loss (FORM_USDT -$25.76 after MAGMA -$26.45).

### CORRECTION THAT RESCALES EVERY STUDY IN THIS DOCUMENT

**1R in the funded week is $25.16, not $15.49.** From `feat.jsonl` funded rows (equity > $800):

    symbol  side   R      risk_usdt  risk % equity  margin % equity
    ZEC     LONG  -0.21     12.87        1.17%          5.9%
    ZEC     LONG  +2.88     24.99        2.28%         13.1%
    ZEC     LONG  +0.43     28.33        2.42%         13.9%
    ZEC     LONG  -1.01     27.87        2.36%         13.2%
    MAGMA   LONG  -1.06     25.16        2.19%         12.2%
    ZEC     LONG  -1.03     19.53        1.69%          9.0%

Median funded risk **2.28%**. Median across the 68 pre-funding rows every prior study used:
**1.435%**. **The bot is drawing 1.6x the risk of the entire measurement window.** The
"1.371-1.381% realised" figure recorded on 2026-09-07 and used in four studies since is the
PRE-DEPOSIT era, not now.

Three load-bearing consequences: every dollar figure in the recent studies is **understated by
1.62x**; every maxDD understates live drawdown by 1.62x (a "-$101.63" baseline is **-$165 live**);
and the $10/month bar is effectively $16/month in study units, so proposals get EASIER to clear.

**The owner's -$52.21 wildcard loss is -2.08R over two fills (-1.04R each). Nothing anomalous
happened — two stops at full size.**

### THE OWNER'S FOUR INTUITIONS

**(1) Shorts > longs, we enter too late.** Side gap does not survive: SHORT +0.251R (n=10) vs
LONG +0.034R (n=40), permutation **p=0.70**, 109% one fill. Asymmetric SIZING priced for the first
time and loses twice: down-sizing longs to 0.5x costs **-$28/mo** AND raises book beta to BTC by
+32%, because the longs carry the hedge.

**"Too late" is REFUTED IN TIME and CONFIRMED IN PRICE.** The signal is **120 seconds old** when
we fill (median, 36 reproducible entries); the price given up is $0.10/fill; entering at first-fire
is +$13/mo at p=0.275. But the fill sits at the **80.8th adverse percentile of its own +/-4h price
range (median 90.4th, p<0.0001)**. We are not chasing a stale signal — **we are buying the local
top**, which is exactly what `|3h ROC|>=8%` plus `cur > prev` is engineered to do. The one
implementable exploitation died: the pullback limit entry's apparent +$122/mo is a **disguised
stop-widening** — hand the same trade a free 0.94% better price with NO pullback condition and it
pays MORE (+$174/mo), while the pullback selection itself is worth **-$52/mo**.

**(2) Sizing too high.** **His arithmetic is right and it is worse than he thought** — see the
1R correction above. But Kelly refuses to support the conclusion: full Kelly on the measured 50
rows is **4.37% risk per trade**, joint with TREND **3.29%** (corr of daily R = +0.045, so almost
no diversification haircut). Kelly says size **UP 2.4x**. **There is no defensible middle:** drop
the two trades that make the sleeve (TUT +5.53R, ENA +4.93R) and mean R is -0.124 and full Kelly
is **exactly 0.00%**. Either the tail repeats and current size is conservative, or it does not and
the correct allocation is zero. P(mean<=0) = 0.37.

**(3) The trail never arms.** Refuted — 47.3% reach 1.0R — but **his reading of the bimodal
distribution is CORRECT**: only 3.6% of fills peak in 0.75-1.00R, so the arm sits in an empty
region, which is why every arm experiment returned null. His fail-fast consequence is **backwards
at the timescale he implied**: cutting dead trades at 15-240 min is **the single most expensive
idea measured anywhere in this project (-$71 to -$247/mo)**.

**THE DURABLE FINDING THAT CLOSES A WHOLE FAMILY OF IDEAS: the sleeve's biggest winners are its
SLOWEST STARTERS.** ENA_USDT (+4.96R) does not clear 0.10R until **minute 101**; TUT_USDT SHORT
(+2.59R) until **minute 207**; TAC_USDT SHORT (+1.36R) until **minute 274**. At P=0.25/T=15, 13 of
the 21 eventual >=1R runners are still below the floor. **Every fast-cut variant is permanently
wrong.** Push the clock to 8h and it turns positive, then dies on the delta-screened tail
($0.37/mo after the top-2 deltas) and on relevance: it fires **zero times in the last 14 days**,
during which 13 fills lost -$212.

**(4) Review the gates.** Right instinct, wrong venue. Twelve gate changes priced, best at
family-wise **p=0.33** against a noise-only median best cell of **$24/mo**. **My ROC-band lead did
NOT reproduce**: on the live 91-row history the 8-10% band is the sleeve's SECOND-BEST at +0.207R
(n=21), not -0.127R, and the shadow ledger reverses the structure on both halves (untaken longs
8-11% resolve +0.216R, >11% resolve -0.208R — the exact reverse of the taken rows). **The
ROC-band line is retired.** All four dark detector gates measured for the first time and all four
fail: MIN_VOL_Z flips sign across the half-split (+$231 -> -$105/mo), MAX_WICK and
VERTICAL_ATR_MULT flip between reconstruction populations, tightening RSI costs money at every
threshold (p=0.977).

**Decisive for the owner: neither funded-week loss is near any live gate.** MAGMA roc 13.7 / RSI
85.7 / wick 0.249 / vert 0.46xATR / vol_z 2.24; FORM roc 13.9 / RSI 68.9 / wick 0.104 / vert
0.57xATR / vol_z 1.93. **No gate change tested would have stopped either one.**

### THE THREE SUGGESTIONS

**1. `FUTURES_EXTERNAL_GATE_MIN_REF_TURNOVER: 500000 -> 12000000` — +$57/mo, ABOVE THE BAR,
UNPROVEN.** The binding constraint is on the REFERENCE side, in a parameter on nobody's list. The
floor is $500k and **the lowest reference turnover ever seen on a taken trade is $3.24M — it has
never bound once in 70 fills.** Raising it drops 14 of 70 fills at mean **-0.803R**, 11 of them
~-1R stop-outs.

    ex-top-5% BY DELTA  +6.89R = +$74/mo (it IMPROVES the tail)
    maxDD               -6.85R -> -4.83R
    ENA (+4.96R, 89M turnover) is KEPT, so the trade that killed three prior proposals
      cannot be flattering it
    PASSED  leave-one-out (worst p 0.0029), leave-one-symbol-out (worst 0.0041), both eras,
            within-month normalisation (+$59/mo p=0.0495), winsorised at +/-1.2R (unchanged —
            on de-tailed returns THE SLEEVE'S ENTIRE LOSS IS THIS COHORT), 7-day placebo
    FAILED  family-wise p = 0.092 across the five continuous variables actually searched;
            walk-forward vs its own shuffled null p = 0.076. Support is one 13-vs-21 split.

Pure env var, zero code, **structurally inert for TREND** (TREND's minimum reference turnover
across 27 closes is **193.6M — 16x the proposed floor**). Cost if wrong -$28/mo. Residual leak:
the guard is `turn > 0` and the OKX fallback returns 0, so an OKX-only pair bypasses it.
**Ship at the 18F boundary, not mid-week.**

**2. RETUNE THE PREEMPTION PREDICATE — unpriced, but the correct version of the cap question.**
`FUTURES_WILDCARD_PREEMPT_MIN_AGE_MIN` 15 -> 60/120 and/or `PREEMPT_BELOW_R` 0.3 -> 0.0.

`MAX_POSITIONS 3->2` was **KILLED at -$60/mo** because the counterfactual was wrong: **the cap does
not REFUSE a signal when the book is full — `runtime.py:6219` converts a full book into an
EVICTION attempt**, and it demonstrably fires live (CONVEX_PREEMPTED: INX 08-12, ZORA 08-31).
Re-simulated with the eviction branch in the loop, 4 of the 5 "blocked" fills are taken anyway.

**The finding: the current settings are configured to kill young winners.** At the HEMI 08-28
episode the eligible victims were TAC at -0.213R (which closed **+1.34R**) and MAGMA at 15.8
minutes old and -0.078R (which closed **+2.93R**). A 15-minute minimum age plus a +0.3R threshold
makes a not-yet-working winner the preferred victim — and we now know **the winners are the slow
starters**, so this is the same defect twice. Exposure ~2 evictions per 90 fills, rising with
contention (3rd-slot use 7% over 90 days, **19% over the last 14**). Order-of-magnitude $25-75 per
bad eviction — an inference from two named episodes, NOT a measurement. Env vars, WILDCARD-only,
zero code. Both dials have **zero measurements of any kind**; the docstring calls them "safety
rails, not tuned parameters."

**3. THE ONE-LINE RISK-DIAL SPLIT — $0/mo, ships free with any deploy.**
`runtime.py:1761`: `risk_pct = self._env_float(f"FUTURES_{kind}_RISK_PCT",
self._env_float("FUTURES_WILDCARD_RISK_PCT", 0.0187))`. Verified: `_entry_margin` already receives
`kind`, and 1761 is the ONLY production read. With no override set, behaviour is **exact-zero
change**. It unwelds the weld that has made every sizing proposal unshippable (halving WILDCARD
currently halves TREND, ~-$150/mo). Caveat the panel missed: the weld is currently a SAFETY
property, and unwelding means a later edit to `FUTURES_WILDCARD_RISK_PCT` silently stops moving
TREND. **Do not ship it as a step toward cutting size** — the 0.75x shrink it enables costs
-$34/mo at true 1R and gains +$46/mo only if the tail does not repeat.

### Below the bar or negative — ranked so they are not revisited

| change | corrected $/mo (true 1R) | why it dies |
|---|---|---|
| `MAX_POSITIONS` 3->2 | **-$60** | the cap EVICTS, does not refuse; effect is exactly 0.000 when MAGMA is dropped |
| `CONVEX_DEAD_CUT` peak<0.15R @8h | +$0.37 | $21.58 of $26.18 is two trades; fires 0 times in 14 days |
| pullback limit entry | +$14 | sim baseline error ($119) exceeds the effect; it is a stop-widening |
| asymmetric ROC floor (LONG 11%) | +$18 | argmax of a 60-cell sweep whose noise median best cell is $24/mo |
| `EXCLUDE_TOP_TURNOVER` 24->12 | +$18 | 220-day replay = $11/mo not $81; ex-tail **-$3.78/mo**; already deferred |
| BE-tighten at 45m | -$12 | sign inverts under the top-2-delta screen |
| corroboration STRENGTH (ROC space) | negative | ratio spans only 0.812-1.271 (median 0.998) against a 0.4 gate sitting 51% BELOW the observed minimum; quintiles non-monotonic p=0.35; raising it is -$20 to -$46/mo at every value 0.90-1.00 |

### GUARD RAIL — the most valuable component in the sleeve is already a gate

**`REQUIRE_LISTED` is earning $246/month at true 1R.** Reproduced from shadow.jsonl: 36
`ref_not_listed` vetoes, all resolved, meanR **-0.455**, sumR -16.38, win 31%, **ex-top-5%
-0.617 — MORE negative than the mean**, so it removes a broadly bad population rather than being
flattered by a tail. The verifier attacked it on slot contention (36 extra candidates is +65% on
32.9 fills/month) and failed to kill it. **That is more than the entire rest of the sleeve's
measured edge. Never relax it.**

### TWO METHODOLOGICAL DEFECTS THAT TOUCH ~190 PRIOR CELLS

**1. THE REPLAY ENGINE'S BASELINE ERROR EXCEEDS EVERY EFFECT MEASURED ON IT.** The Min1 replay
scores the same 50 trades at **-3.841R** while the live book recorded **+3.870R** — a 7.71R /
**$194 at true 1R** baseline error over 25 days. **Standing rule from now on: every replay study
reports sim-baseline vs live-recorded BEFORE reporting any delta, and reports the effect
restricted to the faithful subset.** Applying that retroactively would reopen part of the ~50-item
refutation list **in both directions**.

**2. RECONSTRUCTED ROWS SILENTLY DELETE RECOVERED LOSERS.** Every `EXCHANGE_CLOSE_RECONSTRUCTED`
feature row is missing all entry-time fields, and every one is a ~-1R loser recovered from the
ledger loss-censoring incident. **Any study conditioning on an entry feature silently drops them**
— which is why the same sleeve reads +0.293R on one population, +0.203R on all 75 feature rows,
and +0.077R on the 50 risk-measured rows. Flag them explicitly.

### Measurement queue (zero behaviour change)

- **`entry_lateness` is not capped, it is mis-normalised.** `runtime.py:6737-6750` min-max
  normalises the entry close against the last 13 Min15 closes **including the entry bar**, so
  `cur` defines `hi`. It cannot exceed 1.0 and reads exactly 1.0 whenever the entry bar closes at
  the window high — which the trigger guarantees. Changing `min(c), max(c)` to
  `min(c[:-1]), max(c[:-1])` takes saturation **72% -> 2%** and opens the range to 0.549-1.746.
  NOT free: `_wildcard_rank_key` reads it (`is_deep = 0.50 <= lat < 0.70`). Zero-risk version: add
  `entry_lateness_unc` as a second field.
- **Persist the external gate's continuous outputs** (`ref_roc`, `ref_turnover_usdt`,
  `ref_funding`). ~6 lines, no new network calls. Note `ref_listed` is **conflated**: `listed` is
  overwritten to False when turnover is below the floor, so the flag collapses "not listed" and
  "illiquid" into one bit.
- Stop wiping metadata at close (50 keys on the open position, `{}` on all 90 closed rows).
- Scan id on shadow rows — without it the `_wildcard_rank_key` test is unrunnable.
- A `_rej()` counter: the detector refuses 64,854 of 84,569 trigger bars and writes no row.
- Shadow the pullback touch: record whether price touched `signal_px*(1 -/+ 0.10*sl_frac)` within
  60 minutes and when. Gives fill rate and timing in 2-3 weeks.

**Verdict: ship nothing mid-week.** At the 18F boundary, consider MIN_REF_TURNOVER. Refuted
count ~130.

## 2026-09-08: WILDCARD SHORT-ONLY — REFUTED, and the hedge thesis is BACKWARDS

Seven agents. Owner proposed making WILDCARD short-only so the book becomes LONG-TREND /
SHORT-WILDCARD, asking for the trial 17->18F number and then a full sweep.

### The trial 17->18F number, and why it evaporates

Reproduced to the digit by two independent agents:

    both sides (live)  n=26  net -$16.21  meanR +0.214  SE 0.232  t +0.92  win 61.5%  netR +5.57
    LONG only          n=21  net -$24.20  meanR +0.127
    SHORT only         n= 5  net  +$7.99  meanR +0.582
    per trial: 17 +$10.83 (L4/S1) | 18 -$0.59 (L16/S4) | 18F -$26.45 (L1/S0)

The +$24.20 delta is **109% one fill**. MAGMA_USDT LONG, 2026-09-06, -$26.447 / -1.051R.

    drop that one long          -> delta +$24.20 becomes **-$2.25**
    leave-one-SYMBOL-out MAGMA  -> delta +$24.20 becomes **+$0.87**

MAGMA is 5 of the 26 fills and sits on BOTH sides (2 shorts +$5.04, 3 longs -$23.33).

**In R space the proposal LOSES at every window**: -2.78R over T17->18F, -2.01R post-August,
-7.52R over the full book. The dollar advantage is a **deposit-scale artefact** — MAGMA lost
$26.45 at the post-deposit 6.3x scale while the longs it would delete were sized at 1/7th of it.

**Not distinguishable from live at ANY window**: best permutation **p=0.134**, and that was on the
window chosen after seeing it.

### THE HEDGE DOES NOT EXIST — and the proposal makes the book MORE directional

This is the finding. Regressing daily arm-R on fetched BTC daily return (n=19 days):

    TREND      beta  +0.448 R per +1% BTC   (t +1.98)
    WC_LONG    beta  -0.212                 (t -1.09)   <- the offsetting arm
    WC_SHORT   beta  -0.031                 (t -0.51)   <- no beta at all

    book beta as it stands  +0.205
    book beta under the proposal  **+0.417**

**A WILDCARD short is not short the tape. It is a mean-reversion trade on a coin that just
spiked.** On the full 72-row R history the slope of trade-R on BTC-24h-at-entry is POSITIVE for
BOTH sides (LONG +0.065R per +1%, SHORT +0.110R) — **the shorts carry MORE long-tape beta than
the longs do.** Deleting the longs deletes the only arm hedging TREND.

**The sign the owner predicted is in the data and it is drag, not insurance.**
corr(TREND, WC_LONG) = +0.094; corr(TREND, WC_SHORT) = **-0.239**. Both CIs straddle zero
([-0.377,+0.526] and [-0.625,+0.242]); the gap has permutation p=0.29. And the mechanism is
wrong: **on TREND's four worst days ZERO wildcard shorts closed.** The -0.239 comes entirely from
shorts LOSING on TREND's BEST days (-1.02R). That is correlated drag wearing a hedge's sign.

### The geometry: the docstring is right, the ceiling is not what breaks it

`wildcard.py:100` verifies. Replaying the live detector over 107 symbols x 15m bars,
2026-08-18 -> 09-07: 225 signals (154 LONG / 71 SHORT), **13/71 shorts = 18.3%** get a pre-clamp
target at or through price zero (docstring says 21%); log-space median target-distance ratio
short/long = **1.86x** (docstring 1.7x). Corroborated on the shadow ledger: 12/32 shorts sit at
the 0.20 stop cap where tp_dist = 1.00, and 3 shadow rows carry a recorded TP price <= 0.

**But the ceiling has never bound: ZERO of 90 wildcard closes have ever exited at TAKE_PROFIT.**
Under the retention trail the TP order has never fired once. The real defect is one layer deeper —
**the price distribution does not produce short-side moves of the required size**:

    a LONG needs +45.1% to reach 5R  -> occurs on 7.34% of post-rally bars
    a SHORT needs -50.0% to reach its clamped target -> 0.35% of post-drop bars (21x rarer)
    an UNCAPPED 5R short needs -66.7% -> 0 times in 3,468 samples

    favourable-tail R:  LONG p95 6.24R / p99 13.14R  (both ABOVE the 5R TP — the TP truncates the
                        long's tail)
                        SHORT p05 2.21R / p01 3.22R  (both BELOW the 3.75R median short ceiling —
                        the short's tail dies before the ceiling can bind)

**`FUTURES_WILDCARD_MAX_SHORT_TP_DIST` is measured for the first time and is INERT**: every value
from 0.50 to OFF is identical to the cent, **$0.00/month**. It is already the code default, so no
live short ever had an unreachable target. Its cost is real but small: 70% of shorts clamp,
effective TP_R median 4.18 (min 2.36) against longs' 5.0 — 16% of the convex ceiling.

### Corrections to the record

- **"The runners are structurally long" is REFUTED.** The >=+2R population is n=10 summing
  +38.22R, composed **6 LONG / 4 SHORT**. Denominator-free (pnl_pct >= +40% of margin): 9 fills,
  6L/3S, hit-rate 9.5% LONG vs **11.1% SHORT**. Shorts are 30% of fills and 33-40% of the tail —
  proportional, not concentrated in longs.
- **The full-book SHORT +0.641R is a CENSORING ARTEFACT.** Of 17 pre-August shorts, the 8 carrying
  an r_multiple net +$11.95 (meanR +1.129) and the 9 without net **-$12.89**. On the 50 clean
  post-August rows shorts are **+0.251R (n=10)**. Never quote +0.641R again.
- **"WILDCARD is roughly flat" is wrong in R.** Over the only window where both sleeves exist,
  WILDCARD both-sides made **+5.72R (+$88.60 at 1R=$15.49) on 42 closes** against TREND's +11.42R
  on 27. It was a third of the book. It looks flat only in realised dollars (-$4.46) because its
  losses landed after the deposit multiplied the scale 6.3x.
- **A short SIGNAL does exist.** BTC rose 18% over the book and the detector's shorts still beat
  their own random-entry placebo (+0.435R live, +0.287R replay). Drift is the one control that
  FAVOURS the proposal. The signal is simply far too small and too tail-borne to justify deleting
  an arm that fires 4x as often.
- The forward-return figures on file do not reproduce: measured unconditional forward-24h median
  **+0.70%** (filed -1.19%) and mean **+2.79%** (filed +0.89%); after a -8%/3h drop the mean
  forward 24h is **+6.52% raw / +5.83% drift-controlled** (filed +0.37%). Direction right,
  magnitude ~16x off — the filed numbers came from a different window.
- **Stale premise:** there has been no withdrawal to $190. Equity went $186.11 -> $1,099.36 on
  2026-09-04 and sits at $1,108.16. The one-week hard-reset frame no longer describes the account.

### The one real benefit, and the cheaper way to get it

Short-only genuinely cuts drawdown: **P(-20% DD over 3 months) 8.8% vs 40.5%**. But that is a
de-risking, not an edge, and it is **96% reproducible by simply running BOTH sides at 0.33x size**
(sumR +13.33 vs +13.31). And it costs the median: **LIVE beats PROPOSED on median growth at every
assumed short mean from +0.641R down to -0.043R.**

**Verdict: DO NOT make WILDCARD short-only. Leave `FUTURES_WILDCARD_LONG_ONLY=0`.** Refuted
count ~115.

## 2026-09-08: TREND universe + BTC/SOL/LTC/BNB — REFUTED, and the BTC tier finding is RETRACTED

Ten agents, four harnesses, four adversarial verifiers, three tapes (Min5/Min15/Min30, 182-1,700
days). Owner asked to add BTC, SOL, LTC and BNB. **Every harness refuses the set.** They disagree
on the price by 2.5x; they do not disagree on the sign, in any era, at any slot count, on any exit
convention.

### THE HEADLINE CORRECTION: "BTC +0.948R/fill (t=5.33, n=68)" IS A SIGNAL-BAR COUNT

This number motivated the request and it was quoted to the owner from the 2026-09-07 allocation
study. Three agents reproduced it **to the decimal** — and reproduced it ONLY by counting every
15-minute bar on which the gate was true as an independent observation of the same move.

    A1: n=68 bars +0.948R t=5.29  ->  deduped to 13 realisable fills, +0.262R, t=0.66
    A4: n=66 bars +0.768R t=4.37  ->  through the live slot book: n=11, +0.293R, t=0.61
    A2v: 68 bars -> 15 episodes (4h dedup) / 9 (24h lock). ETH's n=95 -> 31/15 the same way.
    A3: could NOT reach n=68 under any relaxation (3% gate 21, 2% gate 37, no-extreme 18)

A persistent BTC trend fires ~24 consecutive bars that resolve into ONE move; the bot takes one.
That inflates n by ~4.5x and t by ~2.1x. **The tier study is RETRACTED as a per-fill statistic.**
Booked as the bot actually trades, BTC is **-0.13 to -0.26R/fill over >=360 days** — second-worst
of the seven, not "the best-scoring symbol anyone has measured".

Same correction applies to the whole tier table (top-5 +0.387R/fill vs next-fifteen +0.016R): it
is bar-counted and must not be quoted per-fill again.

### Symbol by symbol against the pre-registered screen

| | screen | fires/mo | standalone R/fill | $/mo | as sole addition | in |
|---|---|---|---|---|---|---|
| BTC | **FAIL** raw-% leg negative or p=0.10-0.44; eras 2/4 | 3.8 | -0.13 to -0.26 | -$8 to -$15 | ~-$6 | No |
| BNB | **FAIL** p=0.08-0.12, misses p<0.05 in 3 of 4 | 4-6 | ~0 (-0.05 to +0.19) | -$5 to +$11 | ~$0 | No |
| LTC | **FAIL** all four criteria in 2 of 4 agents | 6-7 | -0.07 to -0.19 | -$9 to -$22 | ~-$18 | No |
| SOL | **FAIL, second time** raw-% excess NEGATIVE in 3 of 4 | 8-9 | -0.04 to -0.29 | -$5 to -$41 | ~-$27 worst | No |

**BNB is the honest near-miss and still a no**: the only one whose R-excess and raw-% excess agree
in sign, but it clears $10/month in ZERO of four books, inverts sign on the exit convention
(+$3.34 -> -$0.93/mo), and its "4/4 eras" was four quarters INSIDE ONE YEAR, not the multi-year
condition the screen requires. On the only genuine multi-year test (3.93y) it is 0/4.

**SOL has now failed the screen TWICE**, on independently fetched tapes and independent
implementations (-0.027% on file; -0.091/-0.092/-0.094% here). Settled. Its two live closes at
+1.53R are n=2 from a retired config and are not evidence.

**LTC had never been measured. It has now**: the most decisively null symbol in the book,
indistinguishable from zero on every window and hold length tested.

### The set as requested

|  | live 3 | owner's 7 |
|---|---|---|
| $/month | baseline | **-$28/mo** (agents -$22.7 / -$28.3 / -$36.8 / -$56.8) |
| fills/mo | 30-34 | 38-43 (+23 to +35%) |
| substitution | 0 | 0.20-0.50 |
| maxDD (R) | -9.9 to -18.9 | -12.6 to -49.9 (**1.3-1.7x worse**) |
| ex-top-5% delta | — | **-$18 to -$60/mo, worse in all four books** |

Negative in 4/4 eras (three agents independently), 0/20 scan-order seeds, at 1/2/3/4/7 slots,
under both exit conventions, on 182-day, 360-day and 1,700-day tapes. **A flat negative field with
isolated unreproducible spikes**, each one cell in a 30-44 cell sweep, each dying to a single
trimmed fill or a convention flip.

**Caveat the owner would find anyway:** on the LAST 131 DAYS all four ARE positive standalone (BTC
+0.717R/fill, SOL +0.462R). He is not hallucinating. But **every one of the seven scores better on
that window than on the full year** (ETH -0.133 -> +0.356, SOL -0.233 -> +0.087, BNB -0.017 ->
+0.337). It is a favourable regime for the whole detector, not a ranking of symbols — and the
owner's set is drawn from names that scored well on exactly that snapshot, which is the same
hindsight-selection defect that killed the 2026-09-07 expansion cell.

### THE BREAK-EVEN ARITHMETIC MOVED IN THE OWNER'S FAVOUR — and the set still fails by ~2x

**His premise was right and this is a real, previously unmeasured finding.** The 4.65x break-even
came from junk-tier arithmetic ($0.999 baseline / $0.215 expanded). Good-tier names DO hold $/fill
up: measured **$0.815-$0.856 expanded, ~4x the junk tier**. The required multiple therefore falls
from **4.65x to 2.33x-2.64x**.

It does not save him because **the binding number is not the symbol multiple**. The 2.33x symbol
multiple converts to an **achieved FILL multiple of only 1.23-1.35x**, verified four ways: one
entry per 900s scan, plus one position per symbol, plus 2 slots, compresses supply. Seven symbols
buy 30% more fills, not 133%. Gap: ~1.3x delivered against ~2.4x needed.

Both escapes close:
- **Remove the slot lock** (7 symbols, 7 slots): substitution falls 0.20 -> 0.05 and it gets
  WORSE (-$83.65/mo). The added symbols' own fills are negative.
- **Capacity is already ~95% free**: both slots occupied only **5.2%** of the time on the live
  universe over 182 days. This was never a crowding problem. (Note the conflicting 11.2% figure
  from 2026-09-07 was measured over TREND's own 18-day life, a different denominator.)

What kills it: the added fills lose money **on their own merits** (-$1.00/fill at U7/2; SOL -$1.50,
LTC -$0.95, BTC -$0.55) **and** destroy incumbents worth +$2.26 (XRP) to +$5.20 average. One
verifier splits the damage 50/50: -$14.25/mo from new fills, -$14.00/mo from displaced ones.
**Both sides of the trade lose.**

### The trigger does not fit — and the fix is worse than the problem

The 4% gate is a volatility artefact as documented, but it does NOT settle this cheaply: BTC fires
3.8/mo, BNB 4-6, LTC 6-7 — 18-35% of ZEC's supply, not zero. **They fail on QUALITY, not scarcity.**

The vol-scaled trigger was swept at the expanded universe, a cell never run before. **It works
exactly as designed and that is why it loses.** Firing-rate CV across the seven falls 0.60 -> 0.13
at k=1.0 sigma (BTC 3.8 -> 13.8 fills/mo). Cost: **-$143/mo**. Every ATR-scaled cell (k=4..14) is
worse.

Mechanism, measured and general: **this sleeve monetises ABSOLUTE move size, because cost is a
fixed 0.190% of notional divided by an ATR-proportional stop.** Sorting all fills by triggering
move size: 0-3% band **-0.277R/fill** (0.247R of it cost drag); 3-4% -0.155R; 4-6% -0.004R; >10%
+0.003R (drag 0.045R). **BTC pays 0.139R per round trip against ZEC's 0.051R — a 2.7x handicap
invisible in an R-denominated scoreboard.** Structurally corroborated: BTC's designed stop is
0.80% against ZEC's 2.00%, so BTC books ~3.2x the R for an identical % move. That is exactly the
artefact the screen's raw-% leg exists to catch, and it is the leg BTC and LTC fail.

**BANK THE GENERAL RULE: any transform admitting moves at equal PERCENTILE rather than equal
ABSOLUTE size loads the book with fills whose cost drag exceeds their edge.** That forecloses
vol-scaling, ATR-scaling and per-symbol gate calibration in one line.

### NO TREND REPLAY IS CURRENTLY CALIBRATABLE

The four calibration factors are 0.79x, 1.10x/1.71x (CI straddling zero), 0.02-0.22x and 0.93x.
They do not converge, and the mechanism was found: **17 of 27 live TREND closes are
`EXCHANGE_CLOSE`, carrying 82% of live R — an exit path no harness models.** Until that is fixed,
do not quote a calibrated TREND dollar figure. **The standing 1.41x fill / 0.85x R factors are
UNVERIFIED and should not be reused.**

### Other corrections to the record

- **ZEC fires 11.1 episodes/month, not 20.9.** The 20.9 figure counted re-entries as episodes.
  ZEC is 53% of U3 supply, not 57%.
- The supply law `episodes/mo ~ 0.126 x annualised vol%` has the right FORM and the wrong
  CONSTANT: cross-sectional slope 0.0721 (R2 0.971), within-symbol 0.0849 (R2 0.781). The filed
  0.126 is 1.5-1.7x too steep.
- Annualised vol: BTC 45.6%, BNB 48.4%, LTC 61.8%, ZEC 142.0% (not the 163.6% on file).
- **Struck from the record:** the "+$34.58/mo at an 8% gate" cell. DECISION_RULE already refutes
  every threshold 3.0-8.0% with the reshuffling mechanism proven. Do not pre-register it.
- The live TREND `$59.36` is two post-deposit ZEC fills (+$75.37, -$28.49) plus noise: equity ran
  $153-$186 for 22 of 27 closes and $1,096-$1,184 for the last 5, so realised risk per fill ran
  $0.56-$4.18 then $12.87-$28.33.

**Verdict: DO NOT SHIP. Leave `FUTURES_TREND_SYMBOLS=ETH_USDT,XRP_USDT,ZEC_USDT` and
`MAX_POSITIONS=2` untouched.** Refuted count ~110.

## 2026-09-08: THE TRAIL ARM — 0.9R REFUTED, and the %-of-margin variant is worse

Twelve agents on the arm, plus a direct test of the owner's follow-up proposal. Triggered by
PONS_USDT peaking at **+$17.82** against an arm at **+$18.46** and giving it back: a $0.64 miss.

### The direct answer

**Leave `FUTURES_CONVEX_TRAIL_ARM_R` unset (1.0).** Not "0.9 is worse" — **0.9 is
indistinguishable from 1.0**, and that is the finding. Five independent corrected harnesses price
the owner's cell at +$3.38, +$5.71, +$5.80, +$13.41 and unmeasurable per month. Median **+$6/mo**
against a $10 bar, 95% interval about **-$30 to +$60**, P(delta<=0) = 0.42-0.47 everywhere.

The canonical ledger, on the wick-peak/close-trigger basis validated against the bot's own poll
(MAE 0.031R on 32 stop exits, where no trail can truncate the peak):

    RESCUED  ONG_USDT   WILDCARD  -1.011R -> +0.479R   +$23.07
    cut      ETH_USDT   TREND     +1.006R -> +0.393R    -$9.50   (unmanaged peak 2.17R)
    cut      BICO_USDT            +0.731R -> +0.449R    -$4.37   (peak 1.48R)
    cut      ZEC_USDT   TREND     +0.559R -> +0.403R    -$2.43   (peak 1.23R)
    cut      HFT_USDT             +0.508R -> +0.458R    -$0.77   (peak 1.03R)
                                  1 rescued / 4 cut    +$6.00 over 32 days

Three things kill it, none fixable by a better point estimate:

- **PLACEBO.** Displace entries 15-480 min on the same tapes: the 1.0->0.9 change scores mean
  **-$42.85/mo, sd $54.59**. The observed result is a +1.0 sigma draw from a distribution centred
  deeply negative. At 0.80R the placebo is negative in **10 of 10** phases.
- **n=1.** Drop ONG_USDT and the cell is -$14 to -$16/mo. Leave-one-out flips the sign in every
  harness.
- **NO PLATEAU.** 0.95 / 0.90 / 0.85 / 0.80 read +$20 / +$6 / +$1 / +$19 and the sign flips at
  0.85. The global maximum of the 84-cell grid is at arm **1.50** — the OPPOSITE direction — and
  the family-wise null's median best-of-84 (+$161/mo) is ABOVE the best observed cell (+$138/mo).
  **The surface is less structured than chance.**

### The reframe that actually decides it

With the trail switched off, **40 of 80 trades (~38/month) TOUCH 0.9R at some point, while only 2
FINISH there.** A 0.9R touch is worth **+1.415R unprotected (n=39-40, median +1.262R,
P(final<0)=0.31)**. The proposal installs a 0.45R floor under 38 trades a month to catch 2. All
four cuts above are trail-to-trail: trades that dipped under 0.9R and then ran, evicted before
the run.

**The trade the owner is angry about and the trade the change would cost him are the same trade
at two different moments.**

### The 1R cliff is MANUFACTURED — retire the peak-bucket table from the record

The table that made the arm look well-placed (peak >=1.0R averages +1.388R vs -0.72R below) is
circular: trades reaching 1R receive a floor at >=0.5R and trades below it receive nothing. With
the trail disabled on identical paths the 1.0-1.5R bucket returns **-0.816R to -0.970R**,
indistinguishable from the 0.9-1.0R bucket's -1.03R. Corroborating: 41 live trades reached peak
>=1.0R and **zero** realised R<0 — the floor holds by construction.

The only non-circular statement is the conditional survival curve, and it has **no step anywhere**:

    P(unmanaged peak >= 2R | reached X):
    0.523 @0.7R  0.561 @0.8R  0.575 @0.9R  0.590 @1.0R  0.639 @1.2R  0.697 @1.3R  0.742 @1.5R

Reaching 1R predicts nothing 0.9R does not. **This cuts against the owner, not for him:** with no
informative level anywhere in 0.7-1.5R, moving the arm reclassifies nothing — it only churns.

### THE %-OF-MARGIN ARM (owner's follow-up: "15%? for PONS that's ~$16")

Tested directly on the same Min1 paths, n=77. A %-of-margin arm is NOT a flat R arm:
profit as % of margin = r x sl_margin_pct, and sl_margin_pct = sl_frac x leverage x 100, so

    r_arm = P / (sl_frac * leverage * 100)

**1R ranges 10.13% to 21.15% of margin (median 17.19%)**, because leverage is set to
`int(20/(sl_frac*100))` and integer truncation leaves the effective stop anywhere from 10% to 21%
of margin. So a flat 15%-of-margin arm fires at **0.71R on some positions and 1.48R on others**.

    P of margin   arm range (median)   resc/cut   $/month    ex-top-5%
     8%           0.38-0.79R (0.47)     12/23      -40.76     +106.74
    10%           0.47-0.99R (0.58)     10/16      +39.30     +113.44
    12%           0.57-1.18R (0.70)      5/8       -21.56      +48.31
    14%           0.66-1.38R (0.81)      4/8       -68.03       -1.40
    15%  <-owner  0.71-1.48R (0.87)      4/6        -7.54       -8.06
    16%           0.76-1.58R (0.93)      5/5        -4.63       -4.95
    17%           0.80-1.68R (0.99)      6/3        +1.25       +1.34
    18%           0.85-1.78R (1.05)      5/3       +39.18      +41.93
    20%           0.95-1.97R (1.16)      6/6        -5.84       -6.25
    22%           1.04-2.17R (1.28)      9/8       +48.35      +51.74
    25%           1.18-2.47R (1.45)     13/9      +133.76     +143.13

**The owner's 15% cell is -$7.54/month**, and the placebo settles it: shifting every entry +/-12h,
**41 of 60 shuffles produce a LARGER absolute effect than the real one** (real -$8.06, placebo
median -$10.00, 5-95% [-$49.31, +$21.64]). Adjacent cells swing +$39 / -$68 / -$7.5 / -$4.6 /
+$1.3 / +$39. A surface that moves $100 between neighbouring cells is measuring path noise.

**And the mechanism runs backwards.** At 15% the single largest move is **MOVR_USDT, -$18.62** —
its 1R is 11.7% of margin, so 15% of margin equals **1.282R** and the rule arms LATE, not early.
The rule arms earliest on positions where integer-leverage truncation happened to make the stop
cheap, which is a rounding artefact, not information about the trade.

**Note for the record: R IS ALREADY A DOLLAR RULE.** 1R is the position's dollar risk; the trail
already arms at a dollar figure ($18.46 for PONS). The %-of-margin variant does not make the rule
more dollar-denominated, it changes the denominator from dollars-at-risk to dollars-of-margin,
and the two differ only by leverage truncation.

### "The account is funded larger so we let more dollars go" — arithmetically void

Sizing is proportional to equity: `margin = risk_pct x available_balance x 100 / sl_margin_pct`,
bounded by another fraction of balance. Equity appears linearly in every term and cancels out of
R. Measured across the 7.01x deposit boundary (equity $169.10 -> $1,098.95): **corr(log equity,
normalised risk_pct_actual) = +0.041, n=75**, and realised 1R stayed at 1.371% (TREND) / 1.381%
(WILDCARD) of equity on BOTH sides. **The deposit multiplied every dollar by ~7x and moved the
R-optimum by exactly zero.** The same ONG rescue worth +$23 today was worth **+$0.55** when it
happened.

What funded size DOES change is dollar variance: bootstrapped one-week P&L at $1,114 equity over
21 trades is **mean +$13.1, sd $93.4, P(week<0) = 45.8%**.

**The strongest form of the owner's argument, made properly and then answered.** He is right that
a one-week-then-withdraw horizon breaks the compounding assumption behind Kelly — variance drag
(geometric = arithmetic - sigma^2/2) is a compounding phenomenon, and on a fixed horizon with a
withdrawal you take the arithmetic mean. That version is real. **It is also empty here:** arm
1.0 -> 0.9 moves week-sd from **$93.4 to $92.7**, a 0.7% reduction. The change buys ZERO variance
reduction. The only cells that meaningfully cut week-sd are arm 0.50-0.70 (sd $66-$89) and every
one of them has mean <= 0. **The variance-reduction frontier exists on this book and every point
on it is bad.**

### Size of the prize, so the ceiling is on the record

Across 80 trades in 32.1 days the book gives back **80.7R = $1,250 of peak excursion**
(~$1,186/month at 1R=$15.49). But **$558/mo sits in the peak<0.5R bucket where no arm change can
reach**, and **$465/mo in the >=1.0R bucket which is ALREADY floored**. The slice the owner is
complaining about — peaks 0.8-1.0R — is **3.89R = $60/month, from two trades.**

### What arming at 0.9R would actually have banked on PONS

Not $17.82. The floor would be `max(0.50 x 0.9653R, 1.5 x cost_r) = 0.483R = $8.91 gross, $8.49
net` — **48% of the excursion**, +$3.21 against the current mark, and it surrenders a live 5R
take-profit worth $92.30. It would also NOT have saved MARSCOIN (peak 0.821R); that needs 0.80R,
where the placebo is negative in 10 of 10 phases.

### Alternatives, all priced and all dead

| mechanism | $/mo | status |
|---|---|---|
| two-stage breakeven floor @0.8R | +$2.13 | p=0.935; offered at +$26 before correction |
| breakeven+cost lock @0.9R | +$3.9 / -$0.5 | matched placebo P=0.53 — trigger carries zero information |
| tiered retain 0.25-0.35 in [0.9,1.0) | +$3.9 to -$4.7 | sign-unstable |
| time-conditional arm (last N hours) | +$0 to +$3 | **INERT** — only 6 of 80 trades reach the clock |
| dollar giveback cap $8-$12 | +$6 | near-inert (1 trade); fully inert at $15-$20 |
| **% giveback cap (10-25% of peak)** | **-$74 to -$164** | **most harmful thing tested** |
| arm 0.70 / 0.60 / 0.50 | -$62 / -$86 / -$110 | genuinely refuted; cuts the tail (ENA -4.6R = -$71) |

### Corrections to the record

- **The prior refutation was reproduced BIT-EXACT** (commit e38b5c4, `tools/pit_arm_sweep.py`,
  unchanged since) and required Min15 bars with the peak updated only at bar END, no cost guard,
  flat 0.03R cost. Intra-bar makes it **STRONGER**: at 0.9R the winners-cut count goes 2 -> 5.
- **THE TRAIL DOES NOT POLL AT 45s OR 450s.** `USE_OPEN_POSITION_GUARD` and
  `FUTURES_OPEN_POSITION_MONITOR_SECONDS=1.0` are live defaults, so
  `_monitor_open_positions_once` -> `_hourly_exit` -> `_convex_runner_trail_exit` and
  `_convex_time_stop_exit` run **once per second** against the WS fair price. 450s is the ENTRY
  scan interval and governs nothing on the exit side. The `/status` clock docstring shipped with
  this error the same day and was corrected.
- **The cost guard is INERT** for every configuration tested: `1.5 x cost_r` runs 0.013R-0.126R
  and exceeds the retention floor on 0 of 80 trades down to retain 0.35, 2 of 80 at retain 0.25.
- **Recorded `peak_r` is a poll-sampled maximum**, written from `r_now` at the poll mark
  (runtime.py:2119), not a true intra-bar high. EGLD_USDT recorded peak 1.1241 live and armed,
  exiting CONVEX_RETENTION_TRAIL at +0.51R — a Min1-CLOSE reconstruction read it as 0.914 and
  scored it a "rescue". Reconstruction on closes rather than wicks manufactures near-misses.
- Of the three named near-misses only TWO clear 0.9R (ONG 0.962R, PONS 0.965R). MARSCOIN (0.821R)
  needs 0.80R.

**Verdict: change nothing. Arm stays 1.0, retain stays 0.50, ratchet stays 3.0R/0.75.** Refuted
count ~100.

## 2026-09-07: SLEEVE ALLOCATION — retire WILDCARD, grow TREND, or neither. Answer: neither.

Twelve agents, 430 tool calls, five configuration questions each adversarially verified, plus a
completeness critic. **All five verifiers rejected their agent's recommendation.** They converge
anyway, and the convergence is the answer.

### THE BOOK SPLITS AT 2026-08-20 AND NOBODY HAD EVER LOOKED

    era                              closes  days   net $      fees $   gross $
    BEFORE 08-20 (the PMT era)         130     76   -108.92     49.66    -59.26
      of which PMT                      55            -101.23    42.73
    SINCE 08-20 (the CURRENT config)    70     17    **+55.07**   10.55    +65.62
      TREND  n=27  +$59.36  |  WILDCARD n=42  -$4.46  |  PMT n=1 +$0.17

Lifetime the corpus reads **-$53.85 on $60.21 of fees**, and a completeness critic reported that
as "the book has lost money and not one of five reports said so". True, and misleading: **the
entire loss is the decommissioned PMT sleeve** (retired 2026-07-13, last close 08-20). PMT ended
the same week TREND began. The configuration actually running has made **+$55.07 in 17 days**.

Use the 08-20 split for every future book-level claim. The pre-08-20 rows are a different bot.

### THREE PREMISES I GAVE THE AGENTS WERE WRONG

**1. "Nothing binds" is a WILDCARD fact, not a TREND fact.** On a 5-minute grid over TREND's
18.2-day life: 0 positions 64.3%, 1 position 24.4%, **BOTH SLOTS FULL 11.2%**. Post-deposit: 0
positions 21.8%, 1 position 78.2%. The slot cap refused a live TREND candidate **58 times in 131
days**, 20 of them inside the 17.4-day live window. Wall-clock idleness is the wrong instrument;
the question is whether a slot was full AT THE MOMENT a signal arrived.

**2. The sleeves DO compete — for available balance, continuously.** `runtime.py:1761` sizes off
`AVAILABLE_BALANCE`, not equity. **16 of 27 TREND fills opened with non-TREND margin locked**,
mean haircut 4.96%, max 19.1%. So retiring WILDCARD up-sizes every later TREND fill ~5%, which is
the same order as WILDCARD's whole contribution. "Retiring frees nothing" was wrong.

**3. TREND books 10.4 closes/week, not the 2.5 this document has been asserting** — off by 4.4x.
Trial 19's "30 closes is 8-12 weeks" is really **3-6 weeks**. Fix that number wherever it appears.

### IS TREND REAL? BOTH ANSWERS

    symbol          n   meanR    sumR
    ZEC            17  +0.353   +6.00
    XRP             4  +0.905   +3.62
    ETH             4  -0.353   -1.41
    SOL             2  +1.605   +3.21   <- NOT in FUTURES_TREND_SYMBOLS
    in-universe    25  +0.328   +8.21
    ex-ZEC          8  +0.276   +2.21   <- removing one trade takes it to -0.110R

**Three agents and one verifier reported ex-ZEC as +0.542R and concluded "TREND is not one
coin". That number is wrong** — it includes two SOL fills from a retired universe. Restricted to
symbols the bot can actually trade it is **n=8, +0.276R, 90% CI [-0.63, +1.28]**. Uninformative.

What IS informative: an independent placebo test, 1 year Min15 and 3.93 years 4h, against random
entry on the SAME symbol, audited for lookahead and **re-run in raw % return with the ATR
denominator stripped** so normalisation cannot manufacture the edge:

    ZEC  +1.028% excess (n=844, t=+5.49)   SURVIVES
    XRP  +0.612%                            SURVIVES
    ETH  +0.124% (p=0.54)                   does not
    SOL  -0.027%                            NEGATIVE

**Ruling: the detector is real on ZEC and XRP. The dollars are ZEC's.** Mechanism is mundane and
matters: the 4% ROC gate is an ABSOLUTE threshold on symbols with 2.5x different volatility, so
ZEC (163.6% annualised) clears it 2.5x as often. ZEC does not trend better (24h efficiency 0.114
vs ETH 0.109) — it just moves more. ZEC has had 10 non-overlapping 15-day runs of >=+53% in 3.83
years, six in the last 12 months; **ETH has had ZERO.**

### THE $/FILL CRITIQUE: RIGHT IN PRINCIPLE, IRRELEVANT IN EFFECT

I argued the prior refutation used the wrong criterion, since +0.215 $/fill is still positive and
capacity looked free. Rebuilt on total dollars, the verdict does not flip, and it fails on
arithmetic rather than preference:

    break-even fill multiple = 0.999 / 0.215 = 4.65x
    measured multiple, 3 -> 11 symbols       = 1.73x to 1.91x
    measured multiple at 20 symbols          = 3.30x
    3.30 < 4.65 at the widest universe anyone tested.

The ceiling on the multiple is linear in symbol count because of one-position-per-symbol, and the
2-slot cap halves the realised figure. **The expansion cannot buy enough fills to pay for the
quality it gives up even with capacity 100% free.** Three quantified mechanisms, none of which is
risk concentration:

1. **Empty population.** Top-5 by turnover average +0.387R/fill standalone; the next fifteen
   average **+0.016R**, with TAO -0.139 (t -2.19), ONDO -0.129, AVAX -0.159 individually
   negative. Expansion by turnover rank buys zero-expectancy fills.
2. **Adverse displacement — fills are NOT additive.** A position holds its slot up to 24h, so a
   new symbol refuses the base symbols' signals concentrated in exactly the broad-trend windows
   where the base pays most. The 8-majors expansion keeps 76 of 129 base fills, **destroys 53
   worth $9.19/fill and buys 147 worth $1.685/fill**. Substitution runs 0.11-0.65, never zero.
3. **Drawdown grows with fill count while return grows sub-linearly.** P(-20% DD in 3 months):
   3 symbols 26%, 5 symbols 54%, 8 symbols 71%, 12 symbols 85%, 20 symbols 92%.

**The one positive expansion cell was lookahead.** A "wider universe, tighter trigger" cell
(top-8, MIN_ROC 6%) priced at +$55/mo. Rebuilding the universe ranking POINT-IN-TIME from the bar
tape at window start, instead of a turnover snapshot taken on the LAST DAY of the measured
window, the same cell goes to **-$64/mo**. The lookahead was worth $119/mo, 79% of the cell. Its
two carriers appear in no point-in-time top-8.

**Replace the pre-registered screen.** Not "$/fill must not fall" but: positive excess over that
symbol's OWN random-entry placebo, in raw % return as well as R, p<0.05 over >=1 year, stable
sign across >=3 of 4 multi-year eras, membership decided by information available at window
start. Of everything measured only ZEC and XRP pass, and both are already in.

### 1R IS $15.49, NOT $25

Realised risk drawn is **1.371% of equity (TREND, n=27) and 1.381% (WILDCARD, n=50)**, not the
2.41% config ceiling, because the regime scaler cuts it. Four of five studies priced at $25 and
are uniformly **1.61x too high**. And trial 19 is pre-registered to open AFTER the withdrawal, at
$190, where 1R is **$2.60** — so the "$10 bar is now 9x looser" argument is backwards for the one
change it was applied to. Every trial-19 estimate divides by 5.95: **+$0.22 to +$1.70/month.**

### THE RANKED CONFIGURATIONS (at realised 1R = $15.49)

    #  configuration                          $/month   maxDD    ex-top-5%   fills/mo  wks->2SE
    1  DO NOTHING (live)                        +241   -13.9R     +$160        78       9-15
    2  Retire WILDCARD                          +201    -8.0R     +$226        47       9-15
    3  Trial 19, slots 2->3                     +241    +0.5-2R    mostly worse 80       >=30
    4  Drop ETH -> XRP+ZEC only                 +243   -12.0R     best cell     42       9-15
    5  Shrink WILDCARD to 0.5x                  +221   -10.1R     +$193        78        201
    6  Refine WILDCARD (any parameter)             0        -         -         78        201
    7  Universe +8 majors, 2 slots              +190   -16..-18R   -$87        133      >=100
    8  Universe + slots coupled (11-20, 3-4)  +120..180 -20..-29R  -$100..-290  95-128   >=100
    9  Retire WILDCARD + lever TREND up         +241    -8.3R     +$241        47       9-15
    10 Re-enable SQUEEZE                        -117    -8.7R     -$183        16        530
    11 Re-enable SNIPER                         -106    -4.2R     -$352        67         44
    12 Re-enable PMT                            -207    -6.3R     -$289        43          4

**Rows 1-5 are inside each other's noise.** The baseline's own 90% band is **$764 wide**
[-$130, +$634]. Every delta argued across five studies is an order of magnitude smaller than the
uncertainty on the thing it is a delta from. Rows 7-12 are outside the noise in the wrong
direction and are settled.

Row 9 is rejected on Kelly: it pushes risk to ~2.72% against a 2.2% pooled-book anchor, buys
dollars 37% likely negative, and concentrates the book on 25 fills of which 17 are one coin in
one 15-day run.

### THE DECISION, AND THE ARGUMENT THAT MAKES IT ONE

**Hold every trading parameter. Do not open trial 19. Amend its pre-registration.**

**TREND reaches a 2-SE read on its own mean in 96 in-universe fills — 9 weeks at 47.4/month, 15
at the conservative 27.4/month.** That read settles whether the sleeve carrying essentially all
the book's expectation exists outside ZEC, a question worth **$139-241/month**. WILDCARD needs
1,521 fills = **201 weeks**. The slot question needs ~47 blocked episodes = ~7 months.

A config change starts a new trial under this project's own reset rule. **Opening trial 19 trades
a 9-15 week read on a $200/month question for a 7-month read on a $0/month question.** That is
the whole argument.

Time-to-verdict scales as (sd/mean)^2, NOT fill rate. WILDCARD's mean/sd is 0.051 against TREND's
0.203. **The sleeve kept because "at least it produces data" produces almost none** — 1.4x the
fill rate and 1/29th the information rate. That retires the measurement-instrument argument for
keeping WILDCARD, which was mine.

### Corrections to live limits that were nearly made on arithmetic errors

- **DO NOT raise trial 19's 20% drawdown kill.** The proposal to raise it to 35% rested on a
  25.4%-of-equity baseline drawdown computed by replaying TREND at 2.41% risk instead of live's
  1.371% — a 1.43x inflation. **Live realised TREND maxDD is 11% of equity.** Nothing breaches.
  Acting on it would have weakened a live safety limit on a funded account to fix a bad number.
- **DO NOT set `FUTURES_WILDCARD_RISK_PCT` to 0.5x.** It is the ONLY risk dial in the codebase;
  `grep` finds no `FUTURES_TREND_RISK_PCT`, and TREND opens through
  `_open_wildcard_position(..., kind="TREND")` at `runtime.py:6255`. Halving it **halves TREND
  too**, roughly -$150/month against the WILDCARD variance it buys.
- **DO NOT ship the shadow-log de-duplication guard.** The defect is real (TREND `slot_occupied`
  duplicates 3.50x) but de-duplication is an ANALYSIS step: five of six equally defensible
  aggregation rules give the OPPOSITE sign to the one proposed, on n=4. The guard would destroy
  the rows needed to sweep that choice. Keep the raw log; de-duplicate in analysis.

### The variance dial nobody priced

`FUTURES_WILDCARD_MAX_POSITIONS` 3 -> 2. Not shared with TREND, no code change — it does what the
0.5x proposal wanted without its defect. Replaying the live WILDCARD entry sequence in order:

    cap  taken  sumR    meanR    ex-top-5%   blocked
    3     62    +4.37   +0.070    -0.147       0
    2     57    +6.35   +0.111    -0.124       5  (sumR -1.98)
    1     41    -2.38   -0.058    -0.239      21  (sumR +6.75)

+1.8R/month, improves the tail, cuts concurrency. **n=5 blocked and post-hoc, so INCONCLUSIVE** —
but better-shaped than the recommendation that was made, and in nobody's grid. WILDCARD occupancy:
3 open **0.9%** of wall-clock, so 3->2 is nearly inert on fills and 3->1 is not.

### The largest measured object in the book, which nobody proposed touching

`FUTURES_TREND_LONG_ONLY=1`. Fourteen de-duplicated blocked SHORT episodes resolve at **-0.671R**,
robust across all six aggregation rules and every gap boundary from 0.25h to 48h, permutation
**p=0.0085** against the live long arm. At realised 1R that is **~$242/month of avoided loss,
against a book earning ~$241/month.** It is already on and appears in none of the three options.
Caveat that keeps it out of the recommendation: 0 of 42 blocked shorts ever reached TP, so this
may be one violent directional era rather than a permanent property. **Protect it** — and note
that universe expansion multiplies the population it must filter, an independent fourth reason
not to expand.

### Corrections to the prior record

- **The 2026-09-07 TREND re-entry-depth finding does NOT replicate.** Live n=8 (all ZEC) gave
  depth>=2 at -0.383R. On an independent 1-year, 4-symbol, **n=556** replay the sign REVERSES:
  shallow (d<2) +0.159R vs deep (d>=2) **+0.471R**, and depth 3+ is the best cell at +0.814R
  (t=+4.29). At matched depth<2, ZEC live is +1.007R (n=9) vs non-ZEC +0.542R (n=10) — ZEC is
  BETTER like-for-like. The live deep cluster was a 19-day accident and the risk$ gradient by
  depth was purely the deposit landing on it. The "do not ship" verdict stands; the DIRECTION
  recorded was backwards.
- **The replay's 4.16x fill inflation is a WILDCARD figure, not a TREND one.** Calibrated on
  TREND over the 17.4-day overlap the harness runs at **1.41x** live's fill rate and UNDERSTATES
  total R by 0.85x. TREND replay work is far better calibrated than the trial-19 estimate was.
- **The 40 WILDCARD rows missing `risk_usdt` are an ERA, not a random subset**: rows WITH it run
  2026-08-12 to 09-06, rows WITHOUT run 06-15 to 08-08, zero overlap. The "n=50 honest
  population" everyone quotes as WILDCARD's edge IS the last 25 days.
- Ring buffer turns over every **52 days** at the current 3.86 closes/day. Within ~7 weeks it
  loses all 55 PMT rows, 6 SQUEEZE rows, 24 early WILDCARD rows and every row lacking
  `risk_usdt`. Snapshot before each roll.

### Verdict

**No trading parameter changes. Do not retire WILDCARD, do not refine it, do not grow TREND.**
Post-week, logging only: persist `ref_roc` (the external gate computes corroboration STRENGTH on
every convex entry, thresholds it at 0.4, and stores only the boolean — the `move_not_corroborated`
veto fired 1 time in 211 shadow candidates, so >99% of the mass and all the structure sit in the
discarded range; n=100 accrues in ~25 days). Then let the 9-15 week TREND read run undisturbed.

## 2026-09-07: THE WILDCARD SLEEVE — "it bleeds" is FALSE; ~50 alternatives priced, none ship

Fifteen agents, 483 tool calls, eight diagnostic angles each adversarially verified, plus a
completeness critic. Triggered by my own claim to the owner that "WILDCARD bleeds". That claim
was wrong and this section is the correction.

### The premise, corrected twice

WILDCARD lifetime: 90 closes, 2026-06-15 to 2026-09-06, net **-$7.66**. That headline is one
trade — MAGMA_USDT LONG 09-06, **-$26.45**, a clean -1.06R stop that happened to be the first
one taken at 6.3x the old dollar scale. Ex-MAGMA the sleeve is **+$18.78 over 89 closes**.

First correction: in R the sleeve is +0.256R/fill (n=72, t +1.16), not negative.

**Second correction, from the completeness critic, and it is the one that matters:** that
+0.256R is carried by rows with no recorded risk denominator.

    population                        n     meanR    SE     t     netR    P(mean<=0)
    published "usable"               72    +0.2557  0.220  1.16  +18.41     0.120
    rows WITH risk_usdt              50    +0.0774  0.213  0.36   +3.87     0.366
    rows with R but NO risk_usdt     22    +0.6609    -      -   +14.54       -
    all 90, first-11-days imputed    90    +0.146     -    0.80  +13.17       -

**79% of the sleeve's netR sits in 22 rows whose R is reconstructed, not measured.** On the 50
fills where the bot actually recorded what it risked the sleeve is **+0.077R, t=0.36** — a coin
flip — and **negative ex-top-5%** (-0.129R). The 18 unscored rows (2026-06-15 to 06-25, a clean
instrumentation-start truncation, NOT the loss-censoring pattern) lost -$13.69; imputing them
makes every published netR for this sleeve about **5R (~$130 at funded scale) too generous.**

**Stop quoting +0.256R.** Defensible: +0.077R (n=50) or +0.146R over all 90 imputed.

### What the sleeve actually is

A tail lottery with **no demonstrated entry skill**, wrapped in an exit stack that is correct and
one gate that is the only thing in it with a real signal.

- Against a placebo re-entering the SAME symbol at random times with the same hold and the same
  designed stop, the LONG arm's excess is **-0.007R** (n=43, t -0.03). Not "evidence of no
  skill" — SE 0.224 cannot separate -0.007 from +0.4 — but nobody had ever looked.
- The loss column is not a distribution, it is a constant: **24 stop-outs, every one at -1.044R
  (SE 0.006).**
- The exit is right and the entry is wrong. After a stop-out price keeps going: mean mark
  **-0.791R four hours later** (t -5.73), profitable 1h later in **0 of 24** cases. The bot is
  NOT being wicked out.
- The whole positive mean is four trades. Ten fills >= +2R contribute +42.79R; the other 61 net
  **-23.42R**.

### THE ONE HIGH-SIGNAL OBJECT: the external listing veto

`FUTURES_EXTERNAL_GATE_REQUIRE_LISTED=1` blocks signals with no second-venue corroboration.
Found independently by two agents on the resolved shadow ledger:

    ref_not_listed   n=32   mean -0.492R   SE 0.178   p=0.0045 (5000 shuffles)
                     leave-one-out -0.594..-0.474    ex-top-5% -0.678R (MORE negative)
    all ext vetoes   n=42   mean -0.363R vs +0.522R control, gap 0.884R, p=0.0145

**This is the only cell anywhere in the study at p<0.01**, in a search spanning ~120 entry-gate
cells (zero at p<0.05 where 6 are expected) and ~68 exit/sizing cells. The four post-deposit
candidates it refused would have cost **-2.528R = -$63.20 in 3.3 days**. The gate is why the
sleeve is not bleeding.

**The strategic content of the whole exercise:** the junk this sleeve admits is NOT selected by
any transform of its own price. It is selected by "MEXC-only pump with no second-venue
corroboration". ROC windows, calm ratios, pullback depths, stop widths, trail parameters and
regime splits are now searched to exhaustion and return LESS structure than random labels.

**NEVER relax REQUIRE_LISTED.** Sub-item: the veto returns `(True,'failopen')` on any exception
behind a 0.6s timeout and nothing counts it. Two fail-open fills identified (US_USDT 08-14,
ORDI_USDT 08-21, both stops), ~0.33/month = -$4 to -$8.5/month. Add a COUNTER; do not touch the
timeout until the logs say whether those two were timeouts or API errors.

### DATA LOSS WITH A DEADLINE — acted on 2026-09-07

`_save_state` writes `trade_history[-200:]` (runtime.py:4379). The buffer holds **exactly 200
rows** and the book closes 3.50/day. The 22 rows carrying 79% of the sleeve's netR sit at buffer
index 65-113: **first evicted in 19 days, last in 33.** Within ~3 weeks nobody could reproduce
any of this, and the era that makes the sleeve look positive would vanish with no alert.

**Snapshot taken and committed: `data_snapshots/futures_runtime_state_2026-09-07.json` (200 rows
back to 2026-06-03) and `futures_feature_store_2026-09-07.jsonl`.** Repeat before each roll.

Still outstanding: a MEXC private-history reconciliation against the ring buffer, which is the
one remaining data-integrity check and needs a live API read.

### THE CLOSED-TRADE RECORD DROPS ALL ENTRY METADATA — fifth occurrence

**WILDCARD rows in trade_history carry `metadata = {}` — 0 of 90.** The live open position
carries **49 keys**, including `turnover_24h_usdt`, `candidate_rank`, `candidate_field`,
`calm_ratio`, `vol_z`, `atr_pct`, `entry_lateness`, `ref_listed`, `risk_pct_actual`.

Cause: `_close_history_trade` (runtime.py:4752-4805) builds the record field by field and
promotes only six metadata keys. The comment beside `entry_slippage_bps` names this exact
failure and it was fixed for that one field only. `_append_feature_store` (~4892) has the
sibling whitelist bug and its own comment already says *"Same bug, third occurrence."*

    THE FIX IS ONE LINE:   "metadata": dict(position.metadata or {}),

**Measured cost of the defect:** one agent spent an entire study reconstructing turnover-at-entry
from klines and its verifier killed the conclusion on a lookahead artefact — while the bot had
recorded the exact point-in-time `turnover_24h_usdt` on the position object and discarded it 48
hours earlier. Three other agents reconstructed values the bot had already measured.

Correction to the smaller fix: `roc_z` is ALREADY whitelisted (4913). It is null because
wildcard.py:229 computes it only under `FUTURES_WILDCARD_SIGMA_TRIGGER`, which is off live. That
belongs in the detector, not the whitelist.

### exit_kind is a relabelling of P&L, not a record of what fired

`_classify_exit_kind` (runtime.py:4956) derives TP/STOP/OTHER from **realised R** — TP at >=0.9x
target, STOP at <=-0.85. So "STOP exits average -1.044R" is a tautology. `EXCHANGE_CLOSE`
(5145) is a reconciler path written whenever a position vanishes from the exchange list, with no
knowledge of which order filled; it splits into STOP 22 (-22.95R) / TP 2 (+10.05R) / untagged 16
(+12.15R). `exit_rule` is a byte-for-byte duplicate of `exit_reason` in all 90 rows.

**Every prior exit-family verdict that filtered on `exit_kind` was filtering on a relabelling of
P&L.** Two mislabelled rows found (BICO 17.17h, BTW 11.26h, both tagged CONVEX_TIME_STOP, closed
two seconds apart on 08-05 — a restart bulk-close wearing a designed exit's label, contaminating
29% of that cohort).

### Refuted this round (~50 alternatives, adding to the ~34 already recorded)

| refuted | measurement |
|---|---|
| WILDCARD long-only / short-only / asymmetric risk | gap collapses to +0.144R p=0.373 ex-preAug; costs $51-163/mo |
| raise turnover floor 2M -> 4M | **LOOKAHEAD**: bar-OPEN keying put up to 60min of post-entry volume in the "pre-entry 24h" window |
| trigger 8% -> 7% | shadow population is not takeable; 2 of 6 rows fail calm_ratio at any trigger; band +0.238R -> +0.025R after the join |
| TP cap 5R -> 6/7/8R | peak window ran 82-183h past entry against a 24h clock; only 2 of 7 reach 7R inside it |
| early-adverse cut, full 5x6 grid | 24 of 30 cells negative, grid mean -3.29R; survivor died on phase-jitter |
| stop tightening 0.5x/0.75x, widening 1.5x | negative in all three exit models; the widening gain is a replay artefact |
| partial exits / scale-outs at 2R | worst result in the study |
| leverage cap 2x-10x | analytically inert — leverage cancels out of risk-targeted sizing, 53/53 rows land on int(20/(sl_frac*100)) |
| per-sleeve risk tilt | the sleeves already draw identical risk, 1.381% vs 1.371%, t +0.07 |
| risk multiplier 0.25x-1.5x | a line through the origin; netR invariant at +18.41 in every cell |
| regime scaler pinned to 1.0 | size-neutral lifetime value +$0.84, permutation p=0.941 |
| WILDCARD slots 3 -> 2 | +$5.3 vs -$5.8/mo, p=0.514; 3 slots occupied **0.35%** of wall-clock |
| regime/session/BTC-context, 18 formulations | family-wise p 0.15-0.68; best placebo beats the real gate |
| cooldown after losses | WILDCARD does BETTER after losses (+0.443R vs +0.083R) — the throttle would fire on its best cell |
| repeat-symbol re-entry (the TREND rule, ported) | depth 1/2/3/4 = +0.192/+0.288/+0.627/+0.192R, p=0.729 |
| min pullback depth, both parameterisations | refuted |
| listing age, spread veto, pump-inflation ratio | cuts nothing and destroys runners / bad bucket is n=4 |

### Structural facts established

- **Live is candidate-starved, not slot-constrained.** 0 of 593 post-deposit scans had slots
  full; 3 WILDCARD slots held 0.35% of wall time; peak simultaneous margin across ALL sleeves
  $244 = 21.7%. The 5% risk cap and 25% margin cap have **never** bound (max 2.36%, 18.48%).
  The "slots bind" finding comes from the replay, which runs at **4.16x** live's fill rate.
  Consequence: every tightening cost in this study is near-pure subtraction with no substitution
  credit, which makes those costs real.
- The **fill-rate collapse is market supply, not a defect.** All four internal explanations
  refuted by direct measurement. `FUTURES_MAX_CONCURRENT_POSITIONS=2` does not constrain the
  convex path at all — `_open_wildcard_position` never reaches the portfolio-margin block.
- `FUTURES_WILDCARD_PREEMPT_ENABLED=1` is **structurally inert** — preemption can only fire when
  slots are full, which is 0.35% of the time; live `preempt_log` is empty.
- **TREND is signal-supply-constrained too** (0 positions 93.2% of wall-clock). There is no queue
  of TREND signals waiting for WILDCARD's margin, so **WILDCARD-vs-more-TREND is a false
  choice**; the comparison is WILDCARD-vs-nothing.
- Diversification, 38 days: corr(WILDCARD daily R, TREND daily R) = **+0.026**, genuinely
  uncorrelated. Book Sharpe 3.00 -> 3.50 adding WILDCARD, but maxDD worsens 7.25R -> 9.94R, the
  block-bootstrap P(no Sharpe gain) = 0.368, and ex-top-5% of WILDCARD the book Sharpe collapses
  3.00 -> 1.22. **Uncorrelated return, not drawdown reduction.**
- **Four code-vs-env divergences**, not one: `wildcard_long_only` code default True vs env 0;
  `max_positions` 2 vs 3; `min_turnover_usdt` $3M vs $2M; `SL_ATR_MULT` 1.5 vs 3.0; `MAX_SCAN`
  25 vs 90. Losing an env var silently changes the strategy in five places.
- `MAX_SCAN=90` **does not bind** (scan_capped=0, movers=35). Live's pool is defined by the $2M
  floor and the 24h-range gate and is 35-57 symbols. **The pullback-resume study's decisive axis
  was a "top-90 slice" meant to represent live — so the most expensive gate in the bot had its
  sign flipped on a mis-specified universe.** Re-run it on the real pool.
- The **7% stopping rule is a rubber stamp**: under a band with exactly zero edge the
  pre-registered two-condition test passes 47.7% at n=30 and 49.1% at n=100. Retire the rule,
  not just the cell.
- Harness defect, generalised: `pit_intrabar.fetch_grids` passed `days` through to a chunk count
  on a hardcoded BAR=900 while the interval was Min5, so **every published intra-bar "full
  history" replay before 2026-09-07 ran on ~one third of its stated window.** Seven WILDCARD
  harnesses have no recorded verdict at all (`pit_cooldown`, `pit_adverse_cut`, `pit_slots`,
  `pit_trail_cooldown`, `pit_short_tp`, `pit_bands`, `pit_tut_class`) — re-run, do not recall.

### THE ONE MEASUREMENT: shadow-log the detector rejects (queue item 0b)

`detect_wildcard_signal` refuses **64,854 of 84,569 trigger bars (76.7%)** on
`no_pullback_resume`, 14.4% `low_volume_z`, 4.2% `climax_wick`, 1.1% `rsi_exhausted`, 0.8%
`vertical_blowoff`. They reject inside the detector via `_rej()` and produce **no shadow row at
all**, so neither the taken nor the rejected population carries their features — which is why
four live gates (`MIN_VOL_Z`, `MAX_WICK`, `VERTICAL_ATR_MULT`, `RSI_MAX/MIN`) have **zero
measurements of any kind** anywhere in this document.

It is the largest unmeasured surface in the bot by two orders of magnitude — tens of thousands
of observations per week against a taken population accruing 11-18 fills/month. **It is the only
instrument that escapes the power wall:** sd is 1.875R, so a 2-SE read on the sleeve's own mean
needs 188 fills, about 20 months at the funded rate. Cost: one `_shadow_log_untaken` call on the
detector-reject path. Logging only; widens no aperture, cannot move a dollar.

Known limit to fix with it: `MIN_VOL_Z` has a live/replay asymmetry — live fetches klines with
`end=now`, so a scan landing 3 minutes into a 15m bar sees ~20% of eventual volume. **Live is
systematically stricter than every replay on exactly this gate.**

### Verdict

**No trading-parameter change ships.** Every behaviour change proposed across eight angles was
killed — four by its own adversarial verifier, four by the agent that proposed it. What survived
is three telemetry fixes at $0/month, one prohibition, and one hold.

Post-week deploy bundle (all logging, no decision path): the one-line `metadata` fix; the
feature-store whitelist (`atr_pct`, `calm_ratio`, `vol_z`, `candidate_rank`, `candidate_field`);
tag `exit_kind` from `exit_reason` and split `EXCHANGE_CLOSE` into `EXCHANGE_STOP`/`EXCHANGE_TP`;
queue item 0b; a fail-open counter on the external gate; and flip the four code defaults to match
live. Then re-run the pullback-resume study on the real 35-57 symbol pool.

Levers still at zero measurement after nine studies, ranked by what they could move:
`EXCLUDE_TOP_TURNOVER=24` (the only lever with a large recorded number, +$81.43, held back
before funding and never re-run); the turnover deflator + `BASELINE_POOL_MULT=2.0`;
`_wildcard_rank_key` (the only quality judgement in the convex path, measurable the moment the
metadata fix lands); `SCAN_INTERVAL_SECONDS=450`; `ATR_PERIOD`/`RSI_PERIOD`/the 96-bar calm
window (hard-coded, unreachable by env, never varied).


## 2026-09-07: TREND re-entry-depth haircut — owner's rule REFUTED, variant INCONCLUSIVE

Owner's proposal: "if we already opened a LONG trend on an all-time high, reduce
risk by 50% on the next all-time high for the same symbol." Tested on the
COMPLETE TREND population — 27 closes, 2026-08-20 to 2026-09-07, all LONG,
feature store and trade_history joining 1:1 with zero unmatched rows.

### The owner's rule as stated (H1) is REFUTED and costs real money

Halving at depth >= 1 shrinks **16 of 27 fills including BOTH +2.9R legs and the
+$75.37 ZEC trade** (which sits at depth 1). Constant 1R: **-$3.93**. Actual
realised dollars: **-$18.79**. At funded 1R ~$26 the ongoing cost is roughly
**-$50/month**. The direction was right; the threshold was off by one.

### The first pass's gradient did NOT survive doubling the sample

    depth   n=15 (first pass)      n=27 (full population)
    0       +0.490                 +0.864   <- now the BEST cell
    1       +1.282  <- was best    +0.622
    2       -0.023                 -0.273
    3+      -0.750                 -0.492

Not a monotone gradient — a single CLIFF between depth 1 and 2. Shallow (n=19,
+0.762R) vs deep (n=8, -0.383R): gap 1.145R, SE 0.485, **t=2.36**. That is one
nominal hit against 35 cells tested, where chance alone predicts 1.75.

### H2 (0.5x at depth >= 2) has genuine virtues — and one fatal hole

    H2   +1.530R   +$6.26 @1R=$4.09   perm p 0.046   31/31 boundaries positive

Virtues, all verified: it **never touches a runner** (largest trade shrunk is
+0.61R; the three +2.8-to-+2.98R legs and the +$75 fill are all depth 0-1, so
ex-top-5% delta EQUALS full delta — the one place this beats every gate study
this session); leave-one-out holds (+0.975R to +1.835R); and the maturity
confound fails in the RIGHT direction (maturity-only loses 7.40R, so depth
carries what ordering exists).

**THE HOLE: all 8 trades it touches are ZEC. Non-ZEC depth >= 2 is n=0.** Not
sparse — ZERO. The variant has literally never been evaluated on another symbol.
"Re-entry depth is bad" cannot be told apart from "the back half of ZEC's
08-22-to-09-06 run was bad". The earlier all-sleeve re-entry study that appeared
to corroborate this was reading SEVEN OF THESE SAME EIGHT TRADES — one
observation, not two independent ones.

### Three more things that sank it

**THE 48h WINDOW IS TUNED**, and it was inherited from the first pass rather
than pre-registered. H2 delta across ten defensible windows:

    entry12 +0.20 | entry24 +1.78 | entry36 +1.75 | entry48 +1.53 | entry60 +0.09
    entry72 -0.15 | entry96 -1.92 | close24 +1.57 | close48 +0.09 | close72 +0.40

**THE SIGN CONTROL FAILED.** H6 (halve only after a WINNING prior leg) = +1.155R
beat H5 (only after a LOSING leg) = +0.375R by 3x, on every axis including the
half-split (31/31 vs 0/31). If depth >= 2 meant "the trend is tiring", H5 must
dominate. In fairness: H5 fires on only 2 trades, so the test was never powered
— the mechanism is UNTESTED rather than disproved.

**THE DEPOSIT LANDS EXACTLY ON THE DEEP CLUSTER.** The 6.3x equity change occurs
09-04 16:55; the five post-deposit TREND trades have depths [3,1,2,3,3] — four
of five at depth >= 2. H2's raw-dollar delta is +$21.28 against +$6.26 at
constant 1R. Any dollar-ordered reading of this is an equity-timeline artefact.

### The owner's literal ATH framing is WRONG IN BOTH DIRECTIONS

Excluding the 4h bar containing the entry (otherwise its own high beats the
entry and nothing is ever an ATH): new 30-day high on 10 of 27, 90-day on 9,
1000-day on 6 (all ZEC). Being an ATH entry is **if anything a NEGATIVE**:

    30d high  IS: n=10  +0.380R  win 60%   |   NOT: n=17  +0.448R  win 53%
    90d high  IS: n= 9  +0.091R  win 56%   |   NOT: n=18  +0.589R

Plain re-entry depth separates better than the ATH version of the same rule. And
this sits alongside the 2026-09-04 refutation of an ATH entry FILTER — different
lever, same conclusion.

### The scaler is working AGAINST this, not duplicating it

corr(depth, regime_size_multiplier) = +0.320 Pearson / +0.483 Spearman. Mean
multiplier by depth: **0 -> 0.679 | 1 -> 0.942 | 2 -> 0.978 | 3+ -> 0.807**. The
scaler sizes deep re-entries UP, because by the second re-entry the symbol's own
path efficiency reads well. So the haircut is not redundant with the scaler — it
would be OPPOSING it. Worth knowing either way.

### The asymmetry that decides it

If H2 is real: **+$66/month** at funded size. If the null is true (deep trades
no different from shallow): H2 halves 8 fills averaging +0.76R, costing ~5R/mo =
**-$130/month**. **The downside is 2x the upside**, and the evidence separating
them is eight ZEC trades in a tuned window with an unpowered mechanism test.

**Verdict: INCONCLUSIVE, do not ship.** Revisit when non-ZEC depth>=2 trades
exist — note trial 19 (TREND 2 -> 3 slots) spreads fills across MORE symbols,
which will either produce that evidence or collapse the deep-cell rate toward
the ex-ZEC rate of 0%. Either outcome is informative. Refuted/inconclusive ~34.

## 2026-09-07: PULLBACK-RESUME priced at last — sign UNRESOLVED, mechanism clear

The bot's largest filter, never before priced. 13 variants on the CORRECTED
harness (the Min5 fetch fix, 7b757bc, delivered 66,534 median bars over 231.3
days across 166/170 symbols — pre-fix this call returned ~77 days).

**The exact rule** (`wildcard.py`, gate 2) is three consecutive 15m closes:

    resumed     = cur > prev    (long)
    pulled_back = prev < prev2  (long)
    if not (resumed and pulled_back): reject no_pullback_resume

It rejects **78.7% of candidates** that pass every other gate.

### The headline reverses on the universe the bot actually scans

    pool                       gate ON vs gate OFF
    full 166-symbol replay     gate SAVES $110.78   (~+$21/mo scaled)
    top-90 slice (LIVE scans)  gate COSTS  $18.27   (~-$3.5/mo)
    shared fills only          gate COSTS  $42-85   (~-$8 to -$16/mo)

Live runs `FUTURES_WILDCARD_MAX_SCAN=90`; the replay used 169 symbols. **The
evidence FOR the gate comes entirely from symbols the bot never sees.** On the
shared-fill axis — the only one the calibration certifies — dropping the gate
wins in every framing. **Sign UNRESOLVED, |effect| under ~$25/month either way.**

### What IS solid: the mechanism, identical in every framing

    turning the gate OFF:  +$191.30 of top-5% TAIL added
                           -$302.08 of BODY destroyed        (full pool)
                           +$143.25 tail / -$124.98 body     (top-90)

Every loosening cell adds tail; every subtractive cell destroys it. **The gate
buys BODY protection in a book where 100% of the P&L is in the TAIL.** That is
the wrong shape for this book, and it is a mechanism finding rather than a
dollar finding.

### The entry-price cost, now priced

Shared fills (same symbol, entries within 6h), sign negative = the cell entered
BETTER than live:

    V1  gate OFF           n=595   mean -0.089R   p25 -0.172R
    V7a first-touch <=1b   n=516   mean -0.197R   p25 -0.338R
    V7b first-touch <=4b   n=561   mean -0.135R   p25 -0.273R

**The owner's instinct is correct and now quantified: on the worst quarter of
shared trades the gate costs 0.14-0.34R of entry price.** What is NOT
established is that the gate is worth paying it.

### MAGMA does NOT support the case — my earlier account was wrong

I told the owner the 58 minutes from 19:00 (0.26041) to 19:58 (0.273) were
consumed by pullback-resume. **They were not.** With the pullback gate REMOVED
and all other gates live, every candidate bar in the window is:

    19:35  age 1  entry 0.271590  ->  -1.037R
    19:50  age 2  entry 0.270480  ->  -1.036R
    19:55  age 3  entry 0.273290  ->  -1.032R   <- the live fill

**There is no candidate at or near 0.26041.** The 19:00 trigger bar never became
a candidate at all — one of the OTHER guards (volume-z, climax wick, or vertical
blow-off) refused 19:00-19:30. Removing pullback-resume buys 20 minutes and
0.0017 of price, and all three available entries stop out within 0.005R of each
other. The trade was unwinnable at every entry the bot could have taken.

### Cell table (pinned $170, 227.4d, wildcard-only)

    cell                        fills   net $    vs V0   $/fill   perm p
    V0  LIVE pullback-resume      776  +166.25   +0.00   +0.214   0.037
    V5d resume + no new extreme   898  +153.78  -12.47   +0.171   0.067
    V7a first-touch <=1 bar      1195  +152.18  -14.07   +0.127   0.083
    V5b pullback leg only         809  +151.95  -14.30   +0.188   0.078
    V4  timeout 8 bars            839  +116.21  -50.04   +0.139   0.154
    V1  gate OFF                 1355   +55.47 -110.78   +0.041     n/a
    V6  gate OFF + 2.0xATR stop  1949   +58.03 -108.22   +0.030     n/a
    V6c gate ON  + 2.0xATR stop   965   -25.88 -192.13   -0.027   0.513

V0 has the highest $/fill and least-negative ex-top-5% of all 13 — but both are
within-replay ratios on a pool that includes invisible symbols.

### Why nothing ships

- **ZERO of 13 cells beat V0 in both halves at any boundary** (chance predicts
  ~3.2). The baseline fails the half-split too.
- **V0's own p=0.037 does not survive an 18-cell family** (Bonferroni 0.0028).
- **The baseline did not replicate itself**: the same V0 cell on the same 83.3d
  overlap booked 363 fills/+$86.48 today vs 399/+$48.31 on 09-06 — a 2x swing in
  per-fill terms, larger than most cells being adjudicated.
- Live cell NOT calibrated this session: the Futures-bot container was scaled to
  zero and refused SSH, so the live figure is a document quote, not a measurement.

**Correction to the docs**: the line "`no_pullback_resume` carried no
information" is WRONG as stated. It carries modest real information (p=0.037 vs
random filters of its own selectivity), and no relaxation carries more.

**Recommendation: change nothing; shadow-log the gate** (queue item 0b). This is
the study that proves why 0b matters — the most expensive filter in the book is
adjudicable only by a replay whose sign flips with the symbol pool.

## 2026-09-07: the WILDCARD ROC-WINDOW sweep — REFUTED, plus a HARNESS DEFECT

Owner watched MAGMA_USDT LONG (entered 09-06 19:58 at 0.273, stopped -1.06R /
-$26.45 after 0.4h, peak 0.02R) and asked to sweep the ROC WINDOW jointly with
its threshold: "5% in 1 hour, 7% in 2 hours, lots of combinations".

### TWO ERRORS IN THE BRIEF I WROTE — own them before the result

1. **I claimed `ROC_BARS` had NEVER been swept. It HAS.**
   `tools/pit_roc_sweep.py` (2026-08-25/29) is titled "ROC trigger window x
   threshold sweep" and sweeps ROC_BARS over {4, 8, 12, 24, 48} across 15 cells
   on 208 days — and it contains the owner's 1h/5% cell explicitly.
2. **I stated the live 24h-range gate is 7%. It is 8%.** `runtime.py:5871` sets
   `min_move` from `FUTURES_WILDCARD_MIN_24H_RANGE`, which defaults to
   `scan_roc`, which defaults to `min_roc` = 0.08. Consequence that matters:
   in LIVE code, dropping the ROC threshold to 5% ALSO drops the 24h prefilter
   to 5%. Any harness that pins the prefilter at 8% mis-specifies every
   low-threshold cell.

### THE ANSWER: the mechanism is BACKWARDS

**At a fixed threshold a FASTER window fires LATER, not earlier.** Verified on
MAGMA with freshly fetched klines: live 3h/8% first became true at the 19:00 bar
(ROC 8.47%, close 0.26041); 1h/8% did not fire until 19:15 at 0.27072 — **4.0%
WORSE**. 6h/5% fires later than 3h/5%. "Faster window = earlier entry" is false.

**Both named cells would have taken MAGMA anyway** (1h/5% fires 18:45, 1h/7%
fires 19:00); 41 of 42 cells fire at or before the live entry. The hypothesis
does not exclude its own motivating trade.

**The owner's 5%/1h cell was already measured** (prior harness, 2026-08-29):
734 fills, +$233.49 against the live cell's +$378.09 = **-$144.60**, $/fill
0.318 vs 0.488, 14/29 positive weeks vs 19/29. Note it took FEWER trades than
live (734 vs 775) — it is a TIGHTENING, so churn and fee drag cannot explain
the loss. It selected a different, worse population.

The only cell that ever beat live is **6h/12%** (+$62.16, 690 fills, $/fill
0.638, ex-top-5% +$137.50, both halves pass) — LONGER and STRICTER, the exact
opposite of the hypothesis, and an unreplicated best-of-15 pick its own author
flagged as candidate-only. It is also the ONLY cell in the grid that never
fires on MAGMA. Retest properly on a calibrated harness before anyone acts.

### THE OWNER WAS RIGHT ABOUT LATENESS — the cause is not the window

    live trigger cleared   19:00   price 0.26041
    bot filled             19:58   price 0.273      58 min, +4.8%

    next hour's drawdown from 0.26041:  -1.62%
    next hour's drawdown from 0.273:    -6.15%  <- THE STOP-OUT

**The lateness cost the trade.** But the 3h window had already cleared an hour
earlier. What consumed the 58 minutes was the PULLBACK-RESUME rule doing its
job — waiting for the dip and buying the bounce. No ROC-window change reaches
it. This is a DIFFERENT component and it is the one genuinely open question
this study produced. Note `no_pullback_resume` rejects **64,854 of 84,569**
trigger bars (76.7%) and has never been priced separately — docs record only
that it "carried no information" as a diagnostic, not what it costs or saves.

### HARNESS DEFECT — affects EVERY prior intra-bar study

`pit_intrabar.fetch_grids` passes `days` straight to `pit_fetch.fetch_frames`,
whose chunk count AND want-bars are computed on a hardcoded `BAR=900` while the
interval is Min5. **At Min5 it fetches ONE THIRD of the requested window and
its report calls it complete.** Verified: `PJ_DAYS=14` returned 6.9 days of 5m
data; `PJ_DAYS=220` would deliver ~79 days, not 220. Every published "full
history" intra-bar replay in this repo has run on roughly a third of its stated
window. Fixed in this run by passing `days*3`; the corrected fetch returned
median 70,034 5m bars (243 days) across 169/170 symbols.

### CALIBRATION FAILS WORSE THAN DOCUMENTED

Live cell over the 83.3d overlap: replay 399 fills $+48.31 vs live 96 fills
$+18.61. **Fill rate off 4.16x, not the documented 2.2x.**

- **Live is CANDIDATE-STARVED, not slot-constrained** — the decisive diagnostic.
  Live occupies 5.23 slot-hours/day of 72 available (7.3%); the replay occupies
  33.69 (46.8%). The replay's extra fills are trades the live bot NEVER SAW,
  hidden by `MAX_SCAN=90` (live scans the top 90 movers, the replay 169), the
  external listing veto, and the live ticker-snapshot universe.
- **The extra population is systematically worse.** Replay fills on symbols live
  actually traded: n=231, +$0.257/fill. On symbols live never traded: n=168,
  **-$0.065/fill**. So a cell that wins by ADDING FILLS wins inside a book that
  provably does not exist live — the mechanism that killed the threshold
  loosening.
- What IS faithful: 21 of 96 live fills matched, **sign agreement 20/21**, and
  the replay's entry averages 0.456% EARLIER than live. Per-trade mechanics are
  sound; the population is not.

### Incomplete, and stated as such

The 42-cell grid NEVER EXECUTED (container SSH went down mid-run). Every grid
number above is from the PRIOR uncorrected harness. The entry-price vs selection
DECOMPOSITION — the heart of the question — was coded, staged and never ran.
At $46/month per-cell noise against a +/-$60/month envelope, the measurement is
blunter than the thing being measured.

**Recommendation: change nothing on the ROC window.** Refuted count ~32.

## REJECTED 2026-09-06 (second pass): sizing and entry-LATENCY levers

The owner rejected "the bot is finished" and tasked a second pass on the
mechanisms never swept: entry LATENCY (distinct from the threshold lateness
already refuted), per-sleeve risk, the SL-margin cap, the sizing denominator,
and the risk LEVEL itself. Five measured, three synthesised, all three attacked,
none ships. What came out instead is three corrections and one preference.

### A. LATENCY — REFUTED, and the premise briefed to the owner was WRONG

- **THE BAR-CLOSE WAIT IS ZERO.** MEXC's contract kline endpoint returns the
  IN-PROGRESS 15m bar with a live-ticking close. Verified: two calls 20s apart,
  same bar index, different closes (79912.9 -> 79912.6). The briefed "up to 15
  minutes of bar-close wait" does not exist.
- **CONTENTION IS 0.4 SIGNALS/DAY AT ZERO EXPECTANCY.**
- A/B on 65 replayable fills: **+0.1196R/fill, SE 0.0772, t=1.55** — below the
  screen before any control. WILDCARD +0.165 (t=1.94), TREND +0.037 (t=0.24).
- **PERMUTATION PLACEBO KILLS IT.** Shifting entry back by ANOTHER trade's
  latency scores HIGHER: placebo +0.1382 vs observed +0.1196, z=-0.29, p=0.574.
- Decomposition: 4 of 65 trades flip stop/no-stop carrying +1.53R each; the
  other 61 carry +0.027R. Trades where the price barely moved (n=25) still show
  +0.071R — the gain is present where the price effect is absent. Path noise.
- n to resolve a $60/mo effect at 2 SE: **1,631 fills, ~21 months.**

### B. PER-SLEEVE RISK TILT (TREND 1.5x / WILDCARD 0.6x) — REFUTED by one day

Premise confirmed — the sleeves draw identical risk (TREND 1.457% +/- 0.123 vs
WILDCARD 1.483% +/- 0.085) — and the tilt is monotone and budget-neutral. It
still dies:

- **LEAVE-ONE-DAY-OUT FLIPS THE SIGN.** Drop 2026-09-03 (three fills in 57 min,
  XRP and ZEC on one impulse) and the reweight goes **+3.95R -> -1.59R**.
  TREND's effective sample is 11 days, 3 episodes, one carrying 69%.
- **WRONG CONTROL.** It bootstrapped over trades; the day-block bootstrap gives
  P(loss) 31%, p5 **-$211/month**.
- **THE ZEC CONTROL CANNOT WORK** — ZEC and XRP fired inside the SAME episodes
  (08-22 01:54/05:02, 09-03 14:55/14:59). Dropping the symbol leaves the episode.
- **SLEEVE AND SYMBOL CLASS ARE PERFECTLY COLLINEAR AT ANY n.** WILDCARD has
  ZERO big-cap fills across 89 fills / 57 symbols; TREND trades 5, all big-caps.
  "Tilt toward TREND" and "tilt toward big caps" cannot be separated.
- Dollars overstated 1.65x: priced at nominal 2.41% ($27.71/R) not realised
  1.46% ($16.76/R).
- Revival: TREND-minus-WILDCARD meanR positive over ~40 more TREND fills across
  15+ days, no day >20% of cumulative R, day-block bootstrap P(>0) >= 0.90.

### C. THE RISK LEVEL — NOT refuted, and it CANNOT be. It is a PREFERENCE.

Raising `FUTURES_WILDCARD_RISK_PCT` 2.41% -> 3.00% correlates **0.978** with the
book itself. It is a pure scalar carrying no independent information, so no
evidence can ever validate it. Leverage is independent of it, slots are
count-capped not margin-capped, and the shadow ledger shows zero balance-driven
rejects in 207 rows — it changes no entries, no exits, and no fill identity.

    metric                     2.41%      3.00%
    median $/month               --       +$48
    P05 / P95                    --    -$39 / +$503
    P(delta < 0)                 --        30%     (proposal claimed 4.4%)
    max drawdown               16.2%      19.9%
    P(drawdown > 30%)            29%        45%

The 4.4% came from a bootstrap CONDITIONING ON THE SAMPLE MEAN BEING TRUE. Its
own kill trigger (revert above 22% drawdown) fires **70.8% of the time when the
lever is working correctly** — it cannot be tested as written.

**KELLY CORRECTION, inverting an argument made to the owner earlier.** The repo's
own sizing docstring puts full Kelly at **1.9%** at 25% of the measured edge. So
2.41% is ALREADY above full Kelly and 3.00% would be **1.6x** it — not the
quarter-Kelly figure quoted from the earlier bootstrap CI.

**Framing: a variance PREFERENCE, not an edge lever.** The owner withdraws to
$190 weekly, so the base is restored regardless. A 30% chance of costing money
against 70% of gaining, drawdown 16% -> 20%, is a legitimate appetite decision.
It must not be sold as evidence-backed.

### D. Three corrections, worth more than the levers

1. **`equity_at_entry` IS NOT EQUITY.** `runtime.py:1802` stamps it from
   `available_balance` (equity minus committed isolated margin). It understates
   true equity by **mean 8.8%, median 7.9%, worst 28.5%** (n=73); 13.6% on the 47
   concurrent entries. Haircut by concurrency: 0 open -> 1.000, 1 -> 0.904,
   2 -> 0.820, 3 -> 0.717. Every risk figure is computed against a biased
   denominator. FIX THE TELEMETRY; keep the sizing — switching the denominator
   has a null permutation control (p=0.344).
2. **THE 20% SL-MARGIN CAP IS ANALYTICALLY INERT.** It cancels out of
   risk-targeted sizing: realised risk is identical to six significant figures
   (2.410%) at caps of 20/25/30, and correlations with outcome are null
   (r=+0.122 risk, +0.038 R, +0.040 $). It is a capital-utilisation dial, NOT a
   risk control. Tightening to 12/15 is strictly dominated — it relocates stops
   TIGHTER on 19.2%/11.0% of fills (vs 4.1% at 20) on a 100% tail-borne book.
3. **"LEVERAGE >= 7 LOSES" IS UNSUPPORTED — retire it, do NOT sign-flip it.** The
   claim that it is positive is a sleeve confound: lev>=7 has ZERO WILDCARD fills
   (TREND 16, SNIPER 8, SQUEEZE 4) while lev<7 is 80% WILDCARD. Within TREND the
   difference is **+0.09R at t~0.15**; 84% of the headline dollars is one ZEC
   fill; ex-top-5% the $89.39 becomes $4.53. Leverage carries no measurable
   signal in either direction — it is a truncated label for volatility and sleeve.

### The honest ceiling

Block bootstrap at 2.41% and $1,150 equity: median **$282/month**, P05 $18,
P95 $696 — a 38x spread. Every lever found is small next to the uncertainty in
the thing it multiplies. Refuted count ~31.

## REJECTED 2026-09-06: making the regime scaler smarter — SIX inputs, none survive

The owner asked for three detailed proposals to improve the scaler beyond
efficiency-only, aimed at limiting big $ losses at funded size. Six candidate
inputs researched on the live corpus with the correct control for each
(permutation for per-trade, placebo for time-keyed), ex-top-5%, and an
independent adversarial attack on each of the three finalists. **All three
finalists were refuted by their own review.** Recorded in full because the
negative result is the useful one.

### THE HEADLINE: no per-trade sizing input reaches 2 SE

    input                        n     verdict
    side (long/short)           18     already refuted
    portfolio heat             135     weak
    move maturity               75     untestable at current n
    volatility / leverage      113     already refuted
    same-symbol re-entry       110     weak
    literature canon           113     untestable at current n

**The ten largest dollar losses are all single full-size LONG stops at leverage
1-8, with no concentration on ANY tested input.** They are not clustered. There
is nothing for a smarter sizer to find. Every sizer's upside is bounded by how
little tail it removes, and the book is tail-borne: ex-top-5% the 96-trade book
is **-$15**.

### The three finalists and how they died

**1. Post-stop re-entry haircut** (halve a WILDCARD re-entry when the prior
same-symbol close was a STOP within 24h). Replay said the cell was 12.6% of
fills at -0.185R. **The live book produced ONE such fill in 74** (1.4%) — MAGMA
09-03, an OPPOSITE-side re-entry, **+1.98R**, which the rule would have halved.
The cell rate was a 170-symbol replay artefact. The proposal also misread its
own table: the scaler already sizes these fills DOWN (0.735 vs 0.846 fresh), not
up. Live ceiling ~$1-2/mo. Killed.

**2. Exhaustion ramp** (inside the full-size band, ramp WILDCARD longs down by
3h ROC above 12%). **83% of the positive evidence is shadow rows the live bot
rejected via other gates** — ref-not-listed, crowded-funding, calm-shock — which
lose at -0.52R because of what those gates measure, not because of exhaustion.
The neutral-reason shadow rows (+1.00R) and the TAKEN cell (**+0.28R, n=13,
p=0.51**) both point the other way. The ramp would have halved O_USDT +5.0R, a
top-5% trade of the whole book. Over 50 cells were cut; one p=0.05 is exactly
the expected false positive. Killed.

**3. Portfolio-margin ceiling at the 45% kill line.** Cannot be both alive and
safe. At 45% it touches **0 of 135** historical entries — dead code that also
makes trial 19's pre-registered margin kill unreachable, destroying the
measurement the trial exists for. At any level that binds, it trims the third
TREND slot on rally days and halves five ~3R TREND winners. Its ruin case rests
on a -3.79R gap-through that was XAU_USDT on the SQUEEZE sleeve — a disabled
sleeve on a now-excluded non-crypto symbol. Killed.

### Three structural facts worth keeping

- **CONCURRENCY MARKS WINNERS, NOT DANGER.** By positions already open:
  0 -> +0.071R (n=76), 1 -> +0.276R (n=39), **2 -> +0.757R (n=18, 67% win,
  ex-top5 +0.509R)**. Stop rate FALLS with heat (43/42/33%). Every heat,
  correlation or account-state sizer binds where the book earns — the identical
  signature that refuted the drawdown brake.
- **CORRELATED STOPS DO NOT HAPPEN HERE.** 74 overlapping pairs: P(both stop)
  **14.9% vs 17.8%** under independence; corr(R_a, R_b) = +0.056; TREND-TREND
  pairs both-win 6, both-lose 1. The r=+0.914 BTC/ETH correlation does NOT
  translate into simultaneous stops. The worst 7-day window (-8.80R) had mean
  heat 0.8% and zero entries at 2+ open.
- **2.41% IS ROUGHLY QUARTER-KELLY.** Bootstrap CI on the full-sample Kelly
  fraction spans 0.1% to 19%. Sizing is already conservative; the constraint
  every proposal inherits is "never size up, never trim the tail".

### Corrections this pass produced

- The **-2.26 SE `regime_size_mult` finding is an artefact** — see the
  withdrawal in the trial-19 staging above. Winners-vs-losers on the scaler is
  -1.27 SE on trial 18, **+1.29 SE pre-08-29**, +0.31 SE on 109 closes.
- The **"shorts -0.225R" premise is a biased subsample** from a pinned90 dedup
  defect; clean sampling gives **-0.043R (t=-0.79)** — flat, not negative. The
  three TREND-shorts refutations stand on their own evidence and are unaffected,
  but the -0.225R figure should not be quoted again.

## REJECTED 2026-09-06: TREND shorts — third refutation, this one live-faithful

Asked: what would TREND have done from the start of trial 18 with shorts
enabled? Answered from the SHADOW LEDGER, not a replay: the bot detects every
TREND short signal, refuses it as `side_disabled`, and resolves the
counterfactual live. That is the decision-grade instrument, and a harness
replay would have been strictly weaker (the trials-window harness inflates
fills 2.2x — see the entry-timing rejection above).

**10 raw refusals since T18, -8.87R summed. Deduped by slot occupancy with the
ledger's own `dedupe_by_occupancy` — three independent positions:**

    when          sym    R      exit      $ at sizing in force
    09-01 18:39   ZEC   +0.58   trail       +2.61
    09-02 10:37   XRP   -1.13   stop        -5.08
    09-04 14:53   XRP   -0.68   timeout    -18.07   (funded size, 1R ~$26.50)
                       -1.23R              -20.54

**Against the TREND longs actually taken in the same window: +$17.78 (trial
18, 7 fills) and +$56.09 (18F, 4 fills) = +$73.87.**

Mechanism, same as the 360-day study named: the shorts fire in flat-to-up tape.
The 09-02 cluster shorted the same dip that made 09-02 the -$8.51 day for
longs, and lost too — both sides lost that morning because ZEC and XRP bounced
within hours. The 09-04 XRP short sat through its 24h timeout at -0.68R while
ZEC, on the same sleeve, printed new highs. Slot contention did NOT bite: the
+$75 ZEC long entered after the XRP short had timed out.

**Three measurements, three methods, one sign:**

    study                       window                    TREND shorts
    book-level A/B              360d, 51 weekly windows   -$61.51, -$108.64 ex-best
    slot sweep                  63d x 8 windows           -$14 to -$34, 24% wins
    shadow ledger (live)        trial 18 -> now           -1.23R, -$20.54

`FUTURES_TREND_LONG_ONLY=1` stays. It is not a restriction; it is the measured
half of the sleeve. The pre-registered deep-drawdown variant (shorts only while
BTC 7d <= -12%) remains the only version worth watching; it did NOT trigger in
this window (BTC held $79-81k) and would correctly have done nothing.

## REJECTED 2026-09-06: "the bot is opening late" — four entry levers swept

Owner's hypothesis: loosening WC_MIN_ROC, WC_MIN_24H_RANGE, TREND_MIN_ROC and
WC_MAX_CALM_RATIO would let the bot enter earlier and better. Requested on trials
17-18F; run on that window AND on 230 days, corrected book (`pit_book.take`),
three intra-bar phase grids, PJ_EQUITY=170, 1000-perm permutation control,
ex-top-5%, boundary-swept half-split, independent re-run by the reviewer.

**The trials window CANNOT answer this, and it was proven before the sweep.**
Calibration of the LIVE cell over T17+T18: live 35 closes $+19.07; replay 66
fills $+33.39. **2.2x WILDCARD fill inflation** (55 vs 25), gap sign flips per
trial (T17 -$23, T18 +$38), 15 of 36 live trades matched. In the 18F tail the
replay booked 13 WC fills where live took **zero**. Per-cell null SD on 9.5 days
is $12.51, so its apparent "+$28 for loosening" is chance sitting in 36 hours
where the model and the bot disagree completely. The calibratable 8-day core
shows LOOSENED +$2.28 — nothing. **Nothing on 9.5 days can distinguish "earlier
is better" from noise.**

**On 230 days: loosening HURTS, tightening does nothing, nothing survives.**

    cell                     d$ vs live   $/mo    $/fill   half-split   perm p
    LIVE                          —          —     0.320       —           —
    WC_MIN_ROC 6%              -34.43     -4.5     0.230      no         0.09
    WC_MIN_ROC 7%              +66.00     +8.6     0.333      NO*        0.375
    WC_MIN_ROC 9%              -65.26     -8.5     0.295      no         0.22
    TREND_MIN_ROC 3%           -37.59     -4.9     0.275      no         0.04 (harmful)
    TREND_MIN_ROC 3.5%         -26.19     -3.4     0.291      no         0.04 (harmful)
    TREND_MIN_ROC 5%           -29.84     -3.9     0.307      no         0.15
    MAX_CALM 0.60              +45.52     +5.9     0.382      NO         0.08
    MAX_CALM 0.90              -31.08     -4.1     0.284      no         0.125
    MAX_CALM off               +59.05     +7.7     0.333      NO         0.26
    ALL LOOSENED          -13.6 to -88.8  -1.8..-11.6  0.181-0.253  no   0.015 (harmful)
    ALL TIGHTENED              -63.74     -8.3     0.333      no         0.345
    * early half -$49, late +$78

**0 of 14 cells beat live AND pass the screen; the screen's own null predicts
3.5 spurious passes.** No cell reaches Bonferroni p<0.0036; the only p<0.05
results point AGAINST the hypothesis. Ordering: LOOSENED < LIVE <= TIGHTENED.
Full-history per-cell null SD is $54.79 — at this outlier concentration (top 45
fills carry ~$610 of $370) **no entry-threshold change in the tested range is
resolvable even on 230 days.**

**Direct band evidence is flat.** Unbooked mean R of candidates by 3h ROC:
6-7% +0.02..+0.07, 7-8% +0.015..+0.04, 8-9% +0.07, 9-12% +0.007, >=12% +0.047.
The trades the bot would catch earlier are no better than the ones it takes;
admitting them costs slot time and turnover. **Earlier entry buys turnover,
not edge.** ALL-LOOSENED collapses $/fill 0.320 -> 0.181.

**Structural findings, kept:**
- **`FUTURES_WILDCARD_MIN_24H_RANGE` is a NO-OP at any value <= MIN_ROC.** A
  24h high/low range >= |3h ROC| by construction (both closes lie inside the
  window). Verified: 0 candidates with roc>=8% and range<8%; 0.09 touched zero
  fills; 0.12 removed 3. Lowering it from 0.07 cannot make the bot enter earlier.
  It only binds ABOVE 8%. Drop it from any future "earlier entry" list.
- **TREND 4% stands in both directions, for the third time.** The 3-4% band
  loses ~-0.12R/trade over 847 candidates (3-3.5% -0.135R n=419, 3.5-4% -0.111R
  n=428); >=5% is +0.218R (n=2751) but 5% still loses via reshuffling.
- **MAX_CALM is non-monotonic** (0.60 +$45, 0.90 -$31, off +$59) — the noise
  signature. The 0.75-0.90 band is +0.098R (n=112) yet booking it loses $31:
  reshuffling dominates. Keep 0.75.

**The WC 7% OPEN item: status SHARPENED, not closed.** It reproduces in sign
only (+$66, $/fill 0.333) and fails every robustness probe: by quarter of
history -27 / -12 / +60 / +44 (first half negative, matching the earlier
finding); ex-top-5% -$26; 7-day block bootstrap CI [-$38, +$172], P(delta<=0)
= 0.15; phase-grid dispersion +$54 / +$6 / +$15 (moves 10x when the 15m clock
shifts 5 min); the top 5 added fills exceed the whole delta. Its "unexplained
mechanism" is now explained: the 7-8% band is ~zero-edge unbooked, so the
booked +$66 is schedule reshuffling. **It stays OPEN, under the bar.** The
7-8% shadow band live-logging since 09-03 (n=2-3) is the only instrument that
can settle it; it needs ~100 rows, not a config change.

**Unmodelled, stated:** the external veto (-0.565R over 24 live rows —
conservative direction), cross-sleeve margin, 18F's 6x equity, live pool
snapshot (replay uses today's top-170: survivorship). Absolute dollars are not
live-comparable; only within-replay deltas are, and those sit inside chance.

Refuted count ~28. Change nothing; the bot is not measurably late.

## REJECTED 2026-09-05: sign-conditional time stop ("extend losers 6h")

Proposed after ZEC_USDT LONG closed at -0.21R on the 24h clock having peaked at
0.22R. Rule: at 24h close if R >= 0, else hold to 30h. Tested with 9 variants
(30h/36h/48h extensions, mild-loser-only, the MIRROR, no clock, 12h/18h/36h
flat) by bar-level replay of every real trade under the live exit stack,
following `pit_arm_sweep.py`.

**The lever is 7% of the book.** Under the live stack only **5 of 75**
replayable trades reach the 24h clock (STOP 35, TRAIL 32, TP 3, CLOCK 5). Only
**2** were negative at that moment. So every extension variant changes at most
ONE resolved trade — LAB SHORT at $1.19 risk, +$0.42 at 30h — and the mild-loser
variant changes ZERO.

**The motivating trade refutes the rule on its own.** ZEC at the 24h bar close
was -0.04R (live fill -0.175R). At 29.3h it sat at **-0.445R**. The owner's rule
would have turned a -$2.66 close into roughly **-$6 to -$8** on a $12.87-risk
position. Priced in, V1 all-in is about **-$3 to -$5** over the whole history,
before slot cost.

**The MIRROR has no content either — and that is the finding.** The sign
control depends on the trail basis: wick-trail replay has V1 (extend losers)
+$0.42 beating V5 (extend winners) -$2.38; close-trail replay has V5 +$0.67
beating V1 -$0.03. Two reasonable replays of the same trail flip the sign.
Neither direction holds.

**24h is a plateau.**

    36h flat      $0.00   (LAB +$1.70 exactly offset by TAC/MAGMA give-back)
    18h flat     -$3.29
    12h flat     -$8.94   (MAGMA 09-03 +1.80R -> +0.27R)
    no clock     -$2.76

**Power.** Observed paired deltas on affected trades have sd ~0.45R, so 0.5R
needs ~7 affected trades and 0.25R ~28. Affected trades accrue at 2.7-6.7% of
convex closes -> **5-12 months** at ~3 closes/day before anything resolves.

**Slot cost bounds it further.** A 6h extension occupies a slot; at the live
mean of ~$0.59 per convex trade one blocked entry per extension costs more than
V1's entire +$0.42 lever. All extension deltas are upper bounds.

**Harness note, stated so the number is trusted where it should be.** V0 replay
+$17.32 vs LIVE +$44.04 — 61% under, entirely on early trail winners the wick
trail cuts short (TUT +5.53R live vs +2.74R replay). The live time-stop cohort
itself replays **within $1.09** of live (6 trades, +$11.19 vs +$12.28), so the
harness is accurate exactly where this study lives.

The exit stack remains uninvolved in the convex losses. ZEC's problem was a
tepid move that never reached 1R; no clock rule addresses that. Leave
`FUTURES_CONVEX_TIME_STOP_HOURS=24`. Refuted count ~27.

## REJECTED 2026-09-04: trading on corroborated news — plus a REAL clusterer defect

Asked after the ZEC alert arrived 25 minutes AFTER the bot had already entered
on price action. Two separate questions came out of it and they have opposite
answers.

### A. Trading on news — REFUTED, no sample, and the premise was wrong

**I got the premise wrong and it is corrected here.** I claimed the Russian
forklog item would have been the THIRD source and that fixing cross-language
matching would have fired the alert 5h39m earlier. It would have been the
**SECOND**: the only Zcash outlet before it is coindesk (twice, but that is one
distinct source). Measured across all 18 shipped alerts, a relaxed matcher makes
**0 fire earlier**, 17 unchanged, and 1 fire 78 min LATER as a merge side-effect.

**The lag is editorial, not technical.**

    first publish -> first fetch          median  12 min   (ours)
    first publish -> THIRD source PUBLISH median 173 min   (newsrooms)
    third publish -> third fetch          median   9 min   (ours)

Everything the bot controls sums to ~21 min. No matcher change can make an alert
fire before a third newsroom has written the story.

**Sample makes the study impossible.** 328 rows, but 43% is one backfill burst;
real forward capture is 186 items over 47.6h. `big_stories(min_sources=3)` finds
18 clusters, 9 genuine, of which **7 name no tradeable ticker** (regulatory,
corporate, security). Corroborated + symbol-linked + liquid = **2 events, both
BTC, same day, de-clustering to 1**. Non-BTC: **zero**. Yield is ~1 symbol-linked
corroborated story every two days and ~85% are BTC, so reaching 30 non-BTC
events needs **6-12 months** of uninterrupted capture — and only after the
clusterer is repaired, or half the events fed in are fusions.

Credit where due: the lookahead bug that kills most news studies was checked and
is ABSENT. Entry was clocked at third-source-fetched + 15 min, after every
publication in each cluster.

### B. The clusterer is ~50% precise — this one is REAL and worth fixing

Of the 18 clusters reaching 3 sources, only **9 are actually one story**. The
others are chain-merges: one fuses "Lazarus moves $30M through Hyperliquid" with
"South Korea arrests four over Syrian payments", "Silhouette RFQ", "Ethena USDe
app" and "Cathie Wood buys Bitcoin".

**Root cause: `rare_df=0.05` is a RATIO and scales with corpus size.** At 330
documents it means "appears in <= 16 headlines", admitting 909 of 1135 distinct
tokens including ordinary words — *market, first, since, token, rally, trading,
global* — plus recurring entities *robinhood, kalshi, strategy, kraken*. Two
headlines sharing "market" inside the 6h window fuse, and a fused cluster
inherits both token sets so the fusion snowballs.

**So roughly half of what the news alert tells the owner is not a story.** The
fix is PRECISION, not the cross-language recall I proposed: an ABSOLUTE
document-frequency cap (df <= 3 headlines) instead of a ratio, and matching only
on tokens the seed item owns rather than ones the cluster inherited. Secondary:
`cluster_stories`' `isalpha()` filter drops "$1,000", which is exactly the token
that would bind a numeric-milestone story across languages.

### C. Kept, not actioned: news arrives at high RANGE POSITION, not after a move

The "news lags a big move" hypothesis is FALSE as stated. Across 70 fresh
symbol-naming headlines the pre-24h move at alert time is median **+1.48%**
against a time-matched null of **+1.57%** — dead centre.

What IS elevated is position in the trailing range: median **0.81** of the
30-day Hour4 range against a null of **0.59**; 60% sit above 0.80 of range
(null 20.4%), 41% above 0.90 (null 9.5%). Ex-BTC (n=26, 9 symbols) the direction
holds and the magnitude shrinks. This is 26 correlated mentions over 48h in one
up-trending regime, so it is a lead, not a finding.

## REJECTED 2026-09-04: the two all-time-high hypotheses

Both proposed by the owner after watching the bot buy ZEC at 1036.54 on
2026-09-04, a fresh peak on the whole available record. Both tested with the
full control stack. Both rejected — but for OPPOSITE reasons, and the
difference matters for how much weight each refutation carries.

### A. "Do not enter LONG at an all-time high" — REJECTED, no sample

Fires on **3 of 97** convex LONG entries; only 2 are closed and scoreable.

    threshold        n   booked $   perm p   ex-top5   half-split
    at the peak      2     -0.93     0.709    -0.945      fails
    within 2%        6     -6.57     0.394    -0.130      fails

Three defects, any one of them fatal:
- **CIRCULAR.** The hypothesis came from one ZEC trade and ZEC dominates every
  cohort that tests it: 1 of 2 at 0%, 5 of 6 at 2%, 12 of 14 at 10%. All 13 ZEC
  near-peak entries fall inside a single 14-day rally, so the effective
  independent sample is about three episodes, not ten trades.
- **THE LABEL IS A PROXY EXACTLY WHERE IT BITES.** All 22 TREND entries sit on
  proxy-history symbols; there is not one true-ATH TREND observation in the
  corpus. ZEC's real all-time high is ~$5,900 from 2016, so 1036.54 is a
  3.7-year MEXC-futures high, not an all-time high at all.
- **THE CORPUS CANNOT RESOLVE ANY PER-TRADE FILTER.** The 96-trade book is
  +$37.01 gross and **-$15.47 ex-top-5**. 100% of the P&L sits in 5% of rows, so
  a filter study returns whichever sign the outlier assignment happens to give.

**Shipping it would be actively harmful.** TREND requires a new 24h extreme by
construction, so a "do not buy near the multi-month high" veto is a TREND
killswitch that fires precisely when a trend is working. At the 2% threshold it
refuses ZEC 2026-09-03 15:17 (+$9.50, third-largest trade in the book) — about
-$57 at funded size, a whole month's envelope, to avoid a class never shown to
lose. Power arithmetic: resolving anything short of a catastrophic effect needs
1 to 11 years of live data at the observed fire rate.

Genuinely new ground, though: `pit_loss_context.py` computes every one of its 13
features inside a 24-HOUR window (`H24 = 96` bars), so distance-from-multi-month-
peak was never tested. This is not a rerun of that refutation.

### B. "SHORT into all-time highs" — REJECTED, and strongly

The opposite situation: abundant evidence, all pointing one way. **All 27 cells
negative** (3 horizons x 3 stop widths x 3 break sizes), where chance alone
predicts ~1.4 apparent winners.

    de-clustered ATH short   n=660   mean -0.1436R   t = -4.96   win 42.7%
    random short, matched    n=3304  mean -0.0782R   -> ATH is 0.065R WORSE
    ex-top-5%                        mean -0.2307R   -> worse, not outlier-borne
    boundary-swept half-split        fails 0 of 7 boundaries
    genuine-ATH subset       n=396   mean -0.1593R   -> WORSE than the proxy half

**Mechanism: 73% of ATH bars are followed by another ATH bar within 24h.** The
rule shorts into continuation, structurally. Exit kinds were 62% timeout, 28%
stop, 10% trail, and the 5R target never paid once.

Two nulls worth keeping:
- **Time-matched null**: same calendar moments, random symbol instead of the one
  making the high, returned **+0.201R** — the ATH short sits at the **0.0
  percentile**, losing to all 2000 draws. Those moments did offer short edge;
  the symbol printing the high was the worst possible pick, by -0.26R.
- **Near-high null**: shorts entered **3-8% below** the peak returned
  **+0.283R**. So it is not "shorting strength" that fails — shorting strength
  slightly off the high is the better half. It is specifically AT THE PEAK.

Cost if shipped: about -$23/month against a +/-$60 envelope. No haircut rescues
it; haircuts move a replay result toward zero and cannot flip a sign.

**OPEN, not rejected:** the near-high short (+0.283R, 3-8% below peak) is an
unexplored signal in this data. It has not been swept, gated, half-split or
placebo'd, and it lives on the measured-negative side of the book. Do not act on
it; note it.

## LIVE GATES — the full stack, in signal order (verified 2026-09-05)

Every row was read from the code and the live Railway environment on the date
above. "live" is the value actually running; where it differs from the code
default, the default is noted. Rejection tags are what the funnel/shadow logs
print.

### Stage 1 — Universe (WILDCARD only; TREND's universe is a fixed list)

| gate | rule | env var | live |
|---|---|---|---|
| USDT perp | must be a `_USDT` perpetual | — | ~1,061 pairs |
| crypto only | non-crypto tokens excluded, list refreshed every 6h | `FUTURES_NON_CRYPTO_REFRESH_SECONDS` | ~429 dropped |
| not open | symbol not already held | — | `symbol_open` |
| not a major | top-N by deflated turnover excluded (TREND's domain) | `FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER` | 24 |
| liquidity | 24h turnover >= floor | `FUTURES_WILDCARD_MIN_TURNOVER_USDT` | $2M (default 3M) |
| 24h range | 24h range >= X% | `FUTURES_WILDCARD_MIN_24H_RANGE` -> defaults to the shadow ROC | 7% |
| scan cap | max symbols evaluated per pass | `FUTURES_WILDCARD_MAX_SCAN` | 90 (never binds) |

### Stage 2 — Detector

WILDCARD (`futuresbot/wildcard.py`)

| gate | rule | env var | live | rejects as |
|---|---|---|---|---|
| trigger | abs(3h ROC) >= 8%; sigma trigger OFF | `FUTURES_WILDCARD_MIN_ROC` | 0.08 | `roc_below_min` |
| shadow floor | 7-8% logged as untaken, never traded | `FUTURES_WILDCARD_SHADOW_MIN_ROC` | 0.07 | `below_trigger` |
| pullback-resume | prior bar against the move, current bar resumes | — | required | `no_pullback_resume` |
| RSI room | long < 90 / short > 10 | `FUTURES_WILDCARD_RSI_MAX/MIN` | 90 / 10 | `rsi_exhausted` |
| climax candle | adverse wick <= 45% of bar | `FUTURES_WILDCARD_MAX_WICK` | 0.45 | `climax_wick` |
| vertical blow-off | last-bar move < 2 x ATR | `FUTURES_WILDCARD_VERTICAL_ATR_MULT` | 2.0 | `vertical_blowoff` |
| volume | breakout-bar volume z >= 1.0 | `FUTURES_WILDCARD_MIN_VOL_Z` | 1.0 | `low_volume_z` |

TREND (`futuresbot/trend.py`)

| gate | rule | env var | live | rejects as |
|---|---|---|---|---|
| universe | fixed list | `FUTURES_TREND_SYMBOLS` | ETH, XRP, ZEC | — |
| trigger | 24h ROC >= 4% | `FUTURES_TREND_MIN_ROC` | 0.04 | `roc_below_min` |
| side | long only | `FUTURES_TREND_LONG_ONLY` | 1 | shorts discarded |
| new extreme | price >= max of the prior 96 bars | — | required | `no_new_extreme` |
| RSI | active only if max > 0 | `FUTURES_TREND_RSI_MAX` | 0.0 = DISABLED | — |

### Stage 3 — Post-detector (both sleeves, `futuresbot/runtime.py`)

| gate | rule | env var | live | note |
|---|---|---|---|---|
| calm-shock | per-symbol `calm_ratio` <= 0.75 | `FUTURES_WILDCARD_MAX_CALM_RATIO` | 0.75 | largest measured saver |
| external veto | listed on the reference exchange, fail-open | `FUTURES_EXTERNAL_GATE_ENABLED` / `_REQUIRE_LISTED` | 1 / 1 | lifetime -14.35R over 34 rows |
| min volume | contracts >= exchange minimum | — | mechanical | `min_vol_skip` |
| side enabled | WILDCARD both sides; TREND long | `FUTURES_WILDCARD_LONG_ONLY` | 0 | `side_disabled` |
| free slot | WILDCARD 3, TREND 2 | `FUTURES_WILDCARD/TREND_MAX_POSITIONS` | 3 / 2 | `slot_occupied` |
| pre-emption | new signal may evict an open WILDCARD below 0.3R and older than 15 min; TREND never | `FUTURES_WILDCARD_PREEMPT_ENABLED` | 1 | `_BELOW_R`=0.3, `_MIN_AGE_MIN`=15 |
| one per pass | at most one entry per scan | — | 450s / 900s | — |

### Stage 4 — Sizing (both)

| gate | rule | env var | live |
|---|---|---|---|
| base risk | 2.41% of AVAILABLE balance (not equity) | `FUTURES_WILDCARD_RISK_PCT` | 0.0241 |
| regime scaler | multiplier in [floor, 1.0] | `FUTURES_REGIME_FLOOR_MULT` | 0.50 |
| streak throttle | halves size on loss streaks | `FUTURES_CONVEX_STREAK_THROTTLE_ENABLED` | OFF |
| hard risk cap | <= 5% of equity per trade | `FUTURES_MAX_TRADE_RISK_PCT` | 5 |
| max margin | <= 25% of available | `FUTURES_WILDCARD_MAX_MARGIN_PCT` | 0.25 |
| balance guard | retry at capped size if the exchange refuses | `FUTURES_BALANCE_GUARD_BUFFER` | 0.95, 2 tries |
| drawdown brake | halves / blocks on equity drawdown | `FUTURES_CONVEX_DRAWDOWN_BRAKE` | OFF (refuted 2026-09-04) |
| leverage | WILDCARD fixed; TREND <= max, set by the SL-margin cap | `FUTURES_WILDCARD_LEVERAGE` | 5x / <= 10x |

### Stage 5 — Exit (both)

| rule | WILDCARD | TREND | env var |
|---|---|---|---|
| stop | 3.0 x ATR | 3.0 x ATR | `_SL_ATR_MULT` — WILDCARD live 3.0, code default 1.5 |
| stop cap | <= 20% of margin | <= 20% | `_MAX_SL_MARGIN_PCT` |
| take profit | 5R | 3R | `_TP_R` |
| trail arms | peak >= 1R | same | `FUTURES_CONVEX_TRAIL_ARM_R` = 1.0 |
| trail floor | 0.50 x peak | same | `FUTURES_CONVEX_TRAIL_RETAIN_FRAC` = 0.50 |
| ratchet | 0.75 x peak above 3R | same | `_RATCHET_R` = 3.0, `_RATCHET_RETAIN` = 0.75 |
| time stop | 24h | 24h | `FUTURES_CONVEX_TIME_STOP_HOURS` = 24 |
| stack selector | both flags required or the legacy stack arms | | `FUTURES_STRATEGY_MODE=pmt_threshold`, `FUTURES_WILDCARD_CONVEX_EXIT_ENABLED=1` |

The trail and the time stop run IN-PROCESS; only the initial stop and TP sit on
the exchange. Three things to know from the assembly: the WILDCARD stop is
3.0 x ATR live against a 1.5 code default; TREND's RSI gate is dead code at its
0.0 default; and the two sleeves have deliberately opposite entry shapes —
WILDCARD demands a pullback THEN a resume, TREND demands a fresh high with no
pullback at all.

## QUEUED FOR AFTER THE FUNDED WEEK (opened 2026-09-04)

Nothing here ships during the funded week. Each item needs a deploy, and a
deploy restarts the bot; none is worth a restart while the week is running.
Ordered by value, not by effort.

**0b. SHADOW-LOG THE DETECTOR-LEVEL REJECTS — the "dark 76%".** The shadow
ledger records post-detector refusals only (calm_shock, veto, below_trigger,
side_disabled, slot_occupied, min_vol_skip). It does NOT record DETECTOR-level
rejects, so the largest filter in the bot has no live counterfactual at all:
`no_pullback_resume` refuses **64,854 of 84,569 trigger bars (76.7%)** — more
than every other gate combined — and not one of those refusals has ever been
resolved against a real outcome. `low_volume_z` (14.4%), `climax_wick` (4.2%),
`rsi_exhausted` (1.1%) and `vertical_blowoff` (0.8%) are equally dark.

Consequence, found 2026-09-07 while commissioning the pullback-resume study:
that question can ONLY be answered by replay, and the WILDCARD replay does not
calibrate (4.16x fill inflation; live is candidate-starved at 7.3% slot
utilisation against the replay's 46.8%). **The single most expensive gate in the
book is measurable only with an instrument known to be unfit for absolute
dollars.** That is the strongest argument for anything on this queue.

Cost: one `_shadow_log_untaken` call on the detector-reject path, the same shape
as the existing sub-trigger logging. Logging only — widens no aperture, changes
no trading behaviour. After ~100 rows the gate becomes answerable from LIVE data
instead of a 4x-inflated replay. Pair with item 1; both are logging-only.

**1. Candidate-ranking instrumentation.** APPROVED by the owner 2026-09-04 for
after the week. The 48h missed-opportunity audit found $16.81 of genuine misses
and **zero dollars of it behind any filter** — UAI SHORT $10.05, CP SHORT $2.35,
PONS LONG $2.27, SKR LONG $2.14, all of which passed every detector and
post-detector gate. They were lost to which candidate the scan ranked first, or
to one-entry-per-pass. That is the only place real money was left, and it is a
PRIORITISATION question, not a filter question. Log the ranked candidate list
and the entry decision per pass so the question becomes answerable. Widens no
aperture, so it carries none of the loosening risk the rejected list warns about.

**2. `/why` prices counterfactuals at TODAY's equity, not the equity in force.**
It reported "gates saved $100.86 over 7d"; the same 24 decisions at the ~$180
actually running are worth **-$16.55**. A ~6x overstatement on a number the
owner reads daily, and it will get worse now that equity is $1,100 while
historical rows were sized at $180. Direction is right, magnitude is not.

**3. `/report` defects, from the funding-day audit.** In severity order:
   - **Risk sizing KPI cannot fail.** `base = margin_wanted x sl_margin_pct /
     equity_at_entry`, and `margin_wanted = risk_pct x available x 100 /
     sl_margin_pct`, so both terms cancel and `base == risk_pct x 100`
     identically. The KPI whose note says "off by more than 0.15 VOIDS the
     trial" is a readback of an env var. `risk_cap_bound` is already stamped on
     every entry and never read — the fix is free.
   - **Tail-loss KPI grades its own baseline as failing.** Verdict is an
     absolute count (`len(tail) <= 1`) while its printed note is a rate
     (`BASE_TAIL_RATE * n`). The 63-close reference sample it was derived from
     scores Bad twice over (8 tails; worst -3.79R trips the -2R branch), and at
     the baseline rate P(Bad) is 91.6% at the n=30 verdict point. Since
     `overall()` returns MIXED whenever any KPI is Bad, this single row makes
     "ON TRACK" structurally near-unreachable. Fix at a trial boundary, never
     mid-trial — the thresholds are pre-registered and frozen on purpose.
   - Drawdown NA fallback is a deterministic false Good when equity stamps are
     missing — a ledger defect renders as a green tick.
   - Regime coverage clamps to bar 0 beyond ~21 days, so a 60-day trial counts
     its first ~39 days as good coverage on data that does not exist.
   - Ledger integrity prints "MISSING ROWS" when rows EXCEED the exchange count,
     sending the reader after absent rows when the fault is duplicates.
   - `$/fill` does not exist in the runtime at all (only in `tools/pit_*.py`),
     so trial 19's PRIMARY criterion cannot be evaluated from `/report`.

**4. `no_new_extreme` is unpriced.** Every other gate has measured dollars in
the gate-cost ledger; this one has zero rows, and it is the binding constraint
on TREND — the sleeve that produced all of trial 18's profit. A 7,600-bar-per-
symbol replay put taken-vs-blocked at +0.49 pts / 1.07 SE with heavily
overlapping windows, i.e. no measurable edge either way; it is a selectivity
filter (2,010 signals -> 342) rather than an edge filter. That is a substitute
for the real instrument, not the instrument.

**0. RETIRE THE NEWS PROCESS.** APPROVED by the owner 2026-09-05. Set
`FUTURES_NEWS_CAPTURE_ENABLED=0` at the first post-week restart. Measured
contribution to P&L: $0. Trading on news refuted on sample (2 corroborated,
symbol-linked, liquid events in the whole corpus, both BTC). The alerts are
NEGATIVE, not neutral: 9 of 18 three-source alerts were chain-merges of
unrelated headlines (clusterer ~50% precise; `rare_df=0.05` is a ratio that
admits ordinary words at this corpus size). The lag is editorial (median 173
min for a third newsroom to publish) so news cannot lead the price trigger. The
one lead — news arriving at 0.81 of the 30-day range vs 0.59 null — is already
encoded more directly and with no latency by TREND's `no_new_extreme` gate.
Retire fully; do NOT half-retire by silencing alerts and leaving capture on —
a subsystem with no consumer and no measurement is the `redis` failure pattern.
The module and the 328 captured rows stay. If a NEGATIVE-news veto (hack,
exploit, delisting — the only place news plausibly leads price) ever earns a
test, it is a new build with a defined sample target, not a revival of this one.
News touches no trading path, so this change carries zero execution risk.

**5. Consider RAISING the turnover floor.** Position notional went from ~$247 to
**$1,461** with the deposit, so participation scaled 5.9x against an unchanged
$2M floor. At the thin end of the universe a single position is 1-3% of a full
day's volume. This is the one change today's numbers argue for, and it TIGHTENS
rather than loosens.

## TRIAL 18 FINAL — closed 2026-09-04 10:57 UTC by the funding re-stamp

27 closes by ENTRY-time membership (not the 25 scored at 09:00; USELESS and ZEC
settled after). **PASSED.**

    PRIMARY  mean realised risk 1.690%  in [1.6, 2.2]      PASS
             max single entry   2.420%  (kill at >3.0%)    clear
    netR     +9.78   ex-best +6.88                         PASS
    net $    +17.18  ex-best +7.69

    TREND     n=7    $+17.78   $/fill +2.539   R/fill +0.564
    WILDCARD  n=20   $ -0.59   $/fill -0.030   R/fill -0.007

**THE TRIAL-19 BASELINE IS R/fill, NOT $/fill.** Trial 19's PRIMARY criterion is
"TREND $/fill not materially below trial 18's baseline", and the funded week
runs at 5.9x equity, so a raw dollar comparison is meaningless across it. The
baseline to beat is **TREND +0.564 R/fill over n=7** (1R was $4.50). Small n --
treat it as a floor to clear, not a precise target.

TREND carried the whole trial again; WILDCARD was flat-to-negative over 20
closes. That asymmetry is now four trials old.

## The evidence, and its limits stated with it

    slots  fills     net $  vs live  $/fill  marginal  both halves?
    1         62   +$28.07  -68.87    0.453       -     no
    2 LIVE    88   +$96.93   +0.00    1.102  +2.649   base
    3        102  +$111.82  +14.89    1.096  +1.064    YES

Three properties, and the second is the one that matters:

1. **It clears the boundary-swept half-split** — the only cell to do so in any
   study this week, and it has now done it on three separate runs (+$9.15
   completed-bar, +$14.89 intra-bar twice).
2. **`$/fill` is FLAT**, 1.102 -> 1.096. The third slot is not buying turnover at
   worse quality; the marginal fill pays +$1.064 against an existing +$1.102.
   Every symbol addition failed exactly this test.
3. All three thirds improve: +47.1/-17.6/+67.5 -> +56.2/-20.3/+75.9.

**IT IS UNDER THE BAR.** +$14.89 over 234 days is **$1.91/month** against the
standing $10 threshold. It is being run because it is the only thing that
survives scrutiny, NOT because it clears the economics. If the trial passes,
that is not a reason to expect $10/month from it.

**THE HARNESS ERROR IS 77% OF THE EFFECT.** Calibrated against live TREND over
the trial-18 window the replay read +$18.55 against +$15.81. The effect is
+$14.89 and the error is up to +$11.40, so this is a 1.3:1 signal. The replay
also OVERSTATES live, so the estimate is optimistic in the same direction.

**4 slots is identical to 3** because the universe is three symbols and the book
already enforces one position per symbol. 3 is the structural ceiling, so this
trial tests the last available unit of TREND capacity.

## Pass criteria (30 TREND closes, or 60 days, whichever first)

TREND books ~2.5 closes/week at 2 slots, so 30 closes is roughly 8-12 weeks.
This is a SLOW trial and that is a property of the sleeve, not a flaw in the rule.

1. **PRIMARY: `$/fill` not materially below trial 18's TREND baseline.** The
   whole thesis is that the third slot is non-dilutive. A fill rate that rises
   while `$/fill` collapses is the failure mode, and it is what killed every
   universe expansion.
2. TREND fill rate per week ABOVE the 2-slot baseline — if capacity was not
   binding, nothing changes and the trial tested nothing.
3. netR > 0 and netR ex-best > 0.

## Kill conditions

- **Any moment with 3 TREND + 3 WILDCARD positions open AND total margin > 45%
  of equity.** Peak simultaneous margin measured 35.5% at the current 5-slot
  ceiling; this trial raises the ceiling to 6 and there is NO portfolio margin
  cap anywhere on the convex path. This is the kill that matters.
- TREND `$/fill` below 50% of the 2-slot baseline at n>=15 -> dilution, restore 2.
- Trial drawdown > 20% of equity -> restore 2.
- Rollback is one env var **plus a redeploy** — Railway marks variable-only
  changes SKIPPED and the running process keeps the old environment.
  **CORRECTED 2026-09-04: this no longer holds.** Setting FUTURES_TRIAL_START_TS
  and FUTURES_TRIAL_LABEL via `railway variables --set` created a deployment on
  its own at 10:57:16 and the new env was live in the process by 10:58:36. A
  following `railway redeploy` was REFUSED ("cannot be redeployed... currently
  building"), which is the correct behaviour and not an error. So: set the
  variables, then WAIT and verify by reading the env inside the process. Do not
  chain a redeploy - it either no-ops or, if it lands first, re-runs the old
  commit (see the deploy trap above).

## What this trial does NOT change

WILDCARD is untouched: 3 slots, 8% trigger, 5R cap, retention 0.50 with the 3R
-> 0.75 ratchet. TREND keeps ETH/XRP/ZEC, the 4% trigger, the 24h clock, the
3.0x stop and long-only. The regime scaler is untouched, though see below.

## The one thing that might displace this — WITHDRAWN 2026-09-06

~~`regime_size_mult` is the only per-trade feature to cross 2 SE~~ — **that
finding is an ARTEFACT and the check it demanded is cancelled.**

The -2.26 SE (winners 0.756 vs losers 0.929) was measured on the trial-18
window alone at n=23. Reconstructed across windows by two independent agents in
the 2026-09-06 scaler research:

    window            n     winners   losers    SE
    trial 18 only     29     0.784     0.880   -1.27
    pre-2026-08-29    43       --        --    +1.29   (OPPOSITE sign)
    full history     109     0.814      --     +0.31

It is a window/bimodal artefact, not a signal. **The scaler has no measured
weakness.** Do NOT run the "check at n>=30 before opening trial 19" gate — there
is nothing to check. Trial 19 (`FUTURES_TREND_MAX_POSITIONS` 2 -> 3) stands on
its own screen result, which remains the only cell to clear the boundary-swept
half-split in any study.


---

# PRE-REGISTERED DECISION RULE — CONVEX TRIAL 18 (opened 2026-08-29)

**Under test: the regime scaler's 0.25 FLOOR.** `FUTURES_REGIME_FLOOR_MULT`
0.25 -> 0.50, scaler shape otherwise unchanged.

**Shipped in the same reset, NOT under test:** `FUTURES_CONVEX_TRAIL_RETAIN_FRAC`
0.30 -> 0.50.

## Trial 17 CLOSED 2026-08-29 at n=4 — EARLY, and the reason is arithmetic

Trial 17 asked whether the cold-streak throttle was suppressing size. With the
throttle OFF (`streak_mult 1.0`) on every entry since 08-27 09:32, realised risk
per trade was still **1.018%** against the 1.6-2.2% target. The throttle was not
the shrinker.

This is an EARLY close against a pre-registration that said 30 closes, and that
is recorded as such rather than dressed up. The justification is that the PRIMARY
criterion is a mean of a *bounded* quantity: the floor imposes a hard lower bound
of `0.0241 x 0.25 = 0.60%` per entry and roughly half of observed entries sit on
it (2.122% at scaler ~0.98, then 0.620% and 0.577% both floored, 0.752% at scaler
~0.31). No additional sample can lift a mean above a band when half the draws are
pinned below it by construction. Trial 17's P&L question is left UNANSWERED and
stays that way; it was never the primary criterion.

## Why retention 0.50 ships in the same reset

Normally one change per trial. The exception is justified because the two changes
are read by **different instruments**, so neither can contaminate the other's
verdict:

- Trial 18's PRIMARY and all three kill conditions are *sizing* measurements
  (realised risk %, single-entry risk %, trial drawdown). An exit-timing change
  cannot move realised risk at entry — the size is fixed before the trail exists.
- Retention 0.50's evidence is a *replay* result, not something this trial is
  powered to test. At the ~20 closes trial 18 will reach by Friday, the P&L
  verdict was never going to be readable for either change.

The evidence for 0.50, replicated across two independent full-coverage runs on
2026-08-28 (`tools/pit_exits_sized.py`):

| | live 0.30 | retain 0.50 |
|---|---|---|
| net $ (220d, live sizing) | +208.85 | **+251.24** (+42.39) |
| fills | 533 | 559 |
| **$ per fill** | 0.392 | **0.449 (+14.6%)** |
| max drawdown | 41.9% | **39.1%** |
| ex-top-5% | -134.87 | **-65.84** |
| both halves, every boundary 35-65% | base | **YES** |

It improves on all four axes and on a per-fill basis, so the gain is not merely
extra turnover. Contrast retain 0.70, which shows +$16.72 net but **$0.385/fill
against live's $0.392** — its entire gain is 53 extra trades at slightly worse
quality, which is exactly why it fails the half-split. That distinction only
became visible when the per-arm fill count was added to the table on 2026-08-29;
before that, 0.70 looked like a candidate.

## Why the turnover band does NOT ship

`FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER` 24 -> 12 is the largest dollar number on
the board (+$81.43 at the live floor, beats live at all four floors in both runs,
passes the half-split at all four). It is held back deliberately:

- Its gain is **tail-concentrated**: ex-top-5% moves the WRONG way, -227.64 ->
  -255.35. More gross, not more bankable.
- It raises turnover 22% (619 -> 755 fills). Adding exposure immediately before a
  possible 3x funding is the wrong order of operations.

Revisit after the funded window closes, on its own trial.

## Pass criteria (30 convex closes)

- **PRIMARY:** realised mean risk per trade in [1.6%, 2.2%]. Same criterion as
  trials 16 and 17, because it is still the thing that has never been achieved.
- netR > 0 AND netR ex-best > 0.

## Kill conditions

- Realised mean risk still < 1.5% at n=10 -> a fourth shrinker exists; halt and
  audit the whole sizing path rather than opening trial 19 on a guess.
- Any single entry risking > 3.0% of equity -> the floor was load-bearing;
  restore 0.25 and close.
- Trial drawdown > 20% of equity -> restore 0.25.
- Rollback is one env var **plus a redeploy** — Railway marks variable-only
  changes SKIPPED and the running process keeps the old environment.
  **CORRECTED 2026-09-04: this no longer holds.** Setting FUTURES_TRIAL_START_TS
  and FUTURES_TRIAL_LABEL via `railway variables --set` created a deployment on
  its own at 10:57:16 and the new env was live in the process by 10:58:36. A
  following `railway redeploy` was REFUSED ("cannot be redeployed... currently
  building"), which is the correct behaviour and not an error. So: set the
  variables, then WAIT and verify by reading the env inside the process. Do not
  chain a redeploy - it either no-ops or, if it lands first, re-runs the old
  commit (see the deploy trap above).

---

## DEPLOY TRAP: `railway redeploy` re-runs the OLD COMMIT and can clobber a push

Measured 2026-09-03. `git push` triggers a GitHub auto-deploy of the new commit.
`railway redeploy` does NOT build the branch tip -- it re-runs the *latest
existing deployment*, i.e. the commit already live. Running both together is a
race, and redeploy wins:

    21:45:31  auto-deploy  5f36a14 (the push)      -> REMOVING (superseded)
    21:45:33  railway redeploy                     -> d3130ed (the OLD commit), SUCCESS
    21:46:54  railway redeploy, tried again        -> d3130ed AGAIN

The new code never went live and nothing reported an error. Both deployments
return exit 0 and both say SUCCESS.

**The rule.** After a `git push`, do NOT redeploy -- wait for the auto-deploy.
Verify with the commit hash, never with deployment status:

```
railway deployment list --json | python -c "import json,sys;
d=json.load(sys.stdin)[0]; print(d['status'], d['meta']['commitHash'][:10])"
```

**It has not bitten before.** Every deployment from 2026-09-01 onward was
checked against `git rev-list --count`: all went strictly forward except the two
redeploys above, both mine, both today. No past feature was silently reverted,
so nothing in the trial record needs re-auditing for this.

`railway redeploy` is for restarting the SAME code -- which is exactly what an
env-var change needs -- though as of 2026-09-04 a variable change TRIGGERS its
own deployment, so a chained redeploy is refused or harmful; see the correction
in the trial sections. Historically Railway marked variable-only changes SKIPPED and the
running process keeps the old environment. Code change -> push and wait.
Variable change -> redeploy. Never both at once.

---

## CARRYOVER: the first two closes of trial 18 are NOT trial 18 trades

Trial 18's environment was written at 2026-08-28 23:46:18Z but the container did
not restart until 00:37Z on 08-29 (`railway redeploy` returns exit 0, prints
nothing and creates no deployment unless `--json` is passed; even then the swap
lagged ~50 minutes). Two WILDCARD positions were open across that boundary. They
were SIZED under trial 17's `FUTURES_REGIME_FLOOR_MULT=0.25`.

Re-stamping `FUTURES_TRIAL_START_TS` does NOT exclude them. The scoreboard filters
on EXIT time, not entry time -- `learning_digest.py:83` selects rows with
`ts >= trial_start`, and `runtime.py:4736` sets that `ts` from `trade["exit_time"]`.
Both positions exit in the future, so any start timestamp short of a future one
still admits them.

**Therefore: exclude the first two WILDCARD closes of trial 18 from the realised
mean-risk statistic, and say so when quoting n.** They are trial 17 trades that
happen to settle inside trial 18's window.

Why this is not pedantry. The Friday funding gate reads mean realised risk against
a [1.6%, 2.2%] band at n>=10. Two trial-17-sized trades in that ten drag the mean
toward the kill condition: eight new trades averaging 1.9% with two carryovers at
0.6% reads 1.64%, which passes by 0.04pp; at 1.0% carryover it reads 1.72%. The
contamination is survivable but it eats most of the margin, and trial 16 was
already voided once by a sizing-measurement failure.

The two carryover positions, measured live at 00:45Z:

| symbol | realised risk %% of equity |
|---|---|
| TAC_USDT | 1.923 (in band) |
| BLESS_USDT | **0.438** |

BLESS looked alarming and I called it wrong. On 2026-08-29 I attributed its 0.438%
to contract truncation. Measured against the feature store, its truncation factor
(`size_efficiency / (regime_size_mult x streak_multiplier)`) is **1.004** -- no
truncation at all. Its size came from the regime scaler sitting on its 0.25 floor,
which is exactly the thing trial 18 changes.

TRUNCATION, MEASURED LIVE over 35 wildcard closes rather than modelled:

| | |
|---|---|
| truncation factor | mean **0.941**, median **0.994**, p10 0.801, min 0.528 |
| trades losing >10% | 6 of 35 |

So `tools/plan_capacity.py`'s replay estimate of ~4% was approximately right (live
says ~6%), and the alarm was not. The dominant shrinker is the SCALER, visible in
the regime column running 0.25 / 0.25 / 0.44 / 0.45 / 0.51 / 0.75 / 0.79 / 0.93.
Trial 18 is aimed at the right link.

`risk_pct_actual` over 28 wildcard closes: mean **1.319%**, median 1.429%, against
the 1.6-2.2% target.

CAPACITY AND SLIPPAGE, measured 2026-08-29 -- the last open objection to funding:

| | |
|---|---|
| median notional | $29.25 (max $92.22) |
| at 6.3x funding | median $184, max $581 |
| max notional vs the $2M/day floor | **0.029% of one day's volume** |
| stop exits (n=3) | mean -1.060R; excess -0.060R, roughly half of it fees |
| implied slippage | ~0.03R, about 0.15% of price |

Notional is an order of magnitude below what `plan_funding.py` printed, because
that tool assumed the configured leverage of 5 while live leverage is DERIVED down
to 1-4 to keep the loss inside `MAX_SL_MARGIN_PCT`. Capacity does not constrain
this account at any deposit size under discussion. The slippage figure rests on
THREE stop exits and should be re-measured once trial 18 has more; it is thin
evidence for a comfortable conclusion, which is the combination worth distrusting.

OPEN DISCREPANCY, not yet explained: the feature store's `margin_used` and
trade_history's `margin_usdt` disagree for the same trade (BLESS: 17.305 vs 4.34,
a factor of ~4). One of the two is not what its name says. This does not affect the
truncation ratio above (which uses feature-store fields throughout) but it does
affect anything that reads margin across the two sources.

The live watch (`scratchpad/trial18_watch.sh`, monitor bojolig1e) filters on entry
time and therefore excludes both carryovers; it also alerts if any trial-18 entry
realises below 1.15%, which would prove the new floor never took effect.

Note the exits themselves are ALSO mixed: `FUTURES_CONVEX_TRAIL_RETAIN_FRAC` is
read at exit-check time (`runtime.py:1932`), so these two positions will trail at
0.50 despite having been opened under 0.30. That affects their P&L, not their
realised risk, so it does not touch the PRIMARY criterion.

---

## THE REGIME QUESTION IS CLOSED, 2026-09-02

Seventeen formulations have now been tested and refuted. The last one closes it,
because it measured the quantity itself rather than a proxy for it.

**What we were trying to predict.** The 7-day post-mortem isolated the mechanism
exactly. Comparing the last 7 days to the 7 before: entries unchanged (3h ROC
12.9 -> 13.2), losses unchanged (-1.04R in BOTH weeks), win rate 54% -> 50% -
but mean peak_r fell **1.487 -> 0.948** and take-profits went **5 -> 0**. The
decomposition is 100% quality: count effect +$5.35, quality effect -$45.31. The
moves stopped EXTENDING. Wins halved (+1.72R -> +0.79R) while losses held exactly.

**Why the first sixteen attempts could not work.** Every one measured either
BTC/ETH/SOL - a proxy for a universe the bot does not trade - or the bot's own
~2.5 closes a day, far too few to detect a change before the drought is over.

**The measurement that closes it** (`tools/pit_universe_followthrough.py`). Of
every qualifying 8% three-hour move across the ~170-symbol universe, what
fraction reaches 1R? 1194 signals over 220 days, aggregated into a daily series:

    daily reach-1R:  mean 50%   sd 23%   min 0%   max 100%

    autocorrelation  lag 1 day  -0.174   (n=112 days)
                     lag 2 day  -0.145
                     lag 3 day  +0.028

**There is no positive persistence.** Lag-1 is negative (~-1.85 SE, so
"mean-reverting" is not established either - the defensible claim is only that
nothing persists). Gating the live book on lagged universe follow-through loses
money at every threshold: -$16.14, -$11.78, -$8.38, all REFUTED by the placebo
control.

**The conclusion.** Tail-availability is measurable AFTER the fact and
unforecastable BEFORE it. The sixteen earlier failures were not failures of
imagination; they were attempts to time a quantity with no memory. n=112 days is
the largest clean sample any regime test in this project has had.

**FORECASTING vs DETECTION - the owner's follow-up, and it is a fair
distinction.** The autocorrelation above answers whether yesterday predicts
tomorrow. It does not answer whether the bot can recognise it is CURRENTLY
inside a drought, and a state can be unforecastable yet persistent enough that
recognising it pays. `tools/pit_drought_persistence.py` settles it on 116 days:

| test | result |
|---|---|
| autocorrelation, every lag 1-14 | lag1 **-0.188** (-2.0 SE); lag 3-14 ~0 |
| trailing 7d vs next 7d | **-0.263** |
| below-median run length | **mean 1.90 days, MAX 5** |
| after 1 dry day -> next day | **52%** |
| after 2 dry days -> next day | **58%** |
| unconditional | **50%** |

Detection is possible and worthless, for three independent reasons: the state
lasts under two days on average, the conditional runs the WRONG WAY (after dry
days conditions are marginally BETTER, so a detector throttles at the worst
moment), and the signal is tiny - see below.

**THE AMPLIFICATION, which is the finding worth keeping.** The week that cost
$40 had a universe reach-1R of **41% against a 50% baseline**. With a daily sd
of 22% over 7 days the standard error is 8.4 points, so that week was a
**1.1 SE deviation** - statistically unremarkable.

    universe mean peak   1.62 -> 1.24   (-24%)
    bot mean peak        1.49 -> 0.95   (-36%)
    bot P&L             +$32.07 -> -$7.89

**Most of this bot's P&L variance is its own sample size, not the market's.** A
28-trade convex book with a fat-tailed payoff amplifies an ordinary wobble in
follow-through into a large swing. That is not a malfunction and not a regime -
it is what a small convex book does, and it is why no detector can help.

The corollary points somewhere the seventeen refuted studies never reached: the
lever that reduces this amplification without touching expectancy is MORE TRADES
PER UNIT TIME. That is not a recommendation - the trigger and slot sweeps failed
on their own terms and "trade more" needs its own evidence - but it is the first
framing that is not about prediction.

**What this leaves.** Not prediction. Sizing down scales wins and losses alike,
so it moves variance rather than expectancy. Entry selectivity was refuted
separately (13 price features across two sleeves, nothing at 2 SE). The
remaining answer is the one the strategy was designed around: a convex sleeve
buys optionality precisely BECAUSE the tail cannot be timed, and it has to sit
through droughts.

**Do not reopen without a genuinely new data class** - order book, funding,
cross-exchange, or the news corpus now accruing. Another price-derived regime
formulation is not new evidence.

---

## STANDING METHOD: the PLACEBO CONTROL is mandatory for regime studies

Added 2026-09-02 after it caught a result that had already passed every other
screen in this document.

**What happened.** A majors-up gate - trade only while any of BTC/ETH/SOL is up
>=1% over the trailing 72h - was applied to the REAL live trades (no replay).
It turned trials 17+18 from -$4.32 into +$12.89, held up on the whole history,
and a permutation test against random same-size subsets returned **p < 1%**. It
was one step from being pre-registered as a trial.

**Why the permutation test could not see the problem.** A permutation test asks
whether a filter picked better trades than a RANDOM subset of the same size.
That is the correct control for a filter selecting trades INDEPENDENTLY - score,
calm_ratio, turnover, ROC band. A regime gate does not select independently: it
selects by TIME, in contiguous stretches. This book is autocorrelated, with good
weeks and bad weeks, so ANY time-correlated filter beats random subsets whether
or not it knows anything about markets. The p<1% was measuring autocorrelation.

**The control.** Run the identical gate on a TIME-SHIFTED signal. A gate driven
by the majors from seven days earlier has the same clustering behaviour and the
same duty cycle, and carries NO information about the market each trade actually
traded in. Result on the gate that had passed:

| majors signal | net $ |
|---|---|
| **REAL, no shift** | **+13.95** |
| shifted -7 days | **+17.07** — the placebo WON |
| shifted +3 days | +6.73 |
| shifted -3 days | +4.82 |
| shifted +14 days | +0.34 |
| shifted -14 days | -22.37 |
| shifted +7 days | -35.52 |

The real result sits inside a placebo spread of -$35.52 to +$17.07 and is beaten
by a signal that cannot work. **Refuted.**

**CORRECTED HOURS AFTER IT SHIPPED.** The first version used SIX shifts, so the
strongest possible verdict was "beat all six" - which a null gate reaches about
one time in seven. Pointed at ten KNOWN-NULL regime hypotheses
(`tools/pit_regime_audit.py`) it called **five of them survivors**. The control
was not measuring anything; it was reporting which gates topped a six-sample
draw. It now uses ~210 shifts from +-4 to +-30 days at 6h steps, making the rank
a real percentile (best achievable 0.48%). Re-run on the same known-null set the
survivor count fell from **5 of 10 to 1 of 15**, and that one is a threshold
chosen in-sample - see the limitation below. Shifts under 4 days are excluded:
a 72h signal shifted by one day is a blurred copy of itself, not a placebo.

**WHAT IT STILL CANNOT DO.** The placebo controls for TIME STRUCTURE, not for
IN-SAMPLE SELECTION. A threshold picked after seeing the outcomes - "the bottom
divergence quintile" - will pass, because the signal genuinely does separate
these particular trades. Selection needs its own control: pre-registration, or
a hold-out. Read a SURVIVES verdict as "not merely calendrical", never as
"real".

**The rule.** `tools/pit_placebo.py`, guarded by `tests/test_placebo_control.py`.
Any study whose decision is a function of TIME rather than of the individual
trade must report a placebo table before its result is quoted:

    majors gates | majors tilts | divergence policies | direction filters
    news-regime policies | cooldowns keyed on market state | seasonality

Per-trade filters are exempt and keep the permutation test. Read the RANK, not
the value: the question is never "did it make money", it is "did it beat signals
that cannot possibly work". Fewer than three usable shifts is INCONCLUSIVE, not
a pass - a shift that empties the book is excluded rather than scored as a
placebo defeat, since counting it would flatter every gate.

**Everything already refuted stays refuted**, since the control only makes the
bar higher. Five distinct regime formulations have now failed: majors gates,
majors tilts, divergence policies, BTC-up direction, and the stateful gate. The
consistency of that is itself the finding.

---

## REJECTED during trial 18, measured 2026-09-01 on the CORRECTED book

Everything below was measured through `pit_book.take()` — the first slot book in
this repo that sizes off AVAILABLE margin, applies the calm filter where live
applies it, and takes at most one entry per scan window. Results computed before
those corrections are not comparable and are superseded where they conflict.

**The investigation that produced these.** The 28 convex losses in the trailing
28 days share ONE mechanical cause: every one peaked below 1.0R, so the retention
trail never armed. The exit stack is not implicated in a single loss. That closes
the exit side of the loss question and moves it entirely to entry selection.

- **Entry price-context scoring: REJECTED.** `tools/pit_loss_context.py` built
  13 features at entry (4h/8h/24h trend, the matching averages, extension above
  each, position in the 24h range, realised vol, straightness, 3h ROC, calm,
  regime mult) for 28 losers AGAINST 33 winners — a control group, because a
  feature found only in losers is unfalsifiable. **Nothing separates at 2 SE.**
  The strongest are 3h ROC (+1.60 SE), 15m vol (+1.51) and position in the 24h
  range (+1.33), and on 13 features at n=61 you expect ~1 spurious 2-SE gap
  anyway. Direction is nonetheless unanimous: 12 of 13 gaps say winners entered
  MORE extended, closer to the 24h high, in wider-range and more volatile
  symbols. Tepid moves lose. That is the convex sleeve working as designed, not
  a filter. Retest only with a materially different feature class — order-book,
  funding, or cross-exchange — not more price transforms.

- **TREND trigger raise, 4% -> 5%: REJECTED, and the band effect is REAL.**
  `tools/pit_trend_trigger.py`. The 4.0-5.0% ROC band IS the worst thing on the
  sleeve and it replicates from n=5 live to n=85 replay: 85 fills, 39 wins,
  **-$26.40, -$0.311/fill** — the only negative band of six, against +$1.458,
  +$0.940, +$1.007 and +$1.772 per fill in the bands above it. **Raising the
  trigger does not capture it: -$2.24 over 231 days.** A trigger does not excise
  a band, it RESHUFFLES THE SCHEDULE. Section D decomposes and reconciles to the
  cent: dropping the 85 band trades also displaces 29 trades at >=5% ROC worth
  **+$61.27**, and admits 74 different ones worth +$35.03. No threshold from
  3.0% to 8.0% clears the boundary-swept half-split against live.

- **TREND trigger CUT to 3.0% / 48h clock: REJECTED — supersedes 2026-08-27.**
  That cell was recommended (+$12.19/220d, "best joint cell") on the UNCORRECTED
  book and was never re-run. On the corrected book 3.0% shows +$16.44 net but
  **ex-top-5% -$12.59** against live's +$2.12 — the entire gain is outlier-borne
  — and it fails the half-split. The two directions are now both refuted, so the
  live 4.0% trigger stands with a measurement behind it for the first time. The
  48h-clock half is separately moot for the observed losers: the five live 4-5%
  trades held 2.6h, 4.1h, 8.7h, 5.3h and 4.2h and every one died on its STOP,
  not the clock.

- **TREND 4-5% band down-sizing: REJECTED on size, not on sign.** The lever that
  does NOT reshuffle is sizing the band down rather than excluding it — the
  trade still opens and still holds its slot, so the fill schedule is unchanged.
  It clears the screen at every level, but is worth **+$1.72/month at 50%
  sizing** and +$2.57/month at 25%, the most aggressive implementable setting
  (0% is not implementable — you cannot open a zero-size position). Against the
  $10/month bar. It is also NOT stable in time: by thirds the band runs
  **-17.7 / +10.9 / -19.6**, negative in aggregate and in both halves at every
  boundary but sign-flipped in the middle third. Retest if TREND volume rises
  materially, since the effect is per-fill and the sleeve only books ~17 closes
  a month.

- **TREND third slot: REJECTION WITHDRAWN 2026-09-01 (same day).** The sweep
  below ran on COMPLETED 15m bars. Re-run on intra-bar detection
  (`tools/pit_trend_intrabar.py`) the sign REVERSES: 3 slots books 98 fills for
  **+$9.15 vs live**, `$/fill` 0.715 against base 0.717, ex-top-5% **+27.53 vs
  +17.51**, and it is the ONLY cell in that run to clear the boundary-swept
  screen. 4 slots is byte-identical to 3 (3-symbol universe, one position per
  symbol). It STILL does not ship - +$9.15 over 234 days is **$1.17/month**
  against a $10 bar - but "live 2 is optimal on every axis" is false and must not
  be re-quoted. The completed-bar table is kept below only to show what moved.

- **TREND factorial, the 5% / 3.0x / 48h / 3-slot cell: REFUTED 2026-09-01.**
  It was the best of 16 at **+$31.12**, carrying a genuine +$10.97 three-way
  interaction term. On intra-bar it is **-$16.98** and fails the screen. The
  three-way term does not survive; neither does the "combinations rescue each
  other" reading built on it. What DOES survive is the 4-5% ROC band being the
  only negative band, at -$0.364/fill intra-bar against -$0.311 completed-bar -
  the one TREND structure the fidelity fix left standing.

- **superseded, completed-bar only:** Live 2 optimal on every axis.
  `tools/pit_trend_slots.py`, the first sweep this parameter has ever had.

  | slots | fills | net $ | $/fill | marginal | ex-top5 | thirds |
  |---|---|---|---|---|---|---|
  | 1 | 161 | +75.56 | 0.469 | — | -20.39 | +37.4 / +43.3 / **-5.2** |
  | **2 (live)** | **210** | **+120.54** | **0.574** | **+0.918** | **+2.12** | **+52.0 / +29.3 / +39.2** |
  | 3 | 234 | +102.89 | 0.440 | **-0.735** | -26.09 | +45.7 / +21.9 / +35.3 |

  2 wins on net $, on $/fill, on the only positive ex-top-5%, and is the only
  row with all three thirds positive. The third slot buys 24 extra fills at
  **-$0.735 each** — turnover, not edge. Rows 4/5/6 are byte-identical to 3
  because the universe is 3 symbols and one-position-per-symbol is already
  enforced, so 3 is the structural ceiling. This also refutes the reading that
  the +$61.27 displacement above meant unmet capacity: it was reshuffling.

- **TP cap raise / SECURE latch / scale-out family: REJECTED.**
  `tools/pit_corrected.py` + `tools/pit_secure_audit.py`. Measured 220d:
  SECURE 5R +$5.01, no-cap plain trail +$18.42, **SECURE 6R +$32.97**, bank 25%
  at 5R +$14.42, bank 50% +$9.60. SECURE 6R is the best exit cell this project
  has found and is strictly better than plain no-cap *per trade* — identical
  below a 6R peak and above an 8R peak, better in between. It still does not
  ship: only 14 of 641 signals differ at all, **+$24.66 of the +$32.97 is one
  trade** (BSB, peak 20.84R), and it fails the boundary-swept screen. Strip BSB
  and the residual is **+3.24R over 220 days** (8 of the 9 winners gain exactly
  +1.00R = +8.00R, against 5 losers at -4.76R; BSB alone is the other +11.31R)
  = about $12.60, or $1.72/month. The general result is that **anything taking
  money off the table early costs more than it saves**, because the payoff is tail-borne:
  a floor at 5R exits runners on their first retrace through 5R, and a scale-out
  at 5R sells the part of the runner that matters. Scale-outs score worse
  monotonically as the banked fraction rises.

**Retracted the same day, recorded so it is not re-found:** `calm_score`
(`runtime.py:1095`, a max over BTC/ETH/SOL at 12h/2%, 24h/5%, 72h/10%) is NOT
`calm_ratio` (`wildcard.py:133`, |3h move| / prior 21h range). Six WILDCARD
closes carry `calm_score >= 0.75` and briefly looked like the entry gate
leaking. It is a naming collision. The gate is intact.

**Carried forward unchanged:** TREND 4.0% trigger, 2 TREND slots, 24h clock,
long-only, 3R TP; WILDCARD 3 slots; retention trail 0.50 with the 3R -> 0.75
ratchet; 5R WILDCARD TP cap.


---

## OPEN, not rejected: the WILDCARD trigger may sit one point too high

> **SUPERSEDED IN ITS REASONING, 2026-09-01 (same day). READ THIS FIRST.**
>
> Everything below the divider was measured on COMPLETED 15m bars. The live bot
> evaluates a PARTIALLY FORMED candle every 450s, and re-running with intra-bar
> detection (`tools/pit_intrabar.py`) **refutes the band argument entirely**:
>
> | 3h ROC | completed-bar $/fill | intra-bar $/fill |
> |---|---|---|
> | 3-4% | -0.227 | +0.079 |
> | 4-5% | -0.266 | +0.243 |
> | 5-6% | -0.174 | -0.399 |
> | 6-7% | -0.331 | +0.126 |
> | **7-8%** | **+0.617** | **-0.398** |
> | 8-10% | +0.950 | +0.747 |
>
> The "bimodal, four negative bands then three positive, sweet spot 7-12%"
> structure does not exist. **The 7-8% band the hypothesis proposed capturing
> earns -$0.398/fill**, not +$0.617. Do not repeat the band rationale.
>
> THE CONCLUSION SURVIVES ON DIFFERENT EVIDENCE, and is now better supported
> than it was. On the intra-bar book the 7% trigger is the ONLY cell of eight to
> clear the boundary-swept screen:
>
> | trigger | fills | net $ | vs live | ex-top5 | $/fill | both? | thirds |
> |---|---|---|---|---|---|---|---|
> | 7% | 431 | +155.18 | **+43.23** | -86.06 | **0.360** | **YES** | +75.1 / +56.2 / +31.3 |
> | 8% (live) | 379 | +111.95 | base | -85.80 | 0.295 | base | +58.7 / +32.2 / +21.0 |
> | 6% | 481 | +92.66 | -19.30 | -127.45 | 0.193 | no | |
>
> It is no longer dilution - $/fill IMPROVES 0.295 -> 0.360 - and ex-top-5% is
> unchanged rather than worse. Both objections in reason 2 and reason 3 below
> are therefore withdrawn. It is +$5.54/month at $170 equity, so reason 1 (under
> the $10 bar) still stands, and reason 4 is replaced by a different worry:
>
> **THE MECHANISM IS NOW UNEXPLAINED.** The band that the trigger admits loses
> money, yet admitting it improves the book. That can only work through slot
> RESCHEDULING, which is real (proven to the cent on TREND) but is not a reason
> anyone can reason about forward. An effect with no mechanism beyond scheduling
> is exactly what the shadow ledger should adjudicate, which is what
> `FUTURES_WILDCARD_SHADOW_MIN_ROC` was staged for.
>
> One thing DID survive both methods: the calm_ratio gradient. 0.00-0.15 is the
> best band under completed bars (+1.374/fill) and intra-bar (+0.962), and
> 0.60-0.75 is negative under both (-0.226, -0.242). Of everything measured on
> WILDCARD today, that is the only structure the fidelity fix did not overturn.

---


The only item from 2026-09-01 that is NOT refuted. It is recorded as OPEN
because the evidence is suggestive, internally inconsistent in one specific way,
and — uniquely among everything tested this session — **cannot currently be
corroborated from live data at any sample size**. The instrumentation to fix
that is staged below.

**How it was found.** The first WILDCARD band sweep sampled the trigger UPWARD
only (8% -> 14%), which was a design hole rather than a reporting omission: the
candidate pool was itself gated at 8%, so the region the bot never trades was
never generated. The owner caught it. Re-running with the pool widened to a 3%
floor gives a band structure that is **bimodal around the live gate**:

| 3h ROC at entry | fills | $/fill | |
|---|---|---|---|
| 3 - 4% | 563 | -0.227 | negative |
| 4 - 5% | 261 | -0.266 | negative |
| 5 - 6% | 157 | -0.174 | negative |
| 6 - 7% | 97 | -0.331 | negative |
| **7 - 8%** | **77** | **+0.617** | **excluded by the live gate** |
| 8 - 10% | 89 | +0.950 | positive |
| 10 - 12% | 47 | +0.580 | positive |
| 12 - 16% | 67 | -0.119 | scatter above here |
| 16 - 24% | 36 | +0.153 | |
| 24 - 40% | 26 | +1.635 | |
| >= 40% | 8 | +0.747 | |
| ALL | 475 | +0.449 | |

Four consecutive negative bands then three consecutive positive ones is a
structure, not scatter — and it is held to the same standard that dismissed the
12-40% region as noise, which alternates sign band to band. **The sweet spot is
7-12% and the trigger is set one point inside its lower edge.**

**Why it does not ship on this evidence.** Four independent reasons:

| | 8% (live) | 7% | 6% |
|---|---|---|---|
| net $ over 234d | +213.08 | +234.54 | +263.68 |
| vs live | base | +21.46 | +50.59 |
| **$/fill** | **0.449** | 0.401 | 0.372 |
| marginal $/extra fill | — | +0.195 | +0.217 |
| **ex-top-5%** | **-80.01** | -112.51 | -127.27 |
| both halves, 35-65% | base | **no** | YES |
| $/month at $170 equity | — | +2.75 | **+6.49** |

1. **Under the bar.** +$6.49/month at the best cell, against $10 either way.
2. **It is dilution, not edge.** $/fill falls 0.449 -> 0.372; the marginal fill
   pays $0.217 against a base of $0.449. That is the pattern `pit_slots.py`
   exists to catch — buying turnover at below-average quality.
3. **Less bankable, not more.** ex-top-5% worsens monotonically as the trigger
   drops: -$80 at 8%, -$127 at 6%, -$653 at 3%. It is already negative at base,
   so the whole WILDCARD replay is outlier-borne; lowering the gate deepens that.
4. **The two views contradict each other.** 6% passes the boundary-swept screen
   and 7% fails it, while the BAND logic says 7% should be the better of the two
   (it adds +$0.617/fill and skips -$0.331/fill). Both cannot be right. At this
   resolution the sweep is schedule-noise dominated — the same reshuffling
   effect proven to the cent on TREND — so its per-cell numbers should not be
   read to one decimal.

**The hypothesis, pre-registered, and it is 7% NOT 6%.** The band structure is
the reliable object; the sweep cell is not. 7% captures the +$0.617/fill band
and excludes the -$0.331/fill one. 6% scores better only in a column that
reason 4 says is unreliable, and it is worse on the two columns that are not
(`$/fill`, `ex-top-5%`). **Do not ship the cell that merely won the noisy
screen.**

**Why this could not be settled from live data, and the fix.** Every other test
this session could be checked against live trades. This one cannot:
`_shadow_log_untaken` only fires on objects that reached the candidate list, and
that list is gated at `FUTURES_WILDCARD_MIN_ROC`. Sub-trigger signals have never
been recorded — not as trades, not as counterfactuals — so the region was
unanswerable IN PRINCIPLE rather than merely unmeasured.

Staged 2026-09-01, **default OFF**:

    FUTURES_WILDCARD_SHADOW_MIN_ROC=0.07     # unset/0 == today's behaviour

The scan widens to `scan_roc` for DETECTION only. Everything below `min_roc` is
shadow-logged as `below_trigger(0.074)` and dropped from the candidate list, in
exactly the position and for exactly the reason long-only and calm-shock are
filtered there. Entry behaviour is unchanged: with the flag unset,
`scan_roc == min_roc` and the detector has already refused everything below it,
so the refusal loop cannot fire and not one extra object survives.

Guarded by `tests/test_sub_trigger_shadow.py` (7 tests, the safety property
being that a sub-trigger signal never reaches the candidate list) and by
`test_sub_trigger_logging_cannot_widen_entry` in `test_trial6.py`. The existing
`test_prefilter_threshold_is_derived_from_the_trigger_not_set_apart` caught this
change and was updated to assert BOTH links of the now two-hop chain, so the
prefilter still cannot be given a threshold of its own.

**What would make it ship.** After >= 3 weeks of sub-trigger logging, the
7.0-8.0% shadow rows must resolve at a mean net R that is (a) positive, and
(b) not below the taken 8-10% population by more than one standard error. That
is a counterfactual-quality test, not a P&L test, because at ~1 sub-trigger
signal every 3 days the sleeve will not book enough dollars to read P&L before
the funded week is long over. If the shadow rows come back negative, the live
8% gate is vindicated and this closes as REJECTED.

**Cost of being wrong in each direction.** Enabling the logging risks nothing —
it is a logging change with no trading effect and a one-variable rollback.
Shipping the 7% trigger on today's evidence risks trading a band whose adjacent
neighbour measures -$0.331/fill, on a sweep whose own cells disagree.


---

# PRE-REGISTERED FUNDING GATE — Friday 2026-09-04

The owner intends to deposit, run ~7 days, then withdraw back to the base
account. This gate is written BEFORE the data arrives so the decision is made
against a rule rather than against a week's mood.

## VERDICT 2026-08-31T19:01Z: **GATE PASSES** at n=10

Recorded at the moment it was answered, not reconstructed later.

| condition | result |
|---|---|
| n >= 10 | **10** |
| mean realised risk in [1.6, 2.2] | **1.713%** |
| kill: <1.5% at n>=10 | not tripped |
| kill: any single entry >3.0% | max 2.461% |

Confirmed independently by the live watch (`scratchpad/trial18_watch.sh`) and by
a hand computation over the same rows; both read 1.713%.

Trial 18's dial worked. The scaler floor 0.25 -> 0.50 lifted mean realised risk
from trial 17's 1.018% into band, with mean regime multiplier 0.760 against the
0.670 the arithmetic required.

**HONEST CAVEATS, recorded with the pass rather than after it.**

 - sd 0.538 over 10 closes gives se 0.170, so the 95% interval is [1.38, 2.05].
   The point estimate is mid-band; the lower bound is BELOW the kill line. Ten
   trades cannot distinguish 1.71% from 1.5%.
 - Six symbols only: ZEC x3, HNT x2, ZORA x2, and one each of SKR, HEMI, 4.
 - netR -0.48, net -$3.25, expectancy -0.047R. The gate does not read P&L by
   design, and at n=10 the standard error on R is ~0.25 - this is not evidence
   of anything either way. It is recorded so nobody later claims the gate passed
   on a profitable trial.

**THE SHAPE FINDING.** All six retention-trail exits landed between +0.48R and
+0.63R; no trade in the trial has exceeded +0.63R. The trail arms at 1R, these
trades peak just above it and fade, so it banks ~0.5R while losers run the full
-1R: mean win +0.565R, mean loss -0.965R at a 60% win rate. The 5R target and
the 3R ratchet have never been reached. This is NOT an argument against
retention 0.50 - at 0.30 those same exits would have banked 0.30-0.36R and the
book would be worse - it is evidence that the fat tail this design depends on
did not appear in this trial.

---

## The gate is a SIZING check, not a P&L check

By Friday trial 18 will hold roughly 15-20 closes. That is ample to verify
realised risk % (a bounded quantity, converges fast) and nowhere near enough to
verify P&L (standard error at 17 trades is ~0.24R, which cannot separate the
replay's +0.13R from live's -0.16R). So:

- **Realised mean risk in [1.6%, 2.2%] at n>=10 -> FUND.**
- **Still < 1.5% at n>=10 -> DO NOT FUND.** That is trial 18's own kill
  condition; a fourth shrinker exists and the sizing path needs auditing before
  any money is scaled onto it.
- Any single entry > 3.0% of equity -> DO NOT FUND, restore the floor first.

Explicitly NOT a gate: whether trial 18 made money this week. It is not powered
to answer that, and treating a profitable week as permission is how a 39%-loss-
probability process gets mistaken for an edge.

## Deposit size

The worst 7-day window in 228 tested (`tools/plan_funding.py`, 2026-08-29) is
**-15.3% of equity**. The deposit returns whole in every case; what absorbs the
entire week's P&L is the BASE account. Sizing follows from that:

| deposit | equity | 1R | worst-week $ | base account after |
|---|---|---|---|---|
| $900 | $1,069 | $25.78 | -$164 | **$5** |
| $500 | $669 | $16.12 | -$102 | $67 |
| **$300** | **$469** | **$11.30** | **-$72** | **$97** |

**THE TABLE ABOVE IS WRONG. Corrected 2026-09-04, before funding.**

Its "base account after" column assumes the owner withdraws **the deposit
amount**, so the week's loss falls entirely on the base. That is not the policy.
The policy, restated by the owner on funding day, is:

> withdraw whatever leaves **$190** in the futures account at the end of the week.

Under that rule the base is **RESTORED every week** and the week's P&L lands on
the deposit, not on the base. A -15.3% week at $1,087 ends at $920, of which
$730 is withdrawn and $190 stays — the owner absorbs $170 of the money they
added, and the base account is untouched. It never reads $5. The $5 figure
required a withdrawal that was never going to happen.

Funding-day base: **$186.57** futures-account equity (2026-09-04 11:0x UTC;
available $168.31 + $19.27 margin on the open XRP, less $0.99 unrealised).

| deposit | equity | 1R | median | P10 | P90 | live record | worst of 228 | base after |
|---|---|---|---|---|---|---|---|---|
| $300 | $486.57 | $11.73 | +$10 | -$39 | +$86 | -$32 | -$74 | **$190** |
| $500 | $686.57 | $16.55 | +$14 | -$55 | +$122 | -$45 | -$105 | **$190** |
| $900 | $1,086.57 | $26.19 | +$22 | -$86 | +$193 | -$71 | -$166 | **$190** |

The base column only breaks if equity falls below $190 in a week — an 83% loss,
against a worst-of-228 of 15.3%. **Net cash to the owner is the week's P&L less
$3.43**, the small top-up from $186.57 to the $190 the base is restored to.

SIZING DENOMINATOR, worth knowing on day one: entries size off AVAILABLE
balance, not equity (`equity_at_entry` is stamped from `available_balance`,
runtime.py:1802). With XRP holding $19.27 of margin, the first post-deposit
entry sizes off ~$1,068 rather than ~$1,087 — 1.8% smaller, and it self-corrects
as positions close.

**Ruling: SUPERSEDED.** The $300 ruling rested entirely on protecting a base
account that this policy protects by construction. What survives as an argument
for restraint is different and weaker: the edge is not established (live record
-$71/week at $1,077 against a replay median of +$22, ~1.7 SE apart, so the
expectation may be negative), capacity at 6.3x notional is unmeasured, and
WILDCARD ran -$5.73 over 19 closes in trial 18 while TREND made +$15.81 over 6.

Framed honestly: on the live record, a $900 week costs about $70 in expectation
and buys a week of execution-cost data at 6.3x notional. That is a purchase, and
a defensible one — but it should be made deliberately, not inherited from a table
whose central column was answering a different question.

## What a funded week is expected to do

| source | 7-day P&L at $1,069 | at $469 |
|---|---|---|
| replay, median | +$22 | +$10 |
| replay, P10 / P90 | -$85 / +$190 | -$37 / +$83 |
| live record (-0.16R x 17 fills) | -$70 | -$31 |

The replay and the live record sit ~1.7 standard errors apart: suggestive that
the replay overstates, short of proof. 57% of 7-day windows contain a top-5%
trade and have a median of +$71.71; the 43% that do not have a median of
**-$18.80**. A single funded week is mostly a bet on whether one tail winner
lands in it.

## Operational preconditions

1. ~~**Drawdown brake ON before the deposit.**~~ **REFUTED 2026-09-04 by replay,
   before funding. Do NOT set `FUTURES_CONVEX_DRAWDOWN_BRAKE=1`.**

   This precondition was written 2026-08-29 without a replay. `tools/
   pit_drawdown_brake.py` replays the brake through trials 17+18 (32 convex
   entries), and three independent reconstructions (replay anchors, the bot's
   own `_build_equity_curve`, and a pass using the bot's live equity snapshots
   from the logs) agree:

   - THROTTLE (x0.5) would have fired on **18 of 32 entries**; 29-31 of 32 once
     its own halving feeds back, because halved winners keep equity under the
     line. HALT never (max 30d dd 14.6%).
   - It would have turned the window's **+$16.22 into -$0.24 to +$5.32** — a
     cost of $10.90 (truncation applied) to $16.46 (bot's own anchors, which
     also halve the +$9.50 ZEC winner of 09-03 15:17). Most or all of the profit.
   - **Expectation is NEGATIVE on this account.** Over 08-05 -> 09-04 (71
     convex entries, 20 gated), trades entered while >=8% under the 30-day peak
     averaged **+$0.90 (60% wins) against +$0.51 (49%)** when NORMAL — being in
     drawdown forecast BETTER trades, not worse. Bootstrap over 121 closes:
     P(brake helps) = 15%. Every throttled stretch in the anchored history was
     net-positive.
   - The 08-22 peak ($182.59) is what the account has sat 2-14% below for a
     month. A point check reading 0.5% dd on 09-04 was true only because equity
     was $0.36 off that peak at the instant.

   **Post-deposit it is worse, not safer.** The curve is flow-invariant, so a
   $900 deposit lifts every historical point and RESETS the brake to ~0% dd.
   But 8% of ~$1,083 is ~$86 — and a P10 week at the new size is -$86. **A
   single ordinary bad week lands on the throttle line.** With open positions'
   unrealised P&L moving the live tip $8-9/hour, it is a coin flip whether the
   funded week's first red day halves every subsequent entry.

   The "shrink dials pay" finding (streak throttle, regime scaler) does not
   transfer: those key on loss STREAKS; this keys on equity LEVEL against a
   trailing peak, and it landed on winning stretches. Rejected on measurement,
   filed with the other rejections. `USE_DRAWDOWN_KILL=1` stays set — it is inert
   on the convex path without the flag and harmless. Live thresholds are `DRAWDOWN_HALT_PCT=0.25`
   and `DRAWDOWN_SOFT_PCT` defaulting to 0.08, both over 30 days. Note the halt
   at 25% sits ABOVE the worst observed week (15.3%), so the halt is a backstop
   for something never yet seen; the 8% soft brake is what will actually
   modulate size.
2. **Withdraw only when FLAT.** Margin on open positions cannot be withdrawn. If
   the bot holds positions on day 7, either wait for them to resolve or accept
   that the calendar, not the strategy, is choosing the exit price.
3. **The deposit does not distort drawdown.** `_build_equity_curve` reconstructs
   from closed-trade P&L anchored to exchange equity, so external cash flows do
   not register as gains or losses. Verified 2026-08-29.
4. **A deposit is a sizing change and therefore RESETS the trial.** Bump
   `FUTURES_TRIAL_START_TS` and `FUTURES_TRIAL_LABEL` on funding day, or trial
   18's sizing statistics will mix two equity regimes.

## Opening checklist (all vars, then redeploy)

```
railway variables --service Futures-bot \
  --set "FUTURES_REGIME_FLOOR_MULT=0.50" \
  --set "FUTURES_CONVEX_TRAIL_RETAIN_FRAC=0.50" \
  --set "FUTURES_TRIAL_START_TS=$(date +%s)" \
  --set "FUTURES_TRIAL_LABEL=18"
railway redeploy --service Futures-bot --yes
```

Missing the label is not hypothetical: it happened opening trial 17, and
`_trial_label_drift()` now warns in /status when the window moves and the label
does not.

---

# Pre-registered decision rule — CONVEX TRIAL 17 (from 2026-08-27)

## Trial 16 CLOSED 2026-08-27: VOID by its own sizing check.

14 closes | net -$0.80 | netR -5.22 | win 3/14 | ex-best -$18.75 (TUT_USDT
LONG +$17.94 paid for nearly the whole tape). But the trial is not scored on
that: its pre-registration says realised mean risk per trade must land near
1.87% or "the renormalisation is not doing what it claims and the trial is
void regardless of P&L". Realised: **1.141%** at n=14 — below the 1.392%
measured BEFORE the trial opened, i.e. the change moved the number the wrong
way. Cause (08-25 audit): the renormalisation compensated for the regime
scaler alone, while the cold-streak throttle — which fires on losing runs, by
construction the same periods the scaler is cutting — fired on 4 of the first
11 entries and cancelled it. Because netR is scale-invariant, no P&L criterion
could ever have caught this; the sizing check was the only instrument, and it
worked. Sizing is R-neutral, so trial 16's R record remains valid evidence.
Owner closed it 2026-08-27 ("I saw enough").

## TRIAL 17: THE COLD-STREAK THROTTLE, OFF.

`FUTURES_CONVEX_STREAK_THROTTLE_ENABLED=0` (env only, no deploy; rollback is
setting it back to 1). Everything else carries over from trial 16 unchanged:
`FUTURES_WILDCARD_RISK_PCT=0.0241`, scaler shape 0.20/0.45/0.25, trail
ratchet 3.0/0.75, TREND ETH/XRP/ZEC 2 slots long-only, WILDCARD 3 slots both
sides, turnover floor $2M, scan cap 90, squeeze off.

### Why the throttle and not something else

Three independent lines, all pointing the same way:

1. **Operational (the audit):** it is the identified confounder that voided
   trial 16. Until it is out of the loop, the sizing design cannot even be
   MEASURED — every other question queues behind this one.
2. **Mechanism (`tools/pit_tut_class.py`, n=888 point-in-time candidates):**
   a losing streak predicts nothing. Next-trade mean after 0/1/2/3/4+
   consecutive losses: +0.137/+0.110/+0.066/-0.171/+0.123R; P(win) flat at
   50-57% throughout; P(TUT-class) after 4+ losses is 21.4%, the HIGHEST
   cell in the table. The throttle sizes down on an information-free signal
   — and the trades it shrinks are drawn from the same distribution as TUT.
3. **Direct A/B (`tools/streak_throttle_ab.py`, 2026-08-22):** FLAT beats
   THROTTLED +$17.93 over 190d, 17/27 weekly windows, t=0.92. Recorded then
   as "directionally remove it, but not at a significance worth acting on
   mid-trial" — the correct call at the time. This trial is the act.

t=0.92 alone would not clear the bar this repo holds; the reason to move is
(1), with (2) and (3) as agreeing sign from two independent methods. If the
throttle really does protect against loss-clustering, the pass criteria below
will show it: that is what a trial is for.

### Boundary annotation (written at open)

`ETH_USDT` TREND LONG opened 2026-08-27 09:29 UTC — three minutes BEFORE the
trial-17 start ts (09:32) — at 0.25x size, throttled by the very mechanism
this trial removes (`[STREAK_THROTTLE] TREND losing streak=5 -> size x0.25`,
margin 25.63 -> 6.41). Its close will land inside the trial window.
**Excluded from the trial-17 tally and from the sizing check** — it is a
trial-16-conditions trade and would contaminate the realised-risk mean in
exactly the direction the trial exists to measure.

### Pass criteria (30 convex closes)

- **PRIMARY — the check trial 16 failed:** realised mean risk per trade in
  [1.6%, 2.2%] of equity-at-entry. This is now the headline criterion; P&L
  criteria are secondary because sizing cannot move R.
- netR > 0 AND netR ex-best > 0 (unchanged from trials 15/16).

### Kill conditions

- Realised mean risk still < 1.5% at n=10 → a THIRD shrinker exists; halt
  the trial and audit the sizing path end to end before anything else.
- Any single entry risking > 3.0% of equity → the throttle was also a brake;
  verify nothing depended on it, restore `=1`, close the trial.
- Max drawdown of the trial book exceeding 20% of equity at any point →
  restore `=1` (the A/B says the throttle costs money on average; this bounds
  the tail scenario where it was earning it).
- Rollback is one env var. No deploy in either direction.

**THE RESET COUNT IS NOW 13** (trials 5..17 in ~3.5 months, zero scored
verdicts). Mitigation, unchanged from trial 16's note: this reset is void-and-
rerun of the SAME question, not a new question; trial 16's R record stays.

---

# Pre-registered decision rule — CONVEX TRIAL 15 (from 2026-08-20)

## Trial 14 closed at 3 closes: netR -1.01, net $-1.75.

LAB -0.63R (24h clock), GPS -0.99R (clean stop), ACE +0.61R (retention trail
from a +2.12R peak). Nothing about the deflator fix was disproved; the sample
was simply too small to say anything, which is the ninth time in a row.

## Trial 15: the BIG-3 TREND sleeve — a STRUCTURAL gap, not a parameter

On 2026-08-19 the US Treasury doubled long-dated bond buybacks and the SEC
proposed a crypto framework. ETH ran **+17.4%/24h**, SOL +11.7%, BTC +8.3%,
amplified by $1.11B of short liquidations on BTC alone. The bot could not touch
any of it, and three independent blocks explain why:

| block | evidence |
|---|---|
| wildcard excludes majors AND hunts a 3h impulse | BTC peak 3h **+6.00%**, SOL **+6.16%** — under its 8% floor |
| ...and ETH DID clear that floor | peak 3h **+9.45%** @ 21:15, then killed by `no_pullback_resume` **x7** |
| squeeze needs a coil to RELEASE | 72h replay: **0 signals** on all three; 285/247/230 bars `no_active_coil` |
| PMT was the only majors sleeve | decommissioned 2026-07-13 |

This is additive capacity — the class of change that has historically worked
here — not a trigger tweak, the class that is 5-for-5 rejected.

### The rule

LONG or SHORT on BTC/ETH/SOL when the **24h return clears 4%** and the bar sets
a **new 24h CLOSING extreme** in that direction. Wildcard sizing (3xATR stop,
20%-of-margin cap re-deriving leverage to x5-x10 on a major), convex exits with
**TP 3R** — not 5R — and its **own slot**.

Deliberately absent: no pullback-resume, no majors exclusion, no coil test.

### Evidence, and its limits

63d x 29 majors, 8 disjoint windows, funding charged, 2-slot cap, point-in-time
turnover floor. Against a RANDOM-ENTRY control on the same universe, sizing and
exits — which itself bled **-$0.389/trade** — every one of **27 parameter cells**
came out ahead by **$50-105 per 120 trades**.

Replayed on the actual 2026-08-19 event: 7 entries, **+$22.74** realised, two
still open; upper bound at a perfect exit was +$44.23.

**What that does NOT establish.** No cell exceeded **5/8** positive windows, and
the surface is non-monotonic (at look=12h the threshold sweep runs +21.28 /
-17.76 / +8.26). The 72h replay is a hand-picked outlier window — the same rule
made +$57.55 over the whole 56 days, so that one event is ~40% of two months'
expected return. This is a LEAN. It goes live as a real-money observation test,
exactly as the wildcard did.

**The short arm is live on operator instruction, not on evidence.** The 90-day
drift-controlled study put the entire measured edge in the LONGS (+0.244R vs
-0.225R) and the probe behind this sleeve was long-only.
`FUTURES_TREND_LONG_ONLY=1` disables shorts without a deploy.

### Pass criteria

| | |
|---|---|
| closes | 30 convex (WILDCARD + TREND) |
| pass | net R > 0 AND net R ex-best > 0 |
| flag | equity drawdown from peak > 20% |

### Kill conditions

- Any single TREND loss worse than **-1.5R** -> the 20% margin cap is not
  binding as designed; investigate before the next entry.
- TREND net R < -3.0 over its first 10 closes -> propose `FUTURES_TREND_ENABLED=0`.
- Short arm net R < -2.0 over its first 5 short closes -> propose
  `FUTURES_TREND_LONG_ONLY=1`, keeping the long arm.
- `FUTURES_TREND_ENABLED=0` disables the whole sleeve, env-only, no deploy.

### Amendment, 2026-08-20 (same day): 3 slots, LONG ONLY

Operator asked whether 1 slot was too restrictive. Measured on the big 3 with
the shipped detector, live exits, funding, 63d x 8 windows:

| arm | 1 slot | 2 slots | 3 slots | win% |
|---|---|---|---|---|
| LONG only | +$6.45 | +$14.31 | **+$16.12** | 53% |
| SHORT only | -$14.05 | -$24.78 | -$33.64 | 24% and falling |
| both (as shipped) | -$7.60 | -$10.47 | -$17.51 | 43% |

Two findings, and they are coupled:

1. **More slots help — but only the arm that works.** Long-only return more than
   doubles 1 -> 3 while max drawdown rises 13% (-15.62 -> -17.64); the third slot
   LOWERS drawdown against the second. Return/DD 0.41 -> 0.79 -> 0.91. BTC/ETH
   correlate at **r=+0.914**, so the expectation was that three concurrent longs
   are one 3x bet — but each name sets its own new 24h closing extreme at a
   different moment, so the holdings only partly overlap.
2. **The short arm loses and slots amplify it.** Shipping 3 slots with shorts on
   would have produced the worst cell in the table.

Drift-controlled: over the span BTC +14.3%, ETH +34.0%, SOL +25.2%, yet a RANDOM
long entry with the same sizing and exits lost **-$73.10 over 595 fills**
(-$0.12/trade, -$3.69 scaled to 30 trades). The long arm at 3 slots is ~+$20
ahead of random, so it is not beta.

Live config becomes `FUTURES_TREND_MAX_POSITIONS=3`, `FUTURES_TREND_LONG_ONLY=1`.
Short signals are still DETECTED and shadow-logged, so the live short question
stays answerable. `FUTURES_TREND_LONG_ONLY=0` restores them, env-only.

Concurrent exposure at the new cap: 3 trend + 2 wildcard = 5 slots, ~$82 margin
(59% of equity) and ~$13.00 of risk at stops (**9.4% of equity**) if all five are
open and all five stop out together. The wildcard's 20% SL cap and the 2-slot
wildcard limit are unchanged.

## What this trial does NOT change

Wildcard (2 slots, small-cap band, 3h impulse), squeeze (off), PMT (off), the
20% SL cap, the cold-streak throttle, and every existing veto. The trend sleeve
runs in its OWN slot, so total concurrent exposure goes from 2 to 3.

---

# Pre-registered decision rule — CONVEX TRIAL 14 (from 2026-08-14)

## TURNOVER-DEFLATOR WINDOW MISMATCH — a defect, not a parameter

`_major_symbols` ranks on `amount24`, a **rolling trailing-24h** turnover figure
that fully contains an in-progress move. It multiplies that by
`_turnover_deflator`, whose job is to stop a small cap being called a major just
because it is spiking. The deflator was computed from `Day1` klines **with the
still-forming bar dropped**, so its denominator was the last COMPLETE calendar
day — a window that by construction cannot see today.

Rank on a window containing the move; correct with one that excludes it. The
deflator could only detect a spike a full day after it finished, by which point
the opportunity is gone.

### Measured cost, 2026-08-14

Top-10 movers on MEXC futures that day. Eight of ten never reached the detector:
two excluded as "majors", six under the $3M turnover floor.

| symbol | 24h | raw turnover | old deflator | outcome |
|---|---|---|---|---|
| ACE_USDT | **+150.5%** | $51M | **1.000** | excluded as major; replays **+4.98R** |
| BEAT_USDT | -32.1% | $31M | 1.000 | excluded as major |
| TUT_USDT | -28.1% | $16M | 1.000 | excluded as major |

ACE was the single largest mover on the exchange and the deflator applied **no
correction at all**. At 1R = $2.66 that is **$13.25** on one trade.

### The fix

`Min60` bars over 9 days. `last` = sum of the trailing 24 hourly bars — the SAME
window `amount24` measures. `prior` = the seven non-overlapping 24h windows
before it. `ratio = min(1.0, median(prior) / last)`.

Units still cancel (both sides are `close x volume` from the symbol's own bars),
so the multiplier stays cross-comparable. The one-sided clamp is unchanged and
still load-bearing — an unclamped ratio ranked SOXL (deflator 16.98) above every
crypto major.

### Verified before deploy

- 865 tests pass, including three new regression tests: an in-progress 10x spike
  must deflate (0.100), a steadily liquid symbol must be untouched (1.000), and a
  spike that has already passed must NOT demote (1.000).
- Live: ACE deflator **1.000 -> 0.050**, deflated $51M -> $2.8M, **now in pool**;
  its signal fires and resolves +4.98R.
- BTC/ETH/SOL/XRP/DOGE/BNB all still excluded.
- Band churn is 2 symbols: ACE and CAP become tradeable, ENA and FILECOIN become
  majors. Both newcomers to the band are genuinely steady high-turnover markets.

### Kill conditions

- Any symbol with >$100M steady turnover entering the tradeable pool -> the
  deflator is promoting, not demoting; revert.
- `FUTURES_WILDCARD_TURNOVER_BASELINE=0` restores raw-turnover ranking, no deploy.
- Deflators reading 1.000 across the whole shortlist -> the Min60 call is failing
  and the code has failed OPEN back into the old bug. Watch for this specifically.

## What this trial does NOT change

Exits are untouched. The near-target family (lock, dwell, arm/floor grid,
scale-out, time-conditioned scale-out) was measured roughly fifteen ways on
2026-08-14 and **every corrected estimate sits between -0.13R and +0.13R per
event**, with the only |t| > 2 cells negative. The reason is structural: trades
that touch 87% of target complete **74.4%** of the time against a **74.7%**
break-even, so the market prices it fairly at every level. A simulator
fill-ordering defect (scale-out evaluated after the TP break, against the prior
bar's peak) had manufactured an apparent +0.207R; corrected, it is +0.015R
(t=+0.17). Do not re-litigate without new data.

## OPEN, carried forward

- **The pullback gate does not select.** Clean ablation, 90 days, separately
  deduped: gate ON longs +0.189R (n=568, t_day +2.29); gate OFF longs +0.193R
  (n=941, t_day +2.72); the signals it rejects score +0.256R (n=646) — a
  difference of t=0.74, i.e. no selection at all. It discards 40% of the
  candidate pool for no measurable quality gain. Removing it is worth ~$0.60/mo
  at current capacity, so the value is not in removing it but in whether a
  larger pool can be RANKED. Unstudied.
- **`pinned90.pkl` had a dedup defect** — one 2h window shared across all
  candidates, so the 17k rejected sub-8%-ROC signals hid passing ones. Any
  number sourced from it (including the long/short asymmetry) is a biased
  subsample. Clean sampling gives shorts -0.043R (t=-0.79), i.e. roughly FLAT,
  not the -0.225R previously recorded.
- Survivorship: the replay pool is selected on CURRENT turnover, and five
  symbols carry 76% of the long-side effect. Unresolved.

---

# Pre-registered decision rule — CONVEX TRIAL 13 (from 2026-08-12)

## Trial 12 closed at 0 closes, ~1h. Same as trial 11: it tested nothing.

## Trial 13: the risk cap is bound to EQUITY, not to a score-scaled term

`FUTURES_WILDCARD_MAX_MARGIN_PCT=0.25` replaces
`FUTURES_WILDCARD_RISK_MARGIN_CAP_MULT=1.5`.

**The defect.** `_entry_margin` capped margin at `legacy x 1.5`, where
`legacy = balance_fraction x available`. The comment above it calibrated that
cap assuming `balance_fraction ~= 0.12` and roughly constant. It is
score-scaled and varies at least 3x live — 0.0235 on INX_USDT against >=0.067
on ALLO_USDT — so a cap expressed as a multiple of `legacy` bound hard on
low-score signals and not at all on high-score ones. **INX_USDT opened risking
0.53% of equity against a 1.87% target: 28% of intended size**, and nothing
recorded that it had happened. The risk dial silently reverted to legacy sizing
for exactly the trades furthest from its target.

**The fix.** The cap's stated purpose was to bound the tail where a very tight
stop demands a large margin and a gap through it loses more than the modelled
1R. That is a DEPLOYMENT bound, so it now bounds deployment: margin may not
exceed 25% of the account. Equity is not score-scaled, so the cap means the
same thing on every signal.

It binds only when `sl_margin_pct < risk_pct*100/max_pct ~ 7.5%`. The live
range is 15-20%, so **on ordinary trades it does not bind at all** — which is
the point. Two slots can therefore deploy at most 50% of the account.

Verified: identical stop + identical account now produce identical size
whatever the score; INX would have received ~$17.35 of margin rather than
$4.91, risking 1.87% rather than 0.53%.

Rollback: `FUTURES_WILDCARD_MAX_MARGIN_PCT=10` (never binds), or
`FUTURES_WILDCARD_RISK_TARGETED=0` for legacy sizing entirely.

## On the reset count, honestly

This is the **9th reset in ~13 days**. It follows the 2026-07-31 standard,
which lists sizing as a treatment change, and the rule was followed rather than
argued around — partly because trials 11 and 12 had produced ZERO closes
between them, so the reset cost nothing and an exception would have been free
only in appearance.

But the count has stopped being informative. Two better numbers:

| metric | value |
|---|---|
| trials that reached a scored readout | **0** |
| longest uninterrupted run | **~47h** (trial 7) |
| live wildcard closes, all time | **22** (netR +14.64, $+9.19, 45% win) |

The 22 closes are the real accumulating record and they are unaffected by
resets, because the trial boundary changes what is being tested, not what has
been traded. **The scoreboard that matters is the 22-trade live record, not the
trial counter.**

Carried into trial 13 and still untested: preemption (0 evictions since
2026-08-11), shorts (n=8 live, contradicted by a 14-day replay), the
calm-shock filter (0 refusals since shipping ~1h ago).

---

# Pre-registered decision rule — CONVEX TRIAL 12 (from 2026-08-12)

## Trial 11 closed at 1 close, ~24h. Preemption tested NOTHING.

One wildcard close (ALLO_USDT SHORT, -1.05R / -$2.80, a clean stop) and one
position still open (INX_USDT SHORT). **Zero evictions** — there was never a
second signal competing for a slot, so the change trial 11 existed to test got
no opportunity to act. It carries into trial 12 untouched and still untested.

## Trial 12: CALM-SHOCK EXCLUSION

`FUTURES_WILDCARD_MAX_CALM_RATIO=0.75` (new). A signal is refused when

    calm_ratio = |3h move| / (range of the PRIOR 21h)  >=  0.75

i.e. when the three-hour move is most of, or bigger than, the whole preceding
day. The baseline window deliberately EXCLUDES the move itself, or a large drop
inflates its own denominator and every shock scores as ordinary.

### Where this came from

Owner observation on the ALLO_USDT loss: *"if a pair is stable for a long
period and suddenly drops, it is very likely to bounce back. The dip was way
too sudden for it to be a good trade."* ALLO scores **1.36** — a 9.75% drop out
of a ~7% day. It is not a fitted parameter; it is a stated mechanism that was
then measured.

### The measurement (47 symbols, 14 days, 58 signals)

| | n | netR | mean R | t_day | ex-top3 | win |
|---|---|---|---|---|---|---|
| calm < 0.75 (keep) | 50 | +36.03 | +0.721 | **+2.02** | **+21.07** | 64% |
| calm >= 0.75 (refuse) | 8 | -3.52 | -0.440 | -2.15 | -5.10 | 38% |

The refused tail is negative on every measure. Keeping only the rest lifts the
book from +32.51R to +36.03R and day-clustered t from +1.74 to +2.02.

**It is a TAIL exclusion, not a ranking variable.** Quintiles are NOT monotonic
(Q1 +0.328, Q2 +0.998, Q3 +0.266, Q4 +1.292, Q5 +0.056) — only the extreme is
reliably bad. Do not read calm_ratio as a quality score.

### What was tested and REJECTED on the way here

The owner's follow-up — *could an ALLO-type move be a LONG instead?* — was
tested as its own scan (own detector, no continuation filters, 4 variants,
14 days):

| variant | n | netR | mean R | ex-top3 |
|---|---|---|---|---|
| long the shock, 5R target, calm >= 0.4 | 64 | -3.27 | -0.051 | -16.35 |
| ...calm >= 1.0 | 16 | -0.06 | -0.004 | -3.33 |
| ...+ wait for first up-bar, calm >= 1.0 | 14 | +1.85 | +0.132 | -1.75 |
| reversion target instead of 5R | 24 | -1.87 | -0.078 | -4.28 |
| **CONTROL: any 8% drop, no calm filter** | **214** | **+17.81** | **+0.083** | **+2.84** |

Buying ANY 8% drop is mildly positive; adding the calm filter makes it WORSE.
The filter is anti-predictive on the long side. Combined with the short side
being negative in that tail (-0.440R), the conclusion is that a shock out of
calm is **noise, not a reversal**: no edge in either direction. Hence exclusion
rather than inversion.

### Design: filtered AFTER the candidate list, never inside the detector

Same rule as long-only, for the same reason: `_shadow_log_untaken` only fires
on objects that reached the candidate list, so rejecting inside
`detect_wildcard_signal` would produce zero shadow rows and destroy the
question permanently. Refused signals are logged as `calm_shock(1.36)` and
resolved counterfactually, so the filter keeps being scored after it ships.
`calm_ratio` is stamped on every signal regardless.

Verified live before deploy: ALLO_USDT scores **1.36 -> REFUSED**; INX_USDT
(open, and superficially identical on RSI 14.9 / lateness 1.00) scores
**0.10 -> KEPT**. Across the current 23-symbol pool, 0 of 20 would be refused
right now — this is a rare filter, not a throttle.

### Kill conditions

- Refused population (`calm_shock` rows) resolving NET POSITIVE at n >= 15 ->
  remove the filter; it is costing money.
- Fewer than 2 wildcard entries per week attributable to this filter blocking
  them -> the filter is not the constraint and should not be credited.
- Rollback: `FUTURES_WILDCARD_MAX_CALM_RATIO=0`, no deploy.

**Unchanged:** preemption, 24h clock, 450s cadence, both sides, majors band 24,
range pre-filter, $3M floor, retention trail, 2 slots.

## Standing caveats, restated because they keep applying

- One 14-day window, a survivorship-selected pool, counterfactual fills. Only
  DIFFERENCES between arms sharing the same bars are trusted; LEVELS are
  inflated ceilings.
- **n=8 in the refused tail.** This is thin. It ships because the mechanism was
  stated in advance and the tail is negative on every measure, not because the
  sample is adequate.
- Trial 12 now carries preemption (untested), shorts (n=8 live, contradicted by
  a 14-day replay showing the short side negative) and this filter. The queue
  of untested changes is itself becoming the risk.

## OPEN, pre-registered for the next boundary

**The risk-dial cap binds silently.** `_entry_margin` caps margin at
`legacy x 1.5` where `legacy = balance_fraction x available`, calibrated
assuming balance_fraction ~= 0.12 and constant. It is score-scaled and varies
3x live (0.0235 on INX vs >=0.067 on ALLO), so INX opened risking **0.53% of
equity against a 1.87% target — 28% of intended size.** Telemetry to measure it
shipped 2026-08-12 (`risk_cap_bound`, `margin_wanted`, `risk_pct_actual`); the
fix — bound RISK directly rather than as a multiple of a score-scaled term — is
a sizing change and waits for a boundary.

---

# Pre-registered decision rule — CONVEX TRIAL 11 (from 2026-08-11)

## Trial 10 closed at 0 closes, ~24h. Shorts worked; one gate ate everything.

Candidate arrival DOUBLED as predicted (4 in 20.6h vs 2 in 23h) and three of
the four were shorts — the change did exactly what it was meant to. All four
died on `veto:ref_not_listed`, whose record is now 11 vetoes, 9 resolved,
**8 of 9 negative, -5.75R**. The gate is not the problem; it is correct.

## Trial 11: SLOT PREEMPTION

`FUTURES_WILDCARD_PREEMPT_ENABLED=1` (new). When a candidate clears its veto
and both slots are full, the bot may close an open wildcard position **that has
already failed** and give the slot to the new signal.

### Why this and not the clock

The convex clock recycles slots INDISCRIMINATELY — at 6h it evicts winners
alongside duds. Preemption chooses. Measured over 8 days / 60 signals / 16
symbols, replayed under the live exit policy net of cost:

| rule | n | netR | mean R | t_day | ex-top3 | $/mo |
|---|---|---|---|---|---|---|
| no preemption (live) | 31 | +10.54 | +0.340 | +1.02 | **-4.41** | +105 |
| 6h clock | 44 | +12.73 | +0.289 | +1.54 | +2.57 | +127 |
| **preempt < +0.3R** | **48** | **+24.40** | **+0.508** | **+2.00** | **+9.44** | **+243** |
| both together | 55 | +12.25 | +0.223 | +1.42 | +2.09 | +122 |

More trades AND better trades — unusual, and the tell that it is not the same
trade-off: the clock buys throughput by cutting winners, preemption by cutting
only what has already failed. **They are substitutes: stacking them is worse
than either alone.** The clock stays at 24h.

First configuration in this programme to reach day-clustered t 2.00 with a
positive top-3 haircut. The live arm's own replay is NEGATIVE after the
haircut (-4.41R), i.e. its entire edge is three trades.

Threshold is a plateau, not a point: +0.3R gives $243, +1.0R gives $250, +0.0R
weakens (ex-top3 -0.71). Chosen 0.3.

### One guard was measured, not assumed

A 60-minute minimum age felt prudent and **halved the effect** — t_day
+2.00 -> +1.03, ex-top3 +9.44 -> -1.37, evictions 16 -> 9. It blocks precisely
the valuable ones: a position below +0.3R inside the first hour has already
failed. Swept: 0 and 15 min are indistinguishable, 30+ degrades monotonically.
**Set to 15 min (one bar)** — anti-churn for free.

### Defects found by adversarial review BEFORE deploy (13 confirmed, 5 critical)

| defect | consequence |
|---|---|
| `sl_price == 0` made `one_r = entry` | a +25% winner computed as +0.248R and was eligible for eviction. Reachable: `/reconcile` adopts orphans with no stop. Now returns None — unknowable R is never evictable |
| eviction happened BEFORE the veto | a vetoed or unfillable candidate left the book one real position poorer with nothing opened. Moved INSIDE the candidate loop, after the veto |
| a failed close left a stopless position | `_close_position_for_exit` cancels the exchange TP/SL first; if the close raised, the scan swallowed it as one WARNING. Now re-arms the stop and sends a Telegram alert |
| replacement sized off a stale balance | freed margin was not in the snapshot, undersizing the replacement ~10-15% — exactly the trade the eviction paid for. Re-read after the close |
| budget charged at SELECTION | a transient price-fetch failure burned an eviction with nothing closed. Charged only on a successful close |
| budget was memory-only | a redeploy reset it; a crash-loop granted unlimited evictions. Now persisted in the state file |

Unpaired evictions log `EVICTED_UNFILLED` so the case the replay cannot model
is measurable rather than silent.

### Kill conditions

- Any eviction followed by no fill more than **3 times in 24h** -> disable.
- Overall netR below the pre-preemption baseline at **n >= 20** -> disable.
- Rollback: `FUTURES_WILDCARD_PREEMPT_ENABLED=0`, no deploy.

**Unchanged:** 24h clock, 450s cadence, both sides, majors band 24, range
pre-filter, $3M floor, retention trail, 2 slots.

## Also measured this session, and NOT changed

- **Turnover floor.** Swept 3.00 / 2.75 / 2.50 / 2.25M. $2.75M is a no-op (the
  extra signals never get a slot; identical 31 trades). $2.50M and below
  COLLAPSE the result (+10.54R -> +2.12R) — not because the added trades lose
  (they are ~breakeven) but because they **displace** better ones under a
  binding slot cap. Independent confirmation that slots, not universe, bind.
- **Dynamic/volatility-scaled clock.** Tuned to land where a fixed 6h clock
  already sits it performs the same; anywhere else it is worse. Adds a fitted
  parameter for no measurable gain.
- **The 'crypto only' filter** (290 pairs). All genuinely non-crypto; only 3
  clear turnover AND range, all marginal; the largest member (XAU) produced
  trial 4's worst trade at -3.79R in 60 seconds.

### Standing caveat on all of the above

One 8-day window, a survivorship-selected pool, counterfactual fills. LEVELS
are inflated ceilings; only DIFFERENCES between arms sharing the same universe
and bars are trusted. Two simulation errors were made and caught in this same
harness today — both inflated the result before correction.

---

# Pre-registered decision rule — CONVEX TRIAL 10 (from 2026-08-10)

## Trial 9 closed at 0 closes after 1.5h. It tested nothing.

Opened 17:12 UTC, superseded 18:4x the same day by an owner decision to
re-enable shorts. No candidate fired in between. The 450s cadence carries into
trial 10 untouched and untested; nothing is lost because nothing was measured.

## Trial 10: shorts re-enabled

**`FUTURES_WILDCARD_LONG_ONLY` 1 -> 0.** Shorts have been DETECTED and
shadow-logged as `side_disabled` since trial 6; they are now taken.

### This is ahead of the pre-registered bar, and that is recorded

Trial 6 set the bar at **n >= 20 resolved short shadow rows**. There are **4**.
Enabling now is a decision made against this document's own standard, and the
2026-08-02 external-gate episode is the cautionary precedent: a gate was
relaxed on 4 rows and reverted the same day, leaving the standing rule that
*"a pre-registered threshold is not satisfied by recomputing evidence the same
document already inspected and rejected."*

What makes this different from that episode — stated so it can be judged later,
not to excuse it:

1. **The original rationale was measured against an exit policy that no longer
   exists.** Long-only shipped because "a short's payoff is bounded at
   `1/sl_frac`, so the convex +5R design is structurally a LONG-side design",
   with a target ladder monotone UP in k for longs (+0.021 -> +0.250) and DOWN
   for shorts (+0.077 -> +0.020). That ladder is a hold-to-target measurement.
   Since trial 7 the bot runs a 0.30xpeak retention trail with ~7% TP
   completion — the target multiple barely governs the outcome any more.
2. **Re-scoring the shorts under the LIVE exit policy improved them**, from
   +0.78R to **+2.23R over 4**. The re-resolution was a measurement fix applied
   to every sleeve, not a search for a favourable reading.
3. **This is being taken as a CAPACITY change, not an edge claim** — the same
   framing used for the 24h clock and the runner trail. Shorts accrue ~3.8x
   faster than the book; the binding constraint on this programme is entries,
   not exit tuning.

### The asymmetry that remains, unfixed and deliberate

A short's target is clamped at 50% price distance (`short_tp_clamped`), because
21% of short signals otherwise had a target at or through **price zero**. So a
short's ceiling is `0.50 / sl_frac` — **2.5R at the widest live stop** — against
the long's 5R, for the same -1R risk. The clamp is NOT being loosened to make
the sides look symmetric; the unreachable-target defect it fixes is real.

Consequence: the short arm is a lower-ceiling bet by construction. It is
scored **separately from the first close**, on `/status` and in the digest, so
neither arm can hide inside the other's number.

### Kill conditions, pre-registered now

- Short arm at **n >= 10** with netR below the long arm's netR per trade by
  more than 1.0R -> revert to long-only. Rollback:
  `FUTURES_WILDCARD_LONG_ONLY=1`, no deploy.
- Any short close worse than **-1.5R** (gap through the stop) -> investigate
  before the next short is taken. Small caps gap harder against shorts than
  longs, and the exchange stop is the only hard protection.

**Unchanged, carried from trials 8/9:** 450s scan cadence, baseline-turnover
majors band (24), lossless 24h-range pre-filter, strict category filter,
retention trail, 24h clock, 2 slots, risk dial, 3.0xATR stop capped at 20%.

## Scoring

30 WILDCARD closes or 90 days. Both arms count toward the 30; each is also
reported alone. All robustness bars carry over verbatim.

**Reset count: 6 in 11 days**, zero scored verdicts. Trials 9 and 10 each cost
under two hours of live time, so the measured loss is nil — but the pattern is
the programme's largest risk and it is now the seventh consecutive trial that
has not reached a readout. **A trial that never runs long enough to score
cannot be wrong, and cannot be right either.**

---

# Pre-registered decision rule — CONVEX TRIAL 9 (from 2026-08-10)

## Trial 8 CLOSED at 0 wildcard closes in ~23h. The zero IS the finding.

Not a performance verdict — there was no performance. The sleeve scanned
cleanly every 15 minutes for a day (19-22 symbols per pass, `candidates=0` on
every one) and opened nothing. The universe changes worked: the pool roughly
doubled (8-11 symbols -> 19-22) and TUT_USDT became tradeable. Arrival was not
the whole problem.

## What trial 8 uncovered: the scan grid samples a transient condition

The 2026-08-10 missed-opportunity report listed **seven symbols where a LONG
signal existed and no position was opened**, two of them within three hours
(GUA_USDT, BLESS_USDT) with both slots free. Three hypotheses, tested in order:

| hypothesis | verdict |
|---|---|
| Partial-bar asymmetry — the live scan evaluates a half-formed final bar, the replay a completed one | **REFUTED.** Re-running the detector the way the scanner does it (`end=scan_time`, partial bar) found the SAME signals — GUA at 11:05 and 14:50, BLESS at 13:20. This had been the leading trial-9 candidate; the evidence killed it. |
| Pool filters excluded them | **REFUTED.** GUA ($15.3M turnover, 117% range) and BLESS ($19.8M, 21%) are cleanly inside the scan pool. |
| The signal is transient and the grid misses it | **CONFIRMED — measured.** |

Sampling GUA_USDT's entry condition every 5 minutes for 5 hours:

```
.....................................SSS....................
11:43                                                   16:38 UTC
condition TRUE on 3/60 samples = 5.0% duty cycle
longest unbroken window: 15 minutes
```

**The condition holds for about 5% of the time, in a single 15-minute window.**
A 15-minute scan grid places ~1 sample inside a 15-minute window, so
`P(zero hits) ~ e^-1 = 37%` per opportunity. On this symbol it saw nothing —
entirely consistent with chance, not with a defect.

This is the same failure mode already documented for the sniper: *"a 30-minute
signal scanned hourly is invisible... the expected catch was 0.8 and we logged
0"*. It was never checked for the wildcard.

## SNIPER RETIRED, 2026-08-10

Final live record, 8 fills over 3 days:

| | |
|---|---|
| net | **-0.90R / -$0.1126**, 3 wins of 8 (37.5%) |
| shape | avg win +1.55R, avg loss -1.11R -> **breakeven needs 41.7%** |
| shadow | SNIPER_FAST n=40: **+12.85R gross, -3.18R net** of its own ~0.5R round trip |

It answered the question it was built for. The open question was fill quality —
whether a notional-capped leg fills where the model says. It does: LINK and XRP
both filled their 2R brackets and netted +1.6-1.7R. The economics were never
open: `FAST` runs with its cost gates deliberately disabled and is flagged "not
viable at taker fees" in its own code. On a 0.37% stop the round trip is ~0.5R,
so it must be right 42% of the time to stand still on a signal whose shadow win
rate is 50% and whose live win rate is 37.5%.

Retired at 8 of a planned 25 fills rather than run to the pre-registered n. The
remaining 17 would have cost ~-$0.30 and could not have changed the verdict:
the fill-quality question is answered and the cost arithmetic is not a sampling
question. Recorded as a deviation from the pre-registration, not a graduation.

**Removed from `/status`, the boot message and the digest.** Historical rows
stay in the ledger; nothing new is written. Reversible with
`FUTURES_SNIPER_ENABLED=1` plus a revert of the display commit.

**If it ever returns, the fix is not more trades — it is a wider stop.** At a 2%
stop the drag is 0.095R instead of 0.51R and the same 50% shadow win rate is
clearly profitable. That is a different sleeve and needs its own trial.

Same review also corrected the boot message, which still advertised the six PMT
pairs — the one universe the bot cannot enter since 2026-07-13. It now states
the wildcard's slots, scan cadence and band, and names the off sleeves.

## Changes under test in trial 9

**Treatment (the reset):**

1. **`FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS` 900 -> 450.** Expected samples in
   a 15-minute window goes 1 -> 2, so `P(miss)` goes ~37% -> ~13.5%: capture
   ~63% -> ~87%, i.e. **about +37% more entries from the same market**. This
   buys CAPTURE, not arrival — it does not make signals more frequent, it stops
   throwing away the ones that occur. Cost: 2x kline calls (~176/hr vs ~88).
   Rollback: set the env var back to 900.

**Unchanged, carried from trial 8:** baseline-turnover majors band (24), the
lossless 24h-range pre-filter, strict category filter, retention trail
(arm +1R, floor 0.30xpeak, cost-floored), 24h convex clock, long-only, 2 slots,
risk dial ON, +5R TP, 3.0xATR stop capped at 20% of margin.

## Honest accounting of what trial 9 is testing

Trial 9 carries **three** untested changes: the band ranking and the range
pre-filter (both from trial 8, which scored zero closes and therefore tested
nothing) plus the scan cadence. Attribution is partly preserved —
`legacy_major` and `legacy_prefilter_ok` are recorded per candidate — but there
is no per-trade tag for "would a 900s grid have seen this", and there cannot be
one, because the counterfactual is about a sample that was never taken.

Stated plainly: **if trial 9 produces a positive result, it will not be
attributable to the cadence alone.** The compensating argument is that all
three changes are about WHICH SIGNALS ARE OBSERVED, not about what is traded
once observed — entry geometry, sizing and exits are untouched since trial 7.

## Do not do this if...

- ...the expectation is that a finer grid creates edge. It cannot. It recovers
  signals the sleeve already generates and discards. If the underlying
  signal has no edge, sampling it twice as often loses money twice as fast.
- ...anyone proposes going to 300s or 120s on the same reasoning. The
  measured window is ~15 minutes; 450s already puts 2 samples inside it and
  the return on further halving falls off as `e^-n`. 300s buys ~+5pp of
  capture for 50% more API load.

## Scoring — unchanged bars

30 WILDCARD closes or 90 days, whichever first. Tripwires, robustness bars
(day-clustered t, leave-one-month-out, top-3 haircut, family-wise null) and all
other rollbacks carry over verbatim.

**Reset count: 5 in ~11 days**, zero scored verdicts. Trials 5, 6, 6.5 and 7
were reset on defects; trial 8 on a measurement that showed the sleeve was
discarding its own signals. Each was justified individually. The count is
recorded here because the pattern is now the largest single risk to this
programme: **a trial that never runs long enough to score cannot be wrong, and
cannot be right either.**

---

# Pre-registered decision rule — CONVEX TRIAL 8 (from 2026-08-09)

## Trial 7 CLOSED at n=2 in-trial closes, ~47h. Not a performance verdict.

| | |
|---|---|
| Closes | 2 / 30 — BICO +$1.168 / 0.42R (migrated, excluded); BTW +$0.646 / 0.53R |
| Net | +$1.81, +0.95R, 2/2 wins, both `CONVEX_RETENTION_TRAIL` |
| Tripwires | TW1 0 of 2 armed closes <= $0 PASS; TW2 2 of 2 >= +0.15R PASS; TW3/TW4 unreadable at n=2 |
| Scoreable n | **1** — BICO was pre-registered as excluded (migrated from trial 6.5) |

Closed by owner decision on a **discovered defect in universe construction**,
not on results. The retention trail is UNCHANGED and carries into trial 8; its
2-for-2 record is not evidence either way at n=1.

## The trial-7 lesson: the majors exclusion was endogenous

`_top_turnover_symbols` ranked the raw ticker list by **24-hour** turnover. But
turnover is *created by* the move, so the rule removed symbols in proportion to
how hard they had just run — the exact event the sleeve exists to catch.

Measured on the live book, 2026-08-09, against that day's top gainers:

| symbol | 24h turnover | rank | 24h move | outcome |
|---|---|---|---|---|
| TUT_USDT | $76.7M | **12** | +19.31% | excluded — 2 clean LONG signals lost |
| SKYAI_USDT | $58.0M | 15 | -13.12% | excluded |
| BICO_USDT | $39.5M | 18 | +6.53% | excluded — 1 LONG signal lost |
| CYS_USDT | $18.1M | 28 | +11.24% | excluded |
| ADA / DOGE / AVAX / LINK / DOT / UNI | — | 16-29 | **all < 2%** | genuine majors |

Turnover rank could not separate "a major" from "a small cap having a big day",
because the second one *becomes* high-turnover by having the day.

Second defect, same function: the ranking ran BEFORE the crypto filter, so
tokenised equities (SKHYNIXSTOCK, SPCXSTOCK, SILVER, MUSTOCK, SPX500 — six of
the top 30) consumed exclusion slots. "Top-30" never meant top-30 crypto.

## Changes under test in trial 8

**Treatment (the reset):**

1. **Majors ranked on baseline turnover, not today's.** `_major_symbols`
   deflates each symbol's 24h turnover by its own 7-day baseline, derived from
   its own daily bars so contract size cancels in the ratio:
   `deflator = min(1.0, median(last 7 complete days) / last complete day)`.
   **Clamped at 1.0 — the correction is one-sided because the distortion is.**
   Unclamped it also *promoted* quiet symbols: SOXL (a tokenised ETF whose
   weekend volume goes to zero) scored a 16.98x deflator and outranked every
   crypto major, and BNB became tradeable. Cached 12h; fails open to the old
   behaviour on any kline error.
2. **Ranking and scanning both use the strict category filter.**
   `_is_tradeable_crypto` = `universe._is_crypto_usdt_symbol` **plus** the
   sniper's end-matching prefix rules. The weaker filter guarded the wildcard
   and passes XAU, SPY, SOXL, JP225, KOSPI, TESLA, ANTHROPIC, OPENAI — XAU_USDT
   produced trial 4's worst trade (-3.79R in 60s on a 0.28% stop) and would
   have become scannable the moment it stopped occupying an exclusion slot.
3. **`FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER` 30 -> 24.** NOT a tuning move:
   holding the treatment constant while fixing how it is measured. The old
   top-30 spent ~6 slots on tokenised equities, so it excluded ~24 crypto
   names. Ranking crypto-only at 30 would have silently WIDENED the exclusion
   and made BMT_USDT (+35.49% that day, raw rank 38) untradeable.

4. **24h pre-filter replaced by the 24h RANGE.** The screen was
   `|24h change| >= 3%` while the detector triggers on `|3h ROC| >= 8%` — a
   different quantity. A symbol that ran +30% in three hours and gave half back
   showed ~0% on the day and never reached the detector; on 2026-08-09 the
   filter admitted **8 of 970 symbols**. The screen is now
   `(high24 - low24) / low24 >= FUTURES_WILDCARD_MIN_ROC`, defaulted FROM the
   trigger so the two cannot drift apart again.
   **This is lossless by construction, not a tuned threshold:** both ends of
   the trailing 3h window lie inside the trailing 24h window, so
   `|3h ROC| >= X` implies `range24 >= X`. Nothing that could fire the trigger
   can be screened out. Measured live at deploy: pool **11 -> 20** symbols,
   **zero dropped**, and it admits exactly the two symbols that produced LONG
   signals and went untaken on 08-09 (SAGA_USDT, IOTX_USDT).
   Bundled into trial 8 at owner instruction.
   Rollback: `FUTURES_WILDCARD_RANGE_PREFILTER=0`.

**On the two-changes-in-one-trial question (settled 2026-08-09).** Trial 8 does
carry both universe changes, and the first write-up called that an
unattributable confound. That was an overstatement, and renaming the trial
would not have fixed it either — both changes are already live, so a new label
is the same two-variable experiment with a different number on it.

What was actually missing was a record of which side of each OLD gate every
candidate sat on. Every wildcard candidate and every shadow row now carries:

| field | meaning |
|---|---|
| `legacy_major` | was this symbol inside the pre-trial-8 raw top-30 by 24h turnover? |
| `legacy_prefilter_ok` | would it have cleared the old `\|24h change\| >= 3%` screen? |

Both are computed from data already in memory (one extra sort of the ticker
list) and flow to the feature store, so a trial-8 verdict splits four ways
after the fact — `legacy_major x legacy_prefilter_ok` — without running two
90-day trials. A trade that is `legacy_major=True` was freed by the band fix; a
trade that is `legacy_prefilter_ok=False` was freed by the range screen; one
that is both was unreachable under either old rule alone.

Note the two changes are not symmetric in risk: the range pre-filter is
**lossless** (strictly a superset of the old pool — measured 11 -> 20, zero
dropped), so it can only add candidates. Only the band ranking can remove one.

**Measurement added (no reset):** the learning digest now runs a
**missed-opportunity check** — the top 10 movers by 24h range in the tradeable
band, each classified as traded / blocked-with-reason / no-signal-with-blocker /
never-scanned-with-funnel-stop, by replaying the live detector over the last 24h
of 15m bars. Built because working out why eight of one day's ten biggest
gainers went untaken took a manual pass over four data sources. Digest cadence
moved to daily. Costs 10 kline fetches/day, ~15s, fail-soft.

**Unchanged from trial 7:** retention trail (arm +1R, floor 0.30xpeak,
ratchet-only, cost-floored), 24h convex clock, long-only, 2 slots, risk dial
ON, +5R TP, 3.0xATR stop capped at 20% of margin.

## What this measurably does and does not fix

Validated against the live book at deploy time:

- **TUT_USDT: FIXED.** Falls out of the excluded band entirely.
- **BMT_USDT: PRESERVED** as tradeable (would have been lost at n=30).
- **BICO_USDT: STILL EXCLUDED**, at deflated rank 17 of 24. Recorded honestly:
  under a *correct* rule BICO is a major — $39.5M turnover, 0.71 deflator,
  $28.0M baseline. Catching it needs the count at <= 16, which would be fitting
  to a single symbol on a single day. **Not done.**
- **BNB_USDT: known artifact.** A single above-median day gives it a 0.75
  deflator and it lands at rank 26, i.e. tradeable. Self-corrects as the
  baseline window rolls. Harmless in practice: BNB sits in the BTC/ETH/SOL
  cohort, which breached |3h ROC| >= 8% **zero times in 1717 windows** over 18
  days of cached bars.

## Not changed, and why (from the same day's evidence)

- **$3M turnover floor** (cost TST_USDT, $1.82M). Kept. EPIC_USDT produced no
  signal at all, so one symbol is the entire case, and the floor is what keeps
  fills honest on a $142 account.
- **Long-only** (cost IOTX_USDT, a SHORT signal). Kept — it is the one gate
  already accruing evidence: shadow rows now read **+2.23R over 4** under the
  live exit policy (was +0.78R under the retired bracket). Pre-registered bar
  is n >= 20. It will answer itself.
- **The 24h pre-filter screening a 3h trigger** (`FUTURES_WILDCARD_MIN_24H_MOVE`
  vs `FUTURES_WILDCARD_MIN_ROC`) — a symbol that runs +30% in 3h and retraces
  never re-enters the pool, and the filter admitted 8 of 970 symbols at 17:20
  on 2026-08-09. This is a REAL defect and is deliberately NOT bundled: it
  would confound the universe change under test. **Highest-priority candidate
  for trial 9**, to be replayed on the harness first.

## Two-window missed-opportunity check + a live exit bug (2026-08-09)

The daily digest's missed-opportunity check now runs **two windows**: top 10 by
24h range (exact, from the ticker) and top 10 by 48h range (from Min60 bars over
a shortlist). Rationale: a symbol that adds 12% two days running is a 25% move
that looks unremarkable on either single day, so it appears on neither a 24h
change nor a 24h range ranking. First live render found three such symbols with
LONG signals — MUBARAK, BLUAI, COOKIE — none of which the 24h list surfaced.

**A pre-existing LIVE TRADING BUG was found reviewing it** (`runtime.py`, exit
loop). On a `get_fair_price` failure the loop fell back to
`_get_reference_price()`, which resolves to whichever position happens to be
`self.open_position`. With two convex slots, a transient failure on an alt at
$0.02 evaluated its exits against BTC at $65,000 — an astronomical fake gain
that the profit locks and the retention trail would act on with a market close.
Fixed: a position whose price cannot be fetched is SKIPPED for that cycle (the
exchange-side stop still stands); the reference price is only substituted when
the symbol matches. Not a treatment change — it removes a failure, and it has
never been observed firing.

Also fixed pre-deploy, from the same review:

| defect | consequence |
|---|---|
| no wall-clock budget on ~100 sequential kline calls | a degraded exchange blocked the trading cycle up to ~79 min — `/pause` dead, no heartbeat, no exits. Now `FUTURES_MISSED_BUDGET_SECONDS` (60s) with the truncation disclosed |
| digest marker written AFTER the work | an unwritable marker read back 0.0 forever: full digest + ~100 kline calls **every cycle**. Now claimed before the work, fails closed |
| failed Telegram send still advanced the marker | silently cost a full day's digest. Now rolled back on failure |
| traded/blocked used a 48h lookback on the 24h list | a fill 40h old stamped "traded" on a 24h line and suppressed the replay — a clean pass on exactly the symbol that mattered |
| replay window silently truncated on short history | a symbol listed 3 days ago got 22h of a 48h window and still answered "never cleared 8%/3h" — new listings are the +100%-over-two-days population |
| top blocker was always `no_pullback_resume` | it is gate 2 of 4 and rejects ~70% of trigger bars on every symbol, so it carried no information. Now reports bars that got PAST it and what killed them |

**That last fix produced a finding.** With pullback-resume excluded, the actual
killer on nearly every candidate is **`low_volume_z`** (XAN 11/11, BLUAI 9/13,
BANANAS31 7/9, CAP 4/6). That was invisible before.

**Recorded, NOT fixed — trial 9 candidate.** The live scan fetches klines with
`end=now`, so its final bar is PARTIALLY FORMED, while the replay uses completed
bars. The volume-z gate divides by a full bar's volume in replay and a partial
bar's in live: a scan landing 3 minutes into a 15m bar sees ~20% of the eventual
volume, so live is systematically STRICTER on exactly the gate now shown to be
binding. Fixing it (drop the incomplete bar) changes which trades are taken and
would reset trial 8, so it is deferred and the digest discloses that its signal
counts are an upper bound.

**Known limitation, disclosed in the report itself:** the 48h list ranks a
shortlist (top 24h-range + top 7d-return), not the whole book. A move that ran
and fully retraced inside hours 48-24 is invisible on both axes and can be
absent.

## Safety amendment 2026-08-09 — unattended operation

Not a treatment change; recorded because one item can bind in the tail.

| change | from | to | why |
|---|---|---|---|
| `FUTURES_HEARTBEAT_SECONDS` | 0 | 21600 | There was NO liveness signal. A dead bot was completely silent. 6h = 4 msgs/day; a missing one is the alarm. |
| `restartPolicyType` | ON_FAILURE, 5 retries | ALWAYS | Five consecutive crashes — a MEXC outage burst would do it — left the bot permanently dead. |
| `DRAWDOWN_HALT_PCT` | 0.95 | 0.25 | 0.95 is not protection. It was parked there when the window was 90d and still carried the PMT era. |

**Verified before shipping, not assumed.** With the live `DRAWDOWN_HALT_WINDOW_DAYS=30`
the bot reads `dd_30d = 0.1%` (NORMAL) — 0.25 cannot fire on deploy. The same
curve on a 90d window reads `dd_90d = 48.4%` and WOULD halt instantly, which is
exactly why 0.95 was parked there. PMT died 27 days ago, so 27 of the 30 window
days are clean and the window self-cleans by 2026-08-12.

At 1R ~ $2.66 and 2 slots, a 25% halt from $142.32 needs ~13R of drawdown — far
outside normal variance, inside the range of a real defect.

**Known gap, accepted in writing:** the convex exits are SOFTWARE. A process
death with a position open leaves the exchange-side SL/TP (entries are
stop-first, so loss stays bounded) but the 24h clock and the 0.30xpeak retention
trail stop running, and the trade rides to -1R or +5R. The retention invariant
does not survive process death.

## Scoring — unchanged bars

30 WILDCARD closes or 90 days, whichever first. Tripwires, robustness bars
(day-clustered t, leave-one-month-out, top-3 haircut, family-wise null) and
rollbacks all carry over from trial 7 verbatim. New rollback:
`FUTURES_WILDCARD_TURNOVER_BASELINE=0` restores raw-24h ranking.

**Freeze discipline.** This is the 4th reset in ~10 days and the fourth trial
to score zero verdicts. It was taken on a defect, not a preference — but the
count is recorded here so the next reset has to argue against it.

---

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

### /status rewrite (same amendment, measurement-only — no reset)

Nothing about the treatment changed. Four surfaces were reporting constants:

- `Signal: none` was structurally guaranteed. The `/status` handler passed no
  signal at all, and the signal it would have passed comes from the PMT scan,
  which returns `None` while `FUTURES_ENTRY_MIN_SCORE>=999`. It read "none"
  whether the bot had just vetoed a 24.3% mover (BTW_USDT, 2026-08-09 14:44,
  `crowded_longs`) or seen nothing for two days. Replaced by the wildcard funnel
  + reject histogram + last untaken candidate, all of which already existed and
  only ever reached the Railway log.
- `Trades: 200` was a saturated window, not a count: `_save_state` persists
  `trade_history[-200:]`, so past 200 lifetime closes it is pinned forever.
  Replaced by `Trial N: n/30 WC closes | netR | net $`, sourced from the
  append-only feature store.
- `TRIAL_START` in `learning_digest.py` was hardcoded to **trial 4**
  (2026-07-13) and never moved through trials 5, 6, 6.5 and 7 — every `n/30`
  the weekly digest reported counted four trials as one. Now
  `FUTURES_TRIAL_START_TS` (epoch seconds); **bumping it IS the reset
  operation**. Default 2026-08-07 19:22 UTC.
- Slot counters: `SQ 0/1` rendered while `FUTURES_SQUEEZE_ENABLED=0`, `PMT 0/2`
  was pinned at 0 by the score floor, and the only sleeve holding real money
  (sniper) had no counter at all. One row now, per enabled sleeve.

Also: sniper per-candidate rows are gone from `/status` — they were shadow
counterfactuals drawn with side/leverage/entry exactly like real positions,
directly above "No open positions.". Paper R and real-money $ are now on
separate lines with the paper one labelled `paper (no fills/fees)`; "would-be"
was factually wrong for a live variant, since every sniper signal is
shadow-logged *before* the live order is attempted.

**Top-30 turnover exclusion: KEPT, and the reason it is kept has changed.**
Owner asked whether PMT's decommission frees the majors. It does not — the
exclusion post-dates the decommission (`d4fbd06`, 2026-07-17; PMT died
07-13) and never referenced PMT. Its actual rationale was a band split
(+24.7R sub-top-30 vs -2.3R top-45) plus habitat allocation to SQUEEZE, and
**both halves have decayed**: squeeze is live-set OFF, and the measurement
exists only as a commit-message line — no output, doc or results file records
it, the two arms overlap at ranks 31-45 so ranks 1-30 were never scored alone,
and it was run at 1.5xATR / both sides / 1 slot. Recorded as **unverified**.
It is nonetheless close to inert on arrival: on the repo's own cached 15m
bars (18d), BTC, ETH and SOL breached |3h ROC| >= 8% **0 times in 1717
windows** (max 4.23% / 5.51% / 5.41%), while band names fired routinely
(ZEC 75/1717, ENA 32/1333). The live funnel agrees: `major_excl` removes 25
of 674 in-band symbols, while turnover and 24h-move gates cut 674 -> 24.
Revisit at the trial boundary, not before.

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
  **QUEUED FOR TRIAL 17 (2026-08-25).** The corrected point-in-time pool is the
  NEW EVIDENCE this entry demands — the same correction reversed three prior
  acceptances, so it can manufacture false negatives too. Note the live stop is
  ALREADY `FUTURES_WILDCARD_SL_ATR_MULT=3.0` (code default 1.5), i.e. wider than
  the 2.0/2.5x retracted here; the re-test covers the multiplier AND the 20%
  `MAX_SL_MARGIN_PCT` cap, which trims LEVERAGE first to preserve stop distance.
  Do NOT open it on anecdote. **Exit reasons identified 2026-08-25: all three
  recent losers (TAC/STX/SPK) stopped out at 19-20% of margin, i.e. AT the 20%
  cap. TAC ran leverage x1 with a 19%-wide stop -- the cap had already trimmed
  leverage to the floor, so that stop CANNOT be widened. The multiplier is the
  wrong dial; only `MAX_SL_MARGIN_PCT` itself is testable, and the anecdote does
  not support changing it.**
- No MIN_ROC raise, no lateness VETO, no ratchet/trail (+1R ratchet costs -12.3R
  across the 7 trades reaching +2R), no funding-hold policy.

## Capital-flow annotations
- 2026-07-21: operator DEPOSIT ~+$72 (equity $65.76 -> $137.83). Not P&L.
- Drawdown must be computed flow-adjusted (or from the cumulative R curve).
  Net R / ex-best R are scale-invariant and unaffected; the conditional-
  expectancy engine compares conditions in R for the same reason.

## Pre-registered candidate (2026-08-22): trend shorts behind a deep drawdown gate

Registered BEFORE the fact so that a real correction becomes an out-of-sample
test rather than an improvised change made mid-drawdown.

**Trigger.** BTC's trailing 7-day return <= **-12%** at the moment of a trend
signal. Above that threshold, nothing changes.

**Change if triggered.** Allow `SHORT` in the TREND sleeve
(`FUTURES_TREND_LONG_ONLY=0`) *only* while the trigger holds; revert when it
lifts. Wildcard shorts are unaffected — they are already on and already measured.

**Why it is not shipped now.** `tools/trend_short_regime_ab.py`, 360 days, 51
weekly windows:

- Unconditional trend shorts: **-$61.51**, -$108.64 ex-best, 180 of 343 signals
  firing in flat weeks at -0.921 each with a negative edge vs a random short.
- Gated on trailing BTC (no lookahead): **-$73.83** at -2%, **-$47.51** at -5%,
  **-$6.26** at -8%, **+$37.60** at -12%. The intuitive "shorts on when the
  market looks weak" version LOSES; only the deepest gate is positive.
- At -12% the recent half is +25.78 and ex-best is +11.82, i.e. roughly ONE
  profitable episode per half. Two episodes is not evidence, and -12% was the
  most extreme threshold tested, chosen after seeing the sweep.

**Pass criteria if it ever runs.** >= 10 trend-short closes while triggered, net
R > 0 AND net R ex-best > 0, scored against the sleeve's own random-short
baseline (-0.173/trade over this window). Fail -> revert and do not retry.

**What needs no change either way.** The trend sleeve is already safe in a crash
long-only: it returned +$6.53 through the two CRASH weeks because its entry
requires a new 24h closing HIGH, which a crash does not produce. It goes quiet
rather than losing. Downside EARNING is the wildcard short arm's job.

---

## TRIAL 15 — CLOSED 2026-08-22. Result: both criteria positive, n short.

Ran 2026-08-20 08:00 UTC to 2026-08-22 10:44 UTC (~2.1 days). Under test: the
big-3 TREND sleeve in its own slots alongside the wildcard.

**Convex record (feature store, reconciled against FULL exchange history —
15 store rows = 15 exchange closes, no censoring):**

```
sleeve        n     netR    net $   wins
TREND         7   +10.270   +19.42   7/7
WILDCARD      7    +1.900    +6.12   3/7
TOTAL        14   +12.170   +25.54
  exBest netR +7.210   (best: ENA_USDT +4.96R / $+11.11)
```

Account: **$139.54 -> $165.12, +18.3%** over the window (the 15th exchange close,
BTC +$0.17, is tagged PMT — an accidental position adopted as RECOVERED and
closed by legacy exits — so it is correctly outside the convex count).

**Verdict: PASS on both criteria, FAIL on n.** netR > 0 and netR ex-best > 0 were
both met, and comfortably. But the rule requires 30 convex closes and the trial
reached 14. This is NOT a scored verdict.

**What the trial actually established.** The TREND sleeve went 7/7 on R and
carried 76% of the P&L on 2 slots. That is a strong signal and a weak sample: the
window was an exceptional market (BTC +2%, ETH/XRP/ZEC all running), the sleeve is
long-only, and 7 wins in a rising market is close to what any long entry returns.
The edge-vs-random discipline has NOT been applied to these live fills.

**Defects fixed during the trial** (all live, all with regression tests): the
PMT-recovery hijack (`692eae2`), the trial scoreboard counting one sleeve instead
of the convex book (`7d96ffd`), and the non-crypto universe filter (`dfc2515`).

## TRIAL 16 — CLOSED 2026-08-27, VOID (sizing check failed; see trial 17 head)

**Under test: renormalised position sizing.** `FUTURES_WILDCARD_RISK_PCT`
0.0187 -> **0.0241**, regime-scaler shape unchanged at 0.20/0.45/0.25.

The scaler's multipliers are all <= 1.0, so it could only ever shrink the book:
mean multiplier 0.777 meant the sleeve ran at 78% of design size and realised
1.45% risk per trade against a designed 1.87%. Renormalising restores the design
level; it does not raise it. Peak per-trade risk becomes 2.41% against
`FUTURES_MAX_TRADE_RISK_PCT=5`, and worst-case concurrent risk across all open
slots goes 9.5% -> 11.4% of equity.

**Evidence** (`tools/regime_scaler_ab.py`, `tools/scaler_equity_path_ab.py`;
208 days, 1476 candidates, 516 fills, compounded with real slots):

- Entry efficiency genuinely predicts: bottom buckets +0.103R / +0.019R, top
  bucket +0.401R on 61.8% wins.
- Renormalised LIVE compounds to +659.1% vs +615.2% for no scaler, with max
  drawdown FALLING 24.2% -> 20.2%.
- Run as two independent paths it beats the no-scaler null in BOTH halves
  (+32.2%/+494.6% vs +27.5%/+491.6%) — the only variant besides floor-0.50 to
  do so.
- Every SHARPER tilt was rejected: all four underperform doing nothing in the
  older half. "Aggressive 0.30/0.50/0.10" compounds best overall (+761.8%) and
  its entire advantage is the recent half, with an older half marginally worse
  than no scaler at all.

**Everything else carries over unchanged:** TREND ETH/XRP/ZEC, 2 slots, long-only;
WILDCARD 3 slots, both sides; turnover floor $2M; scan cap 90; squeeze off.

**Pass criteria:** 30 convex closes, netR > 0 AND netR ex-best > 0.
**Sizing-specific check:** realised mean risk per trade should land near 1.87%,
not 1.45%. If it does not, the renormalisation is not doing what it claims and
the trial is void regardless of P&L.

**THE RESET COUNT IS NOW 12** (trials 5, 6, 6.5, 7, 8...16 in ~3 months, still
zero scored verdicts). Trial 15 closed at 14/30 on a config change, not on
results — the same pattern. It is worth stating plainly that this change is
R-NEUTRAL by construction: sizing moves the dollar multiplier and cannot move R,
so trial 15's R record remains valid evidence and is not invalidated by the
reset. The counter is restarting for bookkeeping, not because the prior data
became wrong.

## Trail ratchet on exceptional trades (live 2026-08-22, inside trial 16)

`FUTURES_CONVEX_TRAIL_RATCHET_R=3.0`, `FUTURES_CONVEX_TRAIL_RATCHET_RETAIN=0.75`
(defaults in code; set `..._RATCHET_R=0` to revert). Below a 3R peak the floor is
unchanged at 0.30 x peak.

**Why, in one line:** the flat floor is right while a runner is growing and wrong
once it has already made its money.

`tools/peak_fate_ab.py`, 208 days, 1380 candidates. From a 3R peak only **13.2%**
of trades exit within 20% of their high and **40.4%** hand the whole run back to
the floor, while the mean peak there is 5.95R against a 5R target. Also: **13.4%
of trades that touched 2.5R still finish at -1R**, because the floor is set from
PRIOR bars — a bar that spikes to a new peak and collapses inside the same bar is
floored on the old peak.

Every threshold/retention pair tested is positive AND passes the half-split,
which nothing else measured this session managed:

```
rule                          net $   vs live   pos wk    recent     older
LIVE flat 0.30              +330.94     +0.00   17/29   +296.03    +34.91
peak>=2.0 -> retain 0.60    +378.26    +47.32   15/29    +41.41     +5.91
peak>=2.5 -> retain 0.75    +358.53    +27.59   16/29     +8.05    +19.55
peak>=3.0 -> retain 0.75    +356.27    +25.33   17/29    +21.30     +4.03   <- shipped
```

3.0/0.75 was chosen over the larger 2.0/0.60 because the latter is 88%
recent-half and costs two positive weeks — the same preference for an evenly
distributed edge that rejected the sharper size tilts.

**Why NOT the Telegram "record" trigger, which is what was actually asked for.**
Re-measured 2026-08-22 it fires on 49% of armed trades with a median trigger of
**3.04R**, so it currently means almost the same thing — and the 2026-08-08 note
saying it costs -$38/yr no longer holds (it fired on 70% then; the account grew
and the weekly-best bar rose with it). It was rejected because it DRIFTS: the
threshold is weekly-best-close / 1R, so one weak week drops the bar and silently
restores the 70%-firing rule that lost money. It also tests weaker — the best
record variant surviving a half-split is +$20.38, and `record only -> 0.75` fails
it outright (-2.50 recent). The 🏆 message now quotes the ratcheted floor, so the
human sees the real number while the orders run off the stable trigger.

**What this does not fix:** the ~13% that gap through inside a single bar, and
the occasional runner cut short — that is the ~$20 of upside the 0.60 variants
capture and 0.75 gives back.

---

## 2026-09-09 — ZEC TREND bull-run forensics: the ATH intuition, REFUTED (5th time). Entries are not the problem; exits are.

**Asked:** review every 18F TREND fill on the ZEC run, test "do not open longs at an all-time
high", find the missed entries. 3 agents / 3 independent replay engines / 3 adversarial
verifiers / ~670 cells.

### The premise correction

TREND did NOT lose on the run. Since 09-03: **9 ZEC longs, +6.45R / +$31.71**, plus XRP +$2.55.
The six post-deposit fills net **+$15.36 (+0.115R)**. The felt loss is the equity peak
($1,183.57 on 09-06 05:55 -> $1,031.54), which is three ZEC stop-outs (-$69.22) plus WILDCARD
(-$31.99).

### The six, entry and exit

| # | entry | px | roc24 | RSI | ext. above prior 24h close-hi | bar/ATR | stop% | 3R needs | exit | R | $ | peak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 09-04 16:55 | 1036.54 | 10.0 | 73.8 | 0.87 ATR (p57) | 1.79 | 4.94 | 14.8% | CLOCK24 | -0.206 | -2.66 | 0.22 |
| 2 | 09-06 01:07 | 1077.87 | 6.1 | 76.6 | **7.48 ATR (p100)** | 6.22 | 2.61 | 7.8% | TP | +3.016 | +75.37 | 3.03 |
| 3 | 09-06 04:59 | 1140.35 | 12.2 | 73.6 | **5.15 ATR (p99.4)** | 3.94 | 4.29 | 12.9% | TRAIL | +0.419 | +11.88 | 1.03 |
| 4 | 09-06 09:26 | 1199.51 | 19.0 | 55.3 | 1.03 ATR (p63) | 1.77 | 4.52 | 13.6% | STOP | -1.022 | -28.49 | 0.09 |
| 5 | 09-06 17:38 | 1224.50 | 18.6 | 53.6 | 1.61 ATR (p78) | 2.89 | 4.76 | 14.3% | STOP | -1.044 | -20.38 | 0.49 |
| 6 | 09-08 16:38 | 1205.82 | **4.4** | 65.3 | 1.66 ATR (p80) | 1.42 | 3.78 | 11.3% | STOP | -1.048 | -20.35 | 0.12 |

Percentiles vs n=345 in-universe episodes / 358 days. All columns knowable at the entry bar.

**What killed the losers is the REQUIRED MOVE, not the price level.** #1/#4/#5/#6 each needed
11.3-14.8% within 24h to reach 3R; their peaks were 0.22 / 0.09 / 0.49 / 0.12R and their best
forward-24h moves +0.5% to +4.7%. That is realised forward vol and nothing at the entry bar
predicts it. The winner won because it entered while ATR was still COMPRESSED, putting 3R only
7.8% away, and it carried the TIGHTEST stop of the six (2.61%, p40 of ordinary 4h ZEC pullbacks).

**Post-exit forensics:** #1 CLOCK24 left **+3.62R on the table in the following 24h** (the one
demonstrably wrong exit). #4 was a whipsaw (price 1221.30 four hours after the 1146.59 stop,
above the entry). #5 and #6 stops were CORRECT (max favourable after exit -0.73R and -0.60R).

### THE ATH INTUITION: REFUTED, six restatements, three engines, never once positive

| restatement | result |
|---|---|
| skip new N-day closing high (n=366) | 7d **-$156/mo**, 14d -$88, 30d -$71, 60d -$52, 90d -$25, 180d -$3. Monotone to zero as it stops binding. **Sign never turns.** |
| independent engine (n=345) | new-high entries earn MORE: 7d +0.4256R vs +0.0433R (t=+2.46); 30d +0.483 vs +0.140; 365d +0.372 vs +0.203 |
| third engine (n=389), block 30d-highs | -$67.5/mo; **verifier re-derivation -$37.2/mo, CI95 [-84.1, +5.9] spans zero**, ZEC-only, drop-ZEC flips, ex-top-5% -$20.7 |
| absolute 24h-ROC cap | 6% -$118/mo, 8% -$74, 10% -$55, 12% -$48, 15% -$25 |
| 3h blow-off cap | 4% -$68/mo, 6% -$65, 8% -$26, 10% -$6 |
| FUTURES_TREND_RSI_MAX (env-only, zero deploy cost) | 70 **-$154/mo**, 75 -$89, 80 -$62, 85 -$43, 90 -$36 |
| half/three-quarter size at a high instead of veto | -$4.1 to -$22.9/mo, all six dosing cells. **No dose of this idea pays.** |
| max-extension veto (ATR above prior 24h high) | >=1.0 -27.5R, >=2.0 -16.1R, >=3.0 -10.7R. Vetoed groups' mean R is HIGHER than baseline in every cell. |

**Applied literally to the six:** prior all-history max daily close was 952.06 / 1025.41 /
1025.41 / 1025.41 / 1025.41 / 1226.83. Trades 1-5 were new all-time closing highs; #6 was not.
**The rule blocks 1-5 including both winners and keeps only the -$20.35 fill: +$15.36 -> -$20.35.**

**Why the six looked so convincing.** Price rose monotonically through the window and the four
losses arrived late, so ANY monotone-in-time variable sorts them into the top half by
construction. The falsification is inside the sample: **#6 is the least extended entry, the only
one below the prior all-time close, and the worst R of the six.**

**Structural correction:** the gate requires a new 24h CLOSING extreme, which by construction sits
below the window's recent wick high — the bot cannot buy an all-time high. Also ZEC's true ATH is
2016 and is not in any feed the bot reads (MEXC daily history is 5y); "all-time" was never
computable.

**Reconciliation with 2026-09-07 (+0.380R ATH vs +0.448R non-ATH):** the record is now CONSISTENT,
not reversed. Agent 2's positive separation was cut down by its verifier as a bull-regime artefact
(ZEC is 193/345 fills and +69.04R of +74.97R; over the window ZEC ran +2238% while ETH -47%,
XRP -55%, SOL -57%, BTC -32%). ATH status carries no reliable positive information EITHER. What it
does not carry is the negative.

### The n=6 trap, named

Entry-bar range / ATR splits the six PERFECTLY: 6.22 and 3.94 for the winners, 1.42-2.89 for the
losers, zero overlap, clean threshold at 3.0. On 389 episodes / 360 days it loses at EVERY
threshold: >=1.5 -$48/mo, >=2.0 -$39, >=2.5 -$106, >=3.0 -$129. At >=2.0 it RAISES mean R from
+0.185 to +0.218 and still loses 18.75R because it deletes 145 of 389 fills.

### The missed entries: 5 of 14, all the symbol lock, and it was NET PROTECTIVE

570 Min15 bars 09-03 -> now; gate TRUE on 36, clustered into **14 episodes; the bot took 9**.
Zero misses from the slot cap (never reached), scan timing, or a false gate. All five were the
one-position-per-symbol lock, and taking them sums **-0.805R = -$20.25**:

    09-03 12:45-14:00  846-863    +2.905R
    09-04 08:45        1023       -1.054R
    09-04 19:45        1039       -0.558R
    09-06 18:30        1229       -1.043R      <- the actual top
    09-06 21:15-21:45  1236-1245  -1.055R      <- the actual top

**The two entries the ATH rule most wants to block were already blocked, by a rule already live.**

### Every alternative entry timing loses, and the control says why

pullback to MA20 (1/2/4/8h validity) -$176.56 / -$171.46 / -$156.49 / -$129.70; first higher-low
after the new high -$64.88 to -$38.98; limit k*ATR below signal (k 0.25->3.0, fill rate 96%->16%)
-$35.91 -> -$223.28, **not one cell positive**; buy a dip within 6h of a new 24h high 1% -$42.6 /
5% -$130.9; first-extreme-after-quiet -$80.6 (6h) to -$133.9 (24h); MIN_ROC 0.03 -$22.9 / 0.035
-$8.3 / **0.04 baseline** / 0.045 -$16.2 / 0.06 -$35.0 / 0.08 -$42.1; drop the new-extreme
requirement -$29.7.

**THE CONTROL.** Grant the same price improvement with NO pullback condition (phantom fill, always
granted, k*ATR better than signal): **+$34 / +$107 / +$175 / +$225 / +$399 / +$582 / +$1,042 per
month** at k = 0.25 / 0.5 / 0.75 / 1.0 / 1.5 / 2.0 / 3.0.

> At k=1.0 ATR the price improvement ALONE is +$225/mo; the conditional version is -$201/mo.
> **The pullback SELECTION is worth about -$426/mo. Waiting only fills you on the moves that fail.**

Independently reproduces the 2026-09-08 WILDCARD disguised-stop-widening result, different sleeve,
different engine. **This is the answer to "find a better entry point": there isn't one. Paying up
for the new extreme IS the edge and it degrades the instant you wait.**

### THE REFRAME: the exits churn a correctly-identified trend

| | R | $ at $25.16/R |
|---|---|---|
| the six as executed | +0.115R | +$15.36 |
| the six at constant $25.16 risk | +0.115R | +$2.90 |
| hold the first 18F signal (1036.54), 3xATR stop only | **+2.667R** | **+$67** (stop 985.38, post-entry low 995.84, never touched) |
| the 9 run fills, same entries, exits stripped to the -1R stop | **+45.73R** vs +6.35R | |
| buy the run's first gate bar (835.38), hold on the stop alone | **+25.494R** vs +6.35R | |

**Nine sequential trades captured 25% of what one held position would have made.**
Three caveats that stop this being a proposal: (1) **funding is not modelled anywhere** and a
multi-week ZEC perp long in a violent bull run pays heavily; (2) it is in direct tension with the
retention invariant — a conflict between two owner rules, not a bug; (3) every 1-D exit change was
swept and all lose: TP_R 2.0 -13.71R / 2.5 -10.42R / **3.0 baseline** / 3.5 -6.03R / 4.0 -11.53R /
5.0 -8.78R; clock extension -$11 to -$24/mo at every setting 12h-240h; profit-conditional clock
negative at every threshold; no-progress time stops refuted in all 24 cells; SL 2.0x -$129.3 /
2.5x -$54.3 / **3.0x baseline** / 3.5x -$17.5 / 4.0x -$31.8 / 5.0x -$39.4 / 6.0x -$41.5.

### VERDICT: ship nothing to entries. ~670 cells, honest total $0/month.

Multiplicity: agent 1 250 cells, permutation null max p95 $24.4/mo vs best rule $3.8/mo, FWER
p=0.62; agent 2 319 cells, best +15.37R vs permutation p95 +18.19R, FWER p=0.1375; agent 3 102
cells, best survivor Bonferroni p=0.059. **A search this size manufactures $6-24/mo of fake edge
as routine.** Nothing clears it.

### REFUTED — added to the do-not-resurrect list

- ATH / new-N-day-high entry veto (5th refutation, now with six restatements and three engines)
- max-extension veto in ATR above the prior 24h high — **this was the untested version; it is now tested and negative at every k**
- FUTURES_TREND_RSI_MAX at any value
- absolute 24h-ROC cap and 3h blow-off cap at entry
- entry-bar ignition filter (range/ATR) — the n=6 trap
- half/three-quarter sizing at highs
- pullback / higher-low / limit-below-signal entries on TREND (control: the selection is -$426/mo)
- post-stop cooldown on TREND (every cell beyond 2h costs -$9 to -$175/mo; 15 cells)
- blocking re-entry above the previous stop-out price (-$83 to -$102/mo)
- MIN_ROC moves in either direction; dropping the new-extreme requirement
- TREND TP_R 3.0 -> 8.0: fails ex-top-5% hardest (-$45 to -$48/mo), 16 of 327 trades carry it,
  most recent quarter negative, TP_R 4.0 outright negative so the surface is non-monotonic.
  The accompanying "dead branch" claim is WRONG: FUTURES_CONVEX_TRAIL_RATCHET_R is SHARED
  across WILDCARD/SQUEEZE/TREND and WILDCARD's TP_R is 5.0, so the tier is live. No bug.
- drop ETH from the universe: null in isolation (+1.51R; n=77, mean -0.060R, t=-0.40, ex-top-5%
  +0.18R). Only value is variance (maxDD 12.6R -> 8.3R, return/DD 4.99 -> 7.76). Not P&L.

### REFUTED AND DANGEROUS — second concurrent position per symbol

Priced by the three agents at +$9, +$47 and +$69/mo (a 7x disagreement that already condemns it).
**It is not implementable as described and its measurement is invalid:**
- open_positions is dict[str, FuturesPosition] **keyed by symbol** (86 refs in runtime.py;
  _register_position does `self.open_positions[position.symbol] = position`). Removing the
  `if sym in self.open_positions: continue` guard does not create a second position — **the second
  entry silently OVERWRITES the first, destroying its stop level, convex peak, arm state and 24h
  clock while the size sits live on MEXC with no exit management.**
- _save_state serialises {sym: pos.to_dict()}; two same-symbol positions cannot survive a restart.
- config.position_mode = 2 (one-way) means **MEXC nets both fills into one blended position with
  one stop.** Every replay priced two independent positions with two independent 3xATR stops.
- Also fails ex-top-5%-by-delta in all three engines, P(delta<=0)=0.08, flat mean R across every
  capacity setting (leverage, not edge), and a random-entry placebo gains from the same change.

**Cost if wrong is not -$69/mo, it is an unmanaged live position.** Do not run it, not even in
shadow, until open_positions is re-keyed and the account is in hedge mode.

### The sizing "defect" was the deposit

Two agents headlined a sizing gap (one at $128). Verifier decomposition: **+$143.13 of it is the
three PRE-deposit winners** (equity $169-186, risk $1.73-$3.27) and **-$12.47 the funded six.**
110% of the "defect" was the deposit landing between the winners and the losers. Not a bot rule.

**The regime size scaler EARNED ~$12.50 of the $15.36** — half size (0.500) to the first loser,
0.730/0.761 to the last two, full size (1.000) to the +$75.37 winner. Switching it off on this run
costs -$11.73. Independently reconfirms 2026-08-26 on new data. **Do not flatten or renormalise it.**

### The one thing left open (not a proposal, a gap in the grid)

Roll the 24h clock only when the trade is flat-to-slightly-negative **AND the entry trigger is
still live** (roc24 still >=4% at the 24h mark). The grid covered the unconditional clock and the
profit-conditional clock and skipped this. It is exactly the case trade #1 was — the one exit in
the six that was demonstrably wrong ex post (+3.62R available in the following 24h).

### Below the bar, cleanest control set in the study, NOT shipped

FUTURES_TREND_SCAN_INTERVAL_SECONDS 900 -> 300. Point estimate **+$69.83/mo** but
**screened floor $6.01-7.56 — under the $10 bar, fails both robustness screens.** 277 fills
changed, 164 the 15m scan never saw. Monotone 900s +62.86R -> 600s +75.37 -> 300s +95.50; mean R
RISES (+0.181 -> +0.242) while n rises (347 -> 394) and t rises +2.40 -> +3.47 — quality and
quantity both improve, not the signature of pure leverage. 3 of 4 quarters positive. **The only
candidate positive on all three leave-one-symbol-out folds** (drop ZEC +3.53R, drop ETH +29.74,
drop XRP +36.52). Day-block bootstrap P(delta<=0)=0.005-0.006. **But 88% of the raw edge is ZEC in
the twelve months it went $40.49 -> $1,226.83**, faster-cadence slippage is untested, maxDD
12.6R -> 14.4R, and it costs 864 public kline calls/day. Revisit only with a non-ZEC-carried sample.

### THE CEILING

Best achievable on this window from a rule choosable IN ADVANCE, using only information available
at the time: **none beat the shipped config.** The gap to the theoretical hold (+$67) is ~$52 over
four days, it is entirely in the EXITS, it is overstated by unpriced funding, and buying it means
abandoning the retention invariant.

**The shipped configuration — 3.0x ATR stop, 3R TP, arm 1.0R, retain 0.50, ratchet 3.0R, 24h clock,
4% ROC, one position per symbol, 2 slots — sits at or adjacent to the optimum of every
one-dimensional slice run this session.** Three independent searches found no ridge leading away.

### The recurring signature, in one line

**Every filter tested this month raises mean R and destroys dollars, because it deletes 20-82% of
the trades. This sleeve is volume-limited, not quality-limited. Its dollars are in the volume, and
every improvement to the average destroys the total.**

---

## 2026-09-09 (later) — trade 7 turns TREND negative. Judgement reviewed. Ruling HOLDS; my headline was the error.

**Trigger:** a 7th TREND fill closed and flipped the sleeve's sign. Owner asked for the judgement
to be reviewed. 4 agents / 4 adversarial verifiers / ~150 new cells.

### The funded ledger (n=11, since the deposit)

    sleeve    symbol     side  entry             hold      pnl      R   peak_r    mae_r  risk  lev  equity
    TREND     ZEC        LONG  09-04T16:55     24.00h    -2.66  -0.21  0.2195  -0.7561  12.9   4    1096
    TREND     ZEC        LONG  09-06T01:07      3.66h   +75.37  +2.88  3.0255  -0.6070  25.0   7    1172
    TREND     ZEC        LONG  09-06T04:59      0.94h   +11.88  +0.43  1.0333  -0.1300  28.3   4    1184
    TREND     ZEC        LONG  09-06T09:26      5.05h   -28.49  -1.01  0.0877  -0.9906  27.9   4    1155
    WILDCARD  MAGMA      LONG  09-06T19:58      0.38h   -26.45  -1.06  0.0245  -1.0034  25.2   3    1126
    TREND     ZEC        LONG  09-06T17:38     20.50h   -20.38  -1.03  0.4855  -0.9698  19.5   4    1108
    WILDCARD  FORM       LONG  09-08T08:11      2.31h   -25.76  -1.06  0.0909  -0.9576  25.3   1    1079
    WILDCARD  PONS       SHORT 09-07T15:42     23.61h   -19.41  -1.08  0.9653  -0.9507  18.5   2    1064
    WILDCARD  MARSCOIN   SHORT 09-08T11:12      4.52h   -11.65  -1.02  0.3213  -0.9810  11.3   1    1052
    TREND     ZEC        LONG  09-08T16:38      2.18h   -20.35  -1.06  0.1168  -0.9994  19.4   5    1032
    TREND     ZEC        LONG  09-09T04:39      1.16h   -27.25  -1.10  0.8481  -0.9875  25.2   8    1004

    TREND -$11.88 (7)   WILDCARD -$83.27 (4)   TOTAL -$95.15
    Equity $1,096 -> peak $1,183.57 (09-06 05:55) -> $1,004.30. -8.7% in five days.

**`peak_r` is now written to closed records** — first time. 93 of the 200 ring-buffer rows carry it
(64 WILDCARD, 29 TREND) back to 2026-08-12. Every earlier arm study had to reconstruct peaks.

### 1. WHAT THE SIGN CHANGE OVERTURNS

**My headline, and nothing else.** The n=6 figure carried s.e. **$94** (per-trade sd $38.55),
t=0.03, CI95 **[-$121, +$200]**. n=7 is CI95 **[-$156, +$187]**. Same number. **It was already ~41%
likely at the time that the next single fill alone would flip the sign.** Ex the +$75.37 winner the
sleeve is -$87.25 on six — the sign is determined entirely by whether one trade is in the sample.

**The ruling holds.** Ship-nothing rested on ~670 cells, not on +$15.36. Trade 7 was a TREND_LONG
at score 96 that stopped out, already inside the entry study's population.

**What was NOT re-established:** my claim that "the gap is in the exits" is not supported by
anything measured today. It is untested, not proven. Trade 7 shows a live entry-PRICE leak, which
is entry-side (below).

### 2. THE ARM — REFUTED, and the motivating anomaly dissolves

**PONS (0.9653R) and ZEC 09-09 (0.8481R) did not "nearly arm".** The trail evaluates the pushed
**FAIR** feed once per second (runtime.py:5709, 5723-5728, 5736-5753) — not a coarse poll. One
agent found Min1 highs of 1.0969 and 1.0202 and called it a sampling miss; its verifier corrected
that: a 0.42%-of-price gap between a 1-second fair maximum and a 1-minute **LAST**-price high is
**basis, not sampling**. On PONS, where both feeds are known, the true sampling residual is
**0.035R**. Both trades genuinely did not reach the arm on the feed the bot trails.

| grid | result |
|---|---|
| 55 cells (11 arms x 5 retentions), 389 TREND fills / 357 days | **54 negative.** arm 0.80 **-$32.7/mo**, 0.85 -$21.5, 0.90 -$4.7, 0.95 +$12.5. **Non-monotone = noise.** |
| the one positive cell | **p_FWER = 1.00** (placebo best-cell median +$36.3 EXCEEDS the observed +$12.5), drop-ZEC -$2.3, bootstrap P(delta<=0)=0.174 |
| 90-cell grid, Min1 engine | every arm<1.0 cell clearing $10 on the point estimate collapses under ex-top-5%-by-delta AND leave-one-symbol-out. **The grid maximum is arm = 2.00 — arming HIGHER** — and even that fails FWER (p=0.116) |
| runner truncation | **real, not "almost never": 73 of 389 fills reach >=2R and carry +167.77R = 233% of total book R.** Path-exact, arm 0.90 costs -$31/mo, arm 0.80 -$76/mo on that set alone |
| breakeven stop k=0.4..1.0 | **all seven cells negative**, best -$5.6/mo |

**The retention invariant vs the dollars — a genuine conflict between two standing owner rules.**
Full compliance IS buyable: arm 0.50 takes the give-back-100% rate among trades building >=0.5R
from **22% to 0.3%** and costs **-$48/mo**, while cutting total R surrendered by only 17%
($534 -> $443/mo), because a 0.50 retention hands back half of peak by construction.
**It resolves for the dollars** ("$ P&L, always" is the senior directive).

**Structural:** `FUTURES_CONVEX_TRAIL_ARM_R` is read globally (runtime.py:2304, VERIFIED) and
`_is_wildcard_convex` (runtime.py:1476) covers WILDCARD, SQUEEZE **and** TREND. **There is no
TREND-only arm — it is a code change**, and setting 0.80 also arms WILDCARD, priced -$62/mo on
2026-09-08. Also runtime.py:2096-2099: any `RETAIN_FRAC >= 0.75` silently disables the ratchet.

**Do not re-open this on funded fills.** At n=7 with CI95 [-$156, +$187] the funded window cannot
move this parameter in either direction.

### 3. THE SIZING STACK — one real defect, worth $0/month

**The streak throttle is not broken. It is switched OFF by design, and the telemetry lies.**
VERIFIED IN FILE:

    runtime.py:5121  def _convex_streak_multiplier(self) -> tuple[float, int]:
    runtime.py:5125      if not self._flag("FUTURES_CONVEX_STREAK_THROTTLE_ENABLED", default=False):
    runtime.py:5126          return 1.0, 0          # <-- hard-coded 0, streak never computed
    runtime.py:5127      streak = self._convex_loss_streak()
    runtime.py:8036      "loss_streak_at_entry": float(loss_streak),

Flag set to 0 on **2026-08-27 09:32** as trial 17 (DECISION_RULE.md:3916). Since then
`loss_streak_at_entry` is a **hard-coded constant, not a reading**. Last row with a nonzero value:
ETH 2026-08-27T09:29, ls=5.0, mult=0.25 — three minutes before the flag flipped.

**The true streak at the 09-09 fill was 7.** Correct per-fill sequence across the funded 11:
1,2,0,0,1,1,3,3,4,6,7. **This is why neither the owner nor I could see from the ledger that the
account had run seven straight losses.** Fix is two lines (compute the streak before the flag
check, gate only the multiplier). Zero behaviour change, $0/month.

`_convex_loss_streak` (runtime.py:5102-5118): walks `trade_history[-20:]` in reverse close-order,
skips non-convex rows, counts consecutive `pnl_usdt < 0`, breaks on the first non-negative.
**GLOBAL, not per-sleeve. PERSISTED** (saved runtime.py:4784 `[-200:]`, reloaded 4752) — a restart
or deploy does NOT reset it. Only a winning convex close resets it.

**Do NOT re-enable the throttle.** +$47.70 over 75 days, but era A **-$229** / era B +$137,
pre-funded **-$89** vs funded +$108 (**the entire gain IS the drawdown under review**),
ex-top-5%-by-delta **-$269**, order-permutation P=0.161 with a shuffled median of **-$173**.
Agrees with two prior methods already in the record.

**LEVERAGE IS AN OUTPUT, NOT AN INPUT.** trend.py:171-186 / wildcard.py:284-298, same algorithm:
`lev = min(cap, floor(0.20 / sl_frac))` where `sl_frac = 3.0 x atr_pct`. **Verified exactly on
85/85 ledger rows carrying `sl_frac_designed`.** The new trade: 0.20/0.024767 = 8.07 -> 8.
**"Leverage >= 7" is arithmetically "designed stop <= 2.86% of price", i.e. atr_pct <= 0.952% — a
LOW-VOLATILITY FILTER, not a risk setting.** Live strata now read lev 7-10 = **+0.4220R (n=17)**,
the BEST bucket, and the >=7 bucket flips sign under ex-top screening in both directions.
**MARK "leverage>=7 reliably loses" SUPERSEDED — not reversed, n is too small for that; void.**
(docs/daily_audit.md:1494 and DECISION_RULE.md:2329-2333 already said this.)

**Do not set the drawdown brake.** 10 cells, all negative, best -$30.51/mo, family-wise P=0.486.
`FUTURES_CONVEX_DRAWDOWN_BRAKE` is UNSET, so the convex sleeves have no equity-drawdown path at
all. `USE_DRAWDOWN_KILL=1` and `IGNORE_HALT=True` are live but unreachable from the convex path.

**Do not touch `FUTURES_WILDCARD_RISK_PCT`.** Two agents proposed cutting it; both verifiers killed
it. There is no compliance breach — the trial primary is a **mean** test (realised 1.943%, inside
[1.6%, 2.2%]) and the per-trade guard is 3.0% (max observed 2.444%). Cutting to 0.0200 scales the
whole book -17%, contaminates trial 19 mid-flight, and drags the mean to ~1.61%, toward the trial's
own "<1.5% -> halt and audit" trigger.

**CONFIRMED, and it reprices old work:** runtime.py:1762 (VERIFIED IN FILE)
`margin = risk_pct * available_balance * 100.0 / sl_margin_pct` — **risk is a fraction of FREE
MARGIN, not equity.** Consistent with the already-recorded fact that the sleeves compete for
`available_balance`, but it means **"halve one sleeve, leave the other alone" is not achievable** —
freeing margin on one sleeve raises the other's dollar risk. Live dial is 2.41%.

### 4. IS THE DRAWDOWN NORMAL? YES — 10.2%, the HOLD band

**P(an 11-fill path <= -$95.15) = 10.2%** under the sleeves' own measured distributions (200,000
bootstrapped paths at the observed risk-fraction distribution; 11.4% all-live WILDCARD).
**If both edges are exactly ZERO, 19.0%.** Independently reproduced: z=-1.25, P~10%.

Marginals: **TREND's -0.966R over 7 is the 27th percentile of its own seven-draw distribution —
utterly ordinary.** WILDCARD's four consecutive full stops is the 3rd percentile of a four-draw
distribution whose floor is -4.4R; unconditionally, four straight losses at a 43.4% win rate is
**10.3%**.

**"Nine of the last ten are losses" computes to 1.4% and is INADMISSIBLE** — it is the worst window
selected post hoc out of 11 fills. My own framing; it is the n=11 trap and I walked into it.

Pre-stated rule was hold at 20%+, reduce at 2%. **10-19% is the hold band, nowhere near reduce.**

### 5. THE DECISION, RANKED

| # | action | $/month | verdict |
|---|---|---|---|
| 1 | **Hold everything** — entries, exits, sizing, leverage, sleeve enablement | 0 | **DO** |
| 2 | **Telemetry fix** to `_convex_streak_multiplier` (2 lines, no behaviour change) | 0 | **DO** |
| 3 | **Log, decision-free:** fair AND last price at each poll and at the exit fill; the 1s fair peak series; scan-instant price alongside the last closed bar's close | 0 | **DO** |
| 4 | pause WILDCARD | +$1 measured / +$106 hostile | NO — sets 19F's fill count to zero; the verdict never arrives |
| 5 | halve WILDCARD only (code) | -$23 to +$54, midpoint ~$0 | NO — sign is a coin flip, estimate dragged by the four losses under review |
| 6 | halve the shared dial (env) | -$61 | NO — a risk-tolerance purchase, not P&L |
| 7 | arm the trail below 1.0R / breakeven stop | -$5 to -$76 | REFUTED |
| 8 | re-enable streak throttle / cap leverage / set drawdown brake | -$30 and worse | REFUTED |
| 9 | scan 900s -> 300s | screened floor ~$5-7 | PARKED — below the bar; shadow-measure first |
| 10 | pause TREND | -$139 | NO — and drawdown gets WORSE |
| 11 | pause everything | -$137 forgone | capital decision only, below the halt level |

**Item 3 is the one with real value.** 17 of 27 live TREND closes are `EXCHANGE_CLOSE`, an exit
path no harness models — **which is WHY no TREND replay is calibratable and every dollar figure in
this review is comparative, not absolute.** Logging the fair/last pair at the exit fill is the only
route to an absolute TREND number.

### 6. THE ENTRY-PRICE LEAK (new, entry-side, not yet a proposal)

Trade 7 stopped out $1.41 below its stop and was back above its entry **31 minutes later**. But the
reason the stop was reachable at all is that **the 900s scan filled 24 minutes late and 1.85% above
the first gate-true bar.** Across all seven funded fills that latency gave up **+1.668R (~$42)** of
entry price. This is the same quantity the 900s->300s candidate measures, and it is why that
candidate keeps scoring positive on the point estimate while failing the ZEC screen.

### 7. THE PRE-REGISTERED HALT

**At 2.41% of free margin with blended sd 1.49R and ~78 fills/month, NO equity-drawdown level
discriminates edge failure from noise inside a year.** Median 3-month max drawdown is ~33% and
P(>=50% within 12 months) is ~48% **with** the measured positive edge. Any floor above ~50% fires
on a healthy path. Therefore:

- **STATISTICAL TRIGGER (this is the halt):** at n=25 post-deposit book fills, recompute the
  envelope percentile of the realised path against the PRE-FUNDED sleeve distributions.
  **< 2% -> halt and audit. >= 20% -> hold. Between -> recompute each fill, do nothing.**
  Current reading: **10.2%**.
- **CAPITAL FLOOR:** a risk-tolerance decision only the owner can make. Set it now, in dollars,
  while it is far away — and set it below -50% or accept that it fires on a healthy path.
- **19F runs to its 20-fire verdict (~2026-10-05) untouched.** Three of the four funded WILDCARD
  losses are exactly its target failure mode.

### 8. THE REPORTING LESSON — the most valuable output of this pass

What should have been said yesterday:

> "Six funded fills: **+$15 +/- $94** (1 s.e.), t=0.03. That is zero. There is a ~41% chance the
> next single fill flips the sign. The reason to ship nothing is the 670 tested cells, not the +$15."

**STANDING RULE FROM HERE: never headline a signed dollar total whose standard error exceeds it.
Report the interval and the flip probability, or report only the decision.**

Two corollaries. (1) I reported a point estimate, buried the interval on the one line the owner was
most likely to remember, and then attached a causal story ("the gap is in the exits") to it.
(2) **1R = $25.16 is itself a point estimate doing more work than it should.** Actual funded
`risk_usdt` ran **$11.28-$28.33, mean $22.6**, so every monthly figure in this review reads ~10%
high. Irrelevant to the rankings; relevant to anything near the $10 bar — which is the 300s scan
candidate, and it falls below it.

---

## 2026-09-09 (third pass) — the owner pushed back on the ATH refutation. He found a real effect I missed. It is not tradeable, and I owe him three retractions.

**Trigger:** owner rejected the ATH refutation, said 18F/19F proved it, and asked for a
DIFFERENTIATED STRATEGY (not a veto). 3 agents / 3 adversarial verifiers / 3 independent corpora /
~1,300 priced cells.

### RETRACTIONS FIRST

**1. My sample was 5.5x under-powered in exactly his cell, and I stated seven refutations more
strongly than it supported.** Of the 389 fills in the 357-day ZEC/ETH/XRP replay, only **24 (6.2%)
sit post-peak of a run that subsequently ended** — the cell where the damage lives — against
**34.5%** in a purpose-built corpus of completed parabolic runs. It was not blind (45 fills, 11.6%,
sit in the final 20% of an ended run, reading +0.056R vs +0.508R for the first 80%) but it was thin.

**2. I used the re-entry-depth study as a club and it does not reproduce.** I told him the n=556
replay "directly contradicts" him (depth 3+ = +0.814R, t=+4.29). On 5 years / 106 symbols that
headline cell returns **+0.0058R, t=+0.11**, and **-0.18R** in the 2026 era. Withdrawn. **Strike
the re-entry-depth reversal from the usable record — it is fragile in both directions.**

**3. My scope was wrong.** He said differentiated STRATEGY; I tested vetoes, half-sizing and
ROC/RSI caps seven times. **Handling the trade differently once open had never been tested.** His
structural argument was also correct: every entry filter this month raised mean R and destroyed
dollars by deleting 20-82% of fills, and an exit rule deletes zero. That was the right place to
look and I did not look there.

### THE EFFECT HE FOUND IS REAL — and I missed it in seven prior passes

**Within a run, later entries genuinely do worse.** Mean within-run Spearman(entry price, R) =
**-0.3523** (se 0.0085, **t = -41.68**) over 2,131 causally-identified runs / 16,961 fills on a
5-year 106-symbol sample; -0.3035 (t=-30.97) on the 1,017 runs with >=7 fills, matching his n;
-0.2374 (t=-8.22) independently on a 360-day 42-symbol sample. Permutation p<0.001 in all four cuts
against a null mean of +0.0003.

My own pooled tabulation had said trades 1-7 are flat (slope +0.0068 R/ordinal, P=0.32). **That was
confounded by run length** — trade_n=1 draws from every run including one-trade runs; trade_n=7
only from long ones. On BALANCED panels (runs with a complete 1..L sequence) it is unambiguous:
L=4 slope -0.338 (P=0.0010, 36 runs), L=5 -0.324 (P=0.0003, 34), L=7 -0.154 (P=0.0022, 34),
L=10 -0.076 (P=0.0063, 30).

**Post-peak fills earn -0.164R against +0.473R pre-peak (n=11,329 vs 5,974).** Large and real.

### WHY IT CANNOT BE HARVESTED — SIMPSON'S PARADOX

**Within a run: later = WORSE (rho -0.35). Pooled across runs — the only view available at entry
time: later = BETTER.** Spearman(pct_since_run_start, R) = **+0.0317 (t=+6.84)** wide and
**+0.0943 (t=+6.64)** fine; fire72 +0.049/+0.133; seq_n positive.

To act on within-run rank you must know at entry whether THIS run will be long. A 7th firing in a
strong run beats a 1st firing in a weak one. **Post-peak is defined by the peak. Final-ness is not
causally observable.** Every causal proxy is a mixture of the harmful final firing with continuing
runs, and the mixture prices **-$91.5/mo** on his own book.

### HIS SEVEN DO NOT SCORE AS MATURE

- **All seven share ONE causal run anchor** (2026-08-16, last daily close <= daily SMA20, close
  486.14). Every run-anchored measure is a monotone relabelling of the calendar inside his window.
  **Spearman(price, time) = +0.964** — at n=7 price and the clock are the same variable and cannot
  be separated even in principle.
- Gain-since-anchor at his entries: **+113/+122/+135/+147/+152/+148/+154%**. A **>=100% maturity
  gate fires on all seven, including the +$75.37 winner.** The only cut that splits them is >=140%,
  which inside one run is arithmetically "ZEC >= 1166" — a price threshold read off the seven
  observations meant to justify it.
- On causal measures that are not pure clock, **his deepest entry is his LOWEST-priced trade**:
  fill #1 at 1036.54 scores runbars 156, run_pct 0.269, run_r 4.28 — the most mature of the seven.
- Extension-over-SMA20 ordering (41.4/37.0/44.9/52.4/55.6/41.2/39.5%) is non-monotone and would
  block winner #1 while allowing losers #6 and #7.
- **nhseq reads [1,1,2,2,1,2,0] — the best rule the entire exit study produced fires on ZERO of
  his seven.**

### THE RUN DID NOT END — verified independently on MEXC daily bars

    2026-09-06  close 1226.83  high 1255.97
    2026-09-07  close 1139.29  high 1229.91
    2026-09-08  close 1177.16  high 1211.66
    2026-09-09  close 1233.73  high 1265.18   <- NEW ALL-TIME HIGH AND NEW ALL-TIME CLOSE

**Trades 4-7 did not buy an exhaustion. They bought a three-day ~12% shakeout inside a run that
made a new all-time high today.** There was nothing for any lookahead-free detector to see on
09-06 09:26 because nothing had happened.

### THE ATH LABEL — REFUTED FOR THE 8TH TIME, now on a sample that CAN see exhaustion

5 years / 106 symbols, containing 11,560 fills followed within 30 days by a -30% drawdown:
**ATH entries +0.1349R (n=773) vs -0.0481R (n=46,603).** The label is a POSITIVE marker.
On his own seven, six of seven are new all-time closing highs including both winners; under the
high definition five of seven including both winners. Any veto keyed on the label keeps the loser
and deletes the +$75.37.

### THE EXIT-SIDE HYPOTHESIS — his actual proposal, tested for the first time, NULL

| construction | best cell | null |
|---|---|---|
| 306 cells (18 causal maturity defs x 17 exit levels), 344 fills, live universe | **+$13.5/mo** | family-wise permutation **median +$13.3/mo**, p=0.48 |
| 280 cells, fine sample | +$14.5/mo point | **-$32.4/mo ex-top-5%-by-delta** |
| 648 cells x 6 maturity states, 17,303 fills | best cell is the IDENTICAL cell in every state, and pays MORE on the non-mature complement in all five | FWER **p >= 0.99** |

**The grid maximum EQUALS the null median.** And the killer nobody ran until verification —
**walk-forward selection** (pick the best cell on the training fold, score on held-out):

    select era1 -> era2   -$8.9/mo     select ex-ZEC -> ZEC   -$16.8/mo
    select era2 -> era1    -$0.0/mo    select ex-ETH -> ETH    -$5.4/mo
    expanding folds  +$6.9 / -$11.8 / -$41.4    select ex-XRP -> XRP   -$0.0/mo
    mean -$15.4/mo, negative in 7 of 9 folds

Entry-shift placebo removes the effect at a **one-hour shift** (-$1.3, +$7.7, -$1.7, +$3.6, -$0.1).

**The degeneracy trap does NOT apply here** (checked first, as required): 0 of 306 cells degenerate,
because the regime is assigned at ENTRY from a causal feature, so the two regimes govern disjoint
trade sets. Unlike the path-state hybrid where every peak passed through the tight regime. The
study was legitimate to run.

**Is it the refuted early-arm in disguise? FOR THE TRAIL, YES, decisively.** His four losers peaked
at **0.2195R, 0.0877R, 0.4855R, 0.1168R**. A trail acts only at or below peak, so touching all four
requires arming **below 0.088R**. Arming below 1.0R was refuted at 54 of 55 cells and reproduces
here (unconditional arm 0.75 -$16.1/mo, 0.50 -$66.8, 0.30 -$103.3). **Conditioning changes WHICH
trades a rule touches; it cannot change the fact that the rule must fire below the peak to act.**

The clock and TP are genuinely different levers, not the early-arm, and they are null. **Every
"bank earlier when mature" cell is negative** (TP 3R->1.5R at atr_ext>=4: -$10.0/mo t=-2.45;
pct_since>=0.30: -$4.3/mo t=-2.27). **The only positive direction is holding LONGER, which dies on
the tail screen. His proposed cure points the wrong way.**

**Every unconditional tightening is negative:** arm 0.30/0.50/0.75 = -$103.3/-$66.8/-$16.1;
retain 0.60/0.70/0.80 = -$14.7/-$40.0/-$44.8; TP 1.0/1.5/2.0/2.5R = -$111.2/-$91.0/-$56.8/-$20.2;
clock 3/6/9/12h = -$87.0/-$47.2/-$43.5/-$21.5. **The live stack is at or near a local optimum on
every axis. That is the strongest single result in the pass.**

Entry-side on his own universe with slot re-allocation: veto trade_n>=4 (his exact shape)
**-$91.5/mo** (deletes 144 of 345 fills); veto gain>=100% -$23.7; fitted gain>=140% -$10.1;
age>=336h -$41.9; no-new-high>=48h -$14.7; half-size gain>=100% -$18.0; half-size trade_n>=4
-$40.6; size-neutral early-run tilt +$3.2 point but **-$35.2 ex-top-5%-by-delta**, permutation
p=0.853 with a null mean six times the observed.

### THE BASE RATE — 1 in 10, not 1 in 35, and an earlier pass got this wrong AGAINST him

"The four highest prices are the four worst R" has exact base rate 1/C(7,4) = **2.9%**. Corrected
for time clustering: circular-shift p = **1/7 = 0.143**, the FLOOR attainable at n=7 (the test is
unpowered by construction). Measured empirically: **P=0.065** over 46,740 seven-fill windows,
**P=0.0845** over the 142 windows matching his exact configuration, **6 of 40 complete 7-trade run
sequences = 15%**. **N ~ 35 raw, N ~ 7-12 once clustering is honoured. Where an earlier pass told
him 1-in-5040, that was wrong and wrong against him.**

### THE PHENOMENON ITSELF IS OPEN — and the two verifications disagree. Not papered over.

- **Verification 1** built a structureless random-walk null carrying the same run partition and
  found the within-run rank statistic returns **-0.30 to -0.32 MECHANICALLY**, against observed
  -0.35 wide and -0.24 fine. A run is a maximal excursion above the MA, so it ends in a breakdown
  by construction; ranking a fill against its own run's later members is itself a lookahead
  quantity. **~85-90% of the "strong effect" is partition arithmetic, and the fine sample is WEAKER
  than pure noise.** The label-shuffle null holds the partition fixed and is blind to this.
- **Verification 3** built an unselected 561-symbol daily corpus (13,311 fills, 6,211 runs, no gain
  filter) and found the pooled causal ordinal monotone negative from the second firing:
  **+0.331, -0.087, -0.128, -0.214, -0.233, -0.266 (n=10,092)**. It also demolished the
  "front-loaded, no bucket negative" reading as an artefact of a corpus restricted to runs that had
  already doubled.
- The 106-symbol hourly sample returns the **OPPOSITE SIGN on the same pooled statistic**
  (+0.030 to +0.125 across seven measures, both cuts, all positive).

**Two independent unselected samples, one statistic, opposite signs.** Universe-dependent effect or
noise; I cannot tell which. It does not change the decision.

### WHAT SHIPS: NOTHING

Closest four, for the record:

| # | candidate | $/mo | deleted | env/code | why not |
|---|---|---|---|---|---|
| 1 | nhseq>=3 -> clock 12h | +13.5 pt | 0 | code (3 call sites + new feature + migration) | = null median; walk-forward -$15.4; fires on 0 of his 7 |
| 2 | fire72>=5 -> arm 2.0R | +14.5 pt | 0 | code (global arm covers WILDCARD too, -$62/mo) | -$32.4 ex-top-5%-by-delta |
| 3 | hours-since-run-start >=72h veto | +3.2 excess | **28% of fills** | code | FWER p=0.138, below placebo median; +$2.1 cross-sample at p=0.91 |
| 4 | his fitted gain>=140% separator | **+$579 in-sample / -$1.1 out** | 653 | code | **130x fit-to-forecast gap** |

**DO NOT SHIP the tempting one:** clock 6h unconditionally scores **+$25.47 on the funded five**,
driven almost entirely by the 09-06 17:38 fill. The same rule across 344 fills is **-$47.2/mo**.

**Telemetry — the only thing worth doing, and NOT today.** The causal maturity vector is computable
at the scan instant at zero behavioural cost: run_anchor_date/close, age_hours, gain_since_anchor,
trade_n, fires_since_anchor, hours_since_prior_new_24h_closing_high, ext_over_daily_sma20,
atr_pct/30d-median, swing_low_break. Two conditions: (a) it is a code change on the write path of a
live trial — bundle it with the fair/last exit-fill logging and do both AFTER 19F's verdict;
(b) **record only pooled, entry-time statistics. The within-run rank statistic must never be logged
without its random-walk null (-0.30) attached**, or at n=100 it will read strongly negative
whatever the market does and this argument runs an eighth time.

### FALSIFICATION — pre-registered now

**One statistic: the slope of R on the POOLED CAUSAL trade_n for in-run TREND fills.** Not the
within-run rank correlation. With sd(R)=1.49, sd(trade_n)=2.09 over ordinals 1-7, 48.3 TREND
fills/month and ~62% inside a run:

    -0.429 R/ordinal (what his seven imply)  -> N=13   -> ~2 weeks
    -0.25                                     -> N=33   -> 1.1 months
    -0.15 (the corpus value)                  -> N=91   -> 3.0 months, verdict ~2026-12-10
    -0.10                                     -> N=204  -> 6.8 months

**Decision rule, declared now:** at N=91 in-run TREND fills, a slope <= -0.15 with t <= -2 reopens
the **early-run UPSIZE** question only — never a late-run veto, never a rule keyed on run length,
because every actionable deletion has already priced between -$10 and -$92 on this book. Otherwise
the line closes at the $10 bar.

---

## 2026-09-09 (fourth pass) — owner's two proposals: RSI_MAX and a symmetric per-symbol cooldown. BOTH REFUSED. And a finding that outranks them: TREND is not measurable at this n.

**Asked:** sweep `FUTURES_TREND_RSI_MAX` over trials 17-19F and pick the correct value; and test a
TREND-only cooldown (>1 loss in 24h -> 12h; >2 wins in 24h -> 12h). 3 agents / 3 verifiers.

### TWO ERRORS OF MINE, CORRECTED FIRST

**1. My RSI reconstruction was wrong in the direction that mattered.** I told the owner the losers
sat at RSI 55.3 and 53.6. The exact `_rsi` is **Cutler/SMA-14 on Min15 INCLUDING the forming bar,
not Wilder** (`wildcard.py:170-176`). Correct values:

| fill | entry | RSI | R |
|---|---|---|---|
| 1 | 1036.54 | 75.7 | -0.206 |
| **2** | 1077.87 | **90.2** | **+3.016** |
| **3** | 1140.35 | **83.9** | **+0.419** |
| 4 | 1199.51 | 67.5 | -1.022 |
| 5 | 1224.50 | 73.7 | -1.044 |
| 6 | 1205.82 | 73.4 | -1.048 |
| 7 | 1234.00 | 75.3 | -1.100 |
| 8 (open) | 1253.38 | 76.6 | — |

**There are NO low-RSI entries in the book. The two winners carry the two HIGHEST RSIs.**
Spearman(RSI, R) = **+0.68** on the owner's own fills. All 17 live TREND entries: 74.49, 74.35,
59.02, 85.72, 89.11, 54.99, 77.43, 91.05, 80.58, 83.48, 75.67, 90.19, 83.91, 67.48, 73.75, 73.43,
75.34. Winners mean 79.5 (n=7) vs losers 75.3 (n=10). **The lowest-RSI signal in the entire book
(54.99, ZEC 09-03T11:10) was the second-best trade at +2.81R.**

**2. My cooldown hand-trace was wrong by 43 minutes.** At fill 5's entry (09-06T17:38) the trailing
24h contains fill 2 (win), fill 3 (win), fill 4 (loss) = **ONE loss**. Fill 1's close (09-05T16:55)
is **24h43m old, outside the window.** Same on the entry clock.
- **Evaluate-at-scan** (`if losses_24h > 1: skip`, the obvious implementation): the loss leg blocks
  **NOTHING** among fills 1-7. **My -$11.88 -> +$8.50 does not happen.**
- **Latch-from-trigger** (arm at a qualifying CLOSE, hold 12h): the condition became true at fill
  4's close while fill 1's loss was still in-window, latching to 09-07T02:29, which blocks fill 5.
  Then it does happen.
**The entire headline rested on a semantics choice the owner never made, worth 0.9R against a
scan-phase noise floor of sd 1.93R.**

### RULE A — RSI_MAX: THE CORRECT VALUE IS UNSET. Refuted WITH A MECHANISM.

**The mechanism is structural, not statistical.** Gate 2 demands a **new 24h CLOSING extreme**,
which mechanically forces RSI-14 high. **Gate 3 is near-collinear with gate 2 — there is no
operating range between "inert" and "off".** Median entry RSI is 76.4 because that is what the
detector IS.

Swept over 17-19F (15-phase ensemble, forward re-scan):

    cap    95  92   90   88    85    82    80    78    75    72    70
    $/mo    0   0  -64  -81  -100  -208  -234  -251  -344  -295  -366
          inert inert

Independent 358-day replay, shipped 3-symbol universe (n=374): 60 -$88, 65 -$87, 70 -$79, 75 -$38,
80 -$29, 85 -$13, 90 -$16, 95 +$2.7 (touches 1.6% of fills). **Same monotone-toward-zero shape as
the prior wide sweep (70 -$154 -> 90 -$36) on a DISJOINT sample.** Wide n=205: Pearson(RSI,R)
**+0.154 (t=+2.22)**, Spearman +0.213; **the fills each cap removes have a HIGHER meanR than the
fills it keeps, at every level.**

**Walk-forward: every cap negative OOS in both directions.** Forward (train 17+18 -> hold 18F+19F)
-$14 to -$42/mo; the in-sample-best cap 90 (worth exactly $0 in-sample because it never binds
there) forecasts -$35/mo. Reverse -$10/mo. **Expanding folds on the wide book keep selecting cap 95
— i.e. they keep choosing "off".**

**BOUNDARY HAZARD:** fill 2's RSI computes to **89.99** on a Min15 reconstruction and **90.19** on
a Min1 one, and the gate is `rsi >= rsi_max`. **A cap at 90 either costs $0 or costs the whole
+$75.37 tail, decided by a 0.2-point reconstruction difference.** The unswept 90.3-91.9 band is the
only region that could bind without touching fill 2 — and it is locatable only by first looking at
the tail's RSI, so it is fitted before it is measured.

**THE DATA SUPPORTS A FLOOR, NOT A CAP — and it is not shippable.** `trend.py` reads
`FUTURES_TREND_RSI_MIN` but applies it only under `if rsi_min > 0 and s < 0` — **SHORTS ONLY**.
Long-side is a code change deployed into live 19F. Best cell looks like +$58/mo then dies:
**ex-top-5%-by-delta -1.27R (SIGN FLIP)**, LOSO ex-XRP +0.02R (the rule IS XRP, 2 of 17 live
fills), Bonferroni p=0.36 over 18 cells, and its OOS gain rides on phantom sim fills.

**TRAP TO NAME:** caps 55/60 score nominally +$35/mo and **delete 19 of 21 fills.** That is not a
filter, it is "switch TREND off" — a different question, interval [-$155, +$123].

### RULE B — THE COOLDOWN: NULL AT THIS BOOK'S RESOLUTION. Point estimate negative.

Construction: **forward re-scan, NOT row deletion.** `runtime.py:6630` skips a symbol only while
HELD, so a blocked entry frees it and the 900s scan re-fires.
**Delete-only overstates by 2.5x (+$59.6 -> +$23.9/mo on the live window). Across the 108-cell grid
45% of cells are positive under delete-only, only 23% under re-scan.**

| reading | live (fills 1-7) delete-only | wide 358d, re-scan | deleted / created |
|---|---|---|---|
| loss leg only | $0 evaluate-at-scan / +$8.50 latched | **-$0.9 +- $4.7/mo** | 6 / 1 |
| both, **win >=2**, close clock | +$37.00 | **-$15.7 +- $21.6/mo** | 68 / 22 |
| both, **win >2** (his literal wording), close clock | never fires | +$0.1 +- $7.8/mo | 22 / 7 |
| both, win >=2, entry clock | — | -$7.5/mo | 57 / 22 |
| both, win >2, entry clock | — | +$2.8/mo | 11 / 2 |

Named created fills (win>=2, live window): ZEC 09-04T08:49 (+0.655R), ZEC 09-04T08:53 (-1.054R),
ETH 09-03T15:25 (+0.557R), plus six ETH re-entries all stopping at -1.13 to -1.19R.
**One block merely moved the same ZEC stop-out 45 minutes earlier.**

**LOSS LEG: UNTESTED, NOT REFUTED.** Fires 6 times in 358 days, -$0.9 +- $4.7/mo. On the live book
its ONLY firing is **fill 8, which is still open** — no measured cost and no measured benefit.
**RETRACTION within the pass:** one agent claimed post-loss fills are BETTER (the mechanism that
refuted the WILDCARD cooldown). That direction holds only on an unconstrained 3052-fill book and
**FLIPS to the owner's direction on both books matching the shipped 2-slot config.** The loss leg
fails on dollars and firing rate, not on mechanism.

**WIN LEG (>=2) — the genuinely novel idea, given a real test.** Direct conditional, no cooldown
mechanics, n=374/358d: after >=2 wins/24h meanR **+0.069 (n=63)** vs **+0.172** otherwise.
Diff **-0.103R**, bootstrap 95% CI **[-0.42, +0.23]**, p(diff<0)=0.73.
**His DIRECTION is right. The magnitude is unresolvable — and the cell he would delete is still
POSITIVE expectancy, so standing aside only pays if the replacement fill is better. The replay says
it is worse.** Wide re-scan -$16.6 +- $21.2/mo; expanding-fold walk-forward **-$13.23/mo held
out**; LOSO negative in **4 of 5** folds; **ex-top-5%-by-delta -$29.5/mo (removing its BEST month
makes it worse)**. Live-window figures span **-$33.2 to +$23.9/mo across two in-house engines on
the same data** — no live dollar figure is quotable in either direction.

**WIN LEG (>2), his literal wording: never fires on his book** (ZEC's max was exactly 2).
A null by construction.

### MULTIPLICITY — the deciding control

108 cells (loss 1/2/3 x win 2/3/4 x lookback 12/24/48h x cooldown 6/12/24/48h), permutation null
with outcome labels shuffled while slot mechanics stay real:

| | real best-of-108 | null median best | family-wise p |
|---|---|---|---|
| wide 358d | +$8.0/mo | **+$19.0** | 0.86 |
| live 17-19F | +$29.8/mo | **+$32.4** | 0.57 |

**On BOTH samples the real grid best is at or below the median of what pure noise manufactures on
this book.** Zero of 108 cells clears +$10/mo in-sample on the wide book.

### THE OUTCOME-BLIND CONTROL — the most informative number in the study

A 12h cooldown of the **same count, same duration, same symbols, at RANDOM times**: the real
win-leg sits at the **68th percentile** of that null (one-sided p=0.317); second independent run
**70th percentile** (p=0.30).

**It is a duty-cycle cut wearing a rationale. The outcome conditioning is worth NOTHING.** ~90% of
its measured cost is arithmetic volume loss (65 deleted x ~0.15R baseline) — the same
volume-limited signature that killed every entry filter this month.

### THE HONEST SIZE OF THE LIVE EVIDENCE

| trial | span | closed TREND fills | net | quotable? |
|---|---|---|---|---|
| 17 | 08-27 09:32Z -> 09-04 10:57Z | **10** | +$8.83 | 1R was ~$2.73 pre-deposit — **dollars not comparable** |
| 18F | 09-04 -> 09-08 18:18Z | **6** | +$15.36 | the total that flipped on one trade |
| 19F | 09-08 18:18Z -> now (0.7d) | **1** closed + 1 open | -$27.25 | **n=1, no rate quoted** |
| pooled | 13.0d | **17** | -$3.06, SE $94.66 | **not headlined** (reporting standard) |

**The ENTIRE win-leg effect lives in trial 18F alone** — +$119 to +$153/mo there (n~4.5 simulated
fills), exactly $0.00 in 19F, **-$25.0/mo in trial 17.** That is the owner's eight-fill window and
it is the only place the rule looks good. **Every reading flips sign between trial 17 and 18F.**

### THE FINDING THAT OUTRANKS BOTH QUESTIONS — TREND IS NOT MEASURABLE AT THIS n

**13-day sleeve P&L moves from -1.7R to +6.0R purely by shifting the scan clock 60 seconds.**
Same rule at phases 400/600/800s: **+0.352R / -0.458R / +0.530R**, with three completely different
blocked lists.

**The family-wise 5% critical value on this window is +$155/mo — LARGER THAN THE BOOK'S ENTIRE
+/-$60/mo ENVELOPE**, because one fill is worth ~$53/mo at 1R=$22.6.

**No TREND entry filter is measurable at this n until the phase sensitivity is understood.**
Everything in this report — including the owner's +$8.50 — is a fifth of that noise floor.

Fidelity, plainly: 17 of 27 live TREND closes are `EXCHANGE_CLOSE`, a path no harness models; the
sim baseline runs +5.29R where the live book is -$3.06 over the same span. **All TREND dollar
figures are COMPARATIVE, not absolute.** The external gate (`FUTURES_EXTERNAL_GATE_ENABLED=1`) is
not replayable, so every counterfactual book may contain fills the live bot would have refused.

### DECISION, RANKED

| # | action | $/mo IS | walk-fwd | del/created | env/code | verdict |
|---|---|---|---|---|---|---|
| **1** | **Leave `FUTURES_TREND_RSI_MAX` UNSET** | 0 | 0 | 0/0 | env | **the null action — DO** |
| **2** | **Do not ship the cooldown, any leg, any of 108 cells** | 0 | 0 | 0/0 | code | **the null action — DO** |
| 3 | shadow counter only (free) | 0 | 0 | 0/0 | ~3 lines on the existing `_shadow_log_untaken` rail | permitted |
| 4 | win leg >=2, close clock | +$23.9 live / -$16.6 wide | -$13.2 | 68/22 | code | REFUSED — blind p=0.32, LOSO 4/5 neg, sign flips |
| 5 | loss leg | $0 measured | -$0.9 | 6/1 | code | REFUSED — untested, 1 open fill |
| 6 | win leg >2 (literal wording) | +$0.1 to +$2.8 | -$3.3 | 22/7 | code | REFUSED — null by construction |
| 7 | RSI cap 90 | -$64 to -$84 | -$35 | 2.5/1.6 | env | REFUSED — boundary cell, kills or misses the tail on 0.2 RSI pts |
| 8 | RSI cap <=85 | -$100 to -$366 | -$189 | up to 75% of fills | env | REFUSED |
| 9 | long-side RSI FLOOR (the opposite rule) | +$58 | +$26 fwd / +$0.06 rev | 5.1/3.2 | **code + deploy into live 19F** | REFUSED — ex-top-5% -1.27R, ex-XRP +0.02R, Bonferroni p=0.36 |
| 10 | cap 55/60 ("+$35/mo") | +$35 | — | 19/0.3 | env | **TRAP — deletes 19 of 21 fills = "switch TREND off"** |

### WHAT WOULD HAVE TO BE TRUE — and why waiting cannot deliver it

The win leg >=2 is **the only non-noise-shaped direction found on TREND this month** (-0.103R).
Current resolution on the 358-day / 374-fill shipped universe is **+/-$21.6/mo**. Shrinking that to
+/-$10 needs ~4.7x the span — roughly **1,700 days (~4.6 years)** of the shipped universe, or
~1,750 more TREND fills. At ~40-48 fills/month **that is not reachable by waiting.**

**Translation: this question cannot be answered by trading. It can only be answered for free.**

**The one thing worth doing, no dollars at risk:** stamp trailing-24h per-symbol win/loss counts
into each TREND trade row at entry, **both clocks** (the two readings gave -$15.7 and -$7.5 on the
same data). Gate nothing. `_shadow_log_untaken` already exists and is already called in the same
scan path for `slot_occupied` and external-gate vetoes.

Clock choice if ever built: **close clock.** `trade_history` rows are appended at close, the
scoreboard's `ts` comes from `exit_time` (runtime.py:4736), `_last_exit_by_symbol` is already
close-keyed (but holds only the LAST exit, so a count rule needs a `trade_history` scan). No
lookahead in either clock. Ring buffer is not a threat (200 rows span 95 days; a 24h window needs
<15). **One live hazard: if the ledger loss-censoring defect recurs, the loss leg silently
under-counts and FAILS OPEN.**

**Revisit criterion:** win-leg conditional diff < -0.25R with a bootstrap CI excluding zero on
>=400 fills, AND beating its own outcome-blind null at p<0.05, AND surviving LOSO on ZEC.
Not before 400 TREND closes.

### ESCALATION — do this before any further TREND entry study

**Fix the scan-phase sensitivity.** A sleeve whose 13-day P&L swings 7.7R on a 60-second clock
offset cannot price a filter worth 0.9R. This now outranks the ATH/maturity follow-ups and the
universe-rotation idea, because all of them would be measured on the same unstable baseline.

---

## 2026-09-09 (fifth pass) — regime forensics on 18F/19F. My chop hypothesis was BACKWARDS. Nothing is broken. One real defect: trial 19F cannot answer its own question.

**Trigger:** 9 consecutive losses, funded book -$118.83 over 12 fills. Owner asked for the MARKET
characteristics of 18F/19F to find a regime the bot is bad in. 3 agents / 3 verifiers / ~20 a-priori
market variables per search.

### MY HYPOTHESIS WAS WRONG AND THE SIGN WAS REVERSED

I proposed the funded era was CHOP and the book needs market-wide trend. Built from market data
before any P&L:

| measure | funded window 09-04 -> 09-09 | percentile vs trailing year |
|---|---|---|
| BTC 14d Kaufman efficiency | 0.074 | **3.6th** |
| BTC 24h realised vol | 0.0107 | 15th |
| BTC ADX14 / 20d realised vol | 47.2 / 0.504 | 94th / 88th |
| **ALT/BTC, 6-day net** | **+10.8%** | **97.8th** |
| equal-weight alt index 7d | +13.8% | 95.6th |
| cross-sectional alt correlation | 0.393 | 39th (DISPERSING) |
| BTC 24h Kaufman efficiency (intraday) | 0.181 | **47th — dead average** |

**This was an ALT-SEASON MELT-UP on a stalled, high-volatility BTC. "Quiet index, live alts."**
Calling it chop is true only of BTC's own path; false of the alt tape, false of breadth, false of
dispersion, and false of the one symbol that carried half the book.

**And the sign is REVERSED: the book's entire lifetime R was earned in LOW-BTC-efficiency tape**
(pre-funded meanR **+0.404 in chop** vs **-0.004 out of it**).

**THE DECISIVE EXHIBIT:** the book was **LONG ZEC through a +32.7% five-day move** — the 88th
percentile of ZEC's own 200-day distribution — **across seven fills, and netted -$11.88.**
Ex the +$75.37 tail it is -$87.25. **That is not a book hurt by chop. It is a book failing to
convert the strongest symbol move in its funded life.** That is a CONVERSION question, not a
regime one.

### THE SLEEVE DECOMPOSITION — the single most useful line, and no agent headlined it

| sleeve | fills | wins | P&L |
|---|---|---|---|
| **WILDCARD** | 5 | **0** | **-$106.95** (every one ~ -1.06R, a full stop-out) |
| TREND (7x ZEC LONG) | 7 | 2 | -$11.88 |

**90% of the funded drawdown is ONE sleeve, and that sleeve was measured 2026-09-07 at +0.077R,
t=0.36 — a coin flip.** P(a 43.4%-win coin flip goes 0 for 5) = **0.058**.
**There is no market state to find inside a coin flip.**

The owner's three counter-examples all land and kill "needs market-wide trend" outright: PONS and
MARSCOIN were SHORTS into a falling tape; ZEC 09-06T09:26 lost on the third-strongest major tape in
the sample. **Correction to one rebuttal:** the historical "SHORT into falling majors" cell is
**UNMEASURED, not favourable** — 17 of its 19 rows sit inside the loss-censoring window and the 2
clean rows mean -0.825R. The story fails for absence of evidence, not contrary evidence.

### THE STREAK IS ORDINARY — it was overdue

Loss rate 0.5721 on the deduplicated corpus (n=201):

| | |
|---|---|
| P(the next 9 fills all lose), naive | 0.66% |
| **P(a run of >=9 losses somewhere in 137 fills)** | **31.3%** |
| **P(a run of >=9 somewhere in 201 fills — the book's observable life)** | **42.9%** |
| P(>=9 somewhere in 400 fills) | 67.9% |

**The longest run already in the corpus is 8.** Nine is one past something the book has already
done.

**P(funded path <= -$118.83): 18.6% if both sleeve edges are exactly zero; 4.0% if you credit the
measured pre-funded edge.** The WILDCARD verdict says the edge is not there, so **18.6% is the
number to carry.** Adding the 12th fill moved the edge-on reading 10.2% -> 4.0% and barely moved
the zero-edge reading 19.0% -> 18.6%; **that gap IS the edge being credited, and it is the
assumption doing the work, not the data.**

P(<=2 wins in 12) = 5.8% at the corpus rate, 1.15% at the actual sleeve mix. **But the honest
denominator is not 12: seven of the twelve fills are ZEC TREND LONG re-entered across three days.
Clustered at 36h this is 7 bets with 1 win, P = 6.3-7.5%. The funded era is closer to n=2
independent decisions than n=12.** Nothing here is below 1%.

### NO REGIME EFFECT SURVIVED — and none ever can on this book

- **"Book needs the majors up":** majors-avg-24h <= 0 gives meanR **+0.206 IN vs +0.205 OUT,
  p=0.998. Literally identical.** Trading AGAINST the majors prices better (+0.262R, n=39) than
  with them (+0.182R, n=98).
- **"Directionless BTC":** sign REVERSED (above). And the two a-priori operationalisations of
  "directionless" agree on only 58% of fills (phi 0.154) and give **opposite-signed gaps**, both
  p>0.28. **The concept does not survive its own restatement.**
- **Best single candidate anywhere** (BTC 24h realised vol below its 400d median): fails FWER
  (p=0.0004 vs a required 0.00034 on a 146-cell grid), collapses under block permutation (0.026),
  retains a third to a half of its effect under a **6-hour entry-shift placebo**, halves
  ex-top-5%, **deletes 66% of fills**, and **deletes the +$75.37 fill that is the entire funded
  upside.** Walk-forward +$32/mo against a **+$155/mo family-wise critical value.**
- Every gate version measured costs **$19-$314/month of forgone realised R** while deleting 65-74
  of 137 fills.
- **Selection floor:** with 2 wins in 12 the exact permutation floor is 1/C(12,2) = **0.0152**.
  No variable CAN score better on this window. Exactly 1 of 20 hit it. Sidak FWER on best-of-20 =
  **0.264. The funded sample is arithmetically incapable of selecting a regime.**

### THE STRUCTURAL CEILING — this closes the regime question permanently

Power arithmetic (sd(R) ~ 1.30, 80% power, alpha 0.05, 45 fills/month):

| detectable gap between arms | fills needed | months |
|---|---|---|
| 0.42R | 300 | 6.7 |
| 0.30R | 589 | 13.1 |
| 0.20R | 1,325 | 29.4 |
| 0.10R | 5,300 | 118 |

Inverted against the $10/month bar: **a gate clearing $10/mo while deleting half the fills needs a
per-deleted-fill gap of 0.020R. That needs ~21,000 fills — FORTY YEARS.** Run the other way: the
SMALLEST gate this book can ever verify (0.42R over half the fills) would be worth **~$214/month —
three and a half times the book's entire +/-$60/month envelope.**

> **There is no gate that is simultaneously large enough to detect and small enough to be
> plausible. This is a structural ceiling on every regime study at this account size.
> STOP COMMISSIONING THEM.**

On independence: a market-wide gate WOULD be a distinct lever (corr with BTC vol -0.048; the sizer
reads the traded symbol's own 6h efficiency, not the market's). But the already-measured
`regime_trimmed`/`chop_regime` AVOID conditions key on `regime_size_mult` itself and are **100%
double-counting the sizer**, exactly as the memory note suspected. Do not touch the scaler.

### THE EARLY-STOP WINDOW — the misses are the rule working as specified

**Historical WILDCARD median time-to--0.5R is 53 minutes. T=30 sits BELOW the median and catches
only the fastest 24-31% of fills. P(miss both live opportunities) = 0.48-0.58** (0.81 on the
all-minutes denominator). **Missing both is the MODAL outcome.** Three of the five readings are
TREND, a **2.3x slower clock** (median 120 min) where the rule is deliberately off.

**Is it regime? No — refuted three times:**
1. Adverse crossings were **FASTER** in the funded era, not slower (median 196 vs 407 min on ZEC;
   242 vs 629 on ATOM). **The premise runs backwards.**
2. No market-state variable predicts t50 — 9 variables, max-statistic permutation, **all FWER
   p > 0.43**. Mechanically expected: the stop is ATR-scaled at entry, so t50 measures traversal of
   a vol-NORMALISED distance and market vol largely cancels.
3. **MAGMA, a funded-era WILDCARD fill in this exact tape, crossed -0.5R at minute 7. FORM at
   minute 13. Both would have fired.** They simply arrived before the flag was armed on 09-08.

**STRUCK — do not carry forward:** one agent found a vol link (58.8 min low vol vs 30.7 high,
p=0.016). Its verifier killed it: the detector used **intrabar wick first-touch, whose bias scales
with volatility — the very variable being contrasted.** On close-basis detection the gap collapses
from +28.1 to +11.0 min and p goes 0.016 -> 0.254. **Specifically do not later build a vol-scaled T
on top of this.**

**What T the data implies — INFORMATION ONLY, not a recommendation.** Live readings imply T>=42 to
catch both misses. The historical grid says that is the worst available move: **T=30 +$130.9/mo,
T=45 -$127.9/mo** (-$105/mo ex-ENA, which is 91% of the raw figure). **T=20 prices at or above
T=30, so T=30 is a PLATEAU MEMBER, not a fitted peak** — a better reason to leave it frozen than
the one originally given. The supporting "30-45 min is the best band" mechanism is **91% one trade**
and should be deleted from the record, not repeated.

### THE ONE REAL DEFECT — TRIAL 19F CANNOT ANSWER ITS OWN QUESTION

Fire rate 12/50 = **0.24**. The stop rule **"30 WILDCARD closes OR 45 days, whichever first"**
delivers **~7.2 expected fires against a primary criterion requiring 20.** At the observed 2.25
fills/day the 30-close arm triggers **~2026-09-22** and the trial terminates unable to evaluate
itself. **P(reaching 20 fires inside 30 closes) = 0 BY CONSTRUCTION.**

Dropping the 30-close arm leaves 45 days x ~2/day x 0.24 = **21.6 expected fires against 20
needed — a knife edge.**

**This defect was pure arithmetic knowable on 09-08 before the flag was set.** That is why an
amendment is defensible at all.

### THE HALT READING AT n=12

Realised path sits at the **3.99 percentile** of the pre-funded envelope under the measured-edge
prior, and **18.6%** under the zero-edge prior. Trigger: <2% halt, >=20% hold, else recompute.
**Both readings are in the do-nothing band. Trigger unmoved, verdict still at n=25.**

Uncomfortable half said out loud: under the OPTIMISTIC prior the path is nearer the halt than the
hold, and **two more full-size losses drop it through 2%.** Under the honest prior it reads 18.6%
and is nowhere near firing. **The trigger's reading is currently driven more by which prior you
credit than by the trades.** Note it; do not change it mid-trial.

### DECISION, RANKED

**1 — DO NOTHING to trading. Keep trading.** No regime gate, no halt, no change to the size scaler,
the streak throttle, X or T. Every gate prices at $19-$314/mo of forgone realised R, deletes 48-66%
of fills, kills the tail, and none clears its multiplicity bar. **The correct response to a
43%-probability event is to keep the sample coming.** $0/month, highest-value option on the board.

**2 — AMEND trial 19F's stopping boundary. OWNER'S CALL — documentation only, no env var, no code,
no deploy.** Replace "30 WILDCARD closes or 45 days, whichever first" with **"45 days"**, dropping
the 30-close arm. Log as an **AMENDMENT WITH REDUCED EVIDENTIAL WEIGHT**, dated, with the reason —
**not as a costless clarification**: two non-fires have been observed and they prompted this study.
**Add the omitted fallback: if fewer than 20 fires have accrued at day 45, report the running delta
at whatever n was reached as DESCRIPTIVE ONLY, and do not let a partial-n positive delta be read as
a pass.** This is the only item that buys time-to-verdict.

**3 — RECORD, do not act: concentration.** 7 of 12 funded fills are ZEC TREND LONG. The funded
window is ~7 clusters, not 12 bets. Belongs to the allocation question, not the regime one.

**4 — RECORD, do not act: two retention-invariant breaches.** PONS peak +0.965R -> closed -1.08R;
ZEC 09-09T04:39 peak +0.848R -> closed -1.10R. Each built ~a full R and returned all of it plus a
stop. Owner's own a-priori rule, so flagging is compliance not pattern-fitting. But n=2, inside the
noise floor, and early banking is already measured harmful (floor-not-bank). **Price on the wide
corpus before anything is touched, and not this week.**

**5 — REJECTED: any market-regime entry gate.** Costs above, and per the ceiling no such gate is
verifiable at this account size in principle.

**6 — REJECTED: halting the book.** The pre-registered trigger has not fired on either prior.

### THE OPEN LEAD WORTH MORE THAN THE REGIME QUESTION

**The book was long the strongest symbol move of its funded life and netted minus eleven dollars.**
That is a CONVERSION question — what the exit stack does with a winner — and it is measurable on
the wide corpus without touching anything live. It now sits alongside the scan-phase sensitivity as
the highest-value open item.

**FINAL: nothing is broken. This is what a 43%-probability streak looks like in a coin-flip sleeve.
The only defect found today is a stopping rule that made trial 19F unable to answer its own
question.** No claim is made that anything here clears the $10/month bar in either direction,
because on a window this short the family-wise 5% critical value is **+$155/month, larger than the
book's entire envelope.**

---

## 2026-09-09 (sixth pass) — the full WILDCARD gate surface priced. NOTHING SHIPS. The grid is closed permanently, and I quoted a retracted number.

**Asked:** enumerate every WILDCARD gate and trigger, and say what fine-tuning is available.
Trigger: **funded WILDCARD is 5 fills, 0 wins, -$106.95, every one a full stop** (peak_r 0.0245,
0.0909, 0.9653, 0.3213, 0.1795 — four of five never cleared 0.33R).
3 agents / 3 verifiers / 437 priced cells.

### MY ERROR: I QUOTED A RETRACTED FIGURE FROM MY OWN INDEX

I told the owner "the standing measurement says the edge is in the LONGS (+0.244R vs -0.225R)".
**That figure was retracted on 2026-08-14** (`DECISION_RULE.md:4178-4182`): `pinned90.pkl` had a
dedup defect, and clean sampling gives shorts **-0.043R (t=-0.79), roughly flat**. It was also an
**ALL-SLEEVE** figure dominated by TREND/PMT — **never a WILDCARD measurement.**

**The memory FILE was already correct.** Its own description says "the -0.225R figure is RETRACTED
and must not be quoted". **The stale object was the MEMORY.md INDEX LINE**, which still carried the
retracted number — and I read the index instead of opening the file. Index line corrected.
**Lesson: a one-line index summary can outlive the correction inside the file it points to.**

### THE COMPLETE LIVE ENTRY PATH (verified at source)

    L1  ENABLED=1, not paused; SCAN_INTERVAL_SECONDS=450; available>0
        slots: MAX_POSITIONS=3, scans anyway when full, PREEMPT_ENABLED=1
        ** runtime.py:6572 `if opened: return` -> AT MOST ONE FILL PER SCAN **
    L2  _USDT ; _is_tradeable_crypto ; sym not open (one per symbol)
        not in top EXCLUDE_TOP_TURNOVER=24 by turnover
        amount24 >= MIN_TURNOVER_USDT = $2,000,000
        24h RANGE >= min_move ; sort by range desc ; movers[:MAX_SCAN=90]
    L3  detect_wildcard_signal, Min15, 672 bars:
        G1 |3h ROC| >= MIN_ROC 0.08 (ROC_BARS=12)   [SIGMA_TRIGGER off]
        G2 PULLBACK-RESUME (REQUIRE_PULLBACK default True)
        G3a RSI_MAX=90 / RSI_MIN=10   G3b MAX_WICK=0.45   G3c VERTICAL_ATR_MULT=2.0
        G4 MIN_VOL_Z=1.0
    L4  rank = (is_deep_lateness in [0.50,0.70), |roc|) desc  ** blind to pullback shape **
        sub-trigger refusal (|roc| < 0.08) ; CALM-SHOCK >= MAX_CALM_RATIO 0.75
        LONG_ONLY=0 -> SHORTS ARE TAKEN ; external listing veto (fail-open)
    L5  RISK_PCT=0.0241 of AVAILABLE (free margin) ; SL_ATR_MULT=3.0 (code default 1.5)
        leverage floor 5, overwritten by MAX_SL_MARGIN_PCT=20 ; TP_R=5.0
        MAX_MARGIN_PCT=0.25 ; regime scaler ON ; streak throttle OFF
        EARLY_STOP_R=0.5 / MINUTES=30 (19F, zero fires)

### 1. THE PULLBACK GATE — HOLD ON. Verdict is NOT MEASURABLE, not refuted.

**The 76% reproduces exactly: 76.1%** on an independent 150-day / 231-symbol / 3,941-signal replay.
**The shape is worth nothing** — gap +0.025R, t=0.71, permutation p=0.47; **the +1-bar entry-shift
placebo produces a LARGER gap (+0.063)**, the classic path-noise signature; the only |t|>2 result
runs AGAINST the gate (non-pullback bars reach a higher exit-free peak R, t=-2.84). A placebo gate
keeping a RANDOM 24% of signals recovers -$215 of the -$299, so **~72% of its apparent value is
generic volume-thinning any 24% filter supplies.**

**BUT MY PREMISE WAS FALSE.** I said loosening only ADDS fills. `_wildcard_rank_key`
(runtime.py:6785-6789) orders on `(deep-lateness, |roc|)` and is **BLIND to pullback shape**, so
turning the gate off floods the ranker with a 3x larger non-pullback stream that **outranks pullback
candidates into the three slots**: 925 fills created, **365-405 existing fills EVICTED**, only 260
of 665 live entries surviving, and 1R shrinks 7%. **61% of the extra signal population is absorbed
by eviction, which turns it back into a two-arm gap test — the expensive kind.**

Raw delta **-$299/mo**. It does not survive its own engine: the OFF arm carries $10,770 more risk
through a Min15 exit engine measured loss-biased by 0.1037 R/fill (SE 0.1301, n=43); break-even
bias is 0.1368, i.e. **0.25 SE away**. **Corrected -$72/mo, honest band [-$669, +$524]/mo,
P(flag is positive) ~ 40%.** Corroborating tell: the harness models the ON arm — the LIVE config —
at -$135/mo against a live verdict of roughly flat, **a ~$318/mo level error on one arm**, which
cannot resolve a $299/mo delta between two.

**Also: the docstring's "never been measured" is ITSELF out of date** — `DECISION_RULE.md:4171-4177`
already carries a clean 90-day ablation: ON longs +0.189R (n=568), OFF +0.193R (n=941), rejected
+0.256R (n=646), t=0.74, "no selection at all", ~$0.60/mo to remove.

**Leave it ON** — not because it earns its keep (it does not; stop defending it as a quality
filter) but because flipping it is a live-money bet with a +/-$600/mo spread against a $10 bar.
Ten graded half-measures all negative in every era; walk-forward over the family **-$33/mo**.

### 1b. THE ADDING-vs-DELETING ASYMMETRY — real, smaller than claimed, and it did not apply

A **DELETING** gate is judged on a GAP between two arms: clearing $10/mo while removing half the
fills needs a 0.020R per-fill gap -> **~8,700 fills, six years. Unverifiable.**

An **ADDING** change is judged against a **BREAK-EVEN CONSTANT** — one mean against a fixed number,
not a difference between two noisy populations. With ~113 extra fills/month at 1R~$21, the added
fills need only **+0.004R** to clear +$10/mo.

**But the required sample is (2*sd/d)^2 where d is the distance between the added fills' TRUE mean
and that constant — the thing you do not know in advance.** At a true mean of +0.05R you need
~1,900 fills; at +0.02R, ~13,000; **at break-even you can never verify it.** The 572-fill figure
assumed the added fills sit 0.078R from break-even, **measured after the fact**; the 75,800 figure
assumed ~zero, which is what this sleeve's mean actually is.

> **An adding change is CHEAPER TO VERIFY PER UNIT OF EDGE, but it does not manufacture power
> against an edge of zero. It is a discount, not an exemption.**

**THE SCREENING RULE — the day's best output.** Before pricing any future candidate ask:
(1) does it ADD fills, (2) **NET of slot eviction**, (3) is there a PRIOR reason the added fills sit
meaningfully away from break-even. **Any "no" -> do not spend a study on it.**

### 2. THE SHORT ARM — HOLD `LONG_ONLY=0`. Not stale, on three checks.

- Shipped **2026-08-10, commit d1dcde0**, "re-enable shorts as a **CAPACITY** change; score each
  side alone" — explicitly capacity, not edge, against the book's own n>=20 bar with 4 rows.
- Re-opened **2026-08-22** (daily_audit.md:2925-2938): "a reason not to touch
  FUTURES_WILDCARD_LONG_ONLY in either direction".
- Re-litigated **2026-09-08 by seven agents**, `DECISION_RULE.md:1194` verbatim: *"DO NOT make
  WILDCARD short-only. Leave FUTURES_WILDCARD_LONG_ONLY=0."* **25 days AFTER the asymmetry finding.**

**Both pre-registered kill conditions are ARMED and NEITHER is met.** `DECISION_RULE.md:4510`:
revert if the short arm at n>=10 sits >1.0R/trade below the long arm. n_short=12. Measured gap
**-0.011R to -0.037R — not met by ~1.0R.** Second condition (any short close worse than -1.5R):
worst is MARSCOIN at -1.052R. Not met.

Disabling shorts prices at **+$8.27/mo, SE $10.49, CI [-$10.75, +$29.65], P(clears the bar) = 0.42.**
Drop the largest-|delta| short (PONS) and it collapses to **+$1.34/mo.** LOSO never exceeds
+$11.78/mo in 22 folds. **Fills created: ZERO — measured, not assumed:** all 11 `slot_occupied`
refusals fall between 2026-07-23 and 2026-08-05 when the sleeve ran 1-2 slots; there has not been
one since MAX_POSITIONS=3. **Slot budget is 86% idle.**

**DO NOT SAY "shorts are ahead of longs."** They look ahead in R and behind in dollars, and the
divergence is mechanical — WILDCARD short fills carried below-mean `risk_usdt`, so R-space flatters
them. Correct statement: **not estimable at n=12; mildly negative-signed in dollars.**

**TREND's precedent does not transfer:** TREND's split has a consistent sign in every cell (shorts
correctly disabled); WILDCARD's cells do not share a sign.

**And the real reason LONG_ONLY exists is not the asymmetry at all** (`wildcard.py:101-110`): a
short's payoff is BOUNDED — short targets clamp at 50% price distance (`DECISION_RULE.md:4491-4500`)
because 21% of short signals otherwise target through price zero. At the live 3.0xATR stop that is a
**2.5R ceiling against the long's 5R for the same -1R risk.** The short arm's single best close
(+2.71R) sits just above it.

### 3. DEAD, INERT AND WRONG — the hygiene list

**`FUTURES_WILDCARD_MIN_24H_MOVE=0.03` IS DEAD.** Confirmed three ways: the read at
runtime.py:6300 is the `else` branch of `range_prefilter`; `_flag` returns True on an absent name
(runtime.py:9159, `os.environ.get(name,"1")`); RANGE_PREFILTER is absent from the live env.
Duplicate dead read at runtime.py:2625.
**Live `min_move` = 0.07**, line by line: MIN_ROC unset -> 0.08; SHADOW_MIN_ROC=0.07 set live;
`scan_roc = shadow_roc if 0 < shadow_roc < min_roc else min_roc` -> 0.07; MIN_24H_RANGE unset ->
defaults to scan_roc. **Live telemetry agrees: `range24>=7%`.**

**LATENT TRAP — do not delete the variable.** Because it is SET to 0.03, anyone who ever sets
`RANGE_PREFILTER=0` gets a **3% screen instead of the 8% code default — a 2.7x universe widening
from a var that today looks dead.** Leave it in place; fix the documentation instead.

**Also inert — stop treating these as dials:**
- `MAX_SCAN=90` never binds (live scan_capped=0 on 5/5 scans, movers 29-31; sim uncapped pool max 73
  over 2,777 scans; cells at 50 and 150 are BYTE-IDENTICAL).
- `LEVERAGE=5` is a floor that MAX_SL_MARGIN_PCT=20 overwrites (wildcard.py:290-294). Live realised
  leverage since trial 3: {1:25, 2:19, 3:8, 4:3} across 55 fills. **The seed value realised ZERO times.**
- `MAX_MARGIN_PCT=0.25` binds only below 9.64% sl_margin = 0% of fills at the live stop width.
- `EARLY_STOP_R=0.5 / MINUTES=30` — armed, **zero fires, never measured.** Do not file it as
  live-and-working.

**Two documentation defects:** `wildcard.py:133` says `calm_ratio` uses the 21h before the move;
the slice is `-(96+12):-12` = 96 Min15 bars = **24h**. And `docs/LIVE_CONFIG.md:141` states the live
range gate is 8%; it is **7%**.

**The ranking function is structurally inert** — it bites only when candidates exceed free slots:
**4 of 2,777 scans (0.14%)**. Eight of twelve alternative orderings, including reversing the |roc|
preference, produce **byte-identical books**. The `_entry_lateness` mis-normalisation is real (15%
pin at exactly 1.0) but **cannot** touch the [0.50,0.70) band: for any value strictly inside (0,1)
the current close is not an extreme, so min/max are unchanged by including it — analytic, not
empirical. Separately, the study behind the ranker **does not reproduce**: the deep band holds
2 of 103 fills, not the 247-fire population it was fitted on.

### 4. THE GRID IS CLOSED — permanently

**437 cells** (37 one-at-a-time, 400 joint draws over a 10-axis product), 119 exchangeable in a
2,000-permutation family-wise null. **Zero clear the 5% bar of +$808/mo. The null's MEDIAN best
cell (+$461/mo) EXCEEDS the observed best (+$361/mo). Family-wise p = 0.709.** Walk-forward
selection: -$176 / -$516 / -$90 / +$105 per month at 2/3/4/6 folds — **negative in 3 of 4, mean
-$169/mo.**

| knob | raw | ex-top-5% by delta | walk-forward | kill |
|---|---|---|---|---|
| EXCLUDE_TOP 24->0 | +$361/mo | +$210/mo | -$176/mo | family best = the null's own median; sim exaggerates this axis ~5x (live excludes 3.6% of in-band symbols, sim 17%) |
| MIN_TURNOVER 2M->1M | +$59/mo | **-$4/mo** | -$516/mo | entire delta is ONE fill; axis non-monotone; sim understates added volume ~3.5x |
| MIN_ROC 0.08->0.07 | +$42/mo | +$14/mo | -$516/mo | almost the whole delta is ONE fill |

**STRUCTURALLY UNVERIFIABLE AT THIS ACCOUNT SIZE — stop asking:** MAX_WICK, VERTICAL_ATR_MULT,
MIN_VOL_Z, RSI_MAX, MAX_CALM_RATIO, and every joint combination. At 1.124R per-fill sd, separating
a $10/mo effect from zero while changing half the fills needs **~75,800 fills: 58 years at the
sim's rate, ~120 at live's.**

### 5. THE STOP WIDTH — and why five full stops does not mean the stop is tight

**Verified at runtime.py:1765:** `margin = risk_pct x available_balance x 100 / sl_margin_pct`, so
the dollar loss at the stop is `risk_pct x available` = **2.41% of free margin AT EVERY STOP
WIDTH.** Median margin committed is **13.9% of free margin at 3.0xATR and 13.9% at 4.0xATR —
identical**, because the 20% cap holds sl_margin near 17% at every rung.

> **Widening the stop cannot reduce what a loss costs. It changes the win rate (46% -> 32% full
> stops at 4.0x), the hold time (median 3.8h -> 9.1h) and the leverage used (2 -> 1). It does not
> change 1R. A wider stop would have lost the same $107 across fewer, longer trades.**

**The ladder is the only real signal in the study:** netR across 1.0/1.5/2.0/2.5/3.0/3.5/4.0/5.0/6.0
= -23.5/-27.4/-21.9/-13.2/-1.7/+3.2/+9.3/+9.6/+5.0, **Spearman +0.933, monotone-trend permutation
p=0.0003 — the only p<0.01 result on the board.** It still does not ship, for four reasons fixed
in advance:
1. **It is an interaction with the RETENTION TRAIL, not a property of the stop.** Spearman across
   rungs is +1.000 with the live exit stack, +0.821 without the 24h clock, **+0.536 with no trail,
   +0.464 with no trail on a 6h clock.** A wider stop makes 1R a bigger price move, so the trail
   arms less often. **An exit-stack finding wearing a stop's name.**
2. The live PRE/POST corroboration is confounded by **five simultaneous changes** (51% of
   post-trial-3 exits go through the convex stack, which fired zero times before; margin cap;
   risk_pct equalisation doubling median margin; account size), with an 8-day fill gap across it.
3. **Family-wise p = 0.599** across the 8-rung ladder; **entry-shift placebo fails at +3 bars
   (-$104/mo).**
4. Apply the study's own fidelity haircut and the book's own 1R: +$261/mo x 0.49 fill-count haircut,
   then at 1R=$15.49 rather than $22.6 -> **~$88/mo against a bootstrap CI of [-$67, +$589] that
   spans zero.**

**ON THE FIVE FILLS.** At the measured 46-47% full-stop rate a 5-fill window going 0-for-5 is a ~2%
event, **but the expected number of 5-stop runs across the 55 fills since trial 3 is ~0.6, so seeing
one SOMEWHERE is roughly a coin flip.** And read the peak_r column: **four of five never cleared
0.33R, and nothing in the exit stack arms below 1.0R.** Only PONS at 0.9653R was ever close to
banking anything. **Four non-starters and one near-miss — a signal-quality distribution, not a
stop-width problem, and no stop-width change converts any of them.**

### 6. DECISION, RANKED — nothing touches live P&L

| # | action | $/mo | env/code |
|---|---|---|---|
| 1 | **Amend the MEMORY.md index line** carrying the retracted -0.225R (DONE) | $0 | memory |
| 2 | Correct `docs/LIVE_CONFIG.md:141`: the live range gate is **7%**, not 8% | $0 | doc |
| 3 | Correct `wildcard.py:133` `calm_ratio` docstring: **24h**, not 21h | $0 | comment |
| 4 | **File the harness fix:** any two-arm delta with UNEQUAL FILL COUNTS through the Min15 exit engine must report the break-even bias b* and fold `sd(b) x delta_risk` into the CI. On this study that term was **2.6x the bootstrap sd** and its omission is how a -$72 became a -$299 headline | $0 | process |
| 5 | Record the MIN_24H_MOVE trap; **leave the variable set** | $0 | doc |
| 6 | HOLD `REQUIRE_PULLBACK` ON | -$72 est, band [-$669,+$524] | env |
| 7 | HOLD `LONG_ONLY=0` | +$8.27 (SE $10.49), +$1.34 ex-top-5% | env |
| 8 | HOLD `SL_ATR_MULT=3.0` | ~$88 after haircuts, CI spans zero | env |
| 9 | HOLD everything else | mean -$169/mo walk-forward | — |

**Item 8 is the only thing I will not call settled.** It is the only p<0.01 monotone trend on the
board and the only positive walk-forward (+$191/mo). If it is ever taken, take it with the label:
**it buys fewer full stops and longer holds at UNCHANGED dollar risk, costs ~20% of fills to slot
occupancy, and has no measured dollar gain.** It is not a fix for the five stop-outs.

### WHAT IS NOT KNOWN, AND THE QUESTION THAT SHOULD BE NEXT

**Whether WILDCARD has any edge at all.** meanR **-0.016 +/- 0.111** in sim and **-$0.024/fill live
over n=55** — statistically zero on both. **Every knob on this entry path multiplies that zero by a
different fill count. There is no tuning solution to a zero mean.**

> **The question worth a study is not where a threshold sits. It is whether WILDCARD should hold
> three slots and 2.41% of free margin at all — because those slots also shrink TREND's 1R, and
> TREND is the sleeve carrying the book's positive expectancy. That is a CAPITAL-ALLOCATION
> question, it has far better measurement properties than any threshold here, and it is the one
> that should go on the board next.**

---

## 2026-09-09 (seventh pass) — 4-week market-regime segmentation vs WILDCARD. The regimes are REAL. The sleeve does not see them. Nothing ships.

**Asked, and bounded by the owner:** segment the last 4 weeks into market trends using standard
crypto practice, score WILDCARD in each, suggest $ P&L improvements. **"Don't look further than
4 weeks ago."** Honoured: 2026-08-12 -> 2026-09-09, warm-up bars only for 50d SMA / Wilder ADX(14)
/ 30d return-stdev. 3 agents / 3 verifiers / n=54 WILDCARD closes.

### 1. THE PERIOD TABLE

**Rule** (applicable 2026-08-12 forward, on closed Day1 bars of the bot's OWN scan universe, the
158-176 non-top-24 perps): `BR` = % of that universe above its own 10d SMA; `AI7` = 7d ROC of its
equal-weight index. **BULL** if BR>=65 and AI7>=+5%; **UP** if BR>=65 and AI7<+5%; **DOWN** if
BR<45 and AI7<=+5%; else **FLAT**. Produces contiguous runs, no isolated flips.

| # | dates | d | label | BTC | alt index | breadth | ADX(14) |
|---|---|---|---|---|---|---|---|
| **P1** | 08-12 -> 08-18 | 7 | **DOWN / narrow** | 63,455 -> 64,694 | 101.5 -> 100.0 | 43% -> 22% | 11 -> 14 |
| **P2** | 08-19 -> 08-27 | 9 | **BULL RUN** | 64,694 -> 80,209 (+26%) | 100 -> 122 | 70-88% | 15 -> 38.5 |
| **P3** | 08-28 -> 09-02 | 6 | **FLAT price / DISTRIBUTION** | 78.5k -> 77.4k | 121 -> 118 | **74.7% -> 24.1%** | 38.5 -> 44 |
| **P4** | 09-03 -> 09-09 | 7 | **UP, alt-led** | 77.3k -> 79.1k (flat) | 121 -> 138 (+14%) | 65-83% | 44 -> 47.8 |

**Convergence is the reason to believe it:** three independent rules (Kaufman efficiency + breadth
+ realised vol; breadth + 7d ROC; a 5-day normalised z on a MEDIAN-return alt index) all place a
boundary at **08-18/19** and at **09-02/03**. The verifier rebuilt breadth under four universe
definitions and got the same two boundaries every time. Only the mid-window boundary is uncertain
(08-25 vs 08-28); nothing downstream turns on it.

**TWO CORRECTIONS TO THE OWNER'S READ:**
- **His "down" leg does not exist at index level.** There was no sustained index downtrend in these
  four weeks. What he saw as down is P1 (drift with participation rotting, breadth 43% -> 22%) and
  P3 (**price pinned at the highs while breadth halved in ONE DAY, 74.7% -> 39.9%, then 24.1%**).
  Both are narrow tape at flat-to-high price. **That is distribution, not decline** — and it is the
  more useful observation.
- **Judge the sleeve against the ALT tape, not BTC.** The two were in opposite phases all month:
  ALT/BTC fell 16% while BTC rose 24%; BTC turnover share 0.42 -> 0.31 at the alt frenzy peak ->
  0.52 by 09-03; **BTC's daily MA20/MA50 never crossed inside the window at all.** A BTC-based
  label would have called P3 "flat" while the sleeve's actual universe was bleeding.
  **Breadth of the bot's own universe does all the segmentation work. BTC price alone does not
  separate these periods.**

### 2. WILDCARD PER PERIOD — and ALL FIVE post-deposit fills landed in P4, in EVERY segmentation

| period | n | win% | sumR | meanR +/- SE | **$ actual** | **post-dep fills** |
|---|---|---|---|---|---|---|
| P1 DOWN/narrow | 8 | 25.0% | -1.85 | -0.231 +/- 0.463 | -$0.76 | 0 |
| P2 BULL RUN | 17 | 35.3% | +0.50 | +0.029 +/- 0.483 | +$12.07 | 0 |
| P3 DISTRIBUTION | 19 | **68.4%** | +4.86 | +0.256 +/- 0.242 | +$9.33 | 0 |
| P4 UP | 10 | 20.0% | -3.91 | -0.391 +/- 0.445 | **-$106.36** | **5 <- THE DEPOSIT** |
| ALL | 54 | 42.6% | -0.40 | -0.007 +/- 0.202 | -$85.73 | 5 |

**Split P4 at the deposit — same period, same market, same days:**

| | n | sumR | meanR | $ | wins |
|---|---|---|---|---|---|
| P4 **pre**-deposit | 5 | +1.42 | **+0.284** | +$0.59 | 2 |
| P4 **post**-deposit | 5 | -5.33 | **-1.066** | **-$106.95** | 0 |

**The "worst market regime" is a period in which the sleeve was POSITIVE right up to the moment the
size changed.**

**Deposit-clean (n=49, constant ~$2/R) THE ORDERING INVERTS:**

| period | n | meanR | $ |
|---|---|---|---|
| P1 DOWN | 8 | **-0.231** | -$0.76 |
| P2 BULL RUN | 17 | +0.029 | +$12.07 |
| P3 DISTRIBUTION | 19 | +0.256 | +$9.33 |
| P4 UP | 5 | **+0.284** | +$0.59 |
| ALL | 49 | **+0.101** | **+$21.22** |

**Deposit-clean, the BEST period is risk-on and the WORST is a down period — the exact opposite of
what the dollar column says. Anyone reading the dollar column alone draws the opposite conclusion
from the truth.**

**At constant 1R the whole four weeks is -$9.04** (sumR -0.40 x $22.6). **89.5% of the headline
-$85.73 is the deposit landing on a losing streak, not a rate of loss.** P(5 straight losers at the
pre-deposit 47% win rate) = **0.042** — unlucky, not anomalous. Slippage on stops worsened only
0.0435R -> 0.0660R against an **11x notional jump** ($20 -> $223 median), ~$0.51/fill, nowhere near
enough to explain it. n=5 cannot separate bad luck from a size effect; needs the next 10-15 fills.

**The one sub-cut carrying real information is `peak_r`:** fraction never reaching +0.33R is
P1 75% / P2 35% / P3 26% / P4 60%; fraction clearing +1.0R is 25/35/63/20%. **That is signal
QUALITY, not exits.** It still fails: 4-way permutation p=0.080 all-54, **p=0.247 pre-deposit**;
DOWN-vs-RISK-ON binary p=0.164/0.386; winsorised continuous p=0.86.

Long/short is 42/12 (**the file has 12 shorts — an earlier brief said 7; reconcile before citing
any short-side number**). LONG-SHORT -0.053R, p=0.912, no side x regime interaction.

### 3. THE VARIATION IS NOT REAL — IT IS BELOW CHANCE

**Four buckets of thirteen coin flips would produce a WIDER spread than the one observed.**
sd(R)=1.47; a 13-trade bucket mean has SE 0.408R; the expected range of four such buckets under the
pure null is 2.059 x 0.408 = **0.840R**. Observed max-min: **0.647R** (all 54), **0.515R**
(pre-deposit), **0.270R** under the strictly mechanical dating.
**There is LESS between-period structure in this P&L than shuffling it would produce.**

- Omnibus permutation, 4 periods: free p = **0.716** (all 54) / **0.892** (pre-deposit);
  circular-block p = 0.623 / 0.533. Block and free agree, so time-clustering manufactures nothing.
  Best of six pairwise p, before correction: 0.138.
- **LABEL CONSISTENCY — the decisive test.** Pooling same-labelled periods, pre-deposit:
  DOWN (n=27) +0.111R vs RISK-ON (n=27) +0.087R, **diff 0.024R, p=0.959.** Within-label spread:
  **P1 DOWN -0.231 vs P3 DOWN +0.256 = 0.487R.**
  **The gap between two periods wearing the SAME label is 20x the gap between the labels.**
  A variable whose within-label variance dwarfs its between-label variance is not a regime variable.
- **Multiplicity, three families, all counted before the P&L was attached.** 29 segmentations:
  **ZERO reach nominal p<0.05 where 1.5 are expected under the null**; family-wise p of the best
  split 0.408 / 0.764. 110-cell grid (11 causal vars x 5 quantiles x 2 directions): best |dR|=1.21,
  P(max >= that under null) = **0.280**. 832 distinct day-labelings: observed best |t| = 4.77
  against a null MEDIAN best of **5.20** — **the real data's best split is WORSE than a typical
  shuffle's best**, FW p=0.573.
- **THE NUMBER TO CARRY.** In a 152-keep-set threshold grid the best REAL rule reaches
  **+$326/month**. Under 2,000 shuffles the **MEDIAN** best rule in that same grid reaches
  **+$260/month**; the 95th percentile is +$368. FW p = 0.144 IID, 0.073 block-rotated.
  **On 54 trades, any search of this shape hands you a +$260/month "improvement" as its EXPECTED
  result under pure noise. Nothing below ~+$370/month is distinguishable from having found nothing
  — and this sleeve's entire envelope is +/-$60/month.**

**Is it the earlier per-fill refutation in disguise?** Mechanically a period label IS a per-fill
condition constant over a date range, so in the limit yes — but it was tested on its own terms, and
period-level adds immunity to per-fill noise in the conditioning variable. It still finds nothing.
**Two independent routes, same ceiling: ~331,800 fills (~5,700 months) to separate a $10/month
effect at 80% power, reproducing the earlier ~75,800-fill figure from a different direction.** Even
"is this sleeve's mean positive or negative" needs ~1,700 fills = **29 months.**

**Fragility:** P2's headline is two tickets (TUT +5.09R, ENA +4.96R = +10.05R; the rest of that
block sums negative). Stripping the EXCHANGE_CLOSE channel flips the best contrast from +0.469R to
**-0.243R**. P3's edge is +0.256 -> +0.104 ex-top-1 -> **+0.031 ex-top-2**.

### 4. THE CAUSAL LAG — it decides tradeability, and it decides against

| indicator | P2 ignition (true 08-19) | P3 turn (true 08-28) | P4 turn (true 09-03) |
|---|---|---|---|
| **alt breadth >=65** | **+24h** | **+24h** | **+24h**, no whipsaw |
| alt index 7d ROC | +48h | +24h | +48h |
| BTC 7d ROC | -24h (whipsaw) | +24h | -96h, fires inside P3 |
| BTC > 20d/50d SMA | -24h (whipsaw) | **never flips** | **never flips** |
| **BTC ADX(14) >=25** | +96h (crosses 08-22, day AFTER the alt peak) | **never flips — rises 38.5 -> 47.5 while breadth halves** | never |
| ALT daily MA20/MA50 | — | — | crosses UP 09-02, **12 days after the alt peak** |
| 50/200 cross | **never fires inside the window** | — | — |

1. **ADX(14) on daily bars has ~27-day effective memory under Wilder smoothing — longer than the
   29-day window itself. It is structurally incapable of dating a boundary inside four weeks.**
   That is arithmetic, and it disqualifies the most commonly proposed regime indicator for this use.
2. **Breadth is the only well-behaved label: consistently +24h, never whipsaws.** On 6-9 day
   regimes that costs 11-17% of each period — and the missed day is the IGNITION day, the highest-
   move day of a three-day +21% thrust. The Hour4 version lags +20h to +60h and **flipped six times
   in the last four days**; a live rule would have been wrong about the tape on 7 of the 10 P4 fills.
3. **The information arrives two orders of magnitude slower than the trades it would gate.**
   Median hold by period: 10.2h / 6.7h / 5.6h / 2.1h. Label formation: 24-60h.

**CORRECTION TO A NUMBER THAT REACHED ME WRONG:** one agent headlined "a one-day lag flips the
sign, +$134.66/mo -> -$27.59/mo." **False** — it compares two different rules (18 vs 35 deletions).
Same blocks, lag varied only: **+$134.66 (0d) / +$108.25 (1d) / +$75.05 (2d). Decay, not reversal.**
And **93% of the +$134.66 is simply deleting the five post-deposit fills** — deposit-clean the same
rule is worth **+$10.05/mo**, and "skip FLAT alone" is **-$33.20/mo** because deposit-clean FLAT was
the BEST period.

### 5. SUGGESTIONS, RANKED

| # | action | $/mo | fills delta (net of eviction) | env/code | in-sample? |
|---|---|---|---|---|---|
| **1** | **Add no market-trend gate** | **$0** | 0 | no change | no |
| **2** | **Complete the market telemetry** | **$0** | 0 | code ~40 lines | no |
| **3** | Halve `FUTURES_WILDCARD_RISK_PCT` | $0 expected (+$1.5 certain) | 0 | **env, today** | no |
| 4 | Cut WILDCARD allocation 3/2/1/0 slots | +$0 / +$4.20 / +$8.42 / +$12.64 | -18/-36/-54 | env | yes |
| 5 | X refuse when alt breadth < 0.80 | +$165 headline | -42 (78%) | code | **yes** |
| 6 | X refuse when prior-close breadth < 0.50 | +$326 headline | -30 (56%) | env | **yes** |
| 7 | X x0.5 size when breadth < 70% | +$31.7-44.5 | 0 | code | **yes** |
| 8 | X refuse when alt-tape z < -0.4 | +$31.1 | -25 (46%) | code | **yes** |
| 9 | X side-restrict by regime | **-$8.4** | -29 | code | yes |
| 10 | X fast 1-day majors term | +1.05R in-window | -63-67% | ~15 lines | **yes** |
| 11 | X RELAX gates in the best regime | +$0.96 | +? | code | yes |

**THE STRUCTURAL ARGUMENT COMES BEFORE THE STATISTICS.** Measured slot occupancy on a 30-minute
grid across the four weeks: **0 slots in use 52.4% of the time, 1 slot 35.0%, 2 slots 11.3%,
3 slots 1.3%. The 3-slot cap binds ~7 hours of 696 (1.0-1.3%).** So **no refusal rule frees a slot
another fill would have used. Every market-regime proposal can ONLY delete fills and never add
them — it fails the screening rule by construction, before any p-value.** And the capacity lever
does not exist: cutting 3 -> 1 removes almost no fills and frees almost no margin.

**That leaves RELAXATION as the only shape that could pass, and it is now MEASURED, not assumed.**
`shadow.jsonl` holds 60 resolved refused WILDCARD candidates in the window: overall meanR_net
**-0.195 +/- 0.120**; by regime DOWN +0.010 (n=4), BULL -0.203 (n=36), FLAT -0.220 (n=20).
Admitting the best bucket is worth **+$0.96/month, p=0.435**; admitting them in BULL costs
**-$171/month.** The one proposal shape that could have cleared the screening rule is dead on
measurement.

**TWO RULES KILLED THAT THE OWNER WOULD OTHERWISE FIND HIMSELF:**
- **"Block entries while the tape is risk-on"**: +$94/mo on all 54. On the 49 pre-deposit fills the
  identical gate **LOSES $12.66** while deleting 22 of them; causal-lagged it loses $27.71. And
  `breadth<0.80` refusal shows +$105.96 raw — of which **+$106.95 is deleting exactly the five
  funded fills and -$0.98 is the other 49.**
- **The fast term — the strongest thing anyone found, killed pre-emptively.** Yesterday's CLOSED
  daily BTC or alt-index return >= +1%, read causally at the entry instant, separates R by
  **+1.05R with a family-wise, day-block-corrected p = 0.003** on the pre-deposit sample. Monotone
  across the sweep, survives LOSO, halves but survives ex-top-2 by delta, and is not entry-day beta
  (same-day-up is NEGATIVE). **It reverses sign on the 40 WILDCARD fills immediately preceding this
  window** (win 40% in vs 50% out; return-on-margin -0.077 vs +0.042) **and the majors-24h version
  was already refuted at n=137 with p=0.998 in the OPPOSITE direction** — a sample with power to
  see a +1.0R effect at t~3.4. **Two independent samples kill it. It is a 29-day artifact. Anyone
  who runs a 1-day market cut on this window will find it; this is the answer.**
- Aside, flagged as a stretch: the x0.5-size-when-breadth-low proposal is **beaten by the
  market-BLIND control "x0.5 on everything" (+$45.93/mo on the same window).** The gain was never
  the breadth term — it was touching the five funded stop-outs.

### THE TELEMETRY ITEM — corrected premise, recommendation stands

**Agents claimed `calm`, `btc_24h`, `eth_24h`, `sol_24h` are null on ALL 54 rows. VERIFIED FALSE.**
Actual coverage, checked directly:

    majors telemetry (btc24/eth24/sol24/calm)  PRESENT on 24 of 54 rows
      clean cutover: missing 08-12T12:29 -> 08-29T10:13 ; present 08-29T19:59 -> 09-09T09:43
    roc3h, regime_size_mult  54/54      mae_r  16/54 (from 09-01T08:14)
    t_adverse_50  1/54 (added 09-08)

So the recording works and started **2026-08-29**; 30 of 54 rows in this window predate it. **The
gap is partial coverage (44%), not a broken feature.** The useful part of the recommendation
survives: **record alt-universe breadth-24h and cross-sectional dispersion onto each trade row.**
The scanner already pulls the full ~1000-row ticker snapshot and already bands non-majors via
`_major_symbols()`, and the payload carries `riseFallRate` per symbol — the statistic is free, no
extra network call, ~30-40 lines, changes no behaviour.

Justification is **time-to-verdict only**. Prior-close breadth was the only market-wide variable
that flickered at all (rho +0.317 with r, surviving the deposit strip at +0.343, LOSO 0/38 sign
flips) — **but it is also the single best rule in a grid whose noise median is +$260/month, so do
not read it as promising.** The version that would matter — **breadth recomputed at each
450-second scan rather than at the previous midnight — cannot be backtested at all today because no
intraday breadth history exists.** Recording it now is what makes that test possible.

### THE RISK_PCT ITEM — and the justification NOT used

Halving `FUTURES_WILDCARD_RISK_PCT` deletes no fills, so it passes the volume screen for free.
**EV-neutral only at the point estimate:** at this window's -0.007R it gains ~$4.60/mo; at the
sleeve's lifetime +0.077R it **costs ~$50/mo**. Honest pricing: **+$1.5/month certain** (margin
released to TREND), **$0/month expected P&L**, a **+/-$130/month coin flip** depending on which
side of zero the true mean sits, and monthly dollar SE cut from **+/-$255 to +/-$128.**
**Below the $10 bar as a P&L change — a variance decision with a real opportunity cost, or nothing.**

**The justification NOT used:** "we earned +4.93R at $2/R and lost 5.33R at $21/R" is exactly the
deposit artefact this study spent four sections disqualifying. Five consecutive stop-outs at a 47%
win rate is p=0.042 — unlucky, carrying no information about whether the size is wrong.
**The defensible reason is the plain one: a sleeve whose mean is statistically zero (-0.007 +/-
0.200 this window, +0.077 lifetime) is now consuming 1.87% risk per trade at ~10x the size at which
that mean was measured. Scaling a zero mean by 10 scales the expectation by 10 x 0 and the standard
deviation by 10.**

### THE CAPITAL-ALLOCATION ALTERNATIVE DOES NOT DOMINATE — measured, not assumed

**WILDCARD's mean margin occupancy is $13.0 = 1.30% of $1,004 equity.** Removing it entirely scales
TREND's size by **x1.0132**. Full ladder at 1R=$22.60: 3 slots $0, 2 slots +$4.20/mo, 1 slot
+$8.42/mo, **0 slots +$12.64/mo — of which only +$2.95/mo is the reliable margin-release
component.** The other $9.70 is "stop running a sleeve whose sumR is -0.40 +/- 10.79", which is not
a measurement. **The reliable part is below the bar.**

### THE COST OF THE 4-WEEK BOUND

The owner set it deliberately and it is not free: **no walk-forward is possible inside 29 days**, so
every threshold here is in-sample, and the noise floor (+$260/month median under the null) exceeds
the sleeve's entire envelope. **The bound did not cause the negative result** — two of the three
strongest candidates were killed by data from OUTSIDE the window (the fast term reverses on the
preceding 40 fills; the majors-24h version was refuted at n=137, p=0.998 opposite) — but it does
mean nothing here could have been confirmed even if it were real. Confirming any of it needs
~1,700 fills for the sign of the mean alone: **29 months.**

---

## 2026-09-09 (eighth pass) — the owner's one-way safety floor. REFUTED, and MY structural framing was the error.

**Proposal (owner's own design, stated precisely):** arm at 1R as today; if the trade reaches
within 20% of 1R (S = 0.80R), trigger a "safety net" that closes the trade if it later crosses back
DOWN through S. Above 1R the normal trail arms as usual.

3 agents / 3 verifiers / path-exact Min1 replays / 24-cell (S x retain) surface on three
independent constructions.

### MY ERROR, FIRST — I told the owner the rule was inert on runners. IT IS THE OPPOSITE.

I framed it as: "the retention floor (0.50 x peak) equals S at peak = 1.6R, so **below peak 1.6R
the safety floor binds and above it the rule is inert**." **That is wrong, and it inverts the
finding.**

**The floor arms against `peak-so-far`, NOT the final peak. Peak-so-far starts at zero on every
trade, so EVERY runner passes through [S, 1.6R) on its way up — at which moment the retention
floor is still below S and the safety floor binds.**

Measured: **100% of the 93 fills whose baseline peak reached >=1.6R dipped back through 0.80R at
some point**, median dip **0.464R below S** — three times the FAIR/LAST basis band, so this is not
a feed artefact.

    at S=0.80, 201 of 389 fills (52%) change hands. Of those 201:
      128 (64%) have baseline peak in [S, 1.6R)   <- the band I predicted
       73 (36%) have baseline peak >= 1.6R        <- the band I called INERT
       54        have baseline peak >= 2.0R
    11 of the 12 fills reaching peak >=1.6R are changed; 7 of 7 reaching >=2.0R.

**THE KILLER CASE:** ENA_USDT 2026-08-20 peaked **0.850R**, fell to **0.698R**, then ran to
**5.02R and hit TP**. The safety floor banks +0.76R and forfeits **4.20R (-$95 at today's 1R)**.
Also cut at a peak-at-fire of 0.83-0.94R: XRP -2.20R, XRP -2.20R, TUT -1.97R.

**This is not a narrow-band tweak. It is a rewrite of the exit for half the book.**

### THE BREAK-EVEN ARITHMETIC — the one-sentence verdict

**Rescues are CAPPED. Truncations are NOT.**

    RESCUES:      126 of 201 fires, average **+0.394R** each.
                  Capped at +1.80R by construction: the best possible rescue turns -1.0R into +0.80R.
    TRUNCATIONS:   75 of 201 fires, average **-1.099R** each, UNCAPPED.
                  Worst single case: a ZEC fill, peak 4.73R, baseline +2.92R, floored to +0.72R = -2.20R.

    Break-even needs rescue share p >= 1.099/(1.099+0.394) = **73.6%**.
    Measured share: 126/201 = **62.7%. FAILS BY 11 POINTS.**

**And it fails at EVERY S, by 9 to 14 points, with no cell approaching the crossover:**

    S      0.60   0.65   0.70   0.75   0.80   0.85   0.90   0.95
    need    56%    62%    68%    72%    74%    74%    75%    75%
    got     44%    51%    55%    58%    63%    63%    66%    66%

Raising S improves the ratio (fewer, larger truncations against a stable rescue count) but **the
average truncation grows faster than the rescue count does, so the gap never closes.**

### THE RECOVERY PRIOR HELD, IN THIS EXACT BAND

**86% of trades that trigger the S=0.80 floor go on to make a new high above the level they
triggered at (30 of 35)** — reproducing the record's 93% (41/44) 10%-giveback figure precisely
where it matters. The rule cuts trades that mostly recover.

### ALL CELLS NEGATIVE, EVERY CONSTRUCTION

    agent 1 (matched cohort, 389 fills): all 24 cells -$50 to -$95/mo; owner's cell -$63/mo real
    agent 2 (path replay, 82 fills):     all 24 cells -$68 to -$308/mo; owner's cell -$113.8/mo
                                         nominal / -$102.3/mo realised; 35.2 fires/month
    agent 3 (Min1, 77 live-stack fills): all 24 cells negative at consistent funded pricing;
                                         best S=0.95/ret0.50 **-$99.40/mo**; owner's cell **-$196.03/mo**
    walk-forward: -$15.6 to -$52.4/mo across three splits (agent 2); -$49/mo (agent 1)

Split at S=0.80: **+$105/mo in the band I reasoned about (peak<1.6R) and -$175/mo in the band I
called inert. Net -$63/mo.**

### MY +$81.60 HEADLINE WAS AN APPLES-TO-ORANGES COMPARISON

I priced PONS at +$34.18 and ZEC 09-09 at +$47.42 by comparing the rule against their **LIVE**
outcomes. **In path replay they are worth +$6.3 and +$7.3, because the sim's own baseline ALREADY
rescues both rows** — they are unfaithful rows (sim +0.53R/+0.43R vs live -1.08R/-1.10R). The
delta must be measured against the same engine's baseline, not against the live ledger.

**And the sign does NOT depend on them: removing both makes the rule WORSE (-$127.9/mo).**

### THE PRICING ARTEFACT THAT MAKES IT LOOK PROFITABLE — worth remembering generally

Agent 3 found the rule flips positive (-$12.69/mo -> +$70.90/mo) **only at realised-risk pricing**,
and diagnosed why: **the 55 pre-09-01 fills carrying the truncated runners were sized at $2.03 mean
risk, while PONS and ZEC were sized at $18.46 and $25.21.** Pricing the forfeited runners at their
historical pocket-money size, and the rescues at funded size, is what manufactures the profit.
**At one consistent 1R it is never positive.**

**GENERAL RULE TO CARRY: any exit-rule delta spanning the deposit boundary must be priced at ONE
consistent 1R. Mixed-era realised-risk pricing systematically flatters rules that rescue recent
losses and truncate older winners.**

### VERDICT: DO NOT SHIP. And the mechanism generalises.

**Any rule that closes on a downward crossing of a fixed R level cuts every runner, because every
runner crosses that level from below and dips back through it at least once.** The proposal's value
depended entirely on the claim that it could not touch the tail, and the tail is exactly what it
touches. That closes not just this rule but the whole family of fixed-level one-way floors.

**What was genuinely new and worth keeping:** the degeneracy check came back the OPPOSITE of the
prior two-regime hybrid — 201 of 389 fills change hands and every fire changes the outcome, so this
was a real test of a real rule, not a bit-identical null. The rule is refuted on its economics, not
dismissed on a technicality.

---

## 2026-09-09 (ninth pass) — TP geometry. The owner's DIAGNOSIS is right and better than anything produced this month. The REMEDY is refuted. The TP is a GAP-CATCHER, not a goal.

**Trigger:** owner watching a live IOST long at x1 with a TP +79.1% from entry: *"How is +100% a
good goal for a trade with no leverage?"* 3 agents / 3 verifiers / 5 path-exact estimators.

### THE ARITHMETIC IS REAL; THE CAUSAL CHANNEL I PROPOSED IS NOT

Confirmed at source (`wildcard.py:284-317`): `sl_frac = SL_ATR_MULT x atr_pct` (env 3.0, **code
default 1.5**); `leverage = int(min(10, max(5, 7)))` — **starts at 7, not 5** — then
`MAX_SL_MARGIN_PCT=20` trims it to `max(1, int(0.20/sl_frac))`, which is the x1 on IOST;
`tp_dist = sl_frac x 5.0` = **15 x atr_pct in price**. The clamp at line 313 is `if s < 0`,
**shorts only**, and its docstring's stated reason is MATHEMATICAL unreachability (a target through
price zero). **Nobody ever asked whether a LONG target was reachable.** That gap is the owner's find.

Distribution reproduces across three samples (n=44/51/61): **median long target 42-47% of price,
p90 82-89%, max 100%. 75-95% of longs sit above 25%.** Shorts: 62-74% would exceed their clamp.

**MY "the 24h clock binds asymmetrically" MECHANISM IS REFUTED DIRECTLY.**
- **High-ATR fills reach their R-targets AS OFTEN OR MORE OFTEN.** By atr_pct tercile, censored at
  24h and at the stop: +1R **45%/45%/52%** (logrank p=0.86), +2R 25%/35%/38% (p=0.38), +3R
  20%/15%/24% (p=0.61). The single p=0.019 at +5R is 1 of 12 tests, non-monotone, Bonferroni
  p=0.23. **On the reach dimension R-space IS time-invariant.**
- **The clock almost never fires.** Median WILDCARD long is dead in **2.15 hours**; **2 of 61**
  survive to 23h. Exits are the stop (~43 of 88) and the trail (~34 of 88).
- Extending the clock is negative at every setting: 30h -$1.83/mo, 36h -$0.22, 48h -$2.98;
  ATR-conditional negative in all 10 cells.

**The real reason the target is never touched is simpler and worse for the proposal: median 24h
peak excursion is 6.2-7.0% of price against a 44-47% target.** A 48h clock does not rescue a 44%
ask from a 7% market. **The live IOST target was reached in 2 of 5,664 rolling 24h windows over 60
days — 0.04%.** The live target sits at **2.51x the symbol's own 24h-MFE p90** (median), implying a
median historical hit probability of **1.0%**.

**ONE PIECE OF THE MECHANISM SURVIVES — keep it on file.** Among fills that DO run, high-ATR ones
are genuinely slower: median hours to +2R **4.9 / 6.8 / 13.6** by tercile. Time dilation is real.
It costs nothing today because only ~10% of fills are clock-censored. **Any future change that
makes trades live longer must re-open this.**

### THE HONEST NULL WINS — AND THE TP IS A GAP-CATCHER

**An unfilled resting limit order transfers exactly $0.** Verified structurally
(`runtime.py:1494-1504`): `_skips_discretionary_locks()` returns True for `_is_wildcard_convex()`,
removing the sleeve from `_profit_lock_exit`, the micro-lock (`max_peak_tp_progress=0.50`), the
stagnation exit and `early_exit_tp_progress` — **every rule in the codebase that reads
`tp_progress()`.** For WILDCARD the target price has **exactly ONE consumer: the exchange-side
order.** It reads nothing, gates nothing, sizes nothing, blocks no margin.

**And it is not idle — it has been paying.** It resolved **2 of 56 fills (3.6%): ENA +4.93R and
TUT +5.53R, the book's two best trades.** Its MARGINAL value over what the ratcheted trail would
have banked anyway (0.75 above 3R -> ~3.70R and ~4.17R) is **~$6 over the window**, not the $29
gross one report headlined. Small, positive, and pointing away from touching it.

> **The unreachable TP costs nothing, and the two times it did reach, it earned more than the trail
> would have. It is not a goal. It is a gap-catcher, and gap-catchers are supposed to sit far away.**

### THE CLAMP — his distinction was legitimate and was honoured. It still fails.

**A price clamp is NOT the uniform TP_R sweep.** At 40% it binds on 26 of 40 longs and leaves 14 at
TP_R=5.0 untouched; at 75% it binds on 6 of 40. It deletes zero fills. **Nobody gets to answer this
by citing -$111/mo at TP 1.0R.** It was built and swept on its own terms.

**It fails on something the uniform sweep never showed: five estimators cannot agree on the sign of
a single binding cell.**

| clamp | Min5 n=88 | Min5 TP-favourable | Min1 n=50 | Min1 vs live | peak_r n=54-56 | median |
|---|---|---|---|---|---|---|
| 15% | -42.87 | — | **+25.89** | -11.19 | -7.47 | **-9.33** |
| 20% | -33.91 | — | +11.54 | +13.96 | -2.86 | -0.87 |
| 25% | -18.41 | +7.89 | — | +7.53 | -2.58 | -2.58 |
| 30% | -17.14 | — | 0.00 | **+16.37** | -2.83 | 0.00 |
| 35% | -7.34 | -23.51 | — | -4.14 | -2.09 | -4.14 |
| 40% | +1.98 | -10.47 | 0.00 | 0.00 | -0.39 | -0.20 |
| 50%+ | 0.00 | -11.39 | 0.00 | 0.00 | 0.00 | 0.00 |

**Spread at 15% is $69 — seven times the decision bar. No cell has a positive median.**

**Three mechanical reasons the positives are not real:**
1. **The Min1 sim mis-scored the tail.** It recorded TUT 2026-08-22 as a +2.98R trail exit; live it
   was a **+5.09R take-profit**. That one row is the difference between +$25.89 and -$11.19 at the
   15% cell. **Exactly the loss-enrichment hazard, catching the study at the cell it was built on.**
2. **"Exactly $0.00, zero outcomes changed" is an INTRABAR ARTIFACT.** Five longs traversed >=50%
   of price (BTW peaked at 56.3% before exiting the trail at +3.05R). The zero comes from the
   engine updating `peak` with the bar's high BEFORE checking the trail, so the trail pre-empts the
   clamped TP on the exact bar it would fire. Under TP-favourable ordering a 50% clamp changes one
   fill and **loses $11.39/mo. The honest 50% figure is [-$11.39, $0.00], not zero.**
3. **The peak_r "$0.00 at 30%" does not reproduce** — it rests on MAGMA firing at peak_r 4.4169
   against a threshold of 4.4218, a 0.11% gap resolved by an sl_frac accurate to +/-5%. On recorded
   `sl_frac_designed` it is -$2.83/mo. **There is no non-negative interior clamp and no near-miss.**

**TAIL COST — the substantive kill.** A price clamp is BY CONSTRUCTION a tail-truncation device:
inert on every fill that didn't run, live only on the largest excursions. **9 of 56 fills reached
>=2R and carry 67-69% of the book's gross winnings.** At 25% the tail supplies 71-80% of the
damage; at 15% it is **-$34/mo on two named fills** (ENA -1.85R, TUT -0.95R). **There is no setting
at which the clamp is both live and tail-safe.**

**TRAIL OVERLAP — why it can't win even when positive.** 22 of the 25 fills reaching >=1R exited on
a CONVEX rule, banking a median **46-47% of peak**. Of the fills a clamp NEWLY banks: at 15%,
**6 of 8 were already profitable trail exits**, carrying +1.409R of the +1.410R total. At 20%, 3 of
4. At 30%, 2 of 3. **The clamp is not capturing give-backs the system missed — it re-prices exits
the trail already took, swapping "keep half of whatever peak you got" for a fixed level. A fill
peaking at 4R exits the ratcheted trail at 3.0R; a 25% clamp banks 2.5R. On every path peaking
above TP_R/0.75 the trail is strictly better.**

**And the in-sample optimum is a mechanism the book already rejected:** at 15% the single trade
making the cell positive is ONG, whose implied TP_R is **0.850** — a target BELOW the trail's 1.0R
arm. That is a sub-1R scalp, and arming below 1.0R is refuted at 54 of 55 cells. Guard against
targets inside the arm and the 15% cell goes **+$25.89 -> -$13.12/mo.**

**Walk-forward:** blocked 7-day -$22.28/mo; expanding (burn-in 15/20/25) -$12.60 / -$1.27 / -$1.47,
**selecting do-nothing on 27 of 36 decisions**; two-fold $0.00. **Sixth candidate this control has
killed.** Permutation p=0.31-0.75 (one observed value IS the null median); era split disagrees in
sign at every live cell; LOO/LOSO flips the sign on one trade at every live cell.

### THE ALREADY-BUILT ALTERNATIVE IS INERT

`FUTURES_WILDCARD_TP_FROM_DESIGNED_STOP = 1`: **-$0.50/mo, 1 fill changes value, 0 exit-reason
flips, exit mix identical. Do not set it.** The margin cap trims LEVERAGE first, preserving the ATR
stop distance and only re-cutting `sl_frac` when even x1 would breach — designed/realised ratio is
0.90-1.09, pure integer-leverage rounding. The docstring's "~9% of signals" is a SIGNAL-level
figure; on FILLS it binds 3 of 56, and on those it **widens** the target.

### THERE IS NO BETTER TARGET — and the signature is the proof

Lookahead-free, from Min15 bars strictly preceding each entry:
- **Target = quantile of the symbol's own trailing 24h MFE:** p50 -$29.77/mo, p70 -$28.32,
  p80 -$19.94, p90 -$3.79, p95 -$7.53, p99 +$3.00 (4 fills, one is 133% of the effect; drop GALA
  and it is -$0.98).
- **Target = k x own 24h realised range:** k=0.5 -$28.12, k=0.75 -$30.15, k=1.0 -$22.40,
  k=1.5 -$10.71, k=2.0 -$5.50, k=3.0 +$3.44 (7 fills, largest is 107% of the effect).

> **THE FAMILY IS MONOTONE IN EXPOSURE: the more fills a variant touches, the more it loses, and
> its optimum is the setting closest to doing nothing. That is what "there is no better target"
> looks like when you measure it instead of arguing it.**

**The reason is structural: a reachable target and a trail are the SAME INSTRUMENT aimed at the
SAME RANGE, and the trail is the better version because it is PROPORTIONAL — it keeps half of
whatever peak actually occurred rather than guessing where the peak will be. WILDCARD already has a
reachable-range exit. It is the retention trail.**

### THE FREE FINDING — this class of question is 20-500x cheaper to close

**A TP change is a PAIRED, LOW-VARIANCE perturbation.** Per-fill dollar-delta sd is **$0.79-$1.48**
against **$6.86** for raw per-fill P&L. So $10/month is detectable in **130-460 fills = 2.6-8.8
months** at 51.7 fills/mo — against **191 months** for a raw-edge question and **~75,800 fills** for
a regime gate. **Exit-parameter questions are answerable on this book; entry-gate and regime
questions are not. Prefer them.**

### RANKED DECISION

| # | action | $/mo | walk-fwd | tail cost | env/code | verdict |
|---|---|---|---|---|---|---|
| **1** | **Do nothing to the exit stack** | **$0** | $0 (**WF selects this 27 of 36**) | $0 | none | **SHIP** |
| **2** | **Fix the readout** — stop scoring positions as "TP 27%"; show trail floor / peak / clock, label the TP a gap-catcher | $0 trading | n/a | $0 | display only | **SHIP** |
| 3 | `MAX_LONG_TP_DIST = 0.50` as a labelled cosmetic | $0.00 median, **[-$11.39, $0.00]** | $0 | $0 | ~2 lines + env var | only if #2 is not done. **0.50, never 0.40** — must clear the 41.95% observed max |
| 4 | `TP_FROM_DESIGNED_STOP = 1` | -$0.50 | -$0.50 | $0 | env only | REJECT — inert, widens where it binds |
| 5 | clamp 15-35% | -$0.87 to -$9.33 median, sign spread **$69** | -$12.60 to -$22.28 | up to **-$34** | ~2 lines + env | REJECT |
| 6 | reachability-anchored target | -$29.77 to -$3.79 at every binding setting | -$0.88 | -$4 to -$30 | per-symbol rolling estimator + storage | REJECT |
| 7 | volatility-conditional clock | negative in all 10 cells | — | -$5.17 | code, 3 call sites | REJECT — the refuted extension wearing a condition |

**Nothing clears $10/month in the right direction on any estimator, and every positive point
estimate loses its sign when you change the intrabar convention, the baseline, or one trade.**

### THE OPEN ITEM — widening was never priced

`peak_r` is a sufficient statistic only for NEARER targets; **the post-exit path does not exist for
any fill that exited, so WIDENING is not identifiable from a closed book.** If the target is
decorative, the untested direction is *"make it decoration that costs nothing and stop pretending
it is a goal"*, not *"move it closer"*. **We proved a nearer target is worse. Nobody proved a wider
one is.** Not a proposal — an open item, and the power arithmetic says it would take ~3-9 months of
fills to close even if designed.

### WHAT COULD NOT BE SETTLED

- **Intrabar ordering at the 50% cell.** Min5 and Min1 cannot resolve whether a clamped TP print or
  the trail print came first — the whole difference between "$0.00" and "-$11.39/mo". Tick data
  would close it; it changes no ranking.
- **Slot/capacity feedback is unpriced.** A nearer target frees a slot earlier and could add fills.
  Direction favours clamping, magnitude unknown, no slot model exists. **The one omission that
  could move a clamp from negative toward zero — not toward shippable.**
- **The two TP resolutions carry `exit_reason = EXCHANGE_CLOSE`**, not a TP label. Attribution is
  arithmetic (final R 4.96 vs peak 4.94; 5.09 vs target 5.00), not a reason code.
- The samples are not the same book (n=44/51/56/61/88 by ring-buffer eviction and required fields).
  **Signs and orderings are comparable; dollar magnitudes are NOT and were not treated as such.**

---

## 2026-09-09 (tenth pass) — the 1R-to-TP window. THE "LEAK" WAS MINE: an era mix, not a defect. The trail is not the instrument operating in that window. Ship nothing.

**Asked (owner):** *"We have the armed trail that provides a nice positive floor, but between it and
the TP there can be a huge window where the trade is twice or more profitable than the locked floor
and we never benefit from it. How can we optimize between +1R and the TP?"*
3 agents / 3 verifiers / **258 cells** across five instrument families.

### MY ERROR — THE LEAK DOES NOT EXIST

I reported realised retention of **39% / 13% / 32%** against a designed 50% and called it "a leak
between policy and execution, 11-37 percentage points of every peak above 1R."

**`FUTURES_CONVEX_TRAIL_RETAIN_FRAC` was 0.30 — the CODE DEFAULT (runtime.py:1930, :2310) — until
2026-08-29 00:37Z, when trial 18 set it to 0.50.** My table averaged two different policies.

| era | n | mean gross-banked / peak | range (non-ratchet) | design |
|---|---|---|---|---|
| <= 2026-08-28 | 12 | **0.312** | 0.239-0.304 (n=11) | 0.30 |
| >= 2026-08-29 | 14 | **0.496** | 0.442-0.496 (n=12) | 0.50 |

**Zero overlap, no intermediate row.** Both apparent outliers are the ratchet firing correctly
against its 0.75 design (0.670 and 0.743). **The trail executes its policy to within 2-6 percentage
points on every fill it has ever taken.** The "graded" pattern was the config date correlating with
which fills landed in which band. **Discard that table.**

**The 13% cell is ONE row:** AVAX 2026-08-09, `risk_usdt` **$0.03**, fee $0.0145 = 0.43R. It is the
exact case named in the code comment at runtime.py:2345-2349 as the reason
`FUTURES_CONVEX_COST_FLOOR_MULT` exists. **Already fixed.**

**The real residual:** floor minus realised gross = **0.0286R per trail fill** (median 0.0250,
sd 0.0173, max 0.0604, n=14, every row positive — one-sided by construction, so its mean can never
be zero even for a perfect trail). Realised **$2.60 total over 11.1 days = $7.19/month, below the
bar.** Projected forward at 1R=$25.16 it is ~$27/month — but that reprices 13 pre-deposit fills
(risk $0.73-$4.07) by ~10x under an untested size-invariance assumption whose **only live-size
observation (ZEC 09-06, risk $28.33) is the LARGEST undershoot in the sample, 0.0604R, 2.1x the
mean.** Quote with that caveat or not at all.

**Fee drag (0.0265R/fill) is CORRECT ACCOUNTING, not slippage:** `_position_pnl_pct`
(runtime.py:1178) has no fee term, so `peak_r` and the floor are GROSS while `pnl_usdt` is NET.
Not recoverable by any exit parameter.

**FAIR-vs-LAST basis REFUTED as the cause:** a fixed ~42bps basis predicts 0.265R undershoot on ZEC
(sl_frac 1.59%) and 0.028R on HNT (15.13%); observed is 0.018R and 0.032R — **wrong magnitude by
15x and wrong ordering.** corr(sl_frac, undershoot_R) = +0.24 while corr(sl_frac, undershoot_bps) =
+0.73. Undershoot is roughly constant in R and scales with the symbol's own ATR: **the signature of
price traversing the floor between discrete evaluations.** Monitor loop verified genuinely 1 Hz and
ungated. Exit-reason mislabelling: **none** — all 9 EXCHANGE_CLOSE rows with peak>=1.0R realised AT
OR ABOVE their peak (they are exchange-side TP fills, +$142.66 net).

### THE ORACLE BOUND — the prize is real, and 96% of it is the POLICY, not a leak

Post-era only (2026-08-29 -> 09-09, 11.1 days, 20 armed fills, 54.2 armed/month), oracle = sell at
the recorded 1-second FAIR peak paying the same fees:

| | R | at own realised risk | at 1R = $25.16 |
|---|---|---|---|
| **total peak-to-banked gap** | **10.02R** | $38.39 = $104/mo | $252 = **$683/mo** |
| of which execution undershoot | 0.40R | $2.60 = $7/mo | $27/mo (**4%**) |
| of which **DESIGNED GIVEBACK** | 9.62R | $35.79 = $97/mo | **$656/mo (96%)** |

> **That $656/month is the answer to "what am I chasing." It is not lost money — it is what a 0.50
> retention IS. At the peak, every armed trade is worth exactly twice its floor by construction.
> The owner's observation that "the trade is twice or more profitable than the locked floor" is not
> a symptom; it is the DEFINITION of the parameter.**

**Capturable without lookahead: measured at <= $0.** 258 cells across five families.
**63 of 73 in one grid and ALL 20 in another are negative, where a coin flip gives half.**
The family is negatively skewed, not noisy-with-a-winner-hidden-in-it.

### THE STRUCTURAL REFUTATION — arithmetic on the closed ledger, no replay engine required

Every replay number here swings $70-$133/month on bar resolution and changes sign. **So the
decisive argument uses none of them.** For any tightening from 0.50 to 0.80 above a trigger T: the
**gain is CAPPED** by the peaks of fills that stall above T; the **exposure** is every R banked by
fills that must cross T on the way up.

| trigger T | stalls above T | max gain @0.80 (zero-truncation, impossible) | runners crossing T | R at risk | **exposure ratio** |
|---|---|---|---|---|---|
| 1.00R | 14 | +6.21R | 12 | 21.68R | **3.5 : 1** |
| 1.25R | 7 | +3.84R | 8 | 19.03R | **5.0 : 1** |
| 1.50R | 2 | +1.82R | 7 | 17.68R | **9.7 : 1** |
| 2.00R | 2 | +1.82R | 6 | 15.73R | **8.6 : 1** |
| 3.00R | 1 | +1.05R | 1 | 2.60R | 2.5 : 1 |

Same shape on the full 35-day 85-row sample (3.9:1 to 9.4:1). **Read as a survival requirement: a
0.80 floor above 1.25R breaks even only if a 20%-retrace trailing stop survives on 80% of the R
carried by every runner that crosses 1.25R, over multi-hour runs on thin alt perps.** And the gain
column is a strict upper bound — a higher floor also fires earlier on the stalls themselves.

**Same geometry that killed the 0.8R one-way floor today — interior rescue CAPPED, truncation
UNCAPPED — arriving from a different direction and without a simulator.**

### THE SCHEDULE — priced as its own object, not dismissed by the uniform sweep

**It IS genuinely different:** linear 0.50@1.0R -> 0.80@4.0R applies 0.50 at 1.00R, 0.51 at 1.05R,
0.55 at 1.5R, where the refuted uniform 0.80 applies 0.80 at 1.05R. Non-degeneracy confirmed:
realised trail-exit level has sd 0.33-0.43R across slopes.

| schedule | $/mo | interior (1-2R) | tail (>=2R) | trades changed |
|---|---|---|---|---|
| 15 linear cells, slopes 0.05-0.30 | **all 15 negative**, best -$10.24 | — | — | 20-21 of 53 |
| linear 0.50@1R -> 0.80@4R | -$31.6 | **+$11.8** | **-$43.5** | 29 of 77 |
| steep 0.50@1R -> 0.80@2R | -$182.8 | **+$32.0** | **-$214.8** | 32 of 77 |

**The gain comes exactly where the owner expects it, and it comes out of the runners. Tripling the
interior capture ($11.8 -> $32.0) QUINTUPLES the tail loss ($43.5 -> $214.8), and the loss-to-gain
ratio worsens monotonically from 3.7:1 to 6.7:1 in precisely the direction the question pushes.**
That shape is the one thing stable across every bar resolution, even where the total flips sign.

**Reporting caveat:** the signed totals are resolution-unstable (the -$31.6 cell prices +$39.0 at
Min15/close). **Report as "priced negative in three independent sweeps and structurally refuted by
the exposure ratio", NOT as a measured -$31.6/month.**

### THE ANSWER: THE TRAIL IS NOT THE INSTRUMENT OPERATING IN THAT WINDOW

Of the 20 armed fills since the config changed, split by which instrument actually closed them:

| exit instrument | n | **capture of peak** | dollars (own risk) |
|---|---|---|---|
| `EXCHANGE_CLOSE` (the TP / gap-catcher) | 4 | **101%** | **$96.53 = 69% of all armed money** |
| `CONVEX_TIME_STOP` (24h clock) | 2 | **91%** | $8.76 |
| `CONVEX_RETENTION_TRAIL` | 14 | **52%** | $35.48 |

**Fills that get deep into the window are already being caught at ~100% of peak by the TP and the
clock. The trail ends up owning the fills that STALL at 1.03-1.46R — and for those there is no huge
window. There is 0.5R of window, and it banks half of it.**

**ONE of twenty armed fills has given back more than 1R from peak since 2026-08-29** (USELESS 09-01,
2.57 -> 1.26). **ZERO have ever given back 2R, in either era.** Under the old 0.30 policy,
**8 of 12 gave back more than 1R.**

> **The pain the owner remembers is real, and it is a memory of a policy that stopped running
> eleven days ago.**

**THE BINDING CONSTRAINT BETWEEN +1R AND THE TP IS REACH, NOT RETENTION.** Only 44 of 93 fills reach
1R, 17 reach 2R, 6 reach 3R, 1 reaches 5R. Retention already executes at design to within 3-6
points on every fill. **The money sits in the handful of fills that get past 2R, and raising the
share that get there is an entry/selection question.**

### THE POWER ARITHMETIC — A CORRECTION. Today's "free finding" does NOT transfer.

| family | sd per fill | months to resolve $10/mo |
|---|---|---|
| below-arm perturbations (the finding I quoted) | $0.79 - $1.48 | 2.6 - 8.8 |
| **ratchet / schedule / ATR — THE INTERIOR** | **$3.56 - $8.32** | **46 - 318** |
| partial scale-out @3R (3 fills touched) | $1.58 | 11.5 — and it prices **-$8.24** |

**The reason is structural: below the arm a change touches many fills by fractions of an R; above
the arm THE FILLS THAT CHANGE ARE THE RUNNERS**, individual deltas of $11-$35, so variance is 3-6x
higher even though FEWER fills change. **You are perturbing the tail, and the tail is the variance.**

**Do not pre-register anything here. This is the first exit family where the power arithmetic
returns a clear NO — that is itself the finding, and it should stop this question being
re-litigated.**

### RANKED DECISION

| # | change | $/mo | share of $683 oracle | walk-fwd | trades chg | env/code | controls |
|---|---|---|---|---|---|---|---|
| **1** | **DO NOTHING** | **$0** | 0% | — | 0 | — | n/a |
| **2** | **Persist `r_now`/`exit_level`/guard price from runtime.py:2357 onto the closed row** | $0 | precondition for measuring the <=$27 | — | 0 | CODE | none needed — no fill changes |
| 3 | ratchet RETAIN 0.75 -> 0.55 | +$58.7 nominal | 9% | +$16.0 | **4** | ENV | **p=0.379**; ex-top-5% -> **+$0.6**; dies on TUT drop; both top movers sit in the 0.30 era |
| 4 | peak-conditional stall stop (120m) | +$7.4 | 1% | $0.00 | 3 | CODE | p=0.697; ex-top-5% -> $0.00 |
| 5 | ATR trail k=6 | +$5.8 | 1% | **-$142.8** | 11 | CODE | p=0.856; intrabar swing $11.4 on a $5.8 effect |
| 6 | lower ratchet trigger to 1.2-2.5R | -$8 to -$144 | neg | -$188.6 | 13 | ENV | **all 20 cells negative** |
| 7 | rising retention schedule | -$10 to -$183 | neg | -$9.5 | 20-32 | CODE | negative under every LOO |
| 8 | partial scale-out 25% @3R | -$8.2 | neg | -$8.2 | 3 | CODE | all 9 cells negative; extends "floor-not-bank" above 2R |
| 9 | `MONITOR_SECONDS` 0.25 | unmeasured | <=4% | — | — | ENV | **REJECT ON RISK** — 4 REST calls/position/sec on WS dropout, rate-limits entries and stop management |

**Nothing clears $10/month. Ship #1. Do #2 because it is free** — `runtime.py:2357` already
log.warnings peak/now/floor/price at the decision poll and never persists it, so the split between
poll lag and fill slippage is gone from every closed row.

---

## 2026-09-09 (eleventh pass) — the staircase/ladder floor with no TP. REFUTED. The rule written to remove the ceiling installs a lower one.

**Proposal (owner's own, specified precisely):** rungs at every NR with a constant **0.2R** buffer
(confirmed from his worked example: 1R=$10 -> arm $8; 2R=$20 -> arm $18; $2 = 0.2R both times), so
floors sit at 0.8R / 1.8R / 2.8R / 3.8R / 4.8R... **The take-profit is removed entirely.** Remaining
exits: initial stop, ladder floor, 24h clock. Rationale: *"no limit to how high it can be."*

3 agents / 3 verifiers / 16-cell grid (spacing x buffer) / path-exact Min1, both intrabar orders.

### THE SURVIVAL TABLE — it answers the proposal on its own

Owner's cell (spacing 1.0R, buffer 0.20R), Min1 adverse-first, n=80 walkable rows:

    rung 1 (floor 0.80R):  41 armed | **37 CUT (90.2%)** |  4 survived
    rung 2 (floor 1.80R):   4 armed | **4 CUT (100%)**   |  0 survived
    rung 3 (floor 2.80R):   **0 ever reached**
    rungs 4, 5:             never reached

> **Max ladder-banked outcome across the entire book = +1.79R.**
> **The rule sold as "no limit to how high it can be" produces the TIGHTEST CEILING OF ANY EXIT YET
> TESTED: 1.8R, against a live book that banked 5.09R.**

**The rung-1 cut rate is 89-100% in EVERY ONE of the 16 cells.** No cell lets more than 7 fills
reach rung 2; no cell lets more than 1 reach rung 3.

**The "reach vs armed" gap is the clearest exposition** (n=53, free-run = what the path would have
done with only the -1R stop and the clock):

| rung | floor | could reach | armed | cut | survived |
|---|---|---|---|---|---|
| 1 | 0.80R | 24 | 24 | 20 | 4 |
| 2 | 1.80R | **14** | **4** | 4 | 0 |
| 3 | 2.80R | **8** | **0** | 0 | 0 |
| 4 | 3.80R | 7 | 0 | 0 | 0 |
| 5 | 4.80R | 5 | 0 | 0 | 0 |

**14 fills could have armed rung 2 and only 4 did, because 20 were already gone at rung 1. Eight
could have armed rung 3 and none did. Everything above rung 2 is priced on a population of zero.**

**THE LADDER AMPUTATES ITS OWN TAIL:** it converts 17 fills that would reach 2R into 7, 6 that would
reach 3R into 3, and **the single 5R fill into zero.**

### THE NAMED CASES — the two biggest wins in the book are both cut at rung 1

    ENA  08-20  live +4.96R (TP)   -> CUT AT RUNG 1 at 0.80R.  Forfeits 4.20R.
    TUT  08-22  live +5.09R (TP)   -> CUT AT RUNG 1 at 0.80R.  Forfeits 4.29R.
    MAGMA 08-28 live +2.98R         -> CUT AT RUNG 1 at 0.80R.
    USELESS 09-04 live +2.55R (peak 3.50R) -> CUT AT RUNG 1 at 0.80R.
    ZEC  08-21  live +2.98R         -> CUT AT RUNG 1 at 0.80R.  -2.18R.
    USELESS 09-01 live +1.21R (peak 2.57R) -> cut at RUNG 2, **+0.52R — the ONE case it improves.**

**ENA forfeits the IDENTICAL 4.20R that the single 0.8R floor forfeited this morning. The ladder
inherits that failure in full and its higher rungs never activate to pay for it.**

**MY ERROR IN THE BRIEF:** I cited a "ZEC fill with peak 4.73R". **It does not exist.** Every ZEC
fill is TREND, whose TP is 3.0R, so ZEC peaks are TP-capped; the highest ZEC peak in the corpus is
**3.026R**. The agent correctly refused to fabricate it and said so.

### RUNG 1 ISOLATED — the premise, measured and inverted

    single 0.8R floor alone:        -$143/mo
    adding rungs 2+:                a FURTHER -$47/mo
    total:                          -$190/mo

**The higher rungs do not pay for rung 1. They deepen its loss.** And the ladder does not work with
rung 1 deleted either (-$148/mo). All 16 grid cells negative, **-$38 to -$339/mo.**

### THE TWO HALVES ARE NOT SEPARABLE — adopting the ladder IS deleting the TP

**Under any ladder in any cell, results with the TP kept are BIT-IDENTICAL to results with it
removed — 0 of 848 fill-cells differ — because nothing survives past 1.8R and the TP sits at
3.0/5.0R.** So the ladder deletes the only exit in the stack that has ever caught a top (2 fills at
~101% of peak, 69% of armed money last window) and returns nothing for it.

**TP removal standalone: -$0.4 to -$46/mo**, 5 fills, robust under every control at slightly negative.

### THE "UNBOUNDED" PREMISE IS WORTH LESS THAN ZERO

**The 5R WILDCARD ceiling was exceeded by exactly ONE closed fill (TUT, 5.56R) and the 3R TREND
ceiling by ONE (ZEC, 3.03R) — 2 of 200. Total real headroom above the ceiling: 0.59R = +$16/mo
gross, against $24-46/mo to remove it.**

### THE BREAK-EVEN — the same margin that killed the single floor

Rescues are structurally **capped** (best case: a -1R stop converted to +1.78R). Truncations are
**uncapped** and reach **-4.25R**.

> **The ladder needs to rescue 78-87% of the trades it touches; it rescues 67-77%. It misses by
> 10-11 points — the same margin, to within 0.3 points, by which the single 0.8R floor missed this
> morning (73.6% needed, 62.7% measured).**

**15 of 15 non-degenerate cells fail their own break-even, by 4.9 to 22.5 points.**
Interior **+$158/mo**, tail **-$348/mo** — the identical signature as the refuted rising schedules.

### THE RECOVERY PRIOR, RE-MEASURED ON ACTUAL RUNG EVENTS

After touching a rung floor, a fill makes a new high **67% at rung 1, 70% at rung 2, 62% at rung 3**
(one agent), or **58% / 57% / 88% / 71% / 100%** ascending on free-run paths (another). Lower than
the generic 93% giveback prior, **but still means two in three cut trades were STILL ALIVE.**
On free-run paths the prior gets STRONGER with height, which is exactly why cutting low is
expensive and why the rule can never collect the cheap cuts higher up.

### THE POSITIVE CELLS ARE AN ARTEFACT — and the control that proves it

Every ladder variant printing positive (+$340 to +$594/mo) **removes the floor entirely below 2R —
"delete the trail", relabelled.** The **entry-shift placebo reproduces them** (placebo median +$345
to +$448/mo on randomly scrambled entries), so that gain is **tape drift, not exit skill.** And
truncating at the live exit collapses +$479 -> +$205 while the owner's own rule moves only $0.70.
**That asymmetry is the tell.**

### CORRECTION STRUCK BEFORE IT SHIPPED — do not let this become next week's proposal

One agent told the owner his high-rung intuition was right (exposure **0.4:1** above 2.8R, "a floor
that only exists above 3R"). **That table was computed against today's TP-CAPPED exits** — the tell
is exposure 0.00R at 5.8R, only possible because a 5R take-profit already amputated everything
above it. **On genuinely free-running paths — the world this proposal creates by deleting the TP —
the ratio WORSENS with height: 1.9:1 at 0.8R, 2.7:1 at 1.8R, 7.7:1 at 2.8R, 14.9:1 at 4.8R.
There is no cheap insurance up there.**

### STRUCTURAL COST IS SMALLER THAN I FEARED — and my "zero buffer" concern was partly wrong

Verified at source: **runtime.py:2331-2336 writes `convex_peak_r`, saves, and RETURNS before
evaluating the floor — so a rung cannot arm and fire on one poll**, and `convex_peak_r` is already
persisted. ~5 lines, not new state. **My "the floor equals the current price at the arming moment,
so the next downtick closes you" concern is prevented by the existing code path.** The rule still
fails, on economics rather than mechanics.

### RANKED DECISION

| rank | action | $/mo | walk-fwd | tail | changed | env/code |
|---|---|---|---|---|---|---|
| **1** | **DO NOTHING** — arm 1.0R / retain 0.50 / ratchet 3.0R->0.75 / TP 5R WC, 3R TREND / 24h clock | **0** | — | — | 0 | — |
| 2 | TP removal only | -$0.4 to -$46 | -$7 | -$24 | 5 | env |
| 3 | widest cell S=2.0/B=0.50 (best in sweep) | -$38 | fails | -$180 | 39 | code |
| 4 | ladder, rung 1 removed | -$148 | -$18 | -$300 | 12 | code |
| 5 | **owner's rule as specified** | **-$120 to -$290** | fails | -$197 to -$348 | 34-41 | code, global |
| — | positive-printing cells (+$340 to +$594) | **ARTEFACT** | — | — | — | reject |

**Both readings of his sentence were tested.** Literal (floor live from $8): **-$180 to -$290/mo**.
Looser (floor live only after price clears $10): **-$90/mo**, ceiling rises to 2.76R, **and it still
cuts ENA at 0.80R.** Both fail.

### THE DEEPER DIAGNOSIS — worth more than the refutation

**The problem is not the ladder. It is the belief that a FLOOR is the instrument.** Every floor at
every height is a bet that a giveback means the move is over, and this book says the opposite:
**58-88% of fills that touch a rung go on to make a new high.** You are not buying protection, you
are paying a toll on a 2-in-3 false alarm, ~24 times a month.

**And the real case is HNT: it free-ran to 13.95R and the book kept 0.55R.** That is a genuine
diagnosis and it is **NOT an exit-floor problem** — a floor can only ever REDUCE the distance
between peak and exit by cutting earlier; **it cannot make you hold longer.** The money on runners
is a sizing or re-entry question. Different brief.

**The safety-arm intuition is already in the stack and better implemented:** arm 1.0R, retain
0.50 x peak, ratchet 0.75 above 3R. **That floor is uniformly LOOSER than the ladder at every peak
level, and looser is what this book pays for.**

### POWER — to close the question, not reopen it

Per-fill delta sd **$12-18**; one-month SE **$116** against a -$120 point estimate; t = -1.04,
permutation p = 0.13-0.47. **Detecting the $10/mo bar in this family needs ~2,600 fills — four
years of WILDCARD at best, decades on the tail-heavy measure.**

> **This window cannot resolve the dollars for ANY exit-floor rule, and re-slicing these 53-80 rows
> will never settle it. Quote the COUNTS, not the total: 37 of 41 cut at rung 1, 4 of 4 at rung 2,
> ZERO fills ever at rung 3 — in every cell and every ordering.**

**Nothing survives, so nothing is pre-registered.**

---

## 2026-09-09 (twelfth pass) — OPTIONAL STOPPING. The failures ARE a theorem, but not the one I named. The exit programme is closed permanently. The real defect is in WILDCARD ENTRY TIMING.

**Asked (owner):** *"Is there a mathematical theorem we can use to improve our closing strategy? It
feels like there's a big gap to fill."* 3 agents / 3 verifiers / two independent free-run
reconstructions / ~1,100 cells re-examined.

### THE THEOREM IS THE CORNER-SOLUTION TRICHOTOMY, NOT "THE PATHS ARE DRIFTLESS"

I framed it as Optional Stopping on a martingale. **That framing was too weak and too strong at
once.** The operative result is **Doob in its SUBmartingale form, applied as a trichotomy**, and it
is stronger because it does not require the drift to be zero:

    mu > 0  -> submartingale  -> E[X_tau] <= E[X_T]  -> HOLD TO THE HORIZON dominates every rule
    mu = 0  -> martingale     -> EVERY RULE IS IDENTICAL in expectation
    mu < 0  -> supermartingale -> EXIT IMMEDIATELY dominates every rule

> **In all three regimes the optimum is a CORNER. No interior rule is ever optimal under a constant
> drift of any sign. Every one of the ~430 cells — trails, one-way floors, ratchets, ladders,
> retention schedules, TP clamps — is an INTERIOR rule.**

**Interior rules become optimal only when drift depends on STATE or on TIME.**
- **State-dependence: measured NULL, WITH POWER.** This forbids the entire trail/floor/ratchet/
  ladder/retention family. **Today's four refutations were predictable in advance.**
- **Time-dependence: measured, REAL, and it is the one hypothesis that genuinely fails.** Drift runs
  negative for the first 2-4h then flat-to-positive (goodness index -3.41 at 1h, +0.54 at 24h).
  Constant-mu is measurably FALSE. **Time-dependence licenses a CLOCK, not a trail** — and clocks
  have been swept 12h-240h and price negative everywhere.

### THE DRIFT TEST IS UNINFORMATIVE; THE STRUCTURE TESTS ARE DECISIVE

| | n | 24h log drift | t | mu/sigma^2 | Shiryaev alpha | CI |
|---|---|---|---|---|---|---|
| Min5, live sleeves | 132 | +0.0216 | +0.89 | +0.504 | +1.004 | [-0.10, +2.11] |
| Min1, WC+TREND | 77 | +0.0016 | +0.07 | ~+0.04 | +0.538 | [-0.92, +1.91] |

**Both intervals span SELL IMMEDIATELY, THE FREE BOUNDARY and HOLD TO HORIZON simultaneously. The
regime is not identified.** The direct test **could not have detected a drift worth $572-$1,946 per
month.** Anyone claiming the martingale is *confirmed* by these t-stats is arguing from ignorance.

**But a trail exploits PATH STRUCTURE, not the mean — and that is measured with far more power:**
- **Variance ratios 0.957-1.014** at every horizon 0.5h-8h, all CIs covering 1.0. Textbook random walk.
- **No increment predictability** conditional on current P&L, drawdown from running max, running
  max, or time held.
- **E[running max] observed 0.1543 vs driftless sigma*sqrt(2T/pi) = 0.1650 — 93.5% of the
  theoretical value.** The strongest single number in the study.
- **THE RECOVERY PRIOR IS THE MARTINGALE'S FINGERPRINT, NOT EVIDENCE OF EDGE.** Observed 93.2% vs
  **95.9% predicted by the reflection principle**; at 25% giveback 88.4% vs 88.8%. **Retire it as
  evidence.**
- Two-barrier passage (denominator corrected to condition on hitting a barrier): 0.196/0.279/0.333/
  0.493 vs driftless 0.167/0.250/0.333/0.500. *(The earlier "jump fingerprint" was a censoring
  artefact — RETIRED.)*

**Verdict: you cannot say the paths are driftless. You CAN say, with power, that they carry no
state-dependent structure for any trail, floor or ratchet to act on.**

### MY COST-PROPORTIONALITY TEST WAS WRONG AND IS STRUCK

I called it "the strongest available evidence." **It is mathematically incapable of testing
anything on this book.**
1. **The replay subtracts exactly one round trip in every branch of every rule, so cost CANCELS in
   every paired delta.** Re-running all 292 cells with `COST_PCT = 0` changed the results by
   **0.0000000000.** The regressor that actually loaded was hold time.
2. **The naive prediction fails directly:** `$/mo ~ fire_rate` gives R^2 = 0.0045, t = -1.15. Over
   88 single-exit reparameterisations with identical turnover by construction, t = -0.84.
3. **Zero-turnover families falsify it outright.** TP clamps add NO round trips (fees are a
   percentage of notional, not per order), so the cost model predicts exactly $0. TP@1.0R prices
   **-$336/month.** Total measurable friction is ~$102/month; the observed slope implies -$483/month
   per unit fire rate.

**THE CORRECT EXPLANATION IS RIGHT-TAIL CONCENTRATION, NOT COST. Top-1 fill = 44% of total R;
top-3 = 108%; top-5 = 156%.** Fees are 0.055R against a per-fill delta sd of 0.6-3.0R.
**A book whose mean IS three trades will refute every rule that touches the right tail and show
nothing for every rule that does not.**

### THE GAP HE FEELS IS A CONSTANT, NOT AN OPPORTUNITY

| ceiling | value | status |
|---|---|---|
| oracle / perfect peak capture | +$1,900 to +$4,900/mo | requires lookahead, unattainable |
| **structural, imposed by the theorem** | **E[max] = sigma*sqrt(2T/pi) ~ 2.0-2.3R per fill** | **IDENTICAL for every stopping rule** |
| best rule you can SELECT AND VALIDATE | **-$42/mo, cl95 [-$280, +$184]** | leave-one-out over 810 cells (in-sample the same family looks like **+$251/mo**) |
| detection floor | $61-$355/mo paired; **$161/mo median cell** | **the $10 bar is 6-35x BELOW the instrument's resolution** |

**The peak-to-banked shortfall is not "designed" in the sense of chosen-and-therefore-changeable.
Under a driftless path it is IMPOSED. Every rule leaves it behind, by theorem, and the measured
running max lands at 93.5% of exactly that prediction.**

**Sample sizes: ~990 fills (~12 months) settles the REGIME question (is alpha above or below 1/2).
~34,000 fills (~35 years) would resolve a $10/month exit effect.**

### AN ENGINE BUG THAT BIASES EVERY TRAILING CELL EVER REPLAYED

**The replay updates the running peak from bar i's HIGH, then tests the trail against bar i's LOW —
a same-bar lookahead.** Lagging the peak one bar moves the Min5 baseline from **-0.0961R to
-0.0001R per fill**, and the single cell that survived a permutation FWER test goes from
**+$12.9/mo (t=4.79) to -$7.7/mo (t=-0.35)**.

> **Until this is fixed, every trailing cell this book has ever replayed is biased DOWN and every
> hold-longer cell biased UP — precisely the pattern the residual leaders showed.** One line.
> **Also: quote NO absolute levels from the simulator, only paired deltas.**

### THE COMPOUNDING HATCH — open in theory, closed by DOMINANCE

Variance drag at f=1.7-2.4% is **$13-53/month**, above the bar, so the question deserved asking.
The in-sample refutation is **circular** (it uses the point estimate of the quantity the same study
declares unmeasurable; under `dmu=0` every clamp turns POSITIVE, +$14 to +$40/mo).

**What closes it is DOMINANCE, which needs no assumption.** Exit rules and the size dial both buy
variance with mean. The exchange rate |dVar/dmu|: **exit clamps 6.6-8.5; the size dial 21-29.**
**The dial buys variance 3-4x cheaper and reaches the WHOLE drag, where the best clamp floors at
55% of it. In both states of the world every exit rule is strictly dominated by a dial the book
already has.** And LOO on the growth criterion returns **-94%/month** — right objective, wrong
instrument.

### THE REAL DEFECT: WILDCARD ENTRY TIMING — the only non-martingale term in the book

**WILDCARD entries carry a market-neutral -0.20R to -0.33R drift in their first 2-3 hours.**
- t = -2.23 at h=3; **median = mean, so NOT a tail**
- **replicated independently at Min1 (post-2026-08-10, n=83): h=2 mean -0.0205 log, day-clustered
  t = -4.71**
- BTC-neutralised: raw -0.0311, BTC-explained -0.0008, **residual -0.0311, t = -2.63**
- **ABSENT in TREND (+0.0008, t=+0.07), SQUEEZE (+0.0008, t=+0.06) on the same calendar days**
- **THE ENTRY-SHIFT PLACEBO PASSES** — run independently by two verifiers, which no agent had done:
  **offset 0 is the ONLY negative of ten offsets; REAL-minus-placebo = -0.204R (se 0.099)**
- Worth roughly **-$25 to -$830/month, best guess -$250 to -$430**

**Not all recoverable** — the -1R stop already truncates part of that leg, and skipping the entry
forfeits whatever the fill later does. **One honest tension: a within-path control found the 22-24h
window equally adverse (t=-2.31), which the offset placebo contradicts. UNRESOLVED.**

### THE DURABLE ASSET: THE FREE-RUN RECONSTRUCTION

Uncensored 24h forward paths from raw Min1/Min5, sampling ENTRIES not OUTCOMES (206 entries
reconstructed, 204 with klines, 202 with >=98% coverage):

    free-run:  65% reach +1R | 47% reach +2R | 32% reach +3R | 18% reach +5R | max +42R
               and 65% ALSO touch -1R MAE, mean MAE -1.91R. E[peak] = +3.19R
    censored ledger said:  30/66 reach 1R | 10 reach 2R | 5 reach 3R | 1 reaches 5R

> **The book has been reasoning about its own distribution from a sample that hides BOTH tails.
> That method, not any rule it produced, is the durable asset from this week.**

### RANKED DECISION

1. **FREEZE THE EXIT STACK. SHIP NOTHING.** Arm 1.0R, retain 0.50, ratchet 0.75 above 3R, TP 5R,
   clock 24h, stop -1R. Not the one-way floor, the rising schedule, the TP clamp, the ladder, nor
   any of the ~1,100 cells swept this week — **including the ones that printed positive.**
2. **FIX THE PEAK-LAG LINE BEFORE ANY FUTURE REPLAY.** One line. Until then no trailing result is
   trustworthy.
3. **ADD A PRE-FLIGHT MDE GATE TO THE STUDY PROTOCOL.** Refuse any cell whose minimum detectable
   effect exceeds the effect being hunted, and any cell whose sign flips between same-bar and
   lagged-peak, or between Min1 and Min5. **Every one of the ~430 historical cells was
   unfalsifiable BEFORE it was run.**
4. **SIZE — a separate decision on a different objective.** f=2.41% per fill with max-4 concurrency
   = 9.64% simultaneous heat against a point-Kelly of 5.35% whose 95% CI includes zero
   (P(mu<=0) = 22.5%). Cutting to ~1.5% and capping heat at ~5% moves P(12-month DD >= 50%) from
   **46% to 6%**. **Argue from RUIN, not growth** — as a growth trade it fails the same test that
   killed the exit cells. Point cost -$57/month of a mean that is statistically zero.
   **Owner's risk tolerance, not a ruling.**
5. **NEXT STUDY: WILDCARD ENTRY TIMING** (above).

### WHAT THIS RULES OUT PERMANENTLY

- **Any interior exit rule on arithmetic dollars.** Corner trichotomy + null state-dependence.
- **Variance-reduction-via-exits on growth.** Dominated by the size dial in every state of the world.
- **"Is the peak-to-banked gap recoverable?"** No. It is sigma*sqrt(2T/pi), a constant, verified to
  within 6.5%.
- **Any exit study on fewer than ~1,000 fills.** It cannot return an answer, only noise with a sign.
- **Du Toit-Peskir / Shiryaev free boundaries** until n is 10x: the CI spans all three regimes and
  constant-mu is measurably false.
- **The 93% recovery prior as evidence of edge** — RETIRED, it is the driftless prediction.
- **The two-barrier "jump fingerprint"** — RETIRED, denominator error.
- **The cost-proportionality claim** — STRUCK, mathematically untestable on this engine.

### WHAT STAYS OPEN

Whether mu > 0 at all (~12 months of fills settles the regime); WILDCARD entry timing; and whether
the historical exit record is contaminated by the peak-lag bug — **probably yes for the trail
family, which is a reason to STOP, not a reason to re-run.**

---

## 2026-09-09 (thirteenth pass) — delayed WILDCARD entry vs the phantom control. REFUSED at the bar. And THREE corrections, one of which retires a hazard that has haunted three studies.

**Asked (owner, with the control named):** *"Test the delayed entry with the price-improvement
control."* 3 agents / 3 verifiers.

### CORRECTION 1 — "DISGUISED STOP-WIDENING" IS THE WRONG INFERENCE AND I HAVE BEEN ASSERTING IT ALL WEEK

I pre-registered: *if the phantom matches or beats the delay, the rule is a disguised
stop-widening.* **That inference is FALSE on this data.** A verifier built the actual twin — enter
at t0, no waiting, widen `sl_frac` 0.105 -> 0.140 so the stop sits exactly where the delayed stop
would sit, dollar risk held constant:

    stop-widening twin:  +$17/mo (targets rescaled) to +$46/mo (targets frozen)
    the phantom:         +$309/mo
    same at d=120/180/240: +$18 to +$57

**A better entry moves the UPSIDE closer as well as the downside further; stop-widening only
reproduces the second half.** The delay is not a disguised stop-widening. **RETIRE THAT SPECIFIC
INFERENCE** — it has been used against three proposals this week.

**So the phantom here is a DECOMPOSITION of an ATTAINABLE price, not a competing rule.** An
unconditional delay fills 100% of the time and the market genuinely hands the improvement over.
That is why this is the first entry-side candidate that could not be dismissed on the phantom alone.

### WHAT THE PHANTOM DOES ESTABLISH — the SELECTION term is worth negative money

| construction | n | DELAY | PHANTOM | **SELECTION (the waiting itself)** |
|---|---|---|---|---|
| live Min1, discovery era, d=150 | 53 | +$387 | +$309 | **+$78, se $200, t=+0.64** |
| live Min1, discovery era, d=90 | 53 | +$210 | +$451 | **-$242, t=-2.52** |
| Min5 INDEPENDENT era, N=180 | 36 | -$9 | **+$435** | **-$444** |
| **pooled, both eras, N=180** | **91** | **+$139** | **+$367** | **-$228, t=-1.49** |
| Min15 detector replay | 3,911 sig | -$119..+$110 | >= delay in 12/14 cells | negative |

> **The value of waiting, price held identical, is zero or negative in EVERY construction, and the
> single cell reaching significance is NEGATIVE. Pooled: -$195 to -$228/month. Only the price is
> worth anything.**

**THE PERMUTATION CONFIRMS IT INDEPENDENTLY:** shuffle which trade receives which realised
improvement and grant it at signal time — null +19.68R (N=120) and +17.55R (N=180) against observed
+21.02R and +24.90R, **p = 0.405 and 0.065. It does not matter WHICH trade gets the better fill.**
That is the signature of a pure price effect and the negation of a selection rule.

### THE THREE-WAY DECOMPOSITION — the same shape as the precedent, on the bad side of it

Pooled, n=91, N=180, 1R=$22.60:

    PRICE      +$367     obtainable, 100% fill
    SELECTION  -$228     t = -1.49
    RUNAWAY      $0      an unconditional delay forgoes nothing
    ----------------
    TOTAL      +$139     t=+1.38, CI [-$58, +$337], **MDE $198**

**The total sits BELOW ITS OWN DETECTION FLOOR, so the cell is REFUSED, not reported as positive.**
Precedent: the 2026-09-08 pullback was +$174 price / -$52 selection (WILDCARD) and +$225 / -$426
(TREND). **This lands at +$367 / -$228.**

**Limit variants are dead on forgone accounting exactly as prior art predicted:** declined signals
were worth **+$280 to +$716/month forgone**, six to fourteen times the price term they chase. Fill
rate is a coin flip (49-55%) at every horizon. **No limit variant, ever.**

### CORRECTION 2 — THE DRIFT DID NOT REPLICATE OUT OF SAMPLE. I SAID IT DID.

**I told the owner the drift was "replicated at Min1, t=-4.71."** That replication is drawn from
**post-2026-08-10 — which IS the discovery window.**

**The only genuinely independent era (Jun 15 - Aug 5, n=36) shows the drift at -1.20% at 120m and
-2.34% at 180m, t = -0.7 and -1.2 — roughly HALF strength and not distinguishable from zero.**

> **The drift is a well-measured property of ONE 27-day window and of live mid-bar fills. It is NOT
> yet a fact about the strategy. Stop describing it as replicated out of sample.**

The drift IS real on live fills (verifier 1 reproduced it at full magnitude on all 53 rows: h=2
-0.350R, t=-4.37, median -0.304 tracking mean -0.350; verifier 3's random-time placebo on the price
improvement is clean at real +3.82% vs 300 random draws at -0.17%, p=0.000). **But obtaining the
price did not produce dollars outside the window it was found in: the independent era was granted
+20.4R of genuine improvement and delivered -0.7R — a 3% CONVERSION, against 98% in discovery.**

### THE MECHANISM IS STOP SATURATION, NOT INFORMATION — and it is the study's real finding

Baseline stop-outs are **28 of 53 (53%; live realised 51%)**. Entering 3% better with a recomputed
stop **translates the whole bracket 3% down, so 14 of those 28 stop being stop-outs.** In the
independent era, whose baseline stop-out rate was 47%, the same delay moved stop-outs 17 -> 15 and
produced nothing.

**The delay's dollar value is a function of how stop-saturated the window happened to be, not of
the drift size — which was equal or larger in the era that paid ZERO.**

> **THE COROLLARY IS THE MOST IMPORTANT NUMBER IN THE STUDY: a phantom gift of k=0.05R — about 30
> BASIS POINTS of price — is worth +$172/month. This book's P&L is a NEAR-DISCONTINUOUS FUNCTION OF
> STOP DISTANCE. Any study that perturbs entry price or stop placement on this corpus will
> manufacture enormous apparent dollars.**
>
> **MAKE THE MATCHED PHANTOM COLUMN A STANDING REQUIREMENT FOR THAT ENTIRE CLASS OF QUESTION, NOT A
> PER-STUDY ONE.**

Pure phantom grid (discovery era, $/mo): k=0.05 **+$172**; 0.10 +$240; 0.15 +$349; 0.20 +$343;
0.30 +$391; 0.35 +$504; 0.50 +$612. **A gift of 30bps is already seventeen times the bar.**

### CORRECTION 3 — THE LIVE ENGINE IS CLEAN. The peak-lag defect is REPLAY-ONLY.

Flagged as "the largest number anyone saw today" and unchecked. **VERIFIED AT SOURCE
(runtime.py:2331-2337):**

    if r_now > peak_r:
        position.metadata["convex_peak_r"] = round(r_now, 4)
        ... self._save_state()
        return False          # <-- RETURNS before evaluating the floor

**The live bot records a new peak and RETURNS without testing the floor on that poll. It cannot
arm-and-fire in one tick and does NOT carry the defect.** The bug is in the replay engine only
(it moved a replay baseline -$73 -> +$248/mo and flipped two headline cells). **The bot is correct;
only the historical STUDY RECORD is contaminated — which is a reason to stop replaying, not to
change the bot.**

### SCALE HONESTY — every headline is a 9.4x rescaling

**Median `risk_usdt` on the 53 rows is $2.40, and only 3 of 53 are >= $11.28.** The sleeve's
realised edge is **+0.013 to +0.027R/fill = $10-20/month.** **A +$387/month claim is 20-40x the
sleeve's entire realised edge** on a book with a +/-$60/mo envelope. On this book, a number that
size has always meant a hidden structural assumption.

### TREND IS REFUTED ON MECHANISM — and the contrast is structural

**TREND price improvement is NEGATIVE at every horizon (-0.21% to -0.80%).**

> **TREND signals CONTINUE; WILDCARD signals REVERT.** No p-value needed. Any future entry-timing
> idea must be sleeve-specific for this reason.

### WHAT THE LIVE RECORD SHOWS

- **Signal->entry latency: 7-9 rows, ~2.5 bps mean** (09-09 ZEC: signal 1233.42 -> entry 1234.00,
  4.7 bps). At the measured lever of **$2.91/month per basis point**, fixing it ENTIRELY is worth
  **$7.37/month — below the bar. The book is not losing money to execution latency.**
- **t_adverse: six readings, 38-95 min.** WILDCARD 38.1 and 41.5 min to -0.5R (6.3 and 14.3 min to
  -0.25R); TREND 37.9, 56.8, 95.2. Consistent with a trough at h=2-3, **but two WILDCARD rows are a
  shape, not a distribution.** 19F has zero fires because every crossing landed past its 30-min
  window.
- **ENTRY LATENESS: WILDCARD fills sit at 0.877 of the prior-3h range** (median 0.890, **91% above
  0.75**). **The |3h ROC| >= 8% gate buys the extreme BY CONSTRUCTION**, and the tape takes 0.2-0.3R
  back over the next 1-3 hours in BOTH eras. **That is a permanent tax on the trigger. It is a
  property of the GATE, and that is where the next study points — not at the clock.**

### RANKED DECISION

**1. DO NOTHING to the live bot. $0/month.** Keep entering WILDCARD at market on the signal bar.
**THE TWO CHANGES CANNOT COEXIST:** a 150-minute delay moves every t_adverse later and shallower,
driving 19F's fire rate to zero, **and 19F's primary is a paired counterfactual on the same
entries — changing the entries VOIDS IT RETROACTIVELY.**

**2. SHADOW-LOG THE COUNTERFACTUAL. $0/month, zero risk, no code on the trading path.** Every input
already exists. Re-run the paired counterfactual monthly at d = 30/60/90/120/150/180/240
**simultaneously**. **Fix the 200-row ring buffer first** (full; every month costs ~33 fills of the
sample that would settle this), and **store 48h of PRE-signal bars as well as post** — the current
corpus holds a median 1.2h before each signal, which is why no backward placebo is computable.

**3. REJECTED — DELAY-MARKET(150min), stop recomputed.** In-sample +$387/mo, **phantom +$309 (80%),
MDE $257, pooled OOS +$139 below its own $198 floor, independent era -$9.** Fails: conversion out of
era, pooled selection negative, median +0.164R vs mean +0.519R with 13 exact zeros, ex-top-15%
collapses to +$197, and it is a 41-trade LONG-side result (+0.620R long vs +0.173R short).
**CODE:** a pending-entry queue surviving `FUTURES_RESUME_ON_BOOT=1`, plus an exchange-bracket fix
(LIVE_CONFIG anchors TP/SL to the SIGNAL price and never moves it, so a 3.8% delay diverges the
exchange stop from the software stop by ~0.36R).

**4. REJECTED — d=120 / d=180 / the "hump".** **There is no computable control on this data
separating d=150 from d=30.** The outcome placebo that condemned d=30 and admitted the band runs on
**n=14** with a se of $400-700/month, and was reported as a clean PASS/FAIL with no n attached.
Strip it and what remains is **an argmax over eleven correlated cells on 53 fills, sitting exactly
where eight trades sit.**

**5. REJECTED — DELAY-LIMIT(N), any k.** -$603/mo net of forgone. Fill rate 49-55%. Declined signals
carry +0.17R to +0.42R live-exit against a book mean of -0.024R.

**6. REJECTED — TREND delay, any N.** Price improvement negative at every horizon. Mechanism.

**7. DO NOT SET `FUTURES_SL_ATR_MULT` 3.0 -> 5.25.** +$280/mo in-sample **through the IDENTICAL
stop-saturation channel that just failed out of sample.** That number is a demonstration of the
sensitivity problem, not a candidate.

### PRE-REGISTRATION — OF THE MEASUREMENT ONLY

**Primary:** running paired dollar delta, logged per fill against the same-signal counterfactual.
Positive at n>=40 with a 95% day-clustered CI excluding zero at n=87. **The primary statistic is the
ex-top-5%-by-delta figure, not the mean.** **Secondary:** the LONG-only delta must hold and the
shorts must stop contradicting it. **Report the placebo n on every run.**
**Kill:** two fills whose delayed entry is worse than signal by >1.0R of stop width, or a negative
running delta at n=40.

**Sample size:** per-fill sd of the dollar delta is **$20.20**. At 33 WILDCARD fills/month —
**87 fills = 2.6 months for a $200/mo MDE; 349 fills = 10.6 months for $100/mo; the $10/mo bar needs
34,900 fills = 88 years and is unreachable.** At the money actually at risk (median $2.40, not
$22.60), the honest expected value of the whole proposal is **$15-40/month.**
First re-read ~2026-11-25, cleanly after 19F closes.

### WHERE THE NEXT STUDY POINTS

**Not the clock. The GATE and the STOP.**
- **~53% of WILDCARD fills give back a full 1R within 2.5 hours**, and a 30bps price gift is worth
  $172/mo. **The lever is stop distance or the entry trigger.**
- **The trigger buys the 3h extreme by construction: fills sit at 0.877 of the prior-3h range, 91%
  above 0.75.** The tape takes 0.2-0.3R back in both eras. **That is a property of the |3h ROC| >= 8%
  gate itself.**

---

## 2026-09-09 (fourteenth pass) — the entry gate. I GAVE A FALSE PREMISE THE REPO HAD ALREADY CORRECTED. Nothing ships but one telemetry key. And the biggest uninstrumented quantity in the system was found.

**Asked (owner):** *"Point the next study at the entry gate."* 3 agents / 3 verifiers.

### MY ERROR — AND IT IS THE SECOND CONSECUTIVE NIGHT

I briefed: *"`ROC_BARS` has never been swept. Only the threshold has."*

**FALSE.** `tools/pit_roc_sweep.py` is titled *"ROC trigger window x threshold sweep"*, its grid is
`W in {4, 8, 12, 24, 48}` x thresholds, **15 cells, 208 days.** And **`docs/DECISION_RULE.md:2141`
corrects this EXACT claim two days ago:** *"I claimed `ROC_BARS` had NEVER been swept. It HAS."*

**I handed the agents a false premise that this repo had already corrected in writing, and the
agent quoted the prior-art section immediately below its own refutation without reading up the
page.** Second consecutive night for this error.

**The two harnesses do not replicate.** Prior winner **6h/12% (W=24 @ 0.12): +$62.16, 690 fills,
22/29 weeks** — the only both-halves survivor. Tonight's winner **12h/8% (W=48 @ 0.08): +$270** — a
cell the prior grid never tested (its lowest W=48 threshold was 0.12), while tonight's grid never
tested the prior winner. **Two independent replays, two non-replicating winners, neither
reproducing the other. That is best-of-N search noise, and the family-wise p=0.0875 confesses it.**

**ROC_BARS is now added to the structurally-unverifiable list beside MAX_WICK and
VERTICAL_ATR_MULT. Swept twice, non-replicating winners, CLOSED.**

### THE LATENESS FEATURE IS BROKEN — but my "it disables the ranker" claim is REFUTED BY PROOF

**Broken, and worse than I said: 70.7-75.0% of fills read EXACTLY 1.0** (53/75 independent pass;
69/92 and 39/56 in the agents'). The live column carries **18-40 distinct values where the fixed one
carries 145.** The owner has been reading a variable that is three-quarters a constant.

**But the second half of my lead is FALSE, and it is provable rather than statistical:**

> **`live = clip(fixed, 0, 1)` is an ALGEBRAIC IDENTITY** — verified, 0 violations in 147 rows.
> **The ranker's deep band [0.50, 0.70) lies STRICTLY INSIDE [0,1], where `clip` is the identity.
> Band membership CANNOT CHANGE for any input.** Bit-identical under both features (34/940 both
> ways; 3 of 147 with zero disagreements). Swapping the fixed feature into the rank key moves the
> book by **EXACTLY $0.00/mo** in all four cells tested.

**So the broken measurement is NOT why the ranker is inert.** The ranker is inert because
**the candidate field is almost always ONE** — 92 of 93 shadow scans are singletons, all three open
positions record `candidate_field = 1.0`, zero `rank_dropped` rows since the recorder was added —
**and because the gate genuinely buys breakouts.** Interior values (0.528, 0.58) sit unclipped in
the live column, **proving the measurement always COULD see deep pullbacks. There simply are none.**

**The ranker's stated justification is now retired with evidence.** Its docstring cites *"247 fires,
60d, deep-pullback +1.55R vs +0.12R at the extreme."* **The band holds 1 of 56 / 2 of 75 / 3 of 147
across three independent corpora, and both live band fills are max losers.** A prior that has sat in
a live docstring for months is dead.

**Also settled:** `fixed < 0` is IMPOSSIBLE — `base = c.iloc[-(ROC_BARS+1)]` is the oldest bar of
the same frame and therefore inside `c[:-1]`, so a LONG (roc>0) requires `cur > base >= min(c[:-1])`.
**The censoring is one-sided.**

### SHIP IT AS A NEW KEY, NOT AN IN-PLACE EDIT

**`entry_lateness` flows to metadata -> `trade_history` -> the feature store the CE engine learns
from. An in-place edit silently mixes censored and uncensored values across the deploy date with no
version marker.** This book already lost 32 days of evidence to a column whose semantics changed
silently.

    KEEP  entry_lateness   exactly as-is (broken, clipped, feeding the inert ranker
                           and five absolute-threshold CE buckets)
    ADD   entry_extension  = (cur - min(c[:-1])) / (max(c[:-1]) - min(c[:-1]))

**Consumer audit at source: the value is read by `_wildcard_rank_key` (ordering only) and
`conditional_expectancy.py:157-170` (propose-only). NO entry, sizing, stop or exit path reads it.**
**$0/month, and the $0 is CERTAIN rather than estimated.** It can ship today.

**DO NOT drop `is_deep_lateness` from the ranker.** That is BEHAVIOURAL, not a bug fix — it deletes
a promotion firing on ~2-3% of fills, evidenced by n=2, mid-trial, with two positions open.

### THE HONEST NULL SURVIVES — extremeness is UNINFORMATIVE

Three engines, three corpora, one answer. **Spearman(lateness, R) = +0.011 / +0.026 / +0.056**,
null at every window from 1h to 12h, null in the refused shadow ledger (+0.088, p=0.411), flat
across eras and **all 58 leave-one-symbol-out folds.**

> **Buying the extreme is NEITHER the defect NOR the edge. It is uninformative. The 0.877 figure
> describes the gate accurately and predicts nothing.**

Every gate built on it sits below its own MDE and deletes 21-52% of fills into a volume-limited
book: keep >1.00 (+$3.6), keep >1.10 (+$4.8), keep <=1.20 (+$0.3), reject [1.00,1.20) (+$10.6),
reject the less-extended half (+$13.0).

**The one nominally significant cell is the cleanest demonstration of why the controls exist.**
Median split inside the saturated block: gap **+1.009R +/- 0.476, t=2.12, permutation p=0.042,
entry-shift placebo CLEAN, LOO 0/39 flips, LOSO 0/30 flips.** Then: family-wise p=0.167;
**ex-top-5 collapses it +1.009 -> +0.083** (three fills carry the entire gap against a block total
of -0.13R); era decay +1.687 -> +0.346; **walk-forward +0.085. Ten in a row.**

**And its direction is the opposite of the intuition: MORE extended did BETTER.** The framing does
not invert the other way either — deep early give-back predicts WORSE outcomes (-1.008R vs +0.755R
at t+24h, p=0.005) **but its entry-shift placebo FAILS outright** (a fake entry one bar later scores
HIGHER, +0.422 vs +0.361; one hour later higher still, +0.477). **That is path autocorrelation, the
same signature that retired the G2 pullback shape.**

### THE REFRAME IS CORRECT — the stop sits inside the move it is trading

    median 3.0xATR stop = 0.645 of the prior-3h high-low range
    94.6% of stops fall INSIDE the move's own 3h range; only 10.9% sit beyond half of it
    median MAE -0.505R by 1h, -0.914R by 6h
    **50.4% of WILDCARD fills settle at R <= -0.9** (exchange-side stops booked as EXCHANGE_CLOSE,
    which is why only 4 rows carry a STOP_LOSS label)

> **The ~41-50% stop-out rate is ARITHMETIC, not misfortune.**

**But it does not monetise.** Best structural cell (stop at 1.25x the prior-3h range) prices
**+$17.8/mo against MDE $20.5**; the family-wise null p90 is **+$17.7** for an observed best of
+$17.8 — **it lands ON the search-noise 90th percentile**; the sweep is a one-cell SPIKE (0.90x and
1.00x negative, 1.10x +$6.3, 1.25x +$17.8, 1.40x +$11.8); **the generic ATR-widening twin at 1.5x
alone prices +$9.6, so half the effect has no structural content**; ex-top-5 keeps only $8.6 of
$17.8. **REFUSED — a true statement about the book's geometry, not a trade.**

### THE BIGGEST UNINSTRUMENTED QUANTITY IN THE SYSTEM — found tonight, never measured once

**`signal_price` and `entry_price` NEVER CO-OCCUR ON A SINGLE ROW — 0 of 125 WILDCARD fills carry
both.** So the gap between "the signal fired" and "we bought" has **never been measured on any
fill, across the whole history.**

**The one case anybody has ever looked at:** `DECISION_RULE.md` records MAGMA — trigger cleared
**19:00 at 0.26041**, bot filled **19:58 at 0.273** = **+480 bps ADVERSE**, and the next hour's
drawdown was **-1.62% from the signal price versus -6.15% from the fill. THE TRADE WOULD NOT HAVE
STOPPED OUT.**

Meanwhile the instrumented `entry_slippage_bps` has a **median of 3 bps on 11 rows** — **that
measures the last-mile ORDER FILL. It does not measure THE WAIT.**

> **A 58-minute hole, ~480 bps in the only observed case, and it is where the 0.877 came from.
> Everyone spent the night arguing about 3h vs 12h ROC windows — a knob worth +/-260 bps of entry
> location that was already refuted — while the signal-to-fill gap sits uninstrumented.**

### THE PHANTOM CONTROL IS NOT ITSELF CONTROLLED

**Three implementations of the mandatory control disagree by 4x on the same input.** A k=0.05R gift
prices **+$3.9/mo (Q1), +$6.3/mo (Q3), ~+$7.9/mo (Q2 normalised)** at 1R=$2.41, against the standing
+$172/mo at ~10x risk which normalises to ~$17/mo. One agent asserted its number "is the same $172
once rescaled" — **its own arithmetic gives $3.9 x 10.4 = $41, not $172.** Another report contains
**two different values for its own +30bps cell** ($74.4 in the table, $172.02 in the verification).

> **A control that is not itself controlled is decoration. Standardise the phantom implementation
> before it is used as a gate again.**

### THE POWER ARITHMETIC — this closes the ENTRY programme

Sleeve realised edge **+0.064R/fill, sd ~1.4R, 33 fills/month.** n = (2.802 x sd / delta)^2:

| to resolve | delta (R/fill) | fills | months |
|---|---|---|---|
| that the sleeve is positive at all (+0.064R) | 0.064 | 3,757 | **114 (9.5 yr)** |
| $10/mo at realised 1R $2.40 | 0.126 | 965 | 29 |
| **$10/mo at the live 1R** | 0.0196 | **40,160** | **1,217 (101 yr)** |
| paired entry/stop change (sd 0.60R), live 1R | 0.0196 | 7,380 | 224 (18.6 yr) |

**MDE in R is scale-invariant; the deposit changed only the dollar figure a resolvable R-effect maps
to. At the size this book now trades the smallest resolvable whole-book gate change is ~$64/month,
and even that takes 29 months. You cannot demonstrate the sleeve is distinguishable from zero inside
a decade, so ranking two versions of its gate is structurally an exercise in ordering noise.**

> **The EXIT programme closed on a theorem. The ENTRY programme closes on arithmetic, and it closes
> harder.**

### RANKED DECISION

| # | change | $/mo | phantom | MDE | fills | label |
|---|---|---|---|---|---|---|
| **1** | **Add `entry_extension` as a NEW key; leave `entry_lateness` untouched** | **$0 CERTAIN** | $0 | n/a | 0 | **bug fix / telemetry** |
| **2** | **DO NOTHING to the gate, the stop, the ranker, the window** | $0 | $0 | $0 | 0 | — |
| 3 | Annotate the dead deep-pullback prior in the ranker docstring + CE comments; add `ROC_BARS` to the unverifiable list | $0 | $0 | n/a | 0 | docs |
| — | REFUSED: ROC_BARS 12->48 @0.08 (volume-unmatched) | +$270 | **+$794** | $346 | +44 | behavioural, 6 call sites |
| — | REFUSED: ROC_BARS 12->48 @0.1175 (volume-neutral) | +$178 | **+$778** | $389 | -22 | the controlled twin — a null |
| — | REFUSED: structural stop at 1.25x prior-3h range | +$17.8 | $0 | $20.5 | 0 | lands ON the null's p90 |
| — | REFUSED: reject fixed lateness in [1.00,1.20) | +$10.6 | $0 | $22 | -12 | |
| — | REFUSED: reject the less-extended half | +$13.0 | $0 | $28 | -20 | |
| — | REFUSED: edit `entry_lateness` in place | $0 | $0 | n/a | 0 | **bug fix WITH A CORPUS BREAK** |
| — | REFUSED: drop `is_deep_lateness` from the ranker | ~$0 | $0 | unmeasurable (n=2) | 0 | **BEHAVIOURAL** |

**Nothing is pre-registered because nothing survived. Every refused cell fails at least two of
{own MDE, family-wise multiplicity, ex-top-5 by delta, walk-forward, the volume rule, the phantom
column}. Item 1 needs no pre-registration: its delta is zero BY PROOF.**

### WHAT TO INSTRUMENT NEXT — and it is the only open direction

**Record `signal_price` and `entry_price` on the SAME row, plus the signal timestamp.** The
signal-to-fill gap is the largest bps quantity in the system, has never been measured, and the one
observed case (MAGMA, +480 bps over 58 minutes) would have changed that trade's outcome. **It is
free to record and nothing can be concluded about the gate until it exists.**

---

## 2026-09-10 — staggered partial TP (the ladder, done properly). REFUSED. And MY IOST counterfactual was wrong by $16.

**Asked (owner):** deep-dive SOPH and IOST, design the best staggered TP, test 4 weeks, then wider
if it survives. 3 agents / 3 verifiers / 3 independently built engines / ~120 cells.

### CORRECTION 1 — THE IOST TRAIL EXIT WAS NEVER $58.02

I reported all evening that the trail would have banked **3.153R = $58.02** off a 4.204R peak.
**Wrong.** Path-exact Min1:

    16:56Z  peak 3.0887R  -> TRIPS THE 3R RATCHET, retain 0.50 -> 0.75, floor jumps to 2.3165R
    17:11Z  low prints 2.2208R -> THROUGH THE FLOOR. The trail exits at ~2.32R = ~$42.
    18:37Z  price runs on WITHOUT the position to 4.5762R (the true free-run max)
    22:02Z  a second, LOWER high at 4.4417R
    09-10 07:14Z  collapses through the stop to -1.35R

**The 4.204R I was tracking was a LATER, LOWER local high, printed 83+ minutes after the position
would already have been flat.** My figure came from a bar-close reconstruction — my tracker polled
every 10-30 minutes and never saw the 17:11 wick. A close-only replay gives $58.70, which is where
my number came from; **the live 1-second poll sees the wick.**

> **CONSEQUENCE: the owner's manual close at 15:45 for +$33.23 cost him about $9, NOT $25.**

**Caveat stated honestly:** the ratchet trips by 2.9% and the breach clears the floor by 0.096R on a
single minute bar. Knife-edge. On a close-only basis the ladder costs IOST -$22.71 instead of
-$10.02. **Every basis is negative; only the size moves.**
**If 3.153R / $58.02 is load-bearing anywhere else in the record, re-derive it.**

### CORRECTION 2 — MY SOPH NUMBER WAS ~30% HIGH

I said thirds at 1R/2R give +$6.20. **Correct: +$4.70.** I compared GROSS rung levels against the
NET realised residual (1.11R). The residual carries the cost too; it must be gross-vs-gross.
**Sign and shape right, magnitude high.**

### CORRECTION 3 — MY CROSSOVER TABLE WAS WRONG FOR THE 2R RUNG

I briefed "a 2R rung helps only when the trade peaks below 4R." **It is below 3R.** The ratchet
raises F **discontinuously**: at peak 2.999 the floor is 1.500 and the 2R rung pays; at 3.001 the
floor is 2.251 and it is **already underwater.** **The ratchet removes a full R of winning zone from
the 2R rung, exactly where the fat fills live.** My 1R statement was exactly right.

### THE CROSSOVER RULE — the durable yield of this study

    delta = SUM_j f_j (L_j - F)     where F = the eventual trail exit level

**A rung at L pays IF AND ONLY IF L exceeds the eventual floor F.** Verified to 4 decimals against
path replay on both named trades by three independent engines.

| rung | pays iff peak is |
|---|---|
| 1.0R | < 2.00R |
| 1.5R | < 3.00R |
| **2.0R** | **< 3.00R — NOT 4R** |
| 2.5R | < 3.33R |
| 3.0R | < 4.00R |
| 4.0R | < 5.00R |

**TWO STRUCTURAL FACTS, neither a sample estimate:**

**(a) The rung fires at L => peak >= L => F >= 0.5L.** So the gain per rung is **CAPPED at 0.5L**
(0.25L above the ratchet) while **the loss grows without bound as peak grows** — and the losses land
on the fills that make the book.

**(b) `L > F` is a condition on a peak the trade HAS NOT YET MADE.** At the instant the 1R rung
fires, a staller and a runner are the same observation. **NO IMPLEMENTABLE RULE CAN SELL ONLY INTO
STALLS. This is not a tuning problem.**

**Live E[peak | armed] = 2.221R, so the median floor sits at 1.111R — ABOVE a 1R rung. The
proposal's first rung is a losing bet before any cost is counted.**

### THE TWO NAMED TRADES

| | peak | baseline F | ladder (thirds 1R/2R) | delta | peak capture |
|---|---|---|---|---|---|
| **SOPH** SHORT | 2.379R | 1.1895R (= 0.50 x peak exactly) | 1.3965R | **+$4.70** | **49.0% -> 57.7%** |
| **IOST** LONG (free-run) | 3.089R at the cut | **2.3165R = ~$42** | 1.7600R | **-$10.02** | **74.6% -> 57.0%** |

**NET OVER THE PAIR: -$5.32.** SOPH is a stall and gains; IOST is a runner and pays for it; **the
runner's loss is twice the stall's gain.**

> **THE OWNER'S SOPH INTUITION WAS CORRECT. It really would have finished closer to its peak, and
> it would have paid him to. The proposal fails on everything else.**

### THE 4-WEEK RESULT — zero positive cells, three engines, ~120 cells

**Rung reach and the sign census (live rows, n=77):**

| rung | reached | pays | costs |
|---|---|---|---|
| 1.0R | 37 (48%) | 22 | 15 |
| 1.5R | 20 (26%) | 7 | **13** |
| 2.0R | 17 (22%) | 5 | **12** |
| 2.5R | 14 (18%) | 2 | **12** |
| 3.0R | 6 (8%) | 3 | 3 |

> **Above 1.5R the MAJORITY of reachers are on the losing side — because reaching a high rung is
> itself evidence the trade is a runner. THE RUNG'S OWN TRIGGER IS NEGATIVELY PREDICTIVE OF THE RUNG
> PAYING.**
>
> **And ZERO of the 39-43 losing fills is touched by any rung: every loser peaks below 1R.
> ALL EXPOSURE SITS ON THE WINNERS.**

**Exposure ratio (loss to runners : gain from stalls): 1R rung 2.7-3.4:1, 1R+2R 5.0:1,
1R+1.5R+2R 7.1:1.** Compare the measured tightening triggers: T=1.00R 3.5:1, 1.50R 9.7:1, 2.00R
8.6:1, and the rising schedules 3.7:1 -> 6.7:1. **Same curve, same ridge, worsening monotonically
with depth. The partial scale-out is the tightening family measured through a different instrument.**

**Walk-forward -$2.25 / -$2.29 / -$22.89/mo. Eleventh kill in a row — and the FIRST candidate to
arrive dead: the optimiser could not find a positive cell to overfit to and converged on "put the
rung so high it never fires."**

**Contamination worth knowing:** the corpus straddles RETAIN 0.30 -> 0.50 (2026-08-29); 43 of 81
rows realised F ~ 0.263 x peak, so half the book was described by the wrong crossover table.
**Repricing at live retain makes every cell WORSE. The era mix was biased in the ladder's favour.**

**Multiplicity, honestly:** "0 of 122 cells" reads stronger than it is — the cells are deterministic
linear combinations of ~7 rung statistics on one overlapping sample. **It is seven numbers, not 122.**
Best |t| anywhere is 2.17; Bonferroni over the week's ~1,255 exit cells needs 4.1.

### IT DOES NOT EVEN BUY THE STATED OBJECTIVE

| | equal-weighted | **R-weighted (the actual P&L)** |
|---|---|---|
| baseline | 57.4% | **74.1%** |
| 1R @ 25% | **57.5% (+0.2pp)** | **67.1% (-7.0pp)** |
| 1R+2R @ 1/3 | 55.8% (-1.6pp) | **58.4% (-15.7pp)** |
| 1R+1.5R+2R @ 25% | 53.7% (-3.7pp) | **55.1% (-19.0pp)** |

**Exactly ONE cell in the entire family raises peak capture — 1R @ 25%, by two tenths of a point,
for about $19/month. And it raises it only on the EQUAL-WEIGHTED metric, which up-weights
small-peak fills relative to their dollar contribution.**

> **"Closer to peak", averaged equally across trades, is arithmetically A REWEIGHTING TOWARD THE
> STALLERS — and the stallers are not where the money is. Weight it by money and the same cell is
> 7 points FURTHER from the peak. THE LADDER BUYS A METRIC, NOT A POSITION.**

### THE COMPOUNDING ARGUMENT DIES ON ITS OWN DECOMPOSITION

Per-fill sd falls 18-46% — real. **And worthless: max drawdown is IDENTICAL across every ladder
cell. Downside sd is IDENTICAL. Zero losing fills are changed.**

> **100% of the variance reduction is UPSIDE dispersion, because a rung can only fire on a trade
> already in profit and cannot touch the left tail by construction. The ladder sells the only
> variance worth owning and buys nothing on the side that hurts.** Log-growth falls at every cell.

The size dial dominates it 3x on |dVar/dmu| — **but the dominance argument is not needed; the
decomposition kills it outright.**

### THE BEST SETUP, AS ASKED — and the trap inside it

**Single rung at 2.0R, sell 25%, residual keeps the unchanged trail, entry and stop untouched.**
Chosen by the crossover, not by search: the lowest rung clearing E[F|armed]=1.11R that still fires
on a SOPH-shaped trade. Gains SOPH **+$4.60 — 98% of the full thirds ladder from one rung.**
Book cost **-$3.8 to -$16.3/mo**, MDE $8.6-26.9, **fails the gate.** Fires on 17 fills/4 weeks.

> **THERE IS NO SETTING THAT DOES BOTH. The rungs that help SOPH (1R, 2R) are the expensive ones.
> The rungs that are nearly free — 3R and 4R, the only ones near break-even (1.12:1 exposure,
> MDE $4.16, a genuine NULL WITH POWER) — NEVER FIRE ON SOPH AT ALL, whose peak was 2.38R.
> The harmless setup cannot deliver the purpose. The setup that delivers it costs the most.**

### THE LABEL THE RECORD MUST CARRY

**NULL WITH CERTAIN COSTS — not "-$43/month measured."** Under a martingale, optional stopping makes
a staggered TP worth EXACTLY ZERO, and the peak-conditioned ratchet does NOT exempt it: conditional
on touching L the residual restarts at L, so E[F | touched] = L regardless of exit definition.
**Two of the three agents got this wrong.** The measured negative requires drift; drift was measured
at +0.45 to +0.79R over 6 of 7 rungs but **nothing clears |t| = 2.6 and the rungs are nested.**
**No cell clears its own MDE — every one sits at 0.45-0.62x its detection threshold, and that ratio
is scale-invariant in f, so NO CHOICE OF FRACTION CAN BUY POWER.**

### ENGINEERING — reusing the existing module would import a refuted family

`partial_bank.py` **exists and is wired end to end, but is DELIBERATELY DORMANT** — refused for
convex sleeves at `runtime.py:1389-1391`, gated on `pmt_stop_first` (the retired PMT sleeve), and it
expresses **only two rungs**. **Worse: `runtime.py:1448` calls `breakeven_stop_price()` after a bank,
moving the runner's stop to entry +/-0.15%. Reusing it would import the breakeven-stop family
(7 of 7 negative) and DESTROY the stop-untouched property that makes this construction clean.**
`_banked_realized_pnl` (`:5139`) is the reusable half.
**Also: 5.6% of fills hold 1 contract and cannot ladder at all; 15.6% hold under 4, so a four-rung
25% ladder is inexpressible on them.**

**No phantom control needed, confirmed at source:** the trail is a function of (price, peak) only,
never of size, so a partial moves neither entry, stop, nor peak, and baseline and ladder exit at the
SAME INSTANT at the SAME PRICE on every path. **Corollary: "the replay matched the algebra to the
cent" is a TAUTOLOGY, not a validation.** Bar basis binds in exactly one place — the IOST named walk
— and there it binds hard.

### THE MEMORY TRANSFERS EXACTLY, AND HAS NOW BEEN MEASURED THREE TIMES

The owner's own standing memory — *"early banking measured harmful, floor-not-bank", 2026-08-08* —
**was written about this exact object.** It recorded **-0.115R/trade at t=-2.06**. Independent
measurement on a **disjoint** window five weeks later: **-0.1216R at t=-1.98** and **-0.1028R**.
**Same object, same magnitude to three significant figures, different sample, different engine.**

### THE WIDE TEST WAS NOT RUN, CORRECTLY

The owner gated it on 4 weeks surviving. It did not. Also checked it was even cheap: `wild.jsonl`
(90 rows to 2026-06-15) carries **no `peak_r` and no `r` column** and spans the PEAK_PROFIT_LOCK and
RETAIN 0.30 eras, so it cannot be baselined without re-deriving peaks from bars for 90 symbols.
**The algebra is window-independent; only the staller/runner mix is not. Budget not spent confirming
a null.**

### RULING

**DO NOT SHIP.** The next step is a deletion from the queue, not a config change.
**The durable yield is the crossover test** — a rung at L pays iff L exceeds the eventual floor F,
where F = 0.50 x peak below 3R and 0.75 x peak above. One line, no replay, applies to any future
exit idea. **And the 4R rung is the first exit cell this week that is measurably NOTHING rather than
merely unmeasured. Remember its shape.**

---

## 2026-09-10 — TRIAL 19F: AMENDMENT TO THE STOPPING RULE. Owner-approved. Documentation only.

**AMENDED WITH REDUCED EVIDENTIAL WEIGHT. This is not a costless clarification and must not be
scored as one.** Two fires had already been observed when the amendment was made, and it was those
non-fires-then-fires that prompted the arithmetic below. The defect being fixed was knowable on
2026-09-08 before the flag was set, which is the only reason the amendment is defensible at all.

### THE CHANGE

    WAS:  stop at "30 WILDCARD closes OR 45 days, whichever comes first"
    NOW:  stop at "45 days"   -- the 30-close arm is DROPPED

Nothing else moves. `FUTURES_WILDCARD_EARLY_STOP_R` stays 0.5, `MINUTES` stays 30,
`FUTURES_TREND_EARLY_STOP_R` stays 0.0. **X MUST STILL NEVER BE REFIT. T may still be tuned only
after n >= 30 fires.** No env var changed, no code changed, no deploy.

### WHY — the trial could not reach its own primary criterion

Measured fire rate since arming (2026-09-08 18:18Z): **2 fires in 7 WILDCARD closes = 29%**,
against the 24% assumed at pre-registration. The primary criterion needs **20 fires**.

    20 fires at 29%           ->  ~69 WILDCARD closes needed
    observed close rate       ->  ~4.7 WILDCARD closes/day
    69 closes                 ->  ~15 days  ->  verdict ~2026-09-23
    the 30-CLOSE ARM triggers ->  ~2026-09-15

> **P(reaching 20 fires inside 30 closes) = 0 BY CONSTRUCTION. The trial was scheduled to terminate
> roughly eight days before it could evaluate itself.**

Dropping the 30-close arm leaves 45 days x ~4.7 closes/day x 0.29 fire rate = **~61 expected fires
against 20 needed** — comfortable, where the original 45-day-only estimate at the lower assumed
fill rate was a knife edge at ~21.6.

### THE FALLBACK THAT WAS OMITTED FROM THE ORIGINAL PRE-REGISTRATION — added now

**If fewer than 20 fires have accrued at day 45, report the running delta at whatever n was reached
as DESCRIPTIVE ONLY. A partial-n positive delta MUST NOT be read as a pass.** The original document
had no instruction for the under-powered case, which is how a trial ends up being scored on whatever
n it happened to reach.

### UNCHANGED — restated so the amendment cannot be read as loosening anything

**KILL (either condition, immediately, no discussion):**
1. **Two cut trades whose peak before the cut was >= 1.0R.** `/report` prints this as "cut above 1R".
2. **After 20 fires, a negative running dollar delta against the logged counterfactual.**

**PASS (30 WILDCARD closes... now 45 days):**
1. PRIMARY: running delta positive at n >= 20 fires.
2. Cuts above 1R peak: zero or one across the whole trial.
3. Mean realised risk per trade stays in [1.6%, 2.2%].
4. TREND untouched: zero `CONVEX_EARLY_STOP` exits on a TREND position.

### STATUS AT THE TIME OF AMENDMENT

**2 fires, both clean, neither a kill event:**

| symbol | window | cut at | minutes | peak before cut | counterfactual | delta |
|---|---|---|---|---|---|---|
| MARSCOIN SHORT | 09-09 22:14 -> 22:42 | -0.570R, -$10.29 | 27.9 | **0.2064R** | stop touched 00:07 -> -$19.01 | **+$8.72** |
| MARSCOIN LONG | 09-10 05:59 -> 06:14 | -0.510R, -$4.79 | 15.5 | **0.2291R** | never stopped, now ~-0.42R | **~-$0.78** |

**Running delta +$7.94 at n=2.** Both peaks are far below the 1.0R kill threshold — these were
non-starters, exactly the target population. **n=2 supports no inference; it is recorded, not
interpreted.**

**The counter-case, recorded for the T question that opens at n>=30:** BTR_USDT LONG 09-10 04:41 ->
05:17 went to a full stop at **-1.12R = -$10.79** with a peak of 0.0646R. Its `t_adverse_50` was
**36.35 minutes — the 30-minute window missed it by 6.35 minutes.** At T=45 it would have been cut
near -0.5R, saving roughly **$5.92**.

**WILDCARD `t_adverse_50` distribution so far (7 readings):** 15.45, 27.93, 36.35, 38.13, 41.53,
72.33, 272.03 minutes. **Median 38.13. T=30 catches 2 of 7; T=45 would catch 5 of 7.**

> **THAT IS SUGGESTIVE AND MUST NOT BE ACTED ON. Tuning T from the two observations that fired plus
> one that did not is fitting to n=3. The pre-registration permits T to move only after 30 fires,
> and that constraint is exactly what stops this from becoming the twelfth refuted candidate.**

---

## 2026-09-10 — SCAN-INSTANT ALT BREADTH: reconstructible after all. Gate REFUSED.

**Question:** could the book since 18F (2026-09-04T10:57Z, n=20 fills, net -$92.81) have been improved
by refusing entries when `breadth_24h <= 0.30`, and is that data recoverable retroactively?

**Answer: the data IS recoverable — and the gate is refused anyway.**

### 1. THE MECHANISM — the durable output of this study, and it was not known yesterday

> **MEXC contract `riseFallRate` is NOT a rolling 24h change. It is the return since the UTC+8
> calendar-day open = 16:00Z, and it RESETS DAILY.** The ticker payload carries
> `riseFallRates.zone = "UTC+8"` and `riseFallRate == r`.

Verified live twice at different prices: BTC rfr -0.0026 at last 77017.8 and rfr -0.0015 at last
77100.6 **both imply reference 77218.6 = the open of the 16:00Z Min15 bar.** A fixed daily anchor, not
a rolling window. On 43 live symbols, median |error| vs the true field is **0.0016** day-anchored
against **0.0563** rolling — 35x. `runtime.py:3136-3142` already documents this for the mover ranking;
`_alt_breadth` reads the same field and therefore inherits it.

**COROLLARY, a live hazard: any scan landing in the first minutes of the UTC+8 day reads breadth off
sub-basis-point noise.** SOPH's 0.6271 was taken 13.5 minutes into the day with `alt_med_24h` +0.0009.
That reading is a coin flip, and it is one of the two rows the whole in-sample story rested on.
(A systematic time-of-day effect was tested and KILLED: mean breadth by 3h bucket is flat, 0.49-0.57.)

### 2. THE RECONSTRUCTION VALIDATES — the 2026-09-09 "un-backtestable" claim is overturned

Three independent agents rebuilt breadth from klines. All five live rows reproduce:

| scan instant | symbol | live | recon | err | n live -> recon | alt_med live -> recon |
|---|---|---|---|---|---|---|
| 09-09T16:13:16Z | SOPH | 0.6271 | 0.586 | -0.041 | 59 -> 58 | +0.00090 -> +0.00047 |
| 09-09T19:14:51Z | PONS | 0.5345 | 0.535 | +0.000 | 58 -> 58 | +0.00255 -> +0.00245 |
| 09-09T22:14:31Z | MARSCOIN | 0.1250 | 0.109 | -0.016 | 64 -> 64 | -0.02790 -> -0.02853 |
| 09-10T04:40:51Z | BTR | 0.2063 | 0.191 | -0.016 | 63 -> 63 | -0.02780 -> -0.02849 |
| 09-10T05:59:05Z | MARSCOIN | 0.2031 | 0.177 | -0.026 | 64 -> 62 | -0.02695 -> -0.02671 |

Mean |err| **0.020**, max 0.041, band size within +/-2 on 5/5, **`alt_med` within 7bp on 5/5**,
gate-decision agreement at 0.30 **5/5**. Matching the cross-sectional MEDIAN to four decimals is the
strongest evidence — it means the whole return distribution is right, not just the sign count.

**A SIXTH POINT, OUTSIDE THE DISCOVERY SAMPLE AND 1.5 DAYS BEFORE THE TELEMETRY SHIPPED.** A complete
raw ticker payload saved at 2026-09-08T08:46:24Z: the bot's own `_alt_breadth` on that payload gives
**0.6154, n=65**; the klines-only reconstruction gives **0.6154, n=65** — per-symbol, band membership
identical 65/65, **zero** symbols in one and not the other, **zero** sign disagreements, median
per-symbol rate error 0.00061. Exact, not a coincidental fraction match.

**THREE LIMITS THAT TRAVEL WITH THE INSTRUMENT:**
1. **The bias is SIGNED, not random.** Recon reads low: 4-5 of 5 negative, mean -0.020, sign-test
   p=0.031. **A reconstructed 0.30 is a live ~0.32.** Flips nothing here; every future study inherits it.
2. **Every validation point sits between 09-08T08:46 and 09-10T05:59.** Nothing validates the
   09-04 -> 09-07 era that carries 9 of the 15 out-of-sample fills and the entire high-breadth range.
   **The technique is proven; the LEVELS more than ~24h before 09-09 are indicative, not validated.**
3. **Treat the reach as 2026-09-01, not "history".** The turnover scale factor (~1.32) is the free
   parameter and it is DISPUTED: one measurement p10 1.296 / p90 1.330 over 90 symbols, a verifier
   1.21-1.32 across four symbols. It sets the effective $2M floor, so an 8% error moves band size 1-2
   symbols. **Re-derive it PER SYMBOL before reaching back further, and validate in the new era.**

### 3. THE GATE — REFUSED. Lead with the 6, not the 20.

**The deciding cell is WILDCARD out-of-sample, n=6.** Nine of the 15 reconstructed fills are
TREND-on-ZEC, and **ZEC sits INSIDE the top-24 majors band that breadth excludes by construction** —
gating ZEC on a number built not to see ZEC. Structural; kills those cells before any statistics.

    WILDCARD OOS (n=6): two decisions — block ATOM -$23.68, block IOST +$33.23.
    Base -$73.72 -> -$83.27.  DELTA -$9.55.  2 of 6 deleted.  meanR -0.569 -> -1.039.  p=0.865.

**The honest statement is NOT "the gate loses $9.55".** On n=6 with two decisions it is
**unresolvable** — but it does not point the way the discovery rows did, and its sign turns on one
fill (IOST, b_hat 0.2632, CI [0.253, 0.322] straddling the threshold) the reconstruction cannot resolve.

    all 20:        +$63.92  (7 deleted)   <- CONTAMINATED, never quote this
    OOS 15:        +$17.70 to +$38.05     <- three reconstructions, 3-4 deleted
    discovery 5:   +$25.87  (3 deleted)   <- in-sample by construction

**One fill's classification is not stable across three good-faith reconstructions** (ZEC 09-08T16:38
reconstructs at 0.17 twice and 0.37 once).

**FIVE KILLS, ANY ONE SUFFICIENT:**

1. **The random-delete null.** This window lost $92.81 over 20 fills, so **every fill deleted is worth
   +$4.64 FOR FREE.** Blocking 7 of 20 at random: median +$37.88, p90 +$101.93. Observed +$63.92 is an
   unremarkable draw. The base total (-$92.81) is itself smaller than its SE ($114.63) — **the six-day
   P&L is not distinguishable from zero BEFORE any gate.**
2. **The placebo destroys the mechanism.** Breadth read **2h AFTER** entry — causally impossible —
   scores **better** than the real reading (+$75.9 vs +$43.6), and still better after null-adjusting
   for deletion count. Observed ranks 3rd-4th of 11 in its own placebo set. Autocorrelation explains
   it: rho +0.925 at 15min, +0.686 at 6h. **Instantaneity, the entire reason the telemetry shipped,
   is worth nothing.**
3. **It is a DATE RULE IN COSTUME.** Pearson(breadth, entry time) = **-0.797**. 75.6% of breadth
   variance is between-day. Era split: deletes NOTHING before 09-08T16:38 and everything after.
   **One regime transition, not twenty observations.**
4. **No interior optimum.** The surface rises with sawteeth to 0.70, where it keeps 2 of 20 fills.
   Walk-forward converges to "block 16 of 16" — **the fitted optimum is "stop trading"**, guaranteed to
   score well on a losing window. **Dead at walk-forward: the TWELFTH consecutive candidate.**
5. **It destroys the right tail.** Top-3 = 108% of net R. It keeps ZEC +$75.37 (breadth 0.74-0.81) by
   luck and **deletes IOST +$33.23, the book's #2 fill.**

**Continuous test, no threshold:** Pearson(breadth, $P&L) on the 11 WILDCARD fills is **-0.10 to -0.16
— the WRONG SIGN.** Positive on all 20 only because TREND/ZEC carries it.

**SLOT RE-ALLOCATION: 0 fills created, and the prior 2.5x delete-only overstatement genuinely does not
transfer — for a reason worth recording.** `runtime.py:6572` (`if opened: return`) promotes a runner-up
when a SYMBOL-SPECIFIC veto fires. **A market-wide veto takes one value per scan and blocks every
candidate simultaneously, so there is no runner-up by construction.** Confirmed: zero WILDCARD
`slot_occupied` and zero `rank_dropped` rows in the shadow ledger since 09-04, on an instrument
carrying 31 `slot_occupied` rows lifetime. **Which makes this pure volume destruction — rule 3's
recurring killer: 27-45% of fills deleted to move meanR by 0.008R.**

### 4. MDE AND THE SELECTION FLOOR — no answer was ever obtainable from this window

| cell | n | deleted | MDE/month | observed |
|---|---|---|---|---|
| all 20, both sleeves | 20 | 7 | ~$830-1,740 | +$63.92 |
| OOS 15, both sleeves | 15 | 3-4 | ~$805-1,920 | +$17.70..+$38.05 |
| WILDCARD 11 | 11 | 5 | ~$470-1,600 | +$16.33 |
| **WILDCARD OOS 6** | **6** | **2** | **~$550-1,600** | **-$9.55** |
| discovery 5 | 5 | 3 | ~$2,660 | +$25.87 |

**Every observed effect is 5x to 50x below its own MDE; against the $10/month bar the window is
50-170x too small.** 1R across the 20 fills ranges $9.39-$28.33, median **$19.49** — the single 1R
used for any R-to-dollar reasoning here. Signs unchanged in R (both-sleeves all20 +3.68R; WC OOS -0.68R).

**SELECTION FLOORS, stated before any p-value.** WILDCARD OOS with 6 fills and 1 winner:
**1/C(6,1) = 0.167. No variable, however perfect, can score better on that window. The observed p is
0.865 — five times worse than the best the window can produce.** And because breadth is market-wide
and 76% between-day, the BINDING floor is the day-block one: **1/C(6,2) = 0.0667** for choosing which
2 of 6 days to sit out. Nothing in the study beats even that. Family 52-62 cells, Bonferroni
alpha ~0.001; the best p anywhere (0.10, in-sample) adjusts to 1.000.

**POWER: $10/month at ~$26/fill sd needs ~18,000-25,000 WILDCARD fills = 45-62 years.** The same wall
the 2026-09-09 regime study hit at ~75,800 fills. **A breadth gate is neither better nor worse than the
thirty rules before it. It is the same wall.**

### 5. FIDELITY VS THE ALREADY-REFUTED PRIOR-MIDNIGHT VARIABLE: **UNRESOLVED — and moot**

Three good-faith reconstructions gave **-0.20 / +0.32 / +0.81** correlation with the prior-midnight
daily-close series, spanning the entire range; their prev-midnight gate deltas diverge just as badly
($0.00 / +$15.58 / +$63.45). **I do not know whether it collapses into the refuted object.** Two
reasons the disagreement was predictable: the prev-midnight series takes ~6 DISTINCT VALUES over a
6-day window (a Pearson quoted "on 649 grid points" borrows precision it does not have); and
mechanically, now the 16:00Z anchor is known, **scan-instant breadth is not a cross-section at all —
it is the same cumulative day statistic read part-way through the day.** A within-day running total.

**It is moot: the gate fails its own out-of-sample test on the sleeve that computes the statistic.**

### 6. DECISION — DO NOTHING. Keep recording, gate nothing.

| # | action | all20 | OOS | del | verdict |
|---|---|---|---|---|---|
| **1** | **DO NOTHING** | **$0** | **$0** | **0** | **ADOPTED** |
| 2 | WILDCARD-only veto <= 0.30 | +$16.33 | **-$9.55** | 5 | fails its own OOS cell; one fill (drop IOST -> +$23.68) |
| 3 | Both-sleeves veto <= 0.30 | +$63.92 | +$17.70..38.05 | 7 | structurally void (ZEC) |
| 4 | TREND-only veto on ALT breadth | +$47.59 | +$47.59 | 2 | structurally void; upper bound; 2 fills |
| 5 | `alt_med_24h <= 0` veto | +$67.99 | +$42.12 | 9 | collinear with breadth>0.40 — same family, not an independent test |
| 6 | Breadth-conditional SIDE selection | — | — | **0** | **data points the WRONG WAY** |

**#6 deserves its own line because it deletes NO fills — the one structural advantage available — and
the data still says no.** Of the 11 WILDCARD fills, the 3 that COMPLY with "long when breadth>0.30,
short when <=0.30" sum to **-$62.49**; the 8 that VIOLATE it sum to **-$14.36**. The rule selects the
losing subset. Its own recommended action (breadth>0.30 LONG) is the single worst cell: n=2, -$52.21,
zero wins. The cell it forbids contains IOST +$33.23. **And the premise that the low-breadth fills
"were or should have been shorts" is FALSE: four of the five were LONGS.**

**Cost of #1 if wrong:** forgoing an effect whose own point estimate is ~$49/month against a
$470-$1,600/month MDE. The telemetry already ships, costs no API call, has no behavioural effect.

**ONE THING TO WATCH, NOT TO ACT ON:** the direction on WILDCARD-only fills is **NEGATIVE** — high
breadth associated with worse outcomes. That matches the reversal already on file (lifetime R earned
in low-BTC-efficiency tape, +0.404R in chop vs -0.004R out of it). **If anything ever ships here it is
likelier to be the OPPOSITE of the rule proposed. Do not chase it; n=11.**

**NOT WORTH MORE TIME ON THIS WINDOW:** further threshold search, sleeve slicing, side-conditioning,
or any additional cell. The grid has no interior optimum and every new cell widens a multiplicity
family that has already sunk the result.

### 7. REJECTED LIST ENTRY — quote the OOS number, NEVER the all-20 number

> **Scan-instant alt breadth gate, threshold 0.30 — WILDCARD out-of-sample -$9.55, 2 of 6 fills
> deleted, p=0.865 against a window floor of 0.167, dies at walk-forward (12th consecutive), one
> blocked fill is the book's #2 by P&L, breadth-vs-time confound -0.797. Fidelity vs the previously
> refuted prior-midnight series UNRESOLVED (three reconstructions: -0.20 / +0.32 / +0.81).**
> **Quoting +$63.92 anywhere repeats the exact contamination this exercise existed to catch.**

### 8. PRE-REGISTERED FALSIFICATION — review 2026-12-10, and the statistic is NOT dollars

Dollars cannot resolve this ($10/month needs ~18,000+ fills). **The only statistic this book can move
on a human horizon is SIGN AND RANK.** Registered now, before the rows exist:

- **Statistic:** Spearman(scan-instant breadth, realised **$** P&L), **WILDCARD fills only**,
  **live-recorded breadth only**, against a **deletion-matched** null.
- **Review date: 2026-12-10** (~100 live WILDCARD breadth rows at the current fill rate).
- **KILL (permanent, goes to the rejected list and is never revisited):** rho <= 0 at n >= 100, OR
  sign unstable across the two halves, OR the delta fails to beat a deletion-matched random null at
  the same k.
- **PASS (advances to PRICING, not to shipping):** rho >= +0.30 with p < 0.01, AND stable in sign
  across both halves, AND delta exceeds the deletion-matched null, AND survives walk-forward on >= 30
  chronological decisions, AND the reconstruction reproduces the live rows in that NEW era.
  **Even a full pass buys a pricing exercise. The MDE arithmetic does not go away.**

**THE BINDING CONSTRAINT HAS MOVED — this is the operational consequence of section 2.** It is no
longer market data; it is **the trade corpus.** Waiting for telemetry at ~5 rows/day is now the WRONG
move, because the reconstruction can price every fill the book already has. **Next: reconcile full
exchange fill history against the 200-row `trade_history` ring buffer (FULL) and the 32-day
loss-censoring window. Until that is done every backtest inherits both defects. Snapshot /data first.**

### 9. PROCESS NOTE — a control was double-counted, and I nearly shipped it

"LOSO drop-ZEC takes the delta to -$9.55" and "WILDCARD out-of-sample n=6 delta -$9.55" are **the same
arithmetic**: the OOS 15 minus the 9 ZEC fills IS the 6 WILDCARD OOS fills. They were presented as two
independent controls. **One observation, counted twice.** Caught in verification. Also caught: a
placebo grid that silently disabled the Min1 price series and did not reproduce 6 of 11 cells (the
conclusion held; the specific numbers were wrong). **Both are the same failure mode — a control that
agrees with the desired conclusion gets less scrutiny than one that does not.**
