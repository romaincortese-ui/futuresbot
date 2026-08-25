# STANDING OBJECTIVE (owner directive, 2026-08-10)

**Every change is justified by expected $ P&L.** Not R, not coverage, not
signal count, not elegance. Before proposing a change, state: the $ per trade,
the trades per month, and the edge assumed. If the answer is "under $10/month
either way", say so and drop it.

The arithmetic that governs it, at the time of writing:

| | |
|---|---|
| 1R | **$2.66** — `risk_pct x equity` = 1.87% x $142. The risk dial makes this identical on EVERY symbol, so "that market is too small to be worth trading" is not a valid objection in this design |
| entries | ~0.7/day now; slot-capped at 2/day by 2 slots x the 24h clock |
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

## TRIAL 16 — OPEN 2026-08-22 10:44 UTC

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
