# WS1: Investment Research Playbook (from the futures bot, Apr-Nov 2026)

Authors: PM and Functional Lead, 2026-11-26. Status: draft for owner sign-off (decision WS1-D1 at the end).
Purpose: turn seven months of the futures bot into rules for any future strategy (Option B first). Use it as a checklist: no stage starts until the previous stage's boxes are ticked and filed.

## 1. What it cost to learn this

- Lifetime to 2026-10-06: $1,305.53 in, $715 out, **-$403.53, money-weighted -75.1% over 191 days**; fees $262.20 = 65% of the loss. The same cash flows in a T-bill fund made +$8.20; in BTC +$148 (`docs/DECISION_RULE.md:19545-19552`).
- Last 90 days to 11-26: 276 trades, -$185.57, profit factor 0.74 (`08_qa2.md` §2.1). Equity today $34.62.
- About 30 configurations in ~95 days; every trial's standard error was larger than its total (e.g. `docs/daily_audit.md:161`, `:290`). Two studies graded 42 rules: 0 A, 0 B (`DECISION_RULE.md:18774-18776`).

What we keep is the method, the tooling and the mistakes below.

## 2. Hard-won lessons

### Always
| # | Rule | Evidence |
|---|---|---|
| L1 | Check the venue and product are legal for the owner **before** any code. | UK listed as a MEXC Prohibited Jurisdiction and MEXC on the FCA Warning List; first recorded on 10-06, ~6 months in (`DECISION_RULE.md:19556-19558`; `02_architect.md`). |
| L2 | Work out what a working edge is worth in money at the real stake before starting. | At this size, +0.4R/trade was worth -$11 to +$22 a month (`DECISION_RULE.md:1-25`). |
| L3 | Pre-register every test (hashed file) and write the verdict rule before seeing data. | Done well from Oct: e.g. FEETRAIL sha256 56b083f2, TIGHTSTOP 785d61cc (`DECISION_RULE.md:19319-19357`). |
| L4 | Keep a "settled, do not re-propose without new evidence" list. | `DECISION_RULE.md:5813`; 121 REJECTED/REFUTED headings in the file. |
| L5 | Test every finding against luck (shuffled outcomes, random entries). | Today's best 80% cells were matched by ~85% cells on shuffled data (briefing §5); a coin-flip side scored within noise of the signals (`DECISION_RULE.md:19372-19384`). |
| L6 | Bootstrap by day-blocks, never by trade. Trades cluster. | Trade bootstrap hid a 31% loss chance (`DECISION_RULE.md:2532-2533`); 235 trades fell on only 50 days (`08_qa2.md` §2.8). |
| L7 | Prove a simulator matches reality before trusting it. | Repaired replay: exits on live entries corr 0.999, but end-to-end exits failed at corr 0.83 (`DECISION_RULE.md:17838-17849`). |
| L8 | Report lifetime, money-weighted, against benchmarks. | The briefing's "-$5.38 over 2 months" hid a -$180.20 month (`08_qa2.md` §2.1). |
| L9 | Archive raw data off the laptop, daily, with checksums. | MEXC keeps 1m bars ~30 days, history ~90 days; the laptop disk filled and the archive aborted (`daily_audit.md:116-122`). |
| L10 | Put safety rules in code and run monitoring server-side. | The $140 floor was "ALERTS, not an automatic pause" (`DECISION_RULE.md:19086-19089`); audit dark since ~10-21 (`daily_audit.md:1-20`). |

### Never
| # | Rule | Evidence |
|---|---|---|
| N1 | Never change a running trial. Any change or cash move = ABORTED = fail. | "Reset count: 6 in 11 days, zero scored verdicts... A trial that never runs long enough to score cannot be wrong, and cannot be right either" (`DECISION_RULE.md:4785-4789`). Trials 23-27 all ended early (`01_pm.md` §1). |
| N2 | Never add money on an in-sample or small-sample "pass". | Trial 18 "PASSED" on 27 closes (`DECISION_RULE.md:3179-3182`); +$915.72 followed; the funded window lost -$198.41 in 3 weeks (`:19550`). TREND went 7/7 (`:5889`), then -0.454R/trade in trial 25 (`:19579`). |
| N3 | Never polish exits while entries show no edge. | Fee trail, tight loss cut, ratchets all refuted (`DECISION_RULE.md:19319-19357`, `:5835`). |
| N4 | Never trade a stake below the venue's minimums. | 12 of 36 decisions refused with MEXC error 7008 at ~$35 (`DECISION_RULE.md:19785-19786`). |
| N5 | Never trust an environment variable is live because a tool says so. | Trial 2's config was not live for ~70 hours (`DECISION_RULE_trial3_archived.md:8`). |
| N6 | Never let credentials expire silently. | API key expired 10-14, 4.5h with no exits possible (`daily_audit.md:403-407`). |
| N7 | Never read a "best cell" p-value without correcting for every cut tried. | Lead 1's p=0.004 becomes family-wise ≈0.15-0.17 (`08_qa2.md` §2.5). |
| N8 | Never write a record the owner cannot read. | `DECISION_RULE.md` is 19,787 lines; 1R was "corrected" several times (`01_pm.md` §3.5). |

## 3. The research process (reuse for any strategy)

**Stage 0: Fit (1 page, before any code).**
- [ ] Venue, product and wrapper legal for the owner, with a dated source (L1).
- [ ] Named benchmark (for Option B: SWDA in a Stocks & Shares ISA, after fees and tax; minutes "Decision" §3), plus cash and one simple passive alternative.
- [ ] Money arithmetic: stake, expected edge, trades per month, resulting £/month range (L2). If it is under ~£10/month either way, say so.

**Stage 1: Pre-registration (P0).**
- [ ] One file: hypothesis, data window, exact feature code, one primary metric, cost model (fees, funding, slippage, minimums), pass bar, kill bar, calendar cap.
- [ ] sha256 of the file recorded in the decision log; amendments only before new data, signed by CEO and QA 2 (minutes "Churn rule").
- [ ] Every rule to be tried is listed, so the multiple-testing correction is fixed in advance (N7).

**Stage 2: Sample-size plan.**
- [ ] Required n stated before running. Basis to reuse: with trades swinging about ±1R, showing a +0.1R edge at 95% needs about (1.96 × 1 / 0.1)² ≈ 384 independent trades (`01_pm.md` §2); telling 66% wins from 50% needs ~60-75 (`08_qa2.md` P6). Count **day-blocks**, not trades (L6).
- [ ] At the expected pace, state the days needed. If the calendar cap is shorter, do not start.

**Stage 3: Luck benchmark.**
- [ ] Same search run on shuffled outcomes and time-shifted placebos (`tools/pit_placebo.py`, `tools/mc_ledger.py`).
- [ ] Must beat "take every candidate" and random entry on the same asset and side (minutes, pass criteria).

**Stage 4: Locked holdout.**
- [ ] Holdout defined by date before any analysis; file hashed; nobody opens it (as `holdout_LOCKED.json` today).
- [ ] Opened **once**, only after all earlier gates pass. Fail = kill; no re-tuning and re-testing.

**Stage 5: Replay-fidelity gate (before trusting any simulation).**
- [ ] Replay real trades from their real entries; kill if exit correlation < 0.90 or win/loss agreement < 90%; dollars within ±20% secondary (minutes, 12-06 gate; `08_qa2.md` P2).
- [ ] Point-in-time universe, delisted symbols scored at -1R, no fill on the signal bar (`08_qa2.md` P3-P4).

**Stage 6: Paper, then staged money.**
- [ ] Go-live checklist A1-A12 all green (`09_qa3.md` §5): legal venue, stake above minimums for ≥95% of orders, holdout pass, tested automatic floor pause, outside watchdog, server-side audit, 12-month archive, drills run.
- [ ] No deposit before the pre-registered sample, a holdout pass and a 30-day wait (minutes "Churn rule").

**Stage 7: Churn and abort rules (during any trial).**
- [ ] Fixed trade count and calendar cap; missing the cap = kill. "Undecidable" = kill.
- [ ] Any config change or cash move = ABORTED = fail. Two aborts close the strategy family.
- [ ] Owner ideas mid-trial go to a queue for the next pre-registration, not into the live system.

**Stage 8: Close-out.**
- [ ] One-page verdict signed (PM, CEO, QA 2); add rejected ideas to the settled list (L4); archive data and code with checksums.

## 4. Owner-facing reporting standard: the five-line owner card

Weekly, one screen, plain English, same format for paper and live (`06_functional.md` §3):

1. **My money:** lifetime money-weighted return after fees, funding/tax and deposits/withdrawals, in £ and %.
2. **Versus:** the same cash flows in the named benchmark (SWDA), in cash (~4%), and in BTC.
3. **Edge:** mean result per trade or per month with a 95% day-block interval, and one verdict: *edge / no edge / need N more (≈D days)*.
4. **Risk:** worst fall from peak, and money at risk right now.
5. **Health:** green/red for heartbeat, audit, data archive, credential expiry, holdout untouched.

Card rules: lifetime only, never a chosen window (L8); one P&L figure, not three (`06_functional.md` §2); no per-trade pings; numbers reconcile with the venue (`futuresbot/scorecard.py:156-164`). Two alerts sit beside the card: a **dead-man switch** (no heartbeat or audit for 24h) and **floor hit**.

## 5. Assets to carry forward

Reusable (`04_dev1.md` §2/§4, `07_qa1.md` §3): replay engine (`futuresbot/replay/exits.py`, `sizing.py`, `acceptance.py`, `bars.py`), point-in-time data tools (`tools/pit_fetch.py`, `tools/pit_pool.py`), luck controls (`tools/pit_placebo.py`, `tools/mc_ledger.py`, Approach 1's `analyze.py`), the evidence-archive pattern (`tools/archive_evidence.py`), the shadow ledger idea (record what you did not trade) and the 2,095-test habit. Extracting a standalone research kit: 3-5 developer-days (Dev 1's estimate, not measured). The trading bot itself, the 866-variable config and `runtime.py` are **not** carried forward.

## 6. Risk the owner should know (he is not touching the bot)

The bot keeps trading ~$34.62 on MEXC, unmonitored since ~10-21, with no automatic floor (L10) and on a venue that lists the UK as prohibited (L1). Worst trading case: roughly the $34.62 balance (basis: that is all the account holds; liquidation behaviour not checked). Separately, the account could be frozen with no recovery route (`02_architect.md`). Whether a pause survives a restart is unknown (`06_functional.md` §2.7). The team cannot act on this under read-only rules. Upside: no changes means no aborted trial, and live trades from 10-20 keep adding to the untouched holdout.

## 7. Decisions for the owner

- **WS1-D1:** Adopt this playbook (stages 0-8 and the owner card) as the mandatory standard for any future strategy, with a stage-gate sign-off before money moves. Recommended: yes.
- **WS1-D2:** Allow the team to store data and research kit off the laptop (cloud storage cost unknown; to be quoted by Dev 2).
- **WS1-D3:** Accept the running-bot risk in §6 in writing, or ask for a one-step note to pause and withdraw.
