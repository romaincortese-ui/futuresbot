# WS5: Gates, acceptance criteria and kill rules

QA 2 and QA 3, 2026-11-26. Draft for owner sign-off. Sources: `30_meeting_minutes.md`, `08_qa2.md` (P0-P7), `09_qa3.md` (A1-A12), `plan/ws1_lessons_playbook.md`, `plan/ws3_directions.md`, `05_dev2.md` (costs).

## 1. Ground rules
- Each gate has a date, a hashed pre-registered bar and one verdict: **PASS, KILL or ABORTED**. No extensions; missing the date = KILL.
- Bars are amended only before new data, signed by the CEO and QA 2. PM, CEO and QA 2 sign verdicts; QA 3 signs operational items.
- A pass is a recommendation. Only the owner moves money.

## 2. Stage gates for the new project (Direction 1 / Option B)

| Gate | Pass when | Date (proposed) |
|---|---|---|
| G0 Fit | UK residency confirmed; ETF wrapper eligibility from the platform's own list; broker on the FCA register; costs at the owner's stake fit the cost model | 12-26 |
| G1 Pre-registration | One hashed file: rule, data, costs, every variant to be tried, holdout, bars, cap | 12-15 |
| G2 Backtest | Section 3 met in full | Verdict 2027-01-29 (basis: ws3's 4-6 weeks from 12-15); cap **2027-02-26** |
| G3 Paper | At least 6 months beside SWDA on the broker's paper account; section 4 met | Cap: 7 months after start |
| G4 Small live | A1-A12 green (section 5); 30-day wait; owner sets stake and loss cap in writing | Owner's call |
| G5 Scale | 12 months live, reviewed quarterly, inside the backtest's band | Owner's call |

If G2 or G3 fails, the product becomes **SWDA plus the owner card** (Direction 2). That counts as a valid result.

## 3. G2: the bar against SWDA, after fees and tax

**Benchmark.** SWDA total return in GBP in an ISA (no tax), less its 0.20%/yr fee and the strategy's platform fee. Before SWDA's 2009 launch, MSCI World net total return in GBP less 0.20%. Cash = Bank Rate history.

**Strategy costs:** £3 a trade or 0.05%, FX 0.03%, ETF fees, £3/month ISA fee, 0.10% spread a trade unless measured, and CGT at 24% above £3,000 on anything outside a wrapper.

**A pass needs all seven:**
1. Return no more than 1.0%/yr below SWDA.
2. Worst fall at least one third shallower than SWDA's.
3. Return above cash.
4. Beats "SWDA plus 15% in a trend ETF at 0.75%/yr" on return per unit of worst fall. If it does not, buy that ETF or nothing.
5. **Luck test.** The cut in worst fall beats at least 95% of 1,000 random in/out schedules that switch as often and stay invested as long.
6. **Robustness.** The verdict holds with lookbacks ±25%. Falls are cut in at least 3 of 4 crashes: 2000-03, 2008-09, 2020 and 2022.
7. **Holdout.** The years 2021-12 to 2026-11 stay locked and are run once, after tests 1-6, and must still meet tests 2 and 4. Caveat: the rule is published and we lived through those years, so this is a check, not proof.

**Honest limit.** Twenty years cannot prove a rule beats SWDA. Basis: if the yearly gap to SWDA varies by about 8%/yr (assumed; to be measured), the error on the average gap is 8/√20 ≈ 1.8%/yr. So the bar is a pre-registered point estimate checked by tests 5-7, not a significance test. Every G2 report says so.

## 4. "Undecidable" means KILL. So does paper failing.

**Undecidable** = the required sample is not reached by the cap; the 95% interval contains both the pass and kill bars; over 5% of data is missing or over 10% of trades cannot be replayed; or the main and robustness tests disagree. **ABORTED** = the spec changed after data was seen, or the holdout was opened early. Two aborts close the strategy family.

**G3 paper checks that live matches the model, not that it wins.** Six months cannot show skill. Pass: every signal on time and matched 100% by an independent recompute; holdings within 1 point of model weights; costs at most 1.5× the model. Kill: two missed rebalances, a reconciliation gap open over 7 days, or a 6-month gap to SWDA outside the backtest's 1st-99th percentile band (computed in G2).

## 5. A1-A12 adapted for B

| # | B version |
|---|---|
| A1 | FCA-authorised broker. Wrapper eligibility confirmed in writing |
| A2 | Every order is at least 1 share. Real costs stay within the model at the owner's stake |
| A3-A4 | G2 (with luck test and holdout) and G3 passed |
| A5 | Tested in code: no leverage, margin or shorting; order-size cap; pause at the loss cap |
| A6 | (was exchange stops) No order goes out without the owner's monthly yes/no |
| A7 | Session/key expiry alerts at 7, 2, 0 days; test alert reaches the phone |
| A8 | An outside dead-man alert fires within 24 hours |
| A9 | Reconciliation runs daily on a server. A missed run raises an alert |
| A10 | Daily archive off the laptop, with checksums, kept 12+ months |
| A11 | Drills run: expired session, stale data, rejected order, duplicate order, restart mid-rebalance |
| A12 | Owner can see, approve and stop everything from a phone in under 5 minutes |

**Live kill (pre-registered):** the owner's loss cap is hit, or a fall reaches 1.5× the backtest's worst fall. A 3-year gap to SWDA below the backtest's 5th percentile triggers a written review, not an automatic sale. Trend can lag for years: SG Trend fell about 20% in 2024-25.

## 6. Futures replay protocol (only if kept)

Public data only. A pass means "archive as research", never money (minutes, Decision §1).

| Step | Test → verdict | Date |
|---|---|---|
| P0 | Hashed spec: feature windows (`08_qa2.md` §2.4), unchanged lead thresholds, one exit rule, fees 0.06-0.08% a side, slippage, funding, $5 minimum; metric mean net R; holdout = replayed candidates entered 10-20 to a P0 cut-off; day-block = one UTC entry day | 12-02 |
| P1 | Synthetic-window and truncation tests; fix any mismatch before P2 | 12-04 |
| P2 | Replay the 235 discovery trades on 5m FAIR bars with each trade's live exit config. **Kill** if exit correlation < 0.90, win/loss agreement < 90%, or > 10% unreplayable. Dollars (±20%) reported only | **12-06** |
| P3-P4 | Delisted candidates at −1R; entry at next bar plus slippage; under-minimum and slot-blocked candidates reported apart | 12-15 |
| P5 | Holm correction over every P0 rule; 10,000-draw day-block bootstrap; 1,000 random entries, same coin and side. **Kill** if no lead survives; holdout never opened | **12-15** |
| P6 | One holdout look. Pass needs ≥60 day-blocks, mean net R ≥ +0.10, bootstrap lower bound > 0, beats take-every-candidate and random entry, ≥95% of orders ≥ $5 | 12-22 |
| P7 | Dollars at $34.62 and at $1,000, against cash, BTC and SWDA | 12-22 |

Anything else on 12-26 is a kill. **Warning:** 10-20 to a cut-off near 12-19 is ~61 calendar days and empty days do not count, so missing the 60-block bar (undecidable = kill) is likely. Live trades from 10-20 stay unread until P6, as a secondary check only.

## 7. Reporting to the owner
- **One page per gate within 2 working days**, same format for good and bad news: verdict word, each bar against its result, spec hash, lifetime money-weighted figures, what is still unknown, and the decision asked, with a default.
- **A weekly five-line owner card** from the start of paper (`ws1_lessons_playbook.md` §4).
- **No answer from the owner means no money moves.**

## 8. Risk outside the gates
The live bot is under no gate and fails A1, A3, A5, A8-A10 and A2. Worst trading loss: about the $34.62 balance; the account could also be frozen. Only the owner can act.

## Decisions for the owner
- **D1:** Adopt G0-G5, "undecidable = kill" and the one-page report. Recommended: yes.
- **D2:** Approve the G2 cap of 2027-02-26 and the G3 length of 6 months, capped at 7.
- **D3:** Set the stake and loss cap before G4. Not needed now.
- **D4:** Run the futures replay only through P2 unless P2 passes. Recommended: yes.
