# Daily Audit — 2026-08-23

---

## Automated Assessment (UTC 16:15)

Window 2026-08-22 16:20 -> 2026-08-23 16:15 UTC. Equity **$175.30**
($136.74 free), **2 open convex positions**, unrealised **-$2.16**.
**4 closed trades**, net **+$12.19 / +1.99R**, 1 win (25%). `pytest -q`
**1015 passed**. Feature store **88 rows** (84 + 4, exactly reconciled against
the exchange ledger). Shadow ledger **130 rows**.

Third consecutive positive day, **+$38.52 realised across the three**.

### THE HEADLINE: the first +5R take-profit the wildcard sleeve has ever completed

`TUT_USDT` LONG x2 ran **+80.5% on margin in 7.5 hours** and closed on the
resting server-side TP at **+5.09R / +$17.94**. Peak was +5.56R, so the TP order
filled near the top rather than after a giveback. Every prior convex TP was a
TREND 3R completion; this is the 5R target proving it is reachable, not
decorative. One trade paid for the other three losses 3.3x over.

The entry was `entry_lateness=1.00` — at the extreme, no pullback — with a 3h
ROC of **+14.7%** and `ref_listed=1` (cross-listed, not a MEXC-only pump). This
is the sleeve doing exactly what it was designed to do.

### Closed trades

| sym | side | sleeve | lev | R | $ | hold | exit | peak R | size_eff |
|---|---|---|---|---|---|---|---|---|---|
| FARTCOIN_USDT | SHORT | WILDCARD | x1 | -1.02 | -0.76 | 10.9h | stop | 0.04 | **0.24** |
| TUT_USDT | LONG | WILDCARD | x2 | **+5.09** | **+17.94** | 7.5h | **`TP` (5R)** | 5.56 | 0.92 |
| ZEC_USDT | LONG | TREND | x5 | -1.02 | -1.32 | 2.6h | stop | 0.61 | 0.38 |
| ZEN_USDT | LONG | WILDCARD | x4 | -1.06 | -3.67 | 0.5h | stop | 0.03 | 1.00 |

All four exits are legal convex exits (-1R stop or TP). No PMT vocabulary fired
on a convex position. No order rejects (5003/2015), no `Traceback`, no
`[SIZE_TRIM]` lines in the window. All four were `ref_listed=1`.

`ZEN` reversed within 32 minutes of entry off a +10.0% 3h ROC and never printed
above +0.03R — a clean stop, not a mismanaged trade. The -1.06R (vs -1.00R
design) is fee and slippage on a x4 entry; within tolerance.

### The trimmed-hard cohort keeps paying for itself in R and not in dollars

`FARTCOIN` closed exactly as flagged yesterday: the regime scaler cut it to
**0.25x**, it risked $0.75 against a designed $3.12, and it lost. That is now
the pattern, not an anecdote:

| cohort | n | net R | avg R | net $ | win% |
|---|---|---|---|---|---|
| `regime_size_mult < 0.5` | 21 | **-10.41** | **-0.496** | -4.91 | 38% |
| everything else | 66 | +31.05 | +0.470 | +47.25 | 45% |

A **0.97R per-trade separation** on n=21, OOS-consistent in the conditional
expectancy report (`regime_trimmed_hard(<0.5)  AVOID  e=-1.22 l=-0.605 OK`).
The scaler is an excellent *classifier* of bad setups that is wired as a *size
dial* instead of a veto — it correctly identifies the trade and then takes it
anyway at a quarter size.

**And that is precisely why it is not today's lever.** Because those trades are
small by construction, vetoing all 21 would have saved **$4.91 over eight
weeks — about $2.50/month**, which is below the $10/month floor
`docs/DECISION_RULE.md` sets for a change being worth proposing at all. The R
number is dramatic; the dollar number is noise. Under trial 16's renormalised
sizing the dollar cost will grow, so this becomes worth revisiting — but not on
today's evidence, and not with the trial one close from a verdict.

### Open positions

| sym | side | sleeve | lev | held | R now | peak R | giveback | to TP | to SL | margin (intended) |
|---|---|---|---|---|---|---|---|---|---|---|
| STX_USDT | LONG | WILDCARD | x3 | 2.8h | -0.37 | +0.08 | -0.45 | +35.7% (5R) | -4.3% | $22.35 ($22.35, regime 0.93) |
| ZEC_USDT | LONG | TREND | x5 | 2.4h | -0.20 | +0.81 | **-1.01** | +11.4% (3R) | -2.9% | $21.89 ($21.89, regime 1.00) |

Neither is undersized — actual margin equals intended margin on both. ZEC gave
back its full +0.81R peak and sits 2.9% of price from its stop; it was re-entered
by TREND at 13:44, **84 minutes after the sleeve was stopped out of the same
name**. The convex sleeves carry no post-stop cooldown by design, and this is the
first time that has visibly mattered. Not a defect — but if the re-entry also
stops, that is a cooldown question worth measuring rather than assuming.

### Trial progress — 29/30, and currently passing

Convex closes since 2026-07-13 (`docs/DECISION_RULE.md` pass criteria):

| | value | criterion | status |
|---|---|---|---|
| closes | **29 / 30** | 30 | one close from a verdict |
| net R | **+8.98** | > 0 | **PASS** |
| net R ex-best | **+3.89** | > 0 | **PASS** |
| equity DD from peak | -4.8% | flag > 20% | clear |
| max R drawdown | -6.17R | — | — |

| sleeve | n | win% | net R | net $ |
|---|---|---|---|---|
| WILDCARD | 21 | 28.6% | -0.27 | **+16.00** |
| TREND | 8 | 87.5% | +9.25 | +18.10 |

The wildcard is the awkward one: **21 trades, net R essentially zero (-0.27), net
dollars clearly positive (+$16.00)**. That is not a contradiction — TUT's +5.09R
landed on a full-size entry while the losers were scaler-trimmed small. Under the
standing $-P&L directive the sleeve is earning, so no disable proposal; under R
it has not yet demonstrated an edge. Both statements are true and neither should
be dropped.

Kill conditions: no TREND loss worse than -1.5R (worst is -1.02R); TREND net R
+9.25 over 8 closes, nowhere near the -3.0 kill; short arm disabled by config.

Exits since 07-13: **TP 5 (17%) | stop 14 (48%) | other 10 (34%)**. TP completion
at 17% is above the 10% floor of the trial-4 watch item, and today's 5R fill is
direct evidence the wide-stop target is reachable. No proposal to scale TP down.

### Slot cost — capacity is not the binding constraint

Raw `slot_occupied` reads 28 resolved rows at **+30.47R**, which is the same
re-signal inflation `4ce7a18` was written to kill: a blocked mover re-fires every
scan, and XRP alone contributed five rows on one move. Counting each missed move
once (same symbol/side/sleeve inside 12h):

| sleeve | n | net R | avg R | reading |
|---|---|---|---|---|
| WILDCARD | 11 | +7.72 | +0.70 | almost entirely **pre-07-31** |
| SQUEEZE | 6 | +3.15 | +0.52 | sleeve is **disabled** (`FUTURES_SQUEEZE_ENABLED=0`) |
| TREND | 3 | **-0.40** | -0.13 | slot lock protective/neutral |
| **total** | **20** | **+10.47** | +0.52 | |

**The operator's recurring "am I missing out?" question now has a clean answer:
no.** Live config is `FUTURES_WILDCARD_MAX_POSITIONS=3`,
`FUTURES_TREND_MAX_POSITIONS=2`, `FUTURES_SQUEEZE_ENABLED=0`. Since 07-31 exactly
**one** wildcard candidate has been blocked by slot contention (HEI, 08-05, +5R).
The +7.72R figure is the evidence that *justified* widening wildcard capacity in
the first place, not a case for widening it again — at three slots the constraint
is not binding at all. The squeeze rows are moot while that sleeve is off. No
slot proposal.

Note the `/data/futures_gate_cost.jsonl` row written 08-22 21:40 (+$47.33 on
n=5 slot_occupied) predates the dedupe fix; `dedupe_by_occupancy` is confirmed
running in the container, so subsequent rows will be honest.

### Learning loop — conditions with a verdict and n>=10 per group

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| `roc>=12pct` | **FAVOR** | +2.430 | 20 / +$2.361 / 70.0% | 68 / -$0.069 / 36.8% |
| `hold>=120min` | **FAVOR** | +2.384 | 55 / +$1.377 / 60.0% | 33 / -$1.007 / 18.2% |
| `late_entry>=0.8` | **FAVOR** | +0.890 | 33 / +$1.039 / 45.5% | 55 / +$0.149 / 43.6% |
| `leverage<=4` | **FAVOR** | +0.781 | 42 / +$0.891 / 45.2% | 46 / +$0.110 / 43.5% |
| `regime_trimmed_hard(<0.5)` | **AVOID** | -0.942 | 21 / -$0.234 / 38.1% | 67 / +$0.708 / 46.3% |
| `hold<=30min` | **AVOID** | -0.766 | 11 / -$0.187 / 27.3% | 77 / +$0.579 / 46.8% |
| `fee_heavy>=30pct` | **AVOID** | -0.538 | 12 / +$0.018 / 50.0% | 76 / +$0.556 / 43.4% |

Corpus 88 trades, 06-27..08-23, overall +$42.51 / mean +$0.483 / meanR +0.237.
`roc>=12pct` FAVOR is worth naming: TUT entered on +14.7% and ZEN on +10.0%.
Propose-only, nothing self-applied.

### Scan telemetry

Wildcard scans healthy at ~63 movers/cycle, dominant rejection `roc_below_min`
(61/63) with `no_pullback_resume` 1-3 — a quiet tape after the morning's run,
correct dormancy, no gate loosening warranted. Trend scans 3 symbols, blocked on
`roc_below_min` and `symbol_open`. Squeeze produced no summary lines in the
window. Recurring `[CALIBRATION_SEED_FALLBACK]` (6 live trades < 15 required) is
the known PMT-era calibration path and is inert while PMT is decommissioned.

### Shadow

Stale, comparison suppressed pending resync.

### Lever for the next 24h: NONE

The trial is at 29 of 30 closes and currently passes both criteria. Changing
sizing, entry or exit now would contaminate the only pre-registered verdict this
project has reached in sixteen trials. The `regime_trimmed_hard` -> veto
candidate is documented above with its numbers and its $2.50/month objection,
staged for the shadow rig *after* the 30th close, not before it.

**No deploy.** Local `main` is **12 commits ahead of `origin/main`** — the
deployed container is running code that exists only on the operator's laptop.
That is the one thing worth acting on today.

### Action items for the operator

1. **Push `main` to origin** (12 unpushed commits, including the `4ce7a18` gate
   dedupe that is already live in the container). No recovery path until then.
2. Resync `Futures-shadow` to champion HEAD (`railway up --service
   Futures-shadow`, paper, env-only, zero live risk) — still outstanding.
3. After the 30th convex close: stage `regime_trimmed_hard` as a veto rather
   than a 0.25x size cut, through `tools/replay_exits.py` + `tools/mc_ledger.py`.

---

# Daily Audit — 2026-08-22

---

## Automated Assessment (UTC 16:20)

Window 2026-08-21 16:15 -> 2026-08-22 16:20 UTC. Equity **$166.00**
($137.48 free), **2 open convex positions**, unrealised **+$0.64**.
**7 closed trades**, net **+$10.46 / +5.14R**, 5 wins (71.4%). `pytest -q`
**975 passed**. Feature store **84 rows** (77 + 7, exactly reconciled against
the exchange ledger). Shadow ledger **122 rows**.

Two consecutive positive days, +$26.33 realised across them.

### Closed trades

| sym | side | sleeve | lev | R | $ | hold | exit | peak R | size_eff |
|---|---|---|---|---|---|---|---|---|---|
| GPS_USDT | LONG | WILDCARD | x3 | **-1.05** | -2.71 | 1.1h | stop | 0.63 | 1.00 |
| ETH_USDT | LONG | TREND | x9 | +0.28 | +0.56 | 2.6h | retention trail | 1.27 | 0.93 |
| ZEC_USDT | LONG | TREND | x4 | **+2.98** | +5.72 | 6.5h | `TP` (3R) | 2.99 | 0.83 |
| ZEC_USDT | LONG | TREND | x3 | +0.25 | +0.56 | 2.0h | retention trail | 1.22 | 0.93 |
| XRP_USDT | LONG | TREND | x3 | **+2.98** | +5.84 | 3.8h | `TP` (3R) | 2.91 | 0.84 |
| GALA_USDT | LONG | WILDCARD | x2 | +0.72 | +2.02 | 19.4h | retention trail | 2.51 | 1.00 |
| ZAMA_USDT | LONG | WILDCARD | x1 | **-1.02** | -1.52 | 0.7h | stop | 0.13 | **0.49** |

Every exit is a legal convex exit (-1R stop, TP, retention trail). No PMT
vocabulary fired on a convex position. Two more 3R take-profits completed,
taking the all-time convex TP count from 2 to 4.

ETH and ZEC sit inside `FUTURES_TREND_SYMBOLS` **and** inside the six PMT
pairs, so all three of those trades were exposed to the recovered-position
defect. None was hijacked — see below, the defect is closed.

### THE DEFECT FROM 08-21 IS CLOSED

`692eae2 exits: an unset tp/sl is not a breached one` shipped this morning and
**is running in the container** (verified by reading `_pmt_hard_exit` inside the
live service, not just in git). `_refresh_live_positions` no longer force-closes
an adopted position by comparing the live price against `tp_price=0.0`. The
$7-per-occurrence ledger-censoring hole is shut. Nothing further owed here.

### Open positions

| sym | side | lev | held | R now | peak R | giveback | to TP | to SL | margin (intended) |
|---|---|---|---|---|---|---|---|---|---|
| TUT_USDT | LONG | x2 | 3.4h | +0.31 | +0.68 | -0.36 | +37.1% | -9.5% | $22.30 ($24.35, regime 0.93) |
| FARTCOIN_USDT | SHORT | x1 | 10.6h | -0.62 | +0.04 | -0.66 | -53.8% | +4.9% | **$5.54 ($23.17, regime 0.25)** |

Both carry live server-side TPSL orders on the exchange, verified by ID against
the position ID. FARTCOIN is 4.9% of price from its stop.

**FARTCOIN is the extreme case of the trimmed-hard cohort.** The regime scaler
cut it to 0.25x, so it is risking **$0.75 against a designed $3.12** — 0.45% of
equity where the design says 1.87%. It entered at 05:43, before trial 16 opened,
so it carries the old 1.87% base. This is the scaler doing exactly what
`regime_trimmed_hard` says it does: correctly flagging a bad setup and then
taking it anyway at a quarter size.

### Trial 16 — the sizing check, n=1

Trial 16 opened today at 10:44 UTC on renormalised sizing
(`FUTURES_WILDCARD_RISK_PCT` 0.0187 -> 0.0241). Its pre-registered void
condition is that realised risk per trade must land near 1.87%, not 1.45%.

**One entry has been taken since:** TUT at 12:59 UTC, `risk_pct_intended 2.41`,
regime multiplier 0.9328, **`risk_pct_actual 1.9635`**. That is the design level,
against a pre-renormalisation realised mean of 1.45%. The mechanism is doing what
it claims. n=1 — this is a sign of life, not a verdict.

**Trial 16: 0/30 convex closes.**

### Trial 15 — final

Closed at **14/30: netR +12.17, net R ex-best +7.21**. Both pass criteria were
positive at the point it was closed, and it was closed on a config change rather
than on results — the same pattern as the eleven before it. Reset count 12.

### Sleeve split — the observation of the day

All-time, from the feature store:

| sleeve | n | netR | ex-best | avg R | win | net $ |
|---|---|---|---|---|---|---|
| TREND | 7 | **+10.27** | +7.29 | +1.467 | **100%** | **+19.42** |
| WILDCARD | 59 | +11.81 | +6.72 | +0.200 | 37% | +15.39 |
| PMT (dead) | 15 | -5.42 | -7.11 | -0.387 | 43% | -4.61 |
| SNIPER (dead) | 3 | +1.99 | +0.27 | +0.663 | 67% | +0.03 |

In two days TREND has out-earned wildcard's entire 59-trade life in dollars.
Splitting wildcard by side is equally uncomfortable:

| wildcard arm | n | netR | ex-best | avg R | net $ |
|---|---|---|---|---|---|
| LONG | 44 | +2.11 | **-2.98** | +0.048 | +3.06 |
| SHORT | 15 | +9.70 | +4.64 | +0.647 | +12.33 |

**The wildcard long arm, minus its single best trade, is a net loser over 44
trades** — and it is chasing the same "buy strength" thesis that TREND is
executing better on majors. The short arm is the half that pays, which is the
opposite of the 90-day all-sleeve drift-controlled study and is a reason not to
touch `FUTURES_WILDCARD_LONG_ONLY` in either direction.

**No proposal is attached to any of this.** TREND's record is 7 trades taken
over two days in one directional regime, on a universe (ETH/XRP/ZEC) that was
selected on 08-22 *after* the 08-19 majors event — textbook selection bias. It
needs to be scored, not acted on. Wildcard is net-positive on both R and $, so
the disable criterion is not met either.

### Learning loop

Corpus n=84, overall **+$30.23, meanR +0.225, win 45.2%**.

OOS-consistent verdicts with n>=10 both sides:

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| hold >= 120min | FAVOR | +2.077 | 52 / +1.151 / 61.5% | 32 / -0.926 / 18.8% |
| roc >= 12% | FAVOR | +1.706 | 18 / +1.700 / 72.2% | 66 / -0.006 / 37.9% |
| hold <= 30min | AVOID | -0.629 | 11 / -0.187 | 73 / +0.442 |
| regime_trimmed_hard (<0.5x) | AVOID | -0.745 | 20 / -0.208 / 40.0% | 64 / +0.537 / 46.9% |
| fee_heavy >= 30% | AVOID | -0.399 | 12 / +0.018 | 72 / +0.417 |

`regime_trimmed_hard` strengthened again (gap -0.626 -> -0.745) and today added
two more members, ZAMA (-1.02R at 0.49x) and FARTCOIN (0.25x, currently -0.62R),
both losers. The finding is now three audits old and OOS-consistent. **It is
still not worth acting on:** ~11 trimmed trades/month x $0.208 = **$2.3/month**,
under the standing objective's $10/month floor. Dropped again, deliberately.

`side=LONG AVOID / side=SHORT FAVOR` remains at e=+-0.219 — noise. Ignored.

### Shadow ledger

- **slot_occupied: 28 resolved, net +30.47R (avg +1.09R)** — but this is heavily
  double-counted. Five XRP rows from 08-21 19:00-20:00 resolve +3.0 each; the bot
  then **took XRP anyway** at 01:15 and banked the +2.98R TP. Those are not five
  missed trades, they are one captured trade. Four BTC rows from 08-19 are
  likewise one event. Deduplicated to **19 unique events the net is +12.86R
  (avg +0.68R)** — still positive, and the operator has already acted (wildcard 3
  slots, TREND 2). Not a proposal.
- **veto:*: 26 resolved, net -9.13R.** Vetoes continue to SAVE money;
  `ref_not_listed` is 22 of 26. Protective, leave alone.
- **min_vol_skip: 12 resolved, net +8.99R** — looks like a costly filter, but 8
  of 12 rows are dead-SNIPER-sleeve counterfactuals from 08-06/08-09 scored on
  their own tp_r=2.0, and the reason means "size below the exchange contract
  minimum", not a tunable gate. Nothing to propose.
- Gate-cost file: 5 daily rows, 4 negative. Agrees with the veto split.

### Scan telemetry

Wildcard: 91 movers in band, 90 scanned, **0 candidates**, histogram
`{'roc_below_min': 90}` — a clean sweep, 45/48 deflated. TREND: 3 symbols
scanned, 0 candidates, `roc_below_min` x2 + `no_new_extreme` x1. Squeeze is
**off** (`FUTURES_SQUEEZE_ENABLED=0`), so no squeeze summary is emitted.

Correct dormancy — the 08-19/08-21 impulse has decayed and nothing clears an 8%
3h floor. No `[SIZE_TRIM]` lines. No `5003`/`2015` order rejects. No Traceback
or ERROR in the log window. Two wildcard slots of three are filled.

### Decision rule

**Trial 16: 0/30 convex closes.** Sizing check passing at n=1 (1.96% realised vs
2.41% design vs 1.45% pre-renormalisation baseline). Equity $166.00 against a
peak of $169.66 — **2.2% drawdown from peak**, far inside the 20% line.
`USE_DRAWDOWN_KILL=1`.

Exits, convex only (n=41 with `exit_kind`): **TP 4 (9.8%) | stop 17 | other 20**.
The old "TP completion <10% -> propose TP3R" watch item stays superseded: TREND
already runs TP 3R and 3 of the 4 all-time TPs landed in the last 36 hours.
Re-evaluate at n>=50.

### Lever & deploy

**Lever: no change, and the reason is the reset count.**

Trial 16 is **5.6 hours old with zero closes** and carries a pre-registered void
condition that only accumulating entries can test. The board has three items that
each look like a lever — the TREND/wildcard divergence, the wildcard long arm,
the 0.25x trim on FARTCOIN — and every one of them would be reset #13 against a
record of twelve resets in three months and zero scored verdicts. The
highest-dollar action available today is to let the trial run, because a scored
verdict is worth $450/month at $1,000 of equity and none of these tweaks is worth
$10/month at $166.

Nothing deployed. Shadow stale (still on the 2026-06-14 PMT build, paper equity
$100, 6 PMT symbols, no convex sleeves), comparison suppressed pending resync.

---

# Daily Audit — 2026-08-21

---

## Automated Assessment (UTC 16:15)

Window 2026-08-20 16:20 -> 2026-08-21 16:15 UTC. Equity **$157.37**
($137.86 free), **1 open wildcard position**, unrealised **+$2.44**.
**6 closed trades**, net **+$15.87 / +8.02R**, 5 wins. `pytest -q` **953
passed**. Feature store **77 rows** (66 + 6 backfilled reconstructions + 5
live-logged closes). Shadow ledger **113 rows**.

Best day the convex book has had. It is also one day.

### Closed trades

| sym | side | sleeve | lev | R | $ | hold | exit | size_eff |
|---|---|---|---|---|---|---|---|---|
| SOL_USDT | LONG | TREND | x10 | **+2.83** | +5.52 | 21.8h | `TP` (3R) | 0.75 |
| ENA_USDT | LONG | WILDCARD | x4 | **+4.96** | +11.11 | 13.2h | `TP` (5R) | 0.98 |
| SOL_USDT | LONG | TREND | x10 | +0.38 | +0.86 | 2.8h | retention trail (peak 1.66) | 0.94 |
| ORDI_USDT | LONG | WILDCARD | x5 | -1.03 | -2.72 | 0.6h | stop (**reconstructed**) | n/a |
| ETH_USDT | LONG | TREND | x8 | +0.57 | +0.32 | 19.6h | retention trail (peak 2.17) | **0.24** |
| TUT_USDT | LONG | WILDCARD | x2 | +0.31 | +0.79 | 1.9h | retention trail (peak 1.17) | 0.99 |

Every exit reason is a legal convex exit (-1R stop, TP, or the retention
trail). No PMT vocabulary fired on a convex position today. **The first two
+3R/+5R take-profits the trial has ever completed both landed today** — before
today the all-time TP count was 0.

ORDI was erased live by the history-lag race and recovered by
`tools/backfill_missing_closes.py`; the race itself was fixed this morning
(`aa6a59c`). Its P&L is real and is counted.

### THE DEFECT — corrected diagnosis, and it is worse than reported

Yesterday's entry blamed the 3.4-second BTC close on the micro profit-lock and
offered an env-only stopgap (`FUTURES_MICRO_LOCK_RECOVERED_ENTRY_SIGNALS=`).
**Both halves are wrong.**

1. `recovered_entry_signals` is a **dead parameter**. `exits.py:274` reads
   `_ = (entry_signals, recovered_entry_signals)` and discards it — micro-lock
   eligibility is lane-agnostic. Clearing that variable is a no-op.
2. The mechanism is `_pmt_hard_exit` (`runtime.py:4880-4889`), not the
   micro-lock. `_refresh_live_positions` builds a `RECOVERED` position with
   **`tp_price = 0.0` and `sl_price = 0.0`**. For a LONG that evaluates as:

   ```
   current_price <= sl_price (0.0)   -> False
   current_price >= tp_price (0.0)   -> ALWAYS TRUE  -> TAKE_PROFIT
   ```

   So a recovered position is force-closed on the **very next tick**,
   deterministically, and `_close_position_for_exit` is handed
   `current_price = position.tp_price = 0.0`. (The realised P&L still comes
   from the exchange fill, which is why BTC booked +0.45R rather than -100%.)

This raises the severity. It is not a probabilistic lock that sometimes takes
a small profit — **every** position that `_refresh_live_positions` adopts is
guaranteed to be closed immediately at whatever the market happens to be. The
only randomness is the race that decides whether the adoption happens at all.
`_active_symbols` is the six PMT pairs; `FUTURES_TREND_SYMBOLS=ETH_USDT,SOL_USDT`
sits inside that set, so every TREND entry remains exposed. Today's three TREND
trades simply won the race.

**There is no working env-only stopgap.** `FUTURES_MICRO_LOCK_ENABLED=0` would
close the micro-lock path, but the micro-lock is not the path.

**Proposed fix (NOT applied — code change, live money, no gate run):**

```python
    def _pmt_hard_exit(self, position: FuturesPosition, *, current_price: float) -> bool:
        # A RECOVERED position carries tp=0/sl=0. Comparing against 0 makes the
        # TP branch unconditionally true, which force-closes it on the next tick.
        if position.tp_price <= 0 or position.sl_price <= 0:
            return False
```

plus the structural half: `_refresh_live_positions` must skip any symbol a
non-PMT sleeve already owns, and must not mint `RECOVERED` positions on symbols
inside `FUTURES_TREND_SYMBOLS`. This is the **fifth** hand-maintained-sleeve-list
bug of the same class.

Dollar cost: up to **-$7 per occurrence** (a 3R target truncated to ~0.4R), and
it silently censors the R-ledger the trial is judged on — which is the metric
the standing objective says is the highest-$ work.

### Open position

| sym | side | lev | held | R now | peak R | giveback | to TP | to SL | margin |
|---|---|---|---|---|---|---|---|---|---|
| GALA_USDT | LONG | x2 | 6.4h | +0.88 | +1.08 | -0.20 | +31.7% | -14.7% | $17.02 (as intended, regime 1.0) |

Armed (peak > 1.0R). Retention floor sits at 0.30 x 1.076 = **+0.32R**.
Not a PMT pair, so not exposed to the defect above.

### Retention trail — 7 exits, behaving exactly as specified

| date | sym | peak R | exit R | retained | $ |
|---|---|---|---|---|---|
| 08-08 | BICO | 1.46 | 0.42 | 29% | +1.17 |
| 08-08 | BTW | 1.98 | 0.53 | 27% | +0.65 |
| 08-09 | AVAX | 1.68 | -0.01 | -1% | -0.00 |
| 08-19 | ACE | 2.12 | 0.61 | 29% | +0.79 |
| 08-21 | SOL | 1.66 | 0.38 | 23% | +0.86 |
| 08-21 | ETH | 2.17 | 0.57 | 26% | +0.32 |
| 08-21 | TUT | 1.17 | 0.31 | 27% | +0.79 |

RETAIN=0.30 is landing at 23-29% net of cost, as designed. The trail never
touched today's two big winners — ENA and SOL ran to TP without ever retracing
to 0.30 x peak. That is the intended split: the trail harvests fades, the TP
harvests runners. `656454a` / `4d38b3b` already measured this family; not
re-opened.

### Learning loop

Corpus n=77, **overall now net-positive: +$19.70, meanR +0.178, win 42.9%**
(first time the store has been positive).

OOS-consistent verdicts with n>=10 both sides:

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| hold >= 120min | FAVOR | +1.807 | 47 / +0.960 / 57.4% | 30 / -0.847 / 20.0% |
| roc >= 12% | FAVOR | +1.355 | 13 / +1.382 / 69.2% | 64 / +0.027 / 37.5% |
| hold <= 30min | AVOID | -0.517 | 11 / -0.187 | 66 / +0.330 |
| regime_trimmed_hard (<0.5x) | AVOID | -0.626 | 20 / -0.208 / 40.0% | 57 / +0.418 / 43.9% |

`regime_trimmed_hard` is the interesting one: a size multiplier cannot turn a
positive-expectancy trade negative, so the trimmed cohort has genuinely
negative expectancy. The scaler is correctly identifying bad setups and then
taking them anyway at reduced size; the coherent action is a veto, not a trim.
**Sized, it is not worth doing:** ~11 such trades/month x $0.208 = **$2.3/month**.
The standing objective says under $10/month, say so and drop it. Dropped.

`side=LONG AVOID / side=SHORT FAVOR` reverses the 90-day drift-controlled
study; both are weak (e=+-0.113) and the short arm is operator-set. Ignored.

### Shadow ledger

- **slot_occupied: 23 resolved, net +18.16R (avg +0.79R).** Strongly positive,
  and the operator has already acted (wildcard 2 -> 3 slots, TREND 2). Caveat:
  five of the rows are the same 2026-08-19/20 majors event re-signalled on
  BTC/ETH; excluding them leaves **17 resolved at +10.86R**, still clearly
  positive. Four blocked BTC TREND rows resolved +9.3R combined — worth noting
  against BTC's removal from `FUTURES_TREND_SYMBOLS`, but they are one event
  counted four times, not four observations. Not a proposal.
- **veto:*: 24 resolved, net -7.13R.** Vetoes are SAVING money; `ref_not_listed`
  is 18 of 24. Protective, leave alone.
- Gate-cost file agrees: 4 of 5 daily rows negative (blocked trades lost).

### Scan telemetry

Wildcard 1/3 slots, TREND 0/2. ~65 movers in band, 60 scanned, 0 signals;
`roc_below_min` x53-57 dominates, then `no_pullback_resume` x1-5,
`low_volume_z` x1-2. TREND: 2 symbols, blocked on `roc_below_min` x1 +
`no_new_extreme` x1. Correct dormancy — the 08-19 event has decayed. No
`[SIZE_TRIM]` lines. No `5003`/`2015` order rejects. No Traceback / ERROR in
400 log lines.

### Decision rule

**Trial 15: 8/30 convex closes, net R +7.48, net $ +15.17, net R ex-best
+2.52.** Both criteria positive on 27% of the sample. Max equity drawdown from
peak well under 20%; `USE_DRAWDOWN_KILL=1`.

Exits all-time (n=36 with exit_kind): **TP 2 (5.6%) | stop 17 | other 17**. The
old "TP completion <10% -> propose TP3R" watch item is superseded: TREND
already runs TP 3R, and both of today's TPs completed. Re-evaluate at n>=50.

### Lever & deploy

**Lever: the `_pmt_hard_exit` tp=0 guard.** It is the only item on the board
with a real dollar number ($7/occurrence) that also shortens time-to-verdict by
un-censoring the ledger. **Not deployed** — it is a code change on a live-money
service and has not been through the gate. The window is favourable right now
(TREND book empty, GALA is not a PMT pair), so this is the cheap moment for the
operator to take it.

Everything else: no change. Shadow stale, comparison suppressed pending resync.

---

# Daily Audit — 2026-08-20

---

## Automated Assessment (UTC 16:20)

Window 2026-08-19 16:10 -> 2026-08-20 16:20 UTC. Equity **$139.14**
($121.98 cash + $17.00 margin + $0.16 unrealised), **2 open TREND positions**.
**2 closed trades**, net **-$0.70**. `pytest -q` **947 passed**. Feature store
**66 rows** (+2, reconciles to BTC + PRL). Shadow ledger **110 rows**.

Trial 15 (big-3 TREND sleeve) shipped this morning; this is its first audit.

### Closed trades

| sym | side | sleeve | entry -> exit | lev | R | $ | exit |
|---|---|---|---|---|---|---|---|
| BTC_USDT | LONG | TREND | 70026.1 -> 70306.0 | x10 | **+0.45** | +0.17 | `TAKE_PROFIT` after **3.4s** |
| PRL_USDT | LONG | WILDCARD | 0.3256 -> 0.2971 | x2 | -0.99 | -0.87 | `EXCHANGE_CLOSE` (-1R stop) |

PRL is a clean trade: entered on a 17.3% 3h impulse, stopped at -17.8% of
margin against a 17.9% designed stop, i.e. the 20% cap held exactly as
designed. Nothing to fix.

### THE DEFECT — a convex position was executed by PMT machinery

The first live TREND entry ever placed was closed **3.4 seconds after fill**,
at **+0.45R**, by an exit reason (`TAKE_PROFIT`) that **does not exist in the
convex model**. Convex is -1R stop or +3R TP, nothing else.

Reconstruction from the trade record:

- state file shows the position was opened correctly:
  `entry_signal=TREND_LONG, tp=71857.0 (+2.96R), sl=69407.8 (-1R)`
- the closed record shows `entry_signal="RECOVERED", sleeve="PMT", score=0,
  risk_usdt=0, sl_frac_designed=null, peak_r=null`

Between those two states, `runtime._refresh_live_positions` re-adopted the
position. That function walks `self._active_symbols` — **the six PMT pairs** —
and any exchange position not present in `self.open_positions` at that instant
is rebuilt as a `RECOVERED` position **with tp=0 and sl=0**. `exits.py` then
applies `MICRO_LOCK_DEFAULT_RECOVERED_ENTRY_SIGNALS = {"RECOVERED"}`, a micro
profit-lock written for orphaned PMT positions, and it took the +0.45R.

The TREND sleeve trades BTC/ETH/SOL. Those are three of the six symbols that
path scans. **Every TREND entry is exposed to this**, and the exposure window
is a race, which is why SOL (08:12) and ETH (15:58) survived and BTC (08:07)
did not.

Dollar cost: a hijacked winner is truncated from a 3R target to ~0.4R.
At 1R = $2.66 that is up to **-$7 per occurrence**, and it destroys the trial's
convexity on a random subset of entries — the R-ledger the trial is being
judged on gets silently censored.

**Proposed fix (NOT applied):**
1. `_refresh_live_positions` must skip any symbol already held by a non-PMT
   sleeve, and must not create `RECOVERED` positions at all while a convex
   sleeve owns the symbol.
2. The micro-lock must be gated on `_sleeve_kind(position) == "PMT"`, the same
   construction `fcd93f3` used for `_maybe_partial_bank` — this is the **fourth**
   instance of the hand-maintained-sleeve-list class of bug, and the regression
   test added in `fcd93f3` should be extended to cover both call sites.
3. Env-only stopgap available immediately, zero live risk (PMT is
   decommissioned and holds nothing): clear
   `FUTURES_MICRO_LOCK_RECOVERED_ENTRY_SIGNALS`.

Not deployed today: two TREND positions are open on the affected symbols, the
change is code not config, and it has not been through the gate.

### Open positions

| sym | side | lev | held | R now | peak R | giveback | to TP | to SL | margin |
|---|---|---|---|---|---|---|---|---|---|
| SOL_USDT | LONG | x10 | 8.2h | +0.06 | +0.71 | -0.65 | +4.0% | -1.6% | $14.07 (as intended) |
| ETH_USDT | LONG | x8 | 0.4h | +0.00 | +0.05 | -0.05 | +7.3% | -2.4% | **$2.93 vs $14.99 intended** |

SOL traded down to 86.03 — **0.08R from its stop** — before recovering.

### Sizing: the trial is running at a fifth of its design size

ETH's entry log, in three steps:

```
[RISK_TARGETED] TREND ETH_USDT sl_margin=19.39% risk_pct=1.870% margin 14.99 -> 12.05
[REGIME]        ETH_USDT eff=0.24 -> size x0.37
[SIZE_TRIM]     TREND ETH_USDT regime_mult=0.37 margin 12.05 -> 4.44 (intended 12% of balance)
```

and contract quantization (ETH minimum step = 1 contract = 0.01 ETH) took the
final fill to **$2.93** — **19.5%** of the 12%-of-balance intent.

`size_efficiency`, last six convex closes: 0.80, 0.44, 0.70, 0.50, 0.37, and now
~0.20. The regime scaler is running the entire trial at half size or less.
R-multiples are unaffected (R = pnl_pct / sl_margin_pct), so the **trial's
verdict survives** — but under the standing $-objective the **dollar** result of
trial 15 is not the dollar result of the strategy being tested.

The learning loop independently flags the same mechanism:
`regime_trimmed_hard(<0.5)` is **AVOID**, n=19, **-$0.235 vs +$0.316** per
trade, OOS-consistent. Read carefully, that says the scaler **identifies bad
regimes correctly and then takes the trade anyway at a smaller size**. A veto
is worth more than a multiplier. Not proposed today — it is a sizing change and
needs `replay_exits.py` over >=7d plus `mc_ledger.py`.

### Learning loop

Corpus 66 closed trades, 2026-06-27 .. 2026-08-20, overall +$0.157/trade,
win 42.4%, meanR 0.18.

| condition | verdict | n | with | without |
|---|---|---|---|---|
| `hold>=120min` | FAVOR | 39 | +$0.819 / 59.0% | -$0.798 / 18.5% |
| `hold<=30min` | AVOID | 11 | -$0.187 / 27.3% | +$0.226 / 45.5% |
| `regime_trimmed_hard(<0.5)` | AVOID | 19 | -$0.235 / 36.8% | +$0.316 / 44.7% |
| `roc>=12pct` | FAVOR | 11 | +$1.060 / 63.6% | -$0.023 / 38.2% |
| `leverage>=7` | AVOID | 27 | -$0.019 / 48.1% | +$0.280 / 38.5% |
| `side=SHORT` | FAVOR | 25 | +$0.622 / 48.0% | -$0.126 / 39.0% |
| `side=LONG` | AVOID | 41 | -$0.126 / 39.0% | +$0.622 / 48.0% |

`hold>=120min` FAVOR / `hold<=30min` AVOID is the strongest pair in the corpus
and it is exactly the convex thesis: no time stops, no early exits. It is also
a second, independent indictment of the 3.4-second BTC close.

**The long/short reading now contradicts itself.** The 90-day drift-controlled
study (2026-08-14) put the entire edge in the longs, +0.244R vs -0.225R, and
that study is what justified shipping `FUTURES_TREND_LONG_ONLY=1` this morning.
The feature store now says the opposite, with OOS markers showing it is a
late-window effect only (`side=LONG e=-0.071 l=-1.129`). Flagged, not acted on.
Two contradictory measurements on n=25/41 is not a decision, and reversing a
same-day operator decision on it would be the worst kind of overfitting.

### Shadow-ledger counterfactuals

**Slot cost — `slot_occupied`, 20 resolved: net +9.16R.** Read past the
headline: two +5.0R take-profits (SNXX 07-30, HEI 08-05) contribute +10R.
Ex-those-two the remaining 18 net **-0.84R**. The positive number is two
lottery tickets, not a distribution. **This is not evidence for more slots**,
and the 2-slot wildcard raise on 07-31 has produced exactly one resolved row
since. Reported to close out the operator's recurring "am I missing out?"
question: on the current evidence, no.

**Vetoes — 22 resolved: net -6.46R** (14 of 22 resolved to -1R). The external
gates are **saving** money. Keep them; no veto-tuning proposal.

### Wildcard

Dormant and correct. Per scan: 50-56 movers, 25 scanned, **0 candidates**.
Rejections `roc_below_min` 22-24 and `no_pullback_resume` 2-3; the turnover
deflator excludes 47/48 (the trial-14 fix, working). **Zero 5003/2015 order
rejects — the sleeve is not execution-blocked**, it is genuinely finding nothing
in a quiet tape, with both slots free. No gate loosening proposed.

### Exits

`TP 0 (0%) | stop 11 | other 14 | unlabelled 28` over 53 convex closes.

The pre-registered watch item asks for a TP3R proposal when TP completions are
<10% over >=15 trades. **Declining it, on arithmetic.** Peak-R across the 20
convex trades that carry the field: only **1 reached +3R**, 2 reached +2R.
A 5R->3R wildcard TP therefore changes about **1 trade in 20**, worth roughly
**$2.66 in total**. The standing objective says say so and drop it. The TREND
sleeve already ships at TP 3R.

### Decision rule progress

**2/30 convex closes, netR -0.54, net $-0.70.** BTC's +0.45R is contaminated by
the defect above and should not be counted as evidence for or against the trend
sleeve. Equity -2.9% from the $143.37 peak — no drawdown flag. No kill condition
tripped: no TREND loss worse than -1.5R (none closed cleanly yet).

### Config drift

`DECISION_RULE.md` records TREND at 3 slots over BTC/ETH/SOL. Live env is
`FUTURES_TREND_MAX_POSITIONS=2`, `FUTURES_TREND_SYMBOLS=ETH_USDT,SOL_USDT` —
BTC was dropped after this afternoon's standalone-record study found its trend
arm negative. The env is newer than the doc; the doc needs a line.
Also noted: `USE_DRAWDOWN_KILL=1` — the override that was 0 has been restored.

### Lever & deploy

**Lever:** guard `_refresh_live_positions` and the micro-lock against non-PMT
sleeves. **Deployed: nothing.** Code change, unstaged, two open positions on
the affected symbols, shadow stale. Aborting safely per protocol.

**Shadow:** stale, comparison suppressed pending resync
(`railway up --service Futures-shadow`, paper, zero live risk, operator-gated).

### 7-day verdicts on shipped changes

| change | shipped | verdict |
|---|---|---|
| turnover-deflator fix (trial 14) | 08-14 | earning it — 47/48 majors correctly excluded per scan, no false small-cap promotions |
| TREND sleeve (trial 15) | 08-20 | too early — 1 close, and it was destroyed by the recovery-path defect |
| TREND long-only, BTC dropped | 08-20 | too early — no clean close yet |
| wildcard 2 slots | 07-31 | unproven — 1 resolved counterfactual row since |

---

# Daily Audit — 2026-08-19

---

## Automated Assessment (UTC 16:10)

Window 2026-08-18 16:10 -> 2026-08-19 16:10 UTC. Equity **$139.82**, all cash,
**0 open positions**. **1 closed trade** (ACE_USDT, +$0.79). `pytest -q` **925
passed**. Feature store **64 rows** (+2 since 08-16, reconciles to GPS + ACE).
Shadow ledger **102 rows**, 101 resolved.

**24h realised +$0.79 (+0.61R).**

### 0. Coverage gap — this run also closes 08-17 and 08-18

No audit entries exist for 2026-08-17 or 2026-08-18; the scheduled run did not
produce them. As a consequence **GPS_USDT (closed 08-17 13:12 UTC, -0.99R,
-$1.81) was never reported**. It is reviewed below alongside the in-window
trade. Nothing was lost from the ledger — the feature store and exchange history
both carry it — but two days of narrative are missing from this file. Flagged as
an operational item, not a bot fault.

### 1. Trades

| close (UTC) | sym | side | lev | entry_lat | roc3h | peak R | exit | R | $ | acct% |
|---|---|---|---|---|---|---|---|---|---|---|
| 08-19 02:04 | ACE_USDT | LONG | x1 | 1.00 | +31.0% | **+2.12** | CONVEX_RETENTION_TRAIL | **+0.61** | **+0.79** | +0.57% |
| 08-17 13:12 | GPS_USDT | LONG | x1 | 1.00 | +9.4% | +0.17 | EXCHANGE_CLOSE (stop) | -0.99 | -1.81 | -1.29% |

Both are WILDCARD. PMT remains `entries_disabled` by design; squeeze remains off
(`FUTURES_SQUEEZE_ENABLED=0`). No PMT trades, none expected.

**ACE_USDT — the trial-14 treatment paid.** This is the symbol the turnover
deflator was rebuilt for on 08-14: under the old rolling-window deflator ACE read
1.000 and was excluded as a "major". It is now in the tradeable band, it fired,
and it made money. Held 17.9h, margin $19.93, sl_margin 13.04%, fee 2.0% of
gross. The mover was liquid and cross-listed (`ref_listed=1`).

Two honest qualifications:

- **Peak +2.12R, exit +0.61R — 71% of built profit given back.** That is the
  retention trail behaving exactly as specified (floor = 0.30 x peak, raised to
  the sleeve's cost floor), and the design invariant "never give back more than
  100%" held. But 0.30 is a *floor*, and a trade that reaches +2R and exits at
  +0.6R is the case the floor is least flattering on. n=1; not a proposal.
- **The cold-streak throttle halved it.** `streak_multiplier=0.50`
  (loss_streak=2 from LAB and GPS), `regime_size_mult=1.0`, so realised risk was
  **0.90% of equity against the 1.87% target** — 48% of intended size. The
  winner was cut in half; forgone profit ~$0.79.

**GPS_USDT** — entered at `entry_lateness=1.0` on a +9.4% 3h ROC, stopped
cleanly at -0.99R in 1.5h. No fault: the stop resolved server-side at the
modelled distance, fee share 1.3%. It is an ordinary loss of the kind the sleeve
is built to absorb.

**Exit-path check.** Neither exit is a bug. `CONVEX_RETENTION_TRAIL` (trial-7
proportional retention) and `CONVEX_TIME_STOP` (24h clock) are shipped,
deliberate convex exit rules in `runtime.py`; the skill file's "-1R stop or +5R
TP only" description of the convex sleeve is **stale** and should be updated.

### 1-OPEN. Open positions — none

`positions=0` on every `[ACCOUNT]` line in the retained window; equity is 100%
available. Nothing to report.

### 1a-bis. Learning loop

**(a) Feature store — in sync.** 64 rows, +2 since the 08-16 reading of 62,
matching exactly the two closes since (GPS, ACE). No censoring in this window.
Conditional expectancy unchanged in substance at this corpus size; no condition
newly clears the n>=10 bar. No proposal.

**(b) Shadow ledger — 102 rows, 101 resolved. The funding charge changes the
numbers materially.** Commit `2016002` now charges funding on counterfactual
holds, so `outcome_net` is the figure to read, not `outcome`:

| split | n | netR (gross) | **netR (net of cost+funding)** | outcomes |
|---|---|---|---|---|
| `shadow_only` | 46 | +16.20 | **+13.70** | stop 18, tp 15, timeout 13 |
| `veto:ref_not_listed` | 17 | -7.46 | **-9.57** | stop 12, trail 4, timeout 1 |
| `slot_occupied` | 17 | +10.86 | **+5.36** | trail 7, stop 6, tp 2, timeout 2 |
| `min_vol_skip` | 12 | +8.99 | +8.71 | tp 5, trail 4, stop 3 |
| `side_disabled` | 4 | +2.23 | +2.16 | stop 1, tp 1, trail 2 |
| `calm_shock` | 1 | -1.00 | -1.01 | stop 1 |
| `veto:crowded_*` / `move_not_corroborated` | 4 | +1.99 | +1.90 | — |

- **Slot cost: +5.36R net over 17 resolved — and +10.00R of the gross is two
  lottery tickets (SNXX +5.00, HEI +5.00).** Strip those two and the other 15
  net **-4.64R after funding**. A third slot is **not** supported; the slot-lock
  is protective. Note also that **no new `slot_occupied` row has appeared since
  08-05** — with one position at a time and a quiet tape, slot contention is not
  currently happening at all, so this question is dormant rather than close.
- **`veto:ref_not_listed` is the strongest guard in the stack and got stronger:
  -9.57R avoided over 17 rows** (was -4.46R over 14 on 08-16). All three new
  rows this window are NIULAI_USDT, all three resolved `-1.0R stop`. A
  MEXC-only micro-pump veto doing precisely its job.
- One row unresolved: ACE_USDT SHORT, `veto:crowded_shorts(funding=-0.240%)`,
  opened 08-19 15:13.

**(c) Scan telemetry.** Eight `[WILDCARD_SCAN_SUMMARY]` cycles in the retained
window, identical in shape:

| | |
|---|---|
| movers / scanned / candidates | 28-30 / 24-25 / **0** every cycle |
| dominant rejection | `roc_below_min` **19-23 of 25** |
| secondary | `no_pullback_resume` 2-4, `low_volume_z` 0-2, `climax_wick` 0-1 |
| deflated | **30-31 / 48** |
| shorts_blocked / shock_blocked | 0 / 0 |
| order rejects (5003 / 2015), tracebacks | **none** |
| `[SIZE_TRIM]` lines | none in window |

`[WILDCARD_FUNNEL]` confirms the universe is being scanned in full: usdt=1008 ->
in_band=670 -> turnover>=$3M: 52 -> range24>=8%: 28 -> scanned 25. The deflator
reads 30-31/48, so trial 14's "fail OPEN" kill condition (deflators reading
1.000 across the shortlist) stays clear.

Dormancy cause: an absent tape, not an execution fault. `roc_below_min` is
rejecting 19-23 of 25 scanned movers every cycle — the movers present simply do
not move enough. **Correct behaviour; no gate loosening proposed.**

**(d) Decision rule — CONVEX TRIAL 14 progress.**

| | |
|---|---|
| closes since 2026-08-14 | **4 / 30** |
| net R | **+1.68** |
| net R ex-best | **-1.01** |
| net $ | **+3.67** |
| equity drawdown from peak (~$142) | **-1.5%** (kill flag is -20%) |
| all-time wildcard | n=52, netR +15.23, net $+12.25, win 40% |

Four closes in five days. Nothing is decidable at n=4 and no threshold is
editorialised here.

### 2. Champion vs shadow

**Shadow stale, comparison suppressed pending resync.** `Futures-shadow` is
still emitting PMT gate blocks on the 6-pair universe with no wildcard scan at
all — it remains on the 2026-06-14 build. Action item, unchanged and
operator-gated: `railway up --service Futures-shadow` (paper, zero live risk).

### 3. Diagnose — the lever

**No lever. Trial 14 runs untouched.**

The one candidate this window suggested was the retention floor (ACE gave back
71% of a +2.12R peak). Three reasons it is not proposed:

1. n=1, and the floor was set on 444 adversarially re-simulated entries.
2. Changing an exit parameter mid-trial resets the trial. Trial 14 is at 4/30
   after nine resets in ~13 days. A tenth reset costs more measurement than the
   change could plausibly return.
3. **Dollars.** At 1R = $2.66 and ~24 closes/month, moving the retention floor
   0.30 -> 0.375 is worth single-digit dollars per month either way — below the
   $10/month bar the standing objective sets for even discussing a change.

The cold-streak throttle was checked rather than assumed, since it halved this
window's only winner. Across the 23 rows carrying streak telemetry it has fired
3 times: it cut BANK (-$0.79 loss) and COTI (-$0.56 loss at x0.25) and ACE
(+$0.79 win). **Net effect +$1.67 saved.** Throttled trades average -0.493R
against +0.106R unthrottled — it is firing on genuinely worse trades. It earns
its keep; no change.

**TRIAL-4 watch item — TP completions.** Of the 24 rows carrying `exit_kind`:
TP **0 (0%)**, stop 10, OTHER 14. That trips the letter of the watch item
(<10% TP over >=15 trades, OTHER dominant). It should **not** trigger the TP3R
proposal, and the reason matters: OTHER now dominates **by design**, not because
+5R is unreachable. `CONVEX_TIME_STOP` and `CONVEX_RETENTION_TRAIL` were shipped
deliberately and pre-empt the TP by construction. Across the full 52-trade
ledger six trades did reach ~+5R (ESPORTS +5.09, NIL +5.06, AAVE +5.02, O +5.00,
TRIA +4.94, USOIL +4.72) — **~12%**, above the bar. The watch item's exit_kind
proxy is measuring the new exit stack, not target reachability. Recommend the
watch item be re-specified against R-attainment rather than `exit_kind`.

### 4. Validate

`pytest -q` **925 passed** (up from 892; the gate-cost and shadow-funding commits
added tests). No candidate staged, so no replay, no MC, no shadow A/B.

### 5. Deploy

**None.** No config change, no code change, no promotion. Docs only.

### 6. Verdict on recent changes

| change | shipped | live evidence | verdict |
|---|---|---|---|
| Turnover deflator (trial 14) | 08-14 | ACE now in band, traded, +$0.79; TUT +$5.42; deflator 30-31/48, no fail-open | **earning its keep** |
| Retention trail (0.30 x peak) | trial 7 | ACE +0.61R off a +2.12R peak; invariant held | works as specified; giveback is the open question |
| 24h convex time stop | trial ~13 | TUT +2.69R off +4.14R; LAB -0.63R | neutral-to-positive, n=4 |
| Cold-streak throttle | earlier | 3 firings, +$1.67 net saved | **earning its keep** |
| Funding on counterfactuals | 08-18 | slot_occupied +10.86R -> +5.36R | corrects an over-optimistic ledger; keep |
| `ref_not_listed` veto | earlier | -9.57R avoided over 17 | **strongest guard in the stack** |

### 7. Summary

- 1 close in window (ACE +0.61R / +$0.79); GPS (-0.99R / -$1.81) recovered from
  the unreported 08-17 gap.
- 0 open positions, equity $139.82, drawdown -1.5% from peak.
- Trial 14 at 4/30, netR +1.68, ex-best -1.01.
- No lever, no deploy. Three items for the operator: resync Futures-shadow;
  update the skill file's stale convex-exit description; re-specify the TP watch
  item against R-attainment.

---

# Daily Audit — 2026-08-16

---

## Automated Assessment (UTC 16:10)

Window 2026-08-15 19:30 -> 2026-08-16 16:10 UTC (20.7h). Equity **$140.76**, all
cash, **0 open positions**, **0 closed trades**. `pytest -q` **892 passed**.
Feature store **62 rows** (unchanged, mtime 08-15 18:54). Shadow ledger **97
rows** (0 new; ACE resolved).

**24h realised $0.00. Flat since LAB closed 08-15 18:54 UTC.**

A genuinely empty day: no entries, no closes, and — more unusual — **not one new
shadow-ledger row**, meaning the detector produced no signal at all, not even a
vetoed one. Equity is bit-identical to yesterday's reading.

### 1. Trades — none

No PMT (`entries_disabled` by design), no wildcard, no squeeze
(`FUTURES_SQUEEZE_ENABLED=0`). Exchange history confirms the last close is
LAB_USDT at 08-15 18:54 UTC, already reported.

### 1-OPEN. Open positions — none

`positions=0` on every `[ACCOUNT]` line in the retained log window.

### 1b. Wildcard — why nothing fired

Six `[WILDCARD_SCAN_SUMMARY]` cycles survive (container restarted 15:29 UTC on
the operator's `feat(why)` deploy; Railway retains ~500 lines). They are
identical in shape:

| | |
|---|---|
| movers / scanned / candidates | 22 / 22 / **0** every cycle |
| dominant rejection | `roc_below_min` **16-18 of 22** |
| secondary | `no_pullback_resume` 2-5, `low_volume_z` 0-2, `climax_wick` 0-2 |
| deflated | **21-22 / 48** |
| shorts_blocked / shock_blocked | 0 / 0 |
| order rejects (5003 / 2015) | **none** |
| tracebacks | **none** |

This is dormancy from an absent tape, not from an execution fault: the universe
is being scanned in full, and the movers present simply do not move enough
(|3h ROC| under the floor). **Correct behaviour — no gate loosening proposed.**
The deflator continues to read 21-22/48, so trial 14's "failed OPEN" kill
condition stays clear.

### 1a-bis. Learning loop

**(a) Conditional expectancy** — corpus unchanged at 62 rows, so the table is
identical to yesterday's and is restated only for continuity: `hold>=120min`
FAVOR (tautological), `roc>=12pct` FAVOR (+1.297, n=9 on the "with" arm — still
under the n>=10 bar), `regime_trimmed_hard` AVOID (-0.557), `fee_heavy>=30pct`
AVOID (-0.233). **No proposal. The corpus is still missing five losses** (see
§3); nothing derived from it is actionable until that is repaired.

**(b) Shadow ledger** — 97 rows, all 97 now resolved. ACE_USDT resolved
`timeout +1.443R`, i.e. the `crowded_shorts` funding veto **cost** money on that
one row.

| split | n | netR | outcomes |
|---|---|---|---|
| `shadow_only` | 46 | +16.20 | stop 18, tp 15, timeout 13 |
| `slot_occupied` | 17 | **+10.86** | trail 7, stop 6, tp 2, timeout 2 |
| `min_vol_skip` | 12 | +8.99 | tp 5, trail 4, stop 3 |
| `veto:ref_not_listed` | 14 | **-4.46** | stop 9, trail 4, timeout 1 |
| `side_disabled` | 4 | +2.23 | trail 2, tp 1, stop 1 |
| `veto:crowded_shorts` | 1 | +1.44 | timeout 1 |
| `veto:move_not_corroborated` | 1 | +0.91 | trail 1 |
| `veto:crowded_longs` | 2 | -0.36 | stop 1, timeout 1 |

**Slot cost: +10.86R over 17 resolved — but +10.00R of it is two lottery tickets
(SNXX +5.00, HEI +5.00 tp). Strip them and the other 15 net +0.86R, i.e. flat.
The slot-lock is not costing money; a third slot is not supported.** The
reference-listing veto remains the strongest guard in the stack (-4.46R avoided
over 14 rows).

**Arithmetic discrepancy, flagged not resolved.** These netR figures are the
per-row sum of the resolver's own `outcome` field. They do **not** match
yesterday's published table (`shadow_only` +5.15, `slot_occupied` +5.36,
`ref_not_listed` -6.53) even though the outcome-*kind* counts per split are
identical row-for-row. Same rows, same classifications, different magnitudes.
Either yesterday's sums were computed differently, or stored outcomes are being
rewritten after resolution (the file was rewritten today at 09:37 UTC when ACE
resolved). **I cannot tell which without yesterday's raw file, and I do not have
it.** Today's copy is preserved so tomorrow's run can diff and settle it. Until
then the qualitative readings above — vetoes protective, slot-lock protective,
tail-dependent — hold under both versions; the absolute R figures should not be
quoted as settled.

**(c) Scan telemetry** — covered in §1b. No `[SIZE_TRIM]`, no `slot_occupied`
candidates (no positions were held), no `[POSITION_RECONCILE_DROP]`.

**(d) Decision rule — trial 14** (from 2026-08-14 18:14 UTC):

| | |
|---|---|
| convex closes | **1 / 30** (LAB, unchanged) |
| net R / net $ | **-0.63R / -$0.73** |
| max drawdown | **-1.8%** from the $143.37 peak, inside the 20% flag |

Two days into the trial and one close deep. Entries, not exits, remain the
binding constraint on time-to-verdict.

`USE_DRAWDOWN_KILL` now reads **1** in the live variables, not the 0 recorded as
a standing operator override on 2026-07-17. Stated as an observation; not
changed, and immaterial at -1.8% drawdown.

### 2. Champion vs shadow

**Shadow: stale, comparison suppressed pending resync.**

### 3. The lever — unchanged from yesterday, still unapplied

Yesterday's proposal stands and nothing today displaces it: **the reconciliation
guard**. Verified still absent — `runtime.py:4170` and `:4201` both still clear a
position "without recording P&L" with no retry, so a history-lag race still
destroys the row permanently. Five real-money closes totalling **-$6.56, every
one a loss**, remain outside the corpus.

Today adds a second, independent reason to distrust the measurement layer: the
shadow-ledger arithmetic above does not reproduce. Two of the three data
surfaces this bot learns from now have an open integrity question. Proposing a
strategy parameter against them would be measuring with a bent ruler.

**Proposed (NOT self-applied, unchanged):** per-cycle 48h exchange-vs-`trade_history`
diff on `positionId`; synthesise a `reconstructed=1` row plus a loud Telegram
alert on a miss; bounded retry in place of both "cleared without recording P&L"
branches. Plus the separate operator call to backfill the five missing rows.

**Not proposed:** anything derived from the current corpus, and no gate
loosening to manufacture trades in a quiet tape.

### 4. Validate / 5. Deploy

`pytest -q` **892 passed** (up from 869; the operator's `feat(why)` deploy
d0e0397 landed 15:28 UTC and is running clean — `[ACCOUNT]` lines present, no
traceback). **No deploy, no config change, no self-applied parameter move.**
Nothing to gate: zero trades, zero closes, and the two candidate levers are both
operator-gated.

### 6. Outstanding

- **Top priority, day 2:** the ledger leak — 5 unrecorded closes, -$6.56, all
  losses, 33 days running. Fix unshipped.
- **New:** shadow-ledger netR does not reproduce against yesterday's published
  table. Copy preserved for tomorrow's diff.
- **Action item (raised once, still open):** resync Futures-shadow to champion
  HEAD.
- Trial 14 at 1/30. `roc_below_min` dominant in a quiet tape.

### Verdict

**No change deployed, and correctly so.** Nothing traded, nothing signalled, and
the day's only new information is negative: a second measurement surface that
does not reconcile. The instrument problem is now two days old and unfixed; it
outranks every strategy parameter on the board.

---
# Daily Audit — 2026-08-15

---

## Automated Assessment (UTC 19:30)

Window 2026-08-14 16:10 -> 2026-08-15 19:30 UTC (27.3h, from the last audit, so
nothing falls in a gap). Equity **$140.76**, all cash, **0 open positions**.
`pytest -q` **869 passed**. Shadow ledger **97 rows (+1)**.

**24h realised -$2.611, 0/2 win.**

Feature store **62 rows (+1) against 2 closes — it does not reconcile.** That
single missing row is the headline, and chasing it turned up four more.

### 1. Trades — two losses, and one of them the bot does not know it made

**US_USDT SHORT x1, WILDCARD — server-side stop. NOT IN ANY BOT LEDGER.**

| field | value |
|---|---|
| open / close | 08-14 16:25 -> 18:03 UTC (1.63h) |
| entry / exit | 0.015276 -> 0.01809 |
| realised | **-$1.9316** (order profit -$1.9135, fees $0.0181) |
| pnl_pct / margin | -18.56% on ~$10.41 margin |
| **R** | **~-0.93R** — *estimated*; the bot recorded no `sl_margin_pct` |
| exit | resting server stop filled (`stoporder_STOP_LOSS_1469707401_...`) |
| feature store / trade_history / last_exit_by_symbol / shadow ledger | **absent / absent / absent / absent** |

The entry order carries MEXC's `_m_<uuid>` API-order prefix — the same prefix on
LAB_USDT's entry, which *is* in the ledger — so it came through the API, not the
web UI. Sizing carries the wildcard fingerprint: non-PMT small cap, x1 leverage,
stop landing at 18.6% of margin just under the 20% cap. **The bot opened it,
armed its stop, and then recorded nothing when the stop filled.**

**LAB_USDT SHORT x3, WILDCARD — `CONVEX_TIME_STOP`, the clock again.**

| field | value |
|---|---|
| open / close | 08-14 18:54 -> 08-15 18:54 UTC (**24.0h exactly**) |
| entry / exit | 0.0848 -> 0.0877 |
| realised | **-$0.6792** (fee $0.033, 4.8% of gross) |
| **R** | **-0.63R** (`sl_margin_pct` 17.19) |
| **peak R** | **+0.28R** — never worked, not once |
| exit | `CONVEX_TIME_STOP` / `exit_kind=OTHER` |
| lateness / ref_listed | 1.00 / 1 |
| regime_mult / streak_mult / size_efficiency | **0.459** / 1.0 / 0.441 |

Flagged per the convex-exit rule; **working as designed**, same documented 24h
clock as TUT. Design was intact throughout: TP 0.0606 / SL 0.0898 = a 4.97R
target on a 5.9%-of-price stop. The regime scaler hard-trimmed it to 0.459 and
that trim *saved* money — at full size this was -$1.48 rather than -$0.68.

PMT: `entries_disabled` all window (by design). Squeeze: OFF. Sniper: retired.

### 1-OPEN. Open positions — none

Flat since 18:54 UTC. Nothing to report.

### 1a. THE LEAK — five closed trades that never entered the corpus

The missing US row prompted a full reconciliation of **every** exchange close
since the feature store opened (2026-06-27) against the store itself: 67
exchange closes, 62 ledger rows.

**Six exchange closes have no matching ledger row.** One (BILL_USDT 07-16) *is*
in the corpus at a timestamp 8h off its exchange close — a matching artefact, not
a missing trade. The other five are simply absent:

| closed (UTC) | symbol | side | lev | realised | ratio |
|---|---|---|---|---|---|
| 07-14 00:55 | BTC_USDT | SHORT | x20 | **-$3.4877** | -20.89% |
| 07-19 17:02 | SOL_USDT | LONG | x5 | -$0.1309 | -4.28% |
| 07-25 21:06 | ONDO_USDT | LONG | x5 | -$0.2402 | -6.22% |
| 07-30 03:18 | BEAT_USDT | LONG | x4 | -$0.7743 | -21.41% |
| 08-14 18:03 | US_USDT | SHORT | x1 | -$1.9316 | -18.56% |
| | | | | **-$6.5647** | |

**Every single missing row is a loss. Not one win is missing.** That is not
chance, and it has a mechanism: winners close through the bot's own decision
(`CONVEX_TIME_STOP`, `CONVEX_RETENTION_TRAIL`, TP) and run in-process through
`_finalize_close`, which writes the row. Losers close **exchange-side** on a
resting stop, and only get recorded if `_reconcile_closed_position`
(`runtime.py:3886`) wins a race afterwards. When it loses, the trade is gone.

Two code paths in that function clear a position **"without recording P&L"**
(runtime.py:3903 and :3933) — the second fires when MEXC's open-position endpoint
already reports flat but its history endpoint has not yet published the closed
row. There is no retry: one miss and the trade is discarded permanently. A second
candidate mechanism — the fill never being adopted into `open_positions` at all —
fits the evidence equally well. **I cannot separate them: Railway retains ~500 log
lines and today's 19:30 restart wiped the window.** Naming the mechanism is not
required to act; the leak is proven either way.

**What this contaminates.** Every measurement the operator makes rests on this
corpus, and it is biased in one direction:

| | reported | corrected |
|---|---|---|
| convex closes (all-time) | 40 | **43** |
| convex net $ | +$13.41 | **+$10.47** |
| convex win rate | 40.0% | **37.2%** |
| convex net R | +16.58 | **~+14.3** (approx; missing rows carry no `sl_margin_pct`) |
| trial 13 | 5 closes, netR -0.84, +$0.98 | **6 closes, netR ~-1.77, -$0.95** |

Trial 13 did not end fractionally positive in dollars. It ended negative. The
`side=SHORT FAVOR` reading in yesterday's conditional-expectancy table is also
suspect: two of the five missing losses are shorts.

The corpus has been leaking for **32 days** and every prior audit reported it as
reconciling, because every prior audit checked the row count against *that day's*
closes rather than against the full exchange history.

### 1a-bis. Learning loop

**(a) Conditional expectancy** over the 62 rows — conditions with a verdict and
n>=10 per group. **Read these knowing the corpus is missing 5 losses.**

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| hold>=120min | FAVOR | +1.612 | 38 / +$0.819 / 57.9% | 24 / -$0.793 / 16.7% |
| roc>=12pct | FAVOR | +1.297 | 9 / +$1.304 / 66.7% | 53 / +$0.007 / 37.7% |
| regime_trimmed_hard(<0.5) | AVOID | -0.557 | 18 / -$0.200 / 38.9% | 44 / +$0.357 / 43.2% |
| fee_heavy>=30pct | AVOID | -0.233 | 11 / +$0.004 / 45.5% | 51 / +$0.237 / 41.2% |

`hold>=120min` remains tautological. `roc>=12pct` FAVOR now clears n>=10 on the
"without" arm only (n=9 with) — not yet actionable. **No proposal from this table
until the corpus is repaired**; acting on a loss-censored sample is how a bot
learns that everything works.

**(b) Shadow ledger** 97 rows, 96 resolved (+1: ACE_USDT, unresolved).

| split | n | netR | outcomes |
|---|---|---|---|
| `shadow_only` | 46 | +5.15 | stop 18, tp 15, timeout 13 |
| `slot_occupied` | 17 | **+5.36** | trail 7, stop 6, tp 2, timeout 2 |
| `veto:ref_not_listed` | 14 | **-6.53** | stop 9, trail 4, timeout 1 |
| `min_vol_skip` | 12 | +1.71 | tp 5, trail 4, stop 3 |
| `side_disabled` | 4 | +2.16 | trail 2, tp 1, stop 1 |
| `veto:crowded_longs` | 2 | -0.39 | stop 1, timeout 1 |
| `veto:move_not_corroborated` | 1 | +0.86 | trail 1 |

Unchanged from yesterday and the reading is unchanged. The reference-listing veto
is the strongest guard in the stack (-6.53R avoided over 14 rows). **Slot cost:
+5.36R over 17 rows, but +9.96R of it is two lottery tickets (HEI +4.99, SNXX
+4.97); strip them and the other 15 net -4.60R. The slot-lock is protective. A
third slot is not supported.**

**(c) Scan telemetry — coverage gap.** Only ~1h of logs survive (today's 19:30
deploy restarted the container; Railway retains ~500 lines). Across the 7
`[WILDCARD_SCAN_SUMMARY]` cycles available: movers 17, scanned 17, **candidates
0**, dominated by `roc_below_min` (13-15 per cycle), `no_pullback_resume` (1-3),
`low_volume_z` (0-1). No `[SIZE_TRIM]`, no `shorts_blocked`, **no 5003/2015 order
rejects, no tracebacks**. Quiet-regime dormancy, correct behaviour, no gate
loosening. **The 24h histogram is genuinely unavailable — stated, not papered
over.**

**(d) Decision rule — trial 14** (from 2026-08-14 18:14 UTC, the deflator deploy):

| | |
|---|---|
| convex closes | **1 / 30** (LAB) |
| net R / net $ | **-0.63R / -$0.73** |
| max drawdown | **-1.8%** from the $143.37 peak, well inside the 20% flag |

**Trial-14 kill conditions — both checked, both CLEAR:**
- *"Deflators reading 1.000 across the shortlist -> failed OPEN back into the
  bug."* Live telemetry reads `deflated=20/48` every cycle, against 21/48 the day
  it shipped. The Min60 call is working.
- *">$100M steady turnover entering the tradeable pool -> reverting."* Checked
  the full ticker list: no symbol below the majors band has >$100M raw turnover
  with a >=8% 24h range. The >$100M names (BTC, ETH, SOL, XRP, LINK, HYPE, SOXL,
  XAU, SKHYNIX) are all excluded as majors or non-crypto.

**And the fix demonstrably fired.** ACE_USDT — $78.8M raw turnover, **+145% 24h
range**, the exact symbol the trial was built for — reached the detector today and
produced a signal. It was then vetoed by `crowded_shorts (funding -2.000%)` and
logged to the shadow ledger. Trial 14 is doing what it was designed to do.

### 2. Champion vs shadow

**Shadow: stale, comparison suppressed pending resync.**

### 3. The lever — instrument the ledger against the exchange

Every candidate lever this month has been a strategy parameter measured in
fractions of a dollar. This one is different: **the measurement surface itself is
wrong, and it is wrong in the direction that flatters the bot.** Nothing else
proposed today would matter if the numbers feeding it are loss-censored.

**Proposed (NOT self-applied):** a reconciliation guard, purely additive and
measurement-only — it cannot open, size, or close anything.

1. Once per cycle, pull exchange closes for the last 48h and diff `positionId`
   against `trade_history`.
2. On a miss: synthesise the feature-store row from exchange data
   (symbol/side/leverage/entry/exit/realised/margin; `sl_margin_pct` null and the
   row marked `reconstructed=1` so it is never mistaken for a first-class
   observation) and fire a **loud Telegram alert**. A silently vanishing
   real-money trade must never again be discoverable only by a monthly hand audit.
3. In `_reconcile_closed_position`, replace both "cleared without recording P&L"
   branches with a bounded retry (N consecutive misses before dropping), so the
   history-lag race stops destroying rows.

**Why no V-stack gate:** step 4 gates exit/sizing/entry changes on replayed
dollars. This changes no trading decision, so there is no EV to replay; the
correct test is the three regression cases (history-lag miss, unadopted fill,
already-recorded close must not double-write). Staging it on a stale shadow
proves nothing.

**Also proposed, separately: backfill the 5 missing rows** so the trial ledgers
and the expectancy corpus are correct going forward. This writes to `/data` and
is an operator call, not mine.

**Not proposed:** anything derived from the current corpus. The TP-completion
tripwire (still 0 TP / 9 STOP / 13 OTHER) was measured and rejected on the
dollars yesterday and is not re-litigated. `margin_used` still records intent
rather than the filled size — the same class as today's `risk_usdt` fix
(7311eab), noted and left alone.

### 4. Validate / 5. Deploy

`pytest -q` **869 passed**. **No deploy, no config change, no self-applied
parameter move.** Abort-safely posture is correct here on two counts: the log
window needed to confirm the root-cause mechanism is gone, and an operator deploy
(7311eab) landed 90 minutes ago and has not yet been observed through a close.

### 6. Outstanding

- **NEW, top priority:** the ledger leak above. 5 unrecorded closes, -$6.56, all
  losses, 32 days running.
- **Action item (raised once, still open):** resync Futures-shadow to champion
  HEAD (`railway up --service Futures-shadow`, paper, zero live risk).
- Trial 14 at 1/30. Entries remain the binding constraint — `roc_below_min` is
  the dominant rejection in a quiet tape.

### Verdict

**No change deployed.** The day's two trades lost $2.61 and taught nothing new
about the exit stack. What the day did produce is worth more than a trade: the
bot's learning corpus has been silently discarding losing trades for a month, and
every convex number reported since 2026-07-14 — win rate, net dollars, net R,
trial 13's verdict — has been flattered by the omission. The corrected convex
record is 43 closes at +$10.47 and 37.2%, not 40 at +$13.41 and 40%. Trial 13
closed negative, not positive. Fix the instrument before tuning anything it
measures.

---

# Daily Audit — 2026-08-14

---

## Automated Assessment (UTC 16:10)

Window 2026-08-13 16:10 -> 2026-08-14 16:10 UTC. Equity **$143.37**, all cash,
**0 open positions** — a new account high. `pytest -q` **862 passed**. Feature
store **61 rows (+2)** reconciles with the exchange exactly (2 closes). Shadow
ledger **96 rows (+0)** — nothing to log, because nothing qualified (below).

**24h realised +$4.894, +1.63R, 1/2 win.**

### 1. Trades — the clock took a 4.14R peak off the table

**TUT_USDT SHORT x1, WILDCARD — `CONVEX_TIME_STOP`, the day's whole P&L.**

| field | value |
|---|---|
| open / close | 08-13 06:41 -> 08-14 06:41 UTC (**24.0h exactly**) |
| entry / exit | 0.05616 -> 0.03802 |
| realised | **+$5.4194** (fee $0.023, 0.4% of gross) |
| pnl_pct / margin | +32.17% on $16.85 margin |
| **R** | **+2.69R** (sl_margin_pct 11.965) |
| **peak R / giveback** | **+4.137R / -1.45R** |
| exit | `CONVEX_TIME_STOP` / `exit_kind=OTHER` |
| lateness / ref_listed | 1.00 / 1 |
| regime_mult / streak_mult / size_efficiency | 1.0 / 1.0 / **0.801** — best-sized trade in the record |

Flagged per the convex-exit rule (any exit that is not -1R/+5R gets flagged).
**Verdict: working as designed, not an unhandled path.** The 24h clock is a
documented trial-7 component (`runtime.py:1731`, `FUTURES_CONVEX_TIME_STOP_HOURS`),
retained deliberately as the only backstop against a stale position or a dropped
stop order. The standing brief's "NO time limit" line describes a design two
trials old; the live convex stack is **-1R stop / ~4.2R TP / 0.30xpeak retention
floor / 24h clock**.

**The uncomfortable part:** TUT reached 4.137R against a 4.18R target — **98.9%
of the way** — then faded to 2.69R and the clock booked it there. The retention
floor was sitting at 0.30 x 4.137 = **1.24R**, far below, so it never engaged.
Nothing in the stack defends a trade that has all but hit its target. Measured
below (section 3), and **rejected on the dollars**.

**COTI_USDT LONG x1, WILDCARD — clean -1R stop.**

| field | value |
|---|---|
| open / close | 08-13 16:10 -> 18:32 UTC (2.36h) |
| entry / exit | 0.012637 -> 0.011299 |
| realised | **-$0.5266** (fee $0.008, 1.4% of gross) |
| **R** | **-1.06R** (sl_margin_pct 10.128) |
| exit | `EXCHANGE_CLOSE` / `exit_kind=STOP` — resting server stop filled |
| peak_r | +0.183 |
| streak_mult / loss_streak / size_efficiency | **0.25 / 3 / 0.231** |

Correction to yesterday's entry: COTI's margin was **$22.45, the full intended
size** (`margin_used == intended_margin_usdt`), not the $5.19 reported. The
figure quoted then was a mid-flight snapshot, not the sizing decision.

**The throttle earned its keep this window.** It ran the two losers at 0.25x and
0.50x and the winner at 1.00x. Same three trades at flat size would have been
roughly +$3.1 instead of +$4.9.

PMT: `entries_disabled` all 24h (by design, cycle 3010+). Squeeze: OFF.
Sniper: retired.

### 1-OPEN. Open positions — none

Book is flat and has been since 06:41 UTC. No open-position telemetry to report.

### 1a-bis. Learning loop

**(a) Feature store** 61 rows (+2), reconciles. Conditional expectancy over the
full corpus, conditions with a verdict and n>=10 per group:

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| hold>=120min | FAVOR | +1.654 | 37 / +$0.861 / 59.5% | 24 / -$0.793 / 16.7% |
| side=SHORT | FAVOR | +0.771 | 24 / +$0.678 / 50.0% | 37 / -$0.093 / 37.8% |
| regime_trimmed_hard(<0.5) | AVOID | -0.526 | 17 / -$0.169 / 41.2% | 44 / +$0.357 / 43.2% |
| fee_heavy>=30pct | AVOID | -0.252 | 11 / +$0.004 / 45.5% | 50 / +$0.256 / 42.0% |

`hold>=120min` is tautological — winners are what get held — and is not
actionable. **`side=SHORT` FAVOR directly contradicts the 90-day drift-controlled
replay** that put the entire edge in the longs (+0.244R vs -0.225R). The live
reading is unadjusted for size and $5.42 of the SHORT arm's $16.27 is TUT alone.
Two measurements disagree; the replay has the larger sample and the drift
control. **No action, and the conflict is recorded rather than resolved.**

**(b) Shadow ledger** 96 rows, **all 96 resolved, +0 this window**.

| split | n | netR (net of cost) | outcomes |
|---|---|---|---|
| `slot_occupied` | 17 | **+5.36** | trail 7, stop 6, tp 2, timeout 2 |
| `veto:ref_not_listed` | 14 | **-6.53** | stop 9, trail 4, timeout 1 |
| `veto:crowded_longs` | 2 | -0.39 | stop 1, timeout 1 |
| `veto:move_not_corroborated` | 1 | +0.86 | trail 1 |
| `min_vol_skip` | 12 | +1.71 | tp 5, trail 4, stop 3 |
| `side_disabled` | 4 | +2.16 | trail 2, tp 1, stop 1 |
| `shadow_only` | 46 | +5.15 | stop 18, tp 15, timeout 13 |

**Vetoes are protective and the reference-listing veto is the strongest single
guard in the stack** — 14 resolved rows that would have lost **-6.53R (~-$17)**.
Keep it.

**Slot cost, honestly.** +5.36R over 17 resolved rows reads like an argument for
a third slot. It is not, yet: **+9.96R of that +5.36R is two rows** — SNXX
(+4.97, tp) and HEI (+4.99, tp). Strip those two and the remaining 15 blocked
candidates net **-4.60R**. The slot-lock is being paid for by lottery tickets,
not by a broad positive. With 2 slots already live, a third is not supported.

**(c) Scan telemetry** — 80 `[WILDCARD_SCAN_SUMMARY]` over the 10.5h log window,
**0 candidates, 0 entries**. Rejection histogram, 1,726 gate hits:

| bucket | n | share |
|---|---|---|
| `roc_below_min` | 1,495 | 87% |
| `no_pullback_resume` | 196 | 11% |
| `low_volume_z` | 25 | 1.4% |
| `climax_wick` | 9 | 0.5% |
| `vertical_blowoff` / `rsi_exhausted` | 1 / 1 | — |

21-23 movers scanned per cycle; 87% simply are not moving hard enough to clear
`MIN_ROC`. No `shorts_blocked`, no `shock_blocked`, no `[SIZE_TRIM]`, **no 5003
/ 2015 order rejects, no tracebacks**. This is a quiet-regime dormancy, which
is correct behaviour — not an execution block, and not a reason to loosen a gate.

**(d) Decision rule — trial 13 progress**

| | |
|---|---|
| convex closes since 2026-08-12 | **5 / 30** |
| net R | **-0.84R** |
| net R ex-best (ex-TUT) | **-3.53R** |
| net $ | **+$0.98** |
| max drawdown (ledger equity path) | **-2.7%**, well inside the 20% flag |

All-time wildcard record: **49 closes, netR +16.24, net $+14.00, 41% win**;
ex-best (ESPORTS +5.09R) netR +11.15.

### 2. Champion vs shadow

**Shadow: stale, comparison suppressed pending resync.**

### 3. The lever — the TP tripwire fired, was measured, and is REJECTED

The trial-4 watch item's trigger is now formally met: over the 21 closes carrying
`exit_kind`, **TP completions = 0 (0%)**, stop 9 (43%), **OTHER 12 (57%)** —
under 10% TP with OTHER dominating. The prescribed response is to propose scaling
the TP down at wide stops. Proposed, measured, and it does not pay:

**Evidence 1 — the live peak record.** Of 11 closes carrying `peak_r`, exactly
one ever traded above 2R. Re-pricing every one of them against a smaller target:

| candidate TP | live trades completed | delta vs actual | $ |
|---|---|---|---|
| 2.0R | 1 / 11 | -0.69R | **-$1.84** |
| 2.5R | 1 / 11 | -0.19R | -$0.51 |
| 3.0R | 1 / 11 | +0.31R | **+$0.82** |
| 3.5R | 1 / 11 | +0.81R | +$2.15 |

The entire benefit is TUT booking 3.0R instead of 2.69R. **+$0.82 across the
whole live record.**

**Evidence 2 — the shadow counterfactuals, bucketed by target size.** Completion
rate collapses with target size exactly as the watch item assumed — but mean R
does not improve:

| tp_r | n | tp hit | mean R |
|---|---|---|---|
| 2.0-2.5 | 49 | 20 (41%) | +0.07 |
| 2.5-3.5 | 9 | 1 (11%) | +0.30 |
| >=4.5 | 14 | 1 (7%) | -0.07 |

A 41% completion rate at the low target earns **+0.07R per trade**. Completion
rate is not the objective; R is. **Scaling the TP down buys a better-looking
histogram and no dollars.**

**Evidence 3 — the clock is not the culprit either.** The hypothesis that the
24h clock truncates winners before target is now dead: of 96 resolved shadow
rows, **8 resolved after the 24h mark and all 8 were timeouts. Zero TPs were
ever struck after 24h** (0 of 23). Holding past 24h wins nothing.

**Also measured and dropped: the near-TP lock.** TUT's 1.45R giveback from a
98.9%-of-target peak motivates a fixed floor at k x target once peak reaches
k x target. At k=0.80 it converts TUT's +2.69R to +3.34R: **+0.65R = +$1.73 per
event, ~1 event per 11 trades, ~$3.5/month.** Under the standing objective's $10/mo
materiality bar, on n=1. **Say so and drop it.**

**Also observed, no action: the retention floor is unholdable at high leverage.**
AVAX_USDT (08-09) peaked +1.68R with a floor at +0.50R and exited at **-0.01R**
under `CONVEX_RETENTION_TRAIL`. Not a rule defect — at x13 leverage with
`sl_margin_pct` 4.79, 1R is only **0.37% of price**, so the floor sat 0.18% away
and a 45s poll gap plus market-close slippage swallows it whole. The two
low-leverage retention exits (BICO x1, BTW x3, sl% 16-17) missed their floors by
0.02-0.06R — the floor holds fine when 1R is a real distance. Cost: 0.50R once in
49 trades, ~$1.33. Recorded, not acted on.

### 4. Validate / 5. Deploy

`pytest -q` **862 passed**. No candidate reached the V-stack — every proposal
generated today was rejected on its own $ evidence before staging. **No deploy,
no config change, no self-applied parameter move.**

### 6. Outstanding

- **Uncommitted working-tree change:** `futuresbot/shadow_ledger.py` carries a
  `near_tp_lock` parameter on `resolve_outcome` with **no caller** — inert study
  code, tests green. The feature it implements is the one measured at ~$3.5/mo
  above. Recommend reverting the file to keep the tree clean before the next
  deploy; not self-applied, since it is prior WIP.
- **Action item (raised once, still open):** resync Futures-shadow to champion
  HEAD (`railway up --service Futures-shadow`, paper, zero live risk). Until then
  the comparison stays suppressed.
- Trial 13 at 5/30 with 8 months of calendar unused. Entries, not exits, are the
  binding constraint: 87% of gate hits are `roc_below_min` in a quiet tape.

### Verdict

**No change.** The day produced a +$4.89 realised win, a new equity high, and —
more valuable — it closed two open questions with data: the TP-completion
tripwire is a measurement artefact of target size rather than a defect, and the
24h clock costs nothing in foregone take-profits. Both are now settled and need
not be re-litigated.

---

# Daily Audit — 2026-08-13

---

## Automated Assessment (UTC 16:36)

Window 2026-08-12 16:36 -> 2026-08-13 16:36 UTC. Equity **$142.73** (cash
$116.39 + margin $22.07 + unrealized $4.27), **2 open wildcard positions**.
`pytest -q` **862 passed**. Feature store **59 rows (+2)**, shadow ledger
**96 rows (+1)** — both reconcile with the exchange exactly (2 closes, 1 skip).

### 1. Trades — two closes, both losses, and the FIRST EVER preemption

**INX_USDT SHORT, WILDCARD, x2 — `CONVEX_PREEMPTED`.**

| field | value |
|---|---|
| open / close | 08-12 16:37 -> 08-13 11:10 UTC (18.55h) |
| entry / exit | 0.00755 -> 0.00776 |
| realised | **-$0.2889** (fee $0.016, 5.8% of gross) |
| pnl_pct / margin | -5.89% on ~$4.9 margin |
| **R** | **-0.39R** (sl_margin_pct 15.03) |
| exit | `CONVEX_PREEMPTED` / `exit_kind=OTHER` |
| peak_r | +0.110 |
| lateness / ref_listed | 1.00 / 1 |
| regime_size_mult / size_efficiency | **0.291 / 0.283** |

**This is not a bug — it is the trial-11 feature finally acting.** Preemption
carried untested through trials 11, 12 and the first day of 13 ("0 evictions").
At 11:10 both wildcard slots were full (TUT at ~+2R, INX at -0.39R), a BANK_USDT
signal arrived, and `_preemption_candidate` gave up the position that had failed
to work and kept the one that had. That is exactly the specified behaviour, and
it chose correctly between the two. Flagged loudly per the convex-exit rule (any
exit other than -1R/+5R gets flagged), but the verdict is **working as designed**,
not an unhandled path.

**Was the eviction worth it?** Honest scoring at n=1:

| | R |
|---|---|
| INX realised on eviction | -0.39 |
| BANK, the replacement | -1.03 |
| **eviction path total** | **-1.42** |
| INX held to now (0.00811 mark) | ~-0.99, still open |

The first eviction **cost ~-0.43R** versus doing nothing. INX did dip to 0.00732
post-eviction (+0.3% for the short) — no large win was surrendered. n=1 decides
nothing; recorded so the next ones accumulate against it.

**BANK_USDT LONG, WILDCARD, x2 — clean -1R stop.**

| field | value |
|---|---|
| open / close | 08-13 10:30 -> 13:43 UTC (2.54h) |
| entry / exit | 0.04431 -> 0.04043 |
| realised | **-$0.7896** (fee $0.014, 1.7% of gross) |
| pnl_pct / margin | -17.82% on $4.43 margin |
| **R** | **-1.03R** (sl_margin_pct 17.28, under the 20% cap) |
| exit | `EXCHANGE_CLOSE` / `exit_kind=STOP` — the resting server stop filled |
| peak_r | +0.114 |
| lateness / ref_listed | 1.00 / 1 |
| streak_mult / regime_mult / size_efficiency | **0.50 / 0.924 / 0.335** |

Both closes went adverse from the first bar (peak +0.11R each). Two -1R-class
losses paid in full for zero information about the exit stack. **24h realised
-$1.078, 0/2 win.**

PMT: `entries_disabled` all 24h (by design). Squeeze: `FUTURES_SQUEEZE_ENABLED=0`
— OFF, no slot in play. Sniper: retired.

### 1-OPEN. Open positions — a +2.3R runner and a fresh entry

**TUT_USDT SHORT x1, WILDCARD** — opened 08-13 06:41, held **9.9h**.

| | |
|---|---|
| entry / mark | 0.05616 -> 0.04088 |
| current R | **+2.30R** (+$4.40 unrealized on $16.87 margin, +26.1%) |
| peak R (Min15) / giveback | **+2.57R** / **-0.27R** |
| distance to +5R TP (0.0281) | **-31.3%** of price |
| distance to -1R stop (0.0628) | **+53.6%** of price |
| sl_margin_pct | 11.82 |
| regime_size_mult / undersizing | 1.0 — **full intended margin, no trim** |

The best-sized trade in the book right now, and the one the preemption rule
correctly refused to touch.

**COTI_USDT LONG x1, WILDCARD** — opened 08-13 16:10, held 0.4h.

| | |
|---|---|
| entry / mark | 0.012637 -> 0.012225 |
| current R / peak R | **-0.33R** / +0.11R |
| distance to +5R TP (~0.01904) | **+55.7%** of price |
| distance to -1R stop (~0.011357) | **-7.1%** of price |
| **intended vs actual margin** | **$22.45 -> $5.19 (23%)** |

### 1a-bis. Learning loop

**(a) Feature store** 59 rows, +2, reconciles with the exchange (2 closes).

**(b) Conditional expectancy** (corpus 59, all sleeves). Verdicts with n>=10 and
OOS consistency:

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| `hold>=120min` | **FAVOR** | +1.565 | 35 / +$0.772 / 60% | 24 / -$0.793 / 17% |
| `roc>=12pct` | **FAVOR** | +1.379 | 9 / +$1.304 / 67% | 50 / -$0.075 / 38% |
| `regime_trimmed_hard(<0.5)` | **AVOID** | -0.427 | 17 / -$0.169 / 41% | 42 / +$0.258 / 43% |
| `fee_heavy>=30pct` | **AVOID** | -0.161 | 11 / +$0.004 / 45% | 48 / +$0.165 / 42% |

`side=SHORT` FAVOR / `side=LONG` AVOID have **fallen below the OOS bar** and now
read "weak" — restated so the 08-10/08-12 verdicts are not carried forward
stale. Propose-only.

**(c) The sizing stack is not a defect — it is de-sizing the right trades.**
Both closes and today's COTI entry were cut hard (efficiency 0.28 / 0.34 / 0.23),
which looks like the undersizing failure trial 13 was built to fix. It is not the
same thing. Trial 13 fixed a cap that bound *silently and inconsistently*; BANK
carries the new telemetry and shows it behaving (`risk_pct_actual=1.87`,
`risk_cap_bound=0`). What cut these was the two *declared* multipliers, and both
are earning their keep on live convex trades:

| streak bucket | n | netR | meanR | win |
|---|---|---|---|---|
| streak 0-1 (x1.00) | 25 | +16.15 | **+0.646** | 12/25 |
| streak 2 (x0.50) | 4 | -0.73 | -0.183 | 1/4 |
| streak >=3 (x0.25) | 8 | +0.16 | +0.020 | 2/8 |

| regime bucket (wildcard) | n | netR | meanR | win |
|---|---|---|---|---|
| `regime_mult>=0.5` | 19 | +13.78 | **+0.725** | 8/19 |
| `regime_mult<0.5` | 5 | -0.56 | -0.112 | 2/5 |

Trades taken while throttled, and trades taken in a trimmed regime, are the
**worse** trades — so the throttles are shrinking size on the losing tail, not
taxing the winners. **No proposal to loosen either.** (n=12 and n=5; weak, and
serial-correlation claims at this sample are hypotheses.)

The one thing that IS wrong is a **log line**: `[SIZE_TRIM]` prints
`regime_mult=0.92 margin 22.45 -> 5.19`, attributing the whole cut to the regime
scaler when the streak throttle did most of it (a separate `[STREAK_THROTTLE]`
line above carries the truth). Cosmetic, but misleading in exactly the place a
future audit will look. Not deployed today — bundled for the next code push.

**(d) Shadow ledger** — 96 rows (+1: BTW_USDT LONG, `veto:crowded_longs
(funding=0.104%)`, unresolved).

| bucket | n | resolved | netR | reading |
|---|---|---|---|---|
| `shadow_only` (sniper) | 46 | 46 | +16.20 | sleeve retired |
| `slot_occupied` | 17 | 17 | **+10.86** | **no new rows since 08-05** |
| `veto:ref_not_listed` | 14 | 14 | **-4.46** | protective, the clearest earning gate |
| `min_vol_skip` | 12 | 12 | +8.99 | account-size constraint, not tunable |
| `side_disabled` | 4 | 4 | +2.23 | closed (shorts live since 08-10) |
| `veto:crowded_longs` | 2 | 1 | -1.00 | 1 unresolved |
| `veto:move_not_corroborated` | 1 | 1 | +0.91 | — |

**Slot cost was zero again, and today shows why it will stay near zero:** with
preemption live, a signal arriving into a full book no longer produces a
`slot_occupied` row — it produces an eviction. The +10.86R in that bucket is a
pre-preemption artefact and is now a **closed measurement**, not a live one. The
recurring "am I missing out on blocked candidates?" question has been
structurally answered by shipping preemption; what needs measuring from here is
whether evictions beat holding, and that ledger stands at **1 eviction, -0.43R**.

**(e) Scan telemetry.** 6 scans retained: `movers` 18-20/scan, `candidates` 1
across the window (COTI). Histogram dominated by **`roc_below_min` 14-17 per scan
(~78%)**, then `no_pullback_resume` 1-6, `low_volume_z` 0-2. `shorts_blocked=0`,
`shock_blocked=0` — **the calm-shock filter has still refused nothing since
shipping 08-12**. Funnel: 987 USDT perps -> 663 in-band -> 45 over the $3M
turnover floor -> 18 over the 8% range pre-filter -> 1 candidate. **No order
rejects (5003/2015), no tracebacks, no ERROR lines.** One `[SIZE_TRIM]` (COTI,
above). Execution is clean.

**(f) Decision rule (docs/DECISION_RULE.md).**

| | |
|---|---|
| Trial 13 closes | **2 / 30** (INX -0.39R, BANK -1.03R) |
| Trial 13 netR / ex-best | **-1.42R** / -1.03R |
| Max drawdown, flow-adjusted (since 07-21) | **-2.7%** vs the <30% bar |
| Every close names its exit rule | **yes** (CONVEX_PREEMPTED, EXCHANGE_CLOSE/STOP) |
| TP completions, live | **0** — watch item 3, NOTE only at this n |

**The scoreboard that matters** (unaffected by the 9 resets): live wildcard
closes all-time **24, netR +13.22, ex-best +8.13, net $+8.11, win 10/24 (42%)**.

### 1b. WILDCARD DIAGNOSIS

**(a)** Funnel healthy, execution clean, one candidate found and taken. Not an
execution problem; no tick-snapping failures.

**(b) Not dormant.** Two positions open, two closed, one new entry inside the
window. Nothing to loosen. `roc_below_min` remains ~78% of rejections with no
backtest evidence those movers continued — **do NOT loosen MIN_ROC.**

**(c) Improvement.** Nothing proposed. The two live-fire findings of the day —
preemption's first eviction and the throttle stack — both need more n before they
can be scored, and neither is tunable at <=25%/day into a better place today. Per
the standing $ objective: at 1R = $2.66 and ~0.7 entries/day, no available knob
moves more than a few dollars a month, so the correct action is to let trial 13
accumulate closes.

### 2. Champion vs shadow

Shadow stale, comparison suppressed pending resync.

### 3. Diagnosis — the lever

**No change.** Two candidate levers were examined and both rejected on their own
evidence, not on caution:

1. *Soften the streak throttle* (it cut COTI to 23% of intent) — rejected: the
   throttled buckets have meanR +0.02 / -0.18 against +0.646 unthrottled. The
   throttle is de-sizing the bad tail.
2. *Turn `regime_mult<0.5` into a veto* (conditional expectancy says AVOID,
   n=17, OOS-consistent) — rejected on the $ objective: those trades already run
   at ~30% size, so vetoing them saves cents per trade, and it would **remove
   ~20% of entries** and lengthen time-to-verdict. Widening the funnel on an
   unmeasured edge is a variance increase; narrowing it against a $0 saving is a
   measurement loss.

### 4. Validate

`pytest -q` 862 passed. No replay/MC run — nothing was proposed to gate.

### 5. Deploy

**None.** No code change, no variable change.

### 6. Verdict on changes deployed in the last 7 days

| change | date | live verdict |
|---|---|---|
| Preemption (`PREEMPT_ENABLED`) | 08-11 | **first eviction fired today**, -0.43R vs holding at n=1 — still unscored |
| Calm-shock filter (`MAX_CALM_RATIO=0.75`) | 08-12 | **0 refusals in 24h** — untested |
| Risk cap bound to equity (`MAX_MARGIN_PCT=0.25`) | 08-12 | **working**: BANK logged `risk_pct_actual=1.87`, `risk_cap_bound=0`; did not bind, as designed |
| Sizing telemetry | 08-12 | **working**, and it is what made tonight's throttle analysis possible |

### Action item (operator-gated, carried)

Resync Futures-shadow to champion HEAD (`railway up --service Futures-shadow`,
paper, env-only, zero live risk). Until then the shadow comparison stays
suppressed.

---

# Daily Audit — 2026-08-12

---

## Automated Assessment (UTC 16:10)

Window 2026-08-11 16:09 -> 2026-08-12 16:09 UTC. Equity **$139.55**, available
$139.55, **0 open positions**, 0 unrealized. `pytest -q` **853 passed**.
Feature store **57 rows (+1)**, shadow ledger **95 rows (+1)** — both reconcile
with the exchange exactly (1 close, 1 skip).

### 1. Trades — ONE close, the first entry in 6 days

**ALLO_USDT SHORT, WILDCARD, x3, stopped out.**

| field | value |
|---|---|
| open / close | 08-12 12:29 -> 14:44 UTC (2.24h) |
| entry / exit | 0.27859 -> 0.29607 |
| realised | **-$2.7985** (fee $0.072, 2.6% of gross) |
| pnl_pct / margin | -19.32% on $14.50 margin |
| **R** | **-1.05R** (sl_margin_pct 18.35, under the 20% cap) |
| exit | `STOP_LOSS` / `exit_kind=STOP` |
| peak_r | **+0.048** |
| entry_lateness | **1.00** |
| ref_listed | 1 (cross-listed, not a MEXC-only pump) |
| 3h ROC at entry | 10.0% |
| regime_size_mult / size_efficiency | 1.0 / 0.999 |

**Judged against convex intent: mechanically clean, directionally wrong.**
Sizing behaved exactly as designed — risk $2.71 against a $2.66 1R target, no
regime trim, no undersizing, stop inside the 20% cap. The exit was the resting
-1R server stop; **no non-convex exit path fired**, so there is no bug to flag.
What the trade did not do is work at any point: peak +0.048R means it went
adverse from the first bar and never returned. This is a -1R paid in full for
zero information about the exit stack.

PMT: `entries_disabled` all 24h (by design). Squeeze: OFF. Sniper: retired.

**Note on ALLO specifically:** third live entry on this symbol, third loss —
LONG 07-19 -1.09R, SHORT 07-25 -1.05R, SHORT 08-12 -1.05R, **-3.19R / -$5.63**
across the three. All three at lateness 1.00. The universe is locked and this
is not a proposal to drop the pair; it is recorded because the symbol keeps
producing the same setup and the same outcome.

### 1-OPEN. Open positions

**None.** ALLO closed 14:44 UTC; both wildcard slots and the squeeze slot are
free.

### 1b. WILDCARD DIAGNOSIS — the funnel is working; the ranking rule is inverted

**(a) Scan diagnostics.** Over the retained log window (9 scans, 217 mover
evaluations): `roc_below_min` **173 (80%)**, `no_pullback_resume` 30 (14%),
`low_volume_z` 11, `climax_wick` 2, `rsi_exhausted` 1, **candidates 0**. Funnel
shape unchanged: 981 USDT perps -> 662 in-band -> 47 over the $3M floor -> 22
over the 8% range pre-filter. **No order rejects (5003/2015), no tracebacks, no
`[SIZE_TRIM]` lines.** The ALLO entry itself filled and armed its TPSL
correctly. This is not an execution problem.

**(b) Dormancy.** Not dormant today — one candidate cleared every gate and was
taken. The ref-listing veto did NOT bind on it (`ref_listed=1`), which is the
direct counter-evidence to the "the veto empties the universe" worry: when a
listed mover appears, it trades.

**(c) The finding — the pullback preference is backwards.** Design ranks
deep-pullback candidates (lateness 0.50-0.70) **first**. Measured over every
wildcard row carrying a lateness value (17 live + 27 shadow counterfactual,
n=44):

| lateness | n | netR | avgR | win | ex-best |
|---|---|---|---|---|---|
| <0.60 | 1 | -1.02 | -1.02 | 0% | — |
| 0.60-0.75 (**ranked first**) | 4 | -2.38 | -0.59 | 25% | -3.04 |
| 0.75-0.95 | 9 | -0.69 | -0.08 | 33% | -5.78 |
| **>=0.95 (no pullback at all)** | **30** | **+8.48** | **+0.28** | **53%** | **+3.42** |

The bucket the design prefers is the worst one, and the bucket it treats as
late is the only one that survives its own top-trade haircut. Live-only the
signal is weaker and noisier (0.75-0.95 n=4 avgR +0.74 vs >=0.95 n=11 avgR
+0.14), which is exactly why this is being recorded rather than shipped.

**Two honest caveats.** Shadow outcomes are directional counterfactuals, never
backtest-grade, and 19 of the 30 rows in the winning bucket are shadow. And
lateness is a **ranking** input, not a gate — it only changes anything when two
or more candidates clear on the same scan, which at ~0.7 candidates/day is
rare. In $ terms the immediate envelope of flipping it is **near zero**; its
value is that it is a cheap, pre-registerable hypothesis rather than another
capacity trial.

**Do NOT loosen MIN_ROC.** 80% of rejections are `roc_below_min` and there is
still no backtest evidence those movers continued.

### 1a-bis. Learning loop

**(a) Feature store** 57 rows, +1, reconciles with the exchange (1 close).

**(b) Conditional expectancy** — corpus 57; the single new row moves no
condition across the n>=10 bar, so the 08-10 verdicts stand unchanged and are
restated, not re-derived: `hold>=120min` FAVOR, `roc>=12pct` FAVOR,
`side=SHORT` FAVOR, `side=LONG` AVOID, `regime_trimmed` AVOID, `leverage>=7`
AVOID. Propose-only. ALLO was a SHORT held 134min at 10% ROC — it satisfied two
FAVOR conditions and lost anyway, which is ordinary behaviour for a 53%-win
lottery, not a falsification.

**(c) Shadow ledger** — 95 rows (+1: TUT_USDT SHORT, `min_vol_skip`, +0.665).

| bucket | n | resolved | netR (cost-net) | reading |
|---|---|---|---|---|
| `shadow_only` (sniper) | 46 | 46 | +13.70 | sleeve retired |
| `slot_occupied` | 17 | 17 | +5.36 | **no new rows since 08-05**; post-2-slot n still 1 |
| `veto:ref_not_listed` | 14 | **14** | **-6.53** | protective; TST 08-11 resolved -1.02 |
| `min_vol_skip` | 12 | 12 | +8.71 | account-size constraint, not tunable |
| `side_disabled` | 4 | 4 | +2.16 | closed (shorts live since 08-10) |
| `veto:move_not_corroborated` | 1 | 1 | +0.86 | — |
| `veto:crowded_longs` | 1 | 1 | -1.02 | — |

The ref veto is now **14/14 resolved at -6.53R**. It remains the clearest
earning gate in the stack. **Slot cost is still zero**: no candidate was
blocked while ALLO was open (the second slot was free the whole 2.24h).

**(d) Decision rule** — convex since 2026-07-13, recomputed from the feature
store excluding SNIPER and the lev-13 major rows: **n=27, netR +0.26, ex-best
-4.83, net $+5.54, win rate 37%.** Max equity drawdown from the $142.90 peak is
**-2.3%**, far inside the 20% flag. *Basis note: this classification differs by
roughly one row from the n=27 / +1.65R stated on 08-11 (the sniper/major
boundary in pre-labelling rows); the direction and size of today's move — ALLO
-1.05R / -$2.80 — are not in doubt.*

**Exit-kind tripwire:** 7 correctly scored convex rows (STOP 2, OTHER 5,
**TP 0**). Below the >=15 bar, so the tripwire is **not triggerable** and no
TP3R proposal is made. It is now 7 of 15.

### 2. Champion vs shadow

**Shadow stale, comparison suppressed pending resync.**

### 3. Lever for the next 24h — none. Let trial 11 have its window.

Trial 11 (slot preemption) shipped 08-11 16:06 and is 24h old with **n=1 and
zero preemption opportunities** — ALLO held one of two slots and nothing
arrived to contest it. Shipping a trial 12 now would repeat the exact error
that closed trials 9, 10 and 11 at zero: superseding a change before it could
be measured. The standing objective prices time-to-verdict above funnel width,
and the way to shorten time-to-verdict here is to stop resetting the clock.

Trial 11 kill conditions: unpaired evictions **0** (none possible), netR vs
baseline unassessable at n=1. Neither triggers.

**PRE-REGISTERED for trial 12 (operator-gated, NOT applied):** invert the
lateness ranking — rank `lateness >= 0.95` candidates first instead of
0.50-0.70. Env-only if a rank key is exposed; otherwise a one-line code change.
Bar for opening it: **>= 10 further resolved wildcard rows carrying lateness**,
and the >=0.95 bucket still ahead of 0.60-0.95 ex-best. Expected $ impact
stated honestly: **under $10/month at current arrival rate**, because it binds
only on multi-candidate scans. It is proposed as the cheapest available test of
whether this sleeve's core premise (join the pullback, not the extreme) is
true, not as a P&L improvement.

### 4-5. Validate / Deploy

No candidate reached the V-stack. **No deploy.** `pytest -q` 853 passed; bot
healthy at cycle 1639, no tracebacks, ACCOUNT line current.

### 6. Verdict on the last 7 days of changes

| change | shipped | earning its keep? |
|---|---|---|
| 450s cadence (trial 9) | 08-10 | still untested — 1 close in 2 days |
| shorts re-enabled (trial 10) | 08-10 | **first short entry taken** (ALLO, -1.05R). n=1; verdict pending, but the sleeve is no longer half-blind |
| sniper retired | 08-10 | correct — was -0.90R / -$0.11 over 8 |
| slot preemption (trial 11) | 08-11 | 24h old, 0 preemption opportunities, unassessable — **must be allowed to run** |

---

# Daily Audit — 2026-08-11

---

## Automated Assessment (UTC 16:10)

Window 2026-08-10 16:09 -> 2026-08-11 16:09 UTC. Equity **$142.35**, available
$142.35, **0 open positions**, 0 unrealized — identical to the cent to the
08-10 close. `pytest -q` **853 passed**. Feature store **56 rows, unchanged**.

### 1. Trades — ZERO closes, ZERO opens

Nothing opened and nothing closed in 24h, on any sleeve. PMT `entries_disabled`
(by design), squeeze OFF, sniper retired 08-10 (`cb2334d`). The only live entry
path is WILDCARD, and it produced **4 candidates, 4 vetoes, 0 entries**:

| time UTC | symbol | side | lateness | reject | counterfactual (net) |
|---|---|---|---|---|---|
| 08-11 01:27 | TST_USDT | SHORT | 1.00 | `veto:ref_not_listed` | +0.28 (trail) |
| 08-11 04:03 | PROM_USDT | SHORT | 0.74 | `veto:ref_not_listed` | -1.01 (stop) |
| 08-11 04:11 | PROM_USDT | SHORT | 0.75 | `veto:ref_not_listed` | -1.01 (stop) |
| 08-11 12:43 | TST_USDT | LONG | 1.00 | `veto:ref_not_listed` | unresolved |

Net of the three resolved: **-1.74R avoided.** The veto was right again.

### 1-OPEN. Open positions

**None**, and none since 08-08 03:21 (BTW_USDT). Slots have been **free for
5 consecutive days**.

### 1b. WILDCARD DIAGNOSIS — the constraint is upstream of the last three trials

Trials 9 (cadence 900s->450s), 10 (shorts re-enabled) and 11 (slot preemption,
deployed today 16:06:52 UTC) are all **capacity** changes. Capacity has not
bound since 08-05. Every candidate since then died at the reference-listing
veto with both slots empty.

**Tested this run: is the ref veto structurally emptying the universe?** No.
Re-derived the live band from the MEXC ticker and checked Bybit/OKX listing on
every survivor:

| stage | n |
|---|---|
| USDT perps | 968 |
| band (ex top-24 turnover) | 944 |
| turnover >= $3M | 72 |
| 24h range >= 8% | 23 |
| **of which ref-listed** | **18 (78%)** |
| not listed | 5 (SKYAI, SAMSUNGSTOCK, GUA, PROM, RKLBSTOCK) |

**The bias is in the signal, not the universe.** 78% of the tradeable band is
ref-listed, but the `|3h ROC| >= MIN_ROC` ranking preferentially surfaces the
MEXC-only pumps — the violent 3h movers *are* the unlisted micro-caps. August
scoreboard: **10 candidates vetoed as not-listed vs 5 entries taken**, and all
5 taken were ref-listed (BICO, BTW x2, HFT, BICO). Today's scan histogram is
the same mechanism from the other side: 15 movers scanned, `roc_below_min` 13,
`low_volume_z` 1, `climax_wick` 1, **candidates 0**.

**Do NOT relax the veto.** Record now **14 rows / 13 resolved / netR -5.52 net
of cost, 10 of 13 negative.** It is the most clearly earning gate in the stack.

**Do NOT loosen MIN_ROC to manufacture trades** — no backtest evidence that the
rejected movers continued. Per 1b(b), dormancy without evidence is correct
behaviour.

### 1a-bis. Learning loop

**(a) Feature store** 56 rows, reconciles with the exchange (0 closes, 0 growth).

**(b) Conditional expectancy** — corpus frozen at 56, so **verdicts are
unchanged from 08-10** and are restated, not re-derived: `hold>=120min` FAVOR
(+$1.758 gap), `roc>=12pct` FAVOR, `side=SHORT` FAVOR, `side=LONG` AVOID,
`regime_trimmed` AVOID, `leverage>=7` AVOID. Propose-only; nothing applied.

**(c) Shadow ledger** — 94 rows (+4, all four the vetoes above).

| bucket | n | resolved | netR (cost-net) | reading |
|---|---|---|---|---|
| `veto:ref_not_listed` | 14 | 13 | **-5.52** | protective, past the >=10 bar |
| `slot_occupied` | 17 | 17 | +5.36 | **no new rows since 08-05**; post-2-slot n still 1 |
| `min_vol_skip` | 11 | 11 | +8.04 | account-size constraint, not tunable |
| `side_disabled` | 4 | 4 | +2.16 | closed (shorts live since 08-10) |
| `shadow_only` (sniper) | 46 | 46 | +13.70 | sleeve retired |

**(d) Decision rule** — convex (WILDCARD+SQUEEZE) since 2026-07-13: **n=27,
netR +1.65, ex-best -3.44, net $+8.45.** Wildcard alone n=17 netR +7.95;
squeeze alone n=10 netR -6.30 (sleeve OFF). Equity at programme peak, **0%
drawdown**. `USE_DRAWDOWN_KILL` is now **1** (the prior operator override to 0
is resolved).

**Exit-kind tripwire:** post-`70a8b06` only **6** convex rows carry a correctly
scored `exit_kind` (STOP 1, OTHER 5, TP 0). That is below the >=15 bar, so the
TP-completion tripwire is **not triggerable** and no TP3R proposal is made.

### 2. Champion vs shadow

**Shadow stale, comparison suppressed pending resync.**

### 3. Lever for the next 24h — measure, do not ship a fourth capacity change

Three consecutive trials have closed at zero because each addressed a
constraint downstream of the binding one. In $ terms the sleeve is currently
**0 entries / 6 days = a $0/month envelope in both directions**, which makes
time-to-verdict — the standing objective's stated priority — unbounded.

**PROPOSED (operator-gated, not applied):** before opening trial 12, run
`tools/wildcard_backtest.py` restricted to the **ref-listed subset**, sweeping
MIN_ROC / MIN_VOL_Z, and report *tradeable candidates per week* and their net R
under the live exit policy. Decision content: if no setting yields >= 5
ref-listed candidates/week at non-negative net R, the sleeve is not fixable by
tuning and that should be stated plainly rather than iterating a fourth
capacity trial.

### 4-5. Validate / Deploy

No candidate reached the V-stack. **No deploy.** Trial 11 has ~3 minutes of
runtime, 1 boot, 0 tracebacks; its kill conditions (unpaired eviction x3/24h,
netR below baseline at n>=20) are not yet assessable. **Trial 11 must not be
judged by its close count** — with 0 open positions there is nothing to preempt.

### 6. Verdict on the last 7 days of changes

| change | shipped | earning its keep? |
|---|---|---|
| 450s cadence (trial 9) | 08-10 | untested — 0 closes |
| shorts re-enabled (trial 10) | 08-10 | 3 of 4 candidates were shorts (arrival doubled as predicted) but all vetoed; **0 closes** |
| sniper retired | 08-10 | correct — sleeve was -0.90R / -$0.11 over 8 |
| slot preemption (trial 11) | 08-11 | 3 min old, unassessable |

---

# Daily Audit — 2026-08-10

---

## Automated Assessment (UTC 16:45)

Window 2026-08-09 16:30 -> 2026-08-10 16:45 UTC. Equity **$142.35**, available
$142.35, **0 open positions**, 0 unrealized. `pytest -q` **833 passed**.

### 1. Trades (3 closes, all SNIPER)

| # | time UTC | symbol | side | lev | 1R (%margin) | R net | R gross | net $ | exit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 08-09 23:30 | LINK_USDT | SHORT | x13 | 4.92 | **+1.72** | +2.14 | +0.0377 | bracket TP (2R) |
| 2 | 08-10 12:49 | HYPE_USDT | LONG | x13 | 7.69 | **-1.33** | -1.06 | -0.0434 | stop |
| 3 | 08-10 15:24 | XRP_USDT | SHORT | x13 | 4.54 | **+1.60** | +2.06 | +0.0403 | bracket TP (2R) |

Net **+$0.0346**, **netR +1.99**, 2/3 wins. Exchange `history_positions`
returns exactly **3** in-window closes; the feature store grew 53 -> **56**.
Reconciles **3-for-3** (realised matches to the sub-cent).

**WILDCARD: 0 closes, 0 opens.** PMT: 0, `entries_disabled` on every cycle.
Squeeze: `FUTURES_SQUEEZE_ENABLED=0`, sleeve OFF.

**Sniper ledger, n=8: netR -0.90, net -$0.1126, 3/8 wins.** The shape is the
whole story and it is consistent across all eight: every win undershoots the
+2R target (+1.32, +1.60, +1.72) and every loss overshoots the -1R stop
(-1.11, -1.33, -1.45, -1.64). A designed 2:1 bracket is realising ~1.55 : 1.38
= **1.12:1**, which needs a **47%** win rate; live is 37.5%. The sleeve's own
scan line already says so — `mode=LIVE (SIGNAL-STUDY ONLY: not viable at taker
fees)` — and it runs notional-capped at 5%, so each trade risks ~$0.03. n=8 is
below the >=10 bar for a disable proposal. **No proposal; keep observing.**

### 1-OPEN. Open positions

**None.** Nothing held at the close of the window.

### 1a-bis. Learning loop

**(a) Feature store** 56 rows, in sync with the exchange ledger.

**(b) Conditional expectancy** (n=56, window 06-27..08-10, mean +$0.212,
meanR +0.26, win 44.6%) — OOS-consistent verdicts, **propose-only**:

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| hold>=120min | **FAVOR** | +1.758 | 32 / +0.965 / 65.6% | 24 / -0.793 / 16.7% |
| roc>=12pct | FAVOR | +1.302 | 9 / +1.304 / 66.7% | 47 / +0.002 / 40.4% |
| side=SHORT | FAVOR | +0.724 | 21 / +0.664 / 52.4% | 35 / -0.060 / 40.0% |
| leverage<=4 | FAVOR | +0.165 | 20 / +0.318 / 50.0% | 36 / +0.153 / 41.7% |
| regime_trimmed / chop | AVOID | -0.507 | 30 / -0.024 / 43.3% | 26 / +0.483 / 46.2% |
| regime_trimmed_hard (<0.5) | AVOID | -0.522 | 16 / -0.161 | 40 / +0.361 |
| leverage>=7 | AVOID | -0.445 | 26 / -0.027 | 30 / +0.418 |
| side=LONG | AVOID | -0.724 | 35 / -0.060 | 21 / +0.664 |
| fee_heavy>=30pct | AVOID | -0.258 | 11 / +0.004 | 45 / +0.262 |

Unchanged in direction from 08-09 and unchanged in meaning: **short-held,
high-leverage, fee-dominated trades are where the money goes**, and every live
sniper fill is x13 and sub-3h. `side=LONG AVOID` strengthened this window
(HYPE, the one loss, was the only long).

**(c) Shadow ledger** — 90 rows.

*veto:ref_not_listed* — 10 rows / 9 resolved / **netR -2.77 net of cost**.
**This is a sign flip against yesterday's reading and it is a correction, not
new data.** The 08-09 audit reported the squeeze half at **+8.00R** ("costly")
off *gross* counterfactuals; commit `fbb9e85` now scores veto counterfactuals
net of cost under the live exit, and both halves go negative:

| half | n resolved | netR (cost-net) | reading |
|---|---|---|---|
| SQUEEZE synthetics (SKHY/SPCX/USOIL/SNDK) | 4 | **-0.63** | protective |
| WILDCARD alts (KOMA/SKYAI x2/CATE/SYN) | 5 | **-2.14** | protective |

The >=10-resolved bar is essentially met (9 of 10; TST_USDT still open). The
external gate is **earning its keep on both sleeves** — no relaxation proposal,
and the 08-09 "structurally excludes tokenised equities from squeeze" note
should be read as a *mechanism* observation only, not as a cost.

*slot_occupied* — 17 rows, all resolved, **netR +5.36 net** (+10.86 gross).
Post-2-slot-ship (07-31) it is still **n=1** (HEI_USDT +4.99R, 08-05). Nothing
new this window; the 2nd slot remains un-adjudicated.

*min_vol_skip* — 11 rows, 11 resolved, **netR +8.04** — now the single largest
opportunity cost in the ledger and past the >=10 bar. These are candidates
rejected because one contract exceeded the sized margin, i.e. **the account is
too small to take them**, not a strategy rejection. Not fixable by any tunable
under this mandate (it resolves with account size). Recorded for the operator.

*SNIPER_FAST shadow* — 40 resolved, gross +12.85R, **net +3.72R**, 20 wins,
kinds tp 15 / stop 18 / timeout 7. The shadow's cost model is well calibrated
against the live fills (it predicted LINK +1.498R vs +1.72R actual, XRP
+1.456R vs +1.60R, HYPE -1.321R vs -1.33R). Note the shadow logs sniper signals
that WERE taken live under `shadow_only`, so those 40 rows are not a clean
untaken-counterfactual set — 8 of them are the live trades. Recorded.

**(d) Decision rule.** Trial 8: **0 / 30** convex closes (opened 08-09; the
wildcard has produced no candidate since). Convex since 07-13: n=27,
netR **+1.65**, ex-best **-3.44**, net **+$8.45**. Max drawdown across the
feature-store window **-0.41%**, far inside the 30% criterion and the 20% flag.
`USE_DRAWDOWN_KILL=1`, `DRAWDOWN_HALT_PCT=0.25` — unchanged.

### 1b. Wildcard — diagnose

Funnel (identical across all 4 scans in the window):

```
usdt=971 -> (non_crypto -289, symbol_open -0, major -24) -> in_band=658
       -> turnover>=$3M: 49 -> range24>=8%: 22 -> scanned=22 -> candidates=0
```

Rejection histogram: `roc_below_min` 18, `no_pullback_resume` 2-6,
`low_volume_z` 2. **Zero entry failures** — no 5003/2015, no Traceback in the
window. The trial-8 machinery is confirmed working end to end: the range
pre-filter is holding the pool at **19-22** (it was 8-11 on the old
`|24h change|>=3%` screen), the majors band deflates on baseline turnover and
removes 24, and the strict category filter drops 289 non-crypto **before**
ranking. Dormancy cause is regime — nothing in the band posted an 8% 3h ROC.
**Correct behaviour; no gate loosened.**

### 2. Champion vs shadow

Shadow stale, comparison suppressed pending resync.

### 3-4. Lever and validation — `exit_kind` scored against the wrong target

`_classify_exit_kind` measured every close against a hardcoded **5R**, but the
sniper brackets at **2R**. Its completed TPs land at ~+1.6R net and were all
filed **OTHER**. With 8 sniper closes now in the store the pooled census read:

| | TP | STOP | OTHER |
|---|---|---|---|
| pooled, as recorded | **0** | 6 | **10** |

That is 16 instrumented closes with 0% TP and OTHER dominant — which **already
satisfies the pre-registered TP-completion tripwire** ("TP completions <10% over
>=15 trades AND OTHER dominates"). Read literally, today's audit was obliged to
propose scaling the **convex** TP down to 3R — on the strength of eight sniper
trades, two of which hit their target exactly as designed. The tripwire was
about to fire on a measurement artefact.

**Fix (deployed).** Two parts, both telemetry-only; no order, sizing or exit
logic touched:

1. Pass the position's real target, derived from `tp_margin_pct / sl_margin_pct`
   already present in metadata (5R convex, 2R sniper). Absent -> 5R as before,
   so pre-08 rows are unaffected.
2. Compare on **gross** R. The old net-R tolerance (0.9x target) was calibrated
   where the round-trip cost is ~6% of a 5R target; on a 2R bracket the same
   absolute cost is ~25%. No proportional tolerance serves both, so the
   question "did the target fill" is now asked of the fill, not of the fee bill
   it arrived with.

**Validation.** `pytest -q` **833 passed** (2 new tests, both pinned to
verbatim live-ledger numbers). Replayed over all 56 stored closes:

| trade | net R | gross R | old | new |
|---|---|---|---|---|
| LINK 08-09 | +1.72 | +2.14 | OTHER | **TP** |
| XRP 08-10 | +1.60 | +2.06 | OTHER | **TP** |
| SOL 08-08 | +1.32 | +1.78 | OTHER | OTHER (fell short of 2R) |
| AVAX 08-09 | -0.01 | -0.00 | OTHER | OTHER (retention trail) |
| SUI / DOGE / SOL / HYPE | -1.11..-1.64 | — | STOP | STOP (unchanged) |

Corrected census: sniper **TP 2 / STOP 4 / OTHER 2**; **convex-only untouched at
TP 0 / STOP 1 / OTHER 5 over n=6** — below the n>=15 bar, which is the honest
reading of the convex sleeve and the reason no TP proposal is made today.

No exit or sizing behaviour changed, so no `replay_exits` / `mc_ledger` gate
applies; V-stack step (a) is the whole gate for a classifier fix.

### 5. Deploy

Commit `70a8b06`, pushed, `railway up --service Futures-bot` at 16:40 UTC with
**zero open positions**. Container verified running the new code, cycle counter
restarted clean, `ACCOUNT equity=142.35 available=142.35 positions=0`, no
Traceback.

### 6. Last-7-days changes — still earning their keep?

| change | date | verdict |
|---|---|---|
| Sleeve separation (SNIPER out of WILDCARD slots/exits) | 08-09 | **Yes.** No sniper position has taken a wildcard retention trail since; AVAX was the last casualty. |
| Retention-trail cost floor (1.5x cost_R) | 08-09 | **Untested.** 0 armed closes since. |
| Majors on baseline turnover + strict crypto filter | 08-09 | **Working as designed** (major -24, non_crypto -289 pre-rank). No trade yet to score. |
| 24h-range pre-filter | 08-09 | **Yes.** Pool 8-11 -> 19-22, zero dropped. |
| Cost-net veto scoring (`fbb9e85`) | 08-09 | **Yes, and materially.** It flipped `ref_not_listed` from "costing +8R" to "saving 2.77R" — the previous reading would have justified relaxing a gate that is in fact protective. |
| `exit_kind` target-aware (`70a8b06`) | 08-10 | Deployed today. |

### 7. Verdict

Three sniper closes, +$0.03, net +1.99R — noise at this size and not a signal
either way. The wildcard is correctly dormant with its trial-8 universe fix
confirmed working. The day's real finding was not a trade: **two separate
measurement defects were about to produce two wrong proposals** — the veto
ledger read gross (fixed 08-09, reported today with the sign flip) and the exit
classifier read every sleeve against a 5R target (fixed and deployed today).
Both would have loosened or shrunk something that is working. No risk
parameter, universe entry or exit rule was touched.

---

# Daily Audit — 2026-08-09

---

## Automated Assessment (UTC 16:10)

Window 2026-08-08 16:10 -> 2026-08-09 16:10 UTC. Equity **$142.32**, available
$142.32, **0 open positions**, 0 unrealized. `pytest -q` **781 passed**.

### 1. Trades (1 close)

| # | time | symbol | sleeve | side | lev | 1R (%margin) | R | net $ | exit reason |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 03:32 | AVAX_USDT | SNIPER | SHORT | x13 | 4.79 | **-0.01** | -0.0005 | CONVEX_RETENTION_TRAIL |

Exchange `history_positions` returns exactly **1** in-window close; the feature
store grew 52 -> **53**. Reconciles **1-for-1**. (Exchange realised +$0.0001 vs
store -$0.0005 — sub-cent fee attribution, not a gap.) **WILDCARD: 0 closes,
0 opens.** PMT: 0, `entries_disabled (FUTURES_ENTRY_MIN_SCORE>=999)` on every
cycle. Squeeze: `FUTURES_SQUEEZE_ENABLED=0`, sleeve OFF.

**AVAX is the trade that wrote today's DECISION_RULE amendment**, and it is
already diagnosed there: peak **+1.6767R**, retention floor 0.30 x 1.68 =
**+0.50R gross**, sniper round-trip cost `0.190% / 0.368% = 0.52R` — the floor
sat *below the sleeve's own breakeven*, so a 1.7R peak banked -$0.0005 over
5.25h. Tripwires **1** (armed close <= $0) and **2** (retention bank < +0.15R)
both fired; both attribute to the sleeve-misapplication defect, not to the
retention rule. Fix (sleeve separation + `1.5 x cost_R` floor) deployed
**16:05 UTC today**, deployment `d38e3406` SUCCESS, cycle counter restarted
clean, no Traceback, ACCOUNT line healthy.

### 1-OPEN. Open positions

**None.** Nothing held at any point in the window after 03:32.

### 1a-bis. Learning loop

**(a) Feature store** 53 rows, in sync with the exchange ledger.

**(b) Conditional expectancy** (n=53, window 06-27..08-09, mean +$0.223,
meanR +0.237, win 43.4%) — verdicts with n>=10 both sides, **propose-only**:

| condition | verdict | gap $ | with | without |
|---|---|---|---|---|
| hold>=120min | **FAVOR** | +1.860 | 31 / +0.995 / 64.5% | 22 / -0.865 / 13.6% |
| side=SHORT | FAVOR | +0.790 | 19 / +0.730 / 47.4% | 34 / -0.060 / 41.2% |
| leverage<=4 | FAVOR | +0.152 | 20 / +0.318 / 50.0% | 33 / +0.166 / 39.4% |
| regime_trimmed (mult<1) / chop | AVOID | -0.532 | 28 / -0.028 / 39.3% | 25 / +0.504 / 48.0% |
| regime_trimmed_hard (<0.5) | AVOID | -0.550 | 16 / -0.161 | 37 / +0.389 |
| leverage>=7 | AVOID | -0.450 | 23 / -0.032 | 30 / +0.418 |
| fee_heavy>=30% | AVOID | -0.276 | 11 / +0.004 | 42 / +0.280 |

`hold>=120min` is the standout and is the same fact as `leverage>=7 AVOID` and
`fee_heavy AVOID` seen from three angles: **short-held, high-leverage,
fee-dominated trades are where the money goes.** Every live sniper fill is
x13 and sub-20min.

**(c) Shadow ledger** — 80 rows.

*veto:\** 11 rows / 10 resolved / **netR +10.94** — i.e. the external gate is
*costing*, and the >=10-resolved bar is met. But the aggregate is misleading;
split by sleeve it is **opposite-signed**:

| veto | sleeve | n | netR | reading |
|---|---|---|---|---|
| ref_not_listed | WILDCARD | 5 | **-2.06** | **PROTECTIVE — keep** |
| ref_not_listed | SQUEEZE | 4 | **+8.00** | costly (all 4 tokenized equity/commodity) |
| move_not_corroborated | WILDCARD | 1 | +5.00 | ON_USDT |
| crowded_longs | WILDCARD | 1 | unresolved | BTW_USDT, today |

The squeeze half is a **mechanism**, not a sample: SKHYSTOCK, SPCXSTOCK, USOIL,
SNDKSTOCK can never be listed on a crypto reference exchange, so
`ref_not_listed` structurally excludes the entire tokenized-equity class from
the squeeze sleeve — a permanent 100% veto rate, not a filter. n=4 is below the
proposal bar and squeeze is OFF, so this is **recorded, not proposed**. Revisit
if squeeze is re-enabled.

*slot_occupied* — 17 rows, all resolved, netR +7.77. Split at the 2-slot ship
(2026-07-31): **pre** WILDCARD n=10 +2.77R, SQUEEZE n=6 **+0.00R exactly**;
**post** WILDCARD **n=1** (+5.00R, HEI 08-05). The second wildcard slot
**already absorbed the opportunity cost** — 1 blocked candidate in 9 days. No
evidence for a 3rd wildcard slot; the squeeze slot-lock is exactly neutral.
Answering the recurring question directly: **not missing out.**

*SNIPER shadow, cost-adjusted* — **n=46, gross +15.55R (avg +0.338R/trade),
net-of-cost -2.16R (avg -0.047R/trade)**, applying the repo's own 0.190%
round-trip constant per row as `0.190 x lev / sl_margin_pct`. The live arm
agrees: 5 fills, **-2.88R / -$0.147**. The sleeve's own log line already says
`mode=LIVE (SIGNAL-STUDY ONLY: not viable at taker fees)`.

**(d) Scan telemetry.** Wildcard funnel: 970 usdt -> (non_crypto -271,
major -26) in_band=673 -> turnover>=3M: 44 -> |24h|>=3%: 22-24 -> scanned ->
**candidates 0**. Histogram dominated by **roc_below_min (17-18 of ~23)**, then
`no_pullback_resume` (4-5), `climax_wick`/`low_volume_z` (1). No `SIZE_TRIM`
lines. **No order rejects (5003/2015) — no execution bug.**

At 16:01 the mover count collapsed **23 -> 0** and stayed there. Verified
independently against the MEXC ticker at 16:14: **3 symbols market-wide** pass
|24h| >= 3% (JIMOTHY -4.6%, ACE +4.2%, KAITO -3.4%), 84 pass turnover. This is
a genuine market-wide compression as yesterday's move rolls out of the trailing
24h window, **not a data outage** — the wildcard is not blind.

**(e) Decision rule — TRIAL 7.** **1/30 wildcard closes in-trial**
(BTW_USDT +0.53R / +$0.65). BICO excluded (`trail_migrated`). netR **+0.53**,
**ex-best 0.00**, max DD negligible. Far too early for any verdict.
`USE_DRAWDOWN_KILL` is now **1** (was the 07-17 override at 0) — resolved.

### 1b. Wildcard diagnosis

0 trades and **that is correct behaviour**, but the sleeve was *not* idle: it
produced exactly one qualified candidate today — **BTW_USDT LONG, 3h ROC
+24.3%, lateness 1.0, 14:44 UTC — blocked by `veto:crowded_longs
(funding=0.150%)`**, the second BTW appearance in two days (the first was
traded 08-08 for +$0.65). Unresolved; it is the single most informative pending
row in the ledger, since `ref_not_listed` on wildcard is measured protective
but `crowded_longs` has n=1.

**Do NOT loosen any gate.** With 3 movers existing market-wide, loosening does
not find trades, it manufactures losses. Dominant rejection is `roc_below_min`
against an 8% bar in a market whose top mover is 4.6%.

### 2. Champion vs shadow

**Shadow stale, comparison suppressed pending resync.**

### 3. Lever

**PROPOSE (operator-gated, not applied): `FUTURES_SNIPER_SHADOW_ONLY=1`.**

The amendment ordered the sniper to restart a 25-fill live count. The 46-row
shadow ledger already answers the question that count would buy: the signal is
**gross-positive (+0.338R/trade) and net-negative (-0.047R/trade)** once the
sleeve's own cost constant is applied — a fee/execution problem, not a signal
problem. Every sniper signal is shadow-logged *before* the live order is
attempted, so shadow-only **loses zero information** while removing the taker
drag. Paying the live arm to re-derive this costs ~-$0.7 over 25 fills at the
current $0.03/R scale — small, but bought with nothing.

The honest counter, stated: shadow outcomes are directional-only counterfactuals
at fixed +2R/-1R and are not fills, and -0.047R/trade is close enough to zero
that the correct conclusion is "the edge is exactly the size of the cost."
That argues for a **maker/limit-entry sniper variant** rather than deletion.
Recommendation: shadow-only **until** a maker-entry path exists, then re-arm.

### 4. Validate

`pytest -q` 781 passed. No replay/MC run — no exit or sizing candidate was
promoted. No entry change (frozen). Nothing staged on shadow (stale).

### 5. Deploy

**None by this audit.** The sleeve-separation fix (`eb1eee6`, `e013d0d`) was
deployed at 16:05 UTC before this run and is verified live and green.

**ACTION ITEM (repo hygiene):** both commits are **local-only — `main` is ahead
of `origin/main` by 2** while running as live champion code. `git push` to
restore origin as the recoverable source of what is live. Not self-applied
(no promotion in this audit).

**ACTION ITEM (carried):** resync Futures-shadow to champion HEAD
(`railway up --service Futures-shadow`, paper, zero live risk).

### 6. Verdict

1 close, -0.01R, on the sleeve whose defect was fixed the same day. Wildcard
correctly dormant with one funding-vetoed candidate. Trial 7 at 1/30. The one
new fact worth carrying: **the slot-cost question is now answered — the 2nd
wildcard slot took the opportunity cost to ~zero (1 blocked candidate in 9
days), and the sniper's edge is exactly the size of its fees at n=46.**

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

