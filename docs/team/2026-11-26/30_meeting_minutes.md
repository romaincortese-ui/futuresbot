# Status meeting minutes: 2026-11-26

**Chair:** CEO. **Decision:** C (hybrid), with Option A taken off the table. No more money on MEXC. The futures question gets one final paper-only test, then it is closed. The new work is a UK-legal allocator that has to beat a named tracker fund.

## Attendees
CEO (chair), PM, Architect, Researcher, Dev 1, Dev 2, Functional Lead, QA 1-3, End users A-C. Memos 01-12 in this folder.

## Where we are
- **Money:** Lifetime result to 10-06 is -$403.53, and fees were 65% of it (`DECISION_RULE.md:19545-19555`). The last 90 days lost **-$185.57** over 276 trades, profit factor 0.74 (08_qa2.md). Equity is **$34.62**.
- **Edge:** None shown. About 30 configs in 95 days; every trial's standard error exceeded its total. All three leads from today fail a multiple-testing correction.
- **Legal:** MEXC's terms (12 Nov 2026) list the UK as a prohibited jurisdiction, MEXC is on the FCA warning list, and the UK retail ban on crypto derivatives still stands (02_architect.md, 05_dev2.md).
- **Operations:** Nobody is watching the bot. The audit has been dark since about 10-21, nothing enforces the $140 floor, and the evidence sits on one laptop while MEXC deletes its copy.

## What each member said
- **PM (3/10, C leaning B):** Freeze each trial, and treat any change or cash move as an aborted (failed) trial.
- **Architect (3/10, C without A):** No lawful MEXC route for a UK resident. Archive data on day 1. B in stages, paper first.
- **Researcher (3/10, B):** There is no "never found before" edge we can honestly name. The target is to match SWDA with smaller falls. Withdrew his "~10%/yr" bar.
- **Dev 1 (5/10, C):** Approach 2 takes about 5 developer-days on public data. Count day-blocks, not trades. Proposed the kill and pass numbers adopted below.
- **Dev 2 (3/10, C):** Since 2026-04-06, new crypto-ETN purchases are not allowed in a Stocks & Shares ISA. IBKR UK needs at least £5k and quarterly rebalancing.
- **Functional Lead (4/10, C):** Proposed four anti-churn rules and the five-line owner card.
- **QA (QA 1 6/10, QA 2 5/10, QA 3 3/10):** We can likely reach a kill verdict, but not a pass, on 35 real trades. "Undecidable" means kill. The bot fails 7 of A1-A12.
- **User A (lowered to 1-2/10, B):** Default to "just buy the tracker". Crypto at most 5%.
- **User B (2.5/10, C as a bridge to B):** Pause now. Never re-fund MEXC.
- **User C (2.5/10, short C):** A replay pass can buy more research, never funding.

## Decision and why
**C, run as a bridge to B.**
1. MEXC fails A1 (legal venue) whatever the replay shows, so Option A is dropped, not just postponed. A replay pass can only mean "archive as research".
2. The replay costs about 5-7 developer-days and no money. It closes the question in writing; open questions fed seven months of churn.
3. New goal: **"beat, or match with smaller falls, iShares Core MSCI World (SWDA) held in a Stocks & Shares ISA, after fees and tax."** SPIVA reports that about 97% of active GBP global funds lagged their index over 10 years (03_researcher.md). Beating SWDA therefore already meets the owner's goal of "beating commercial funds". The fixed 10%/yr bar is retracted.
4. "Buy the tracker" is a valid result, not a failure.

## What we stop doing
- No deposits, no new API keys and no live orders on MEXC. Recommend the owner pause, not run a "minimum stake".
- No config tweaks, no trial 28, and no refactoring of `runtime.py`.
- No flattering-window reports; always lifetime and money-weighted.
- No absolute return bar, and no broker adapter until B beats SWDA on paper.
- No evidence kept only on the laptop. No managing other people's money.

## Next 30 days (day 30 = 2026-12-26)
| Action | Owner | Due |
|---|---|---|
| Owner action note: pause, export MEXC history, decide on wind-down | CEO + Architect (note); owner acts | 11-27 |
| Archive public 5m/1m bars off-laptop with checksums; 10-20 onward left unanalysed | Dev 2 | 11-30 |
| Briefing addendum: lifetime and money-weighted figures | PM | 12-01 |
| P0 hashed; holdout = replayed candidates from 10-20, in day-blocks | QA 2 + Dev 1; CEO signs | 12-02 |
| Day-30 decision criteria and one-page report format frozen | PM + Functional Lead | 12-03 |
| Research kit off FuturesRuntime; P1 feature tests; CI on Python 3.12 | Dev 1, QA 1 | 12-04 |
| Owner card v1 (vs SWDA, cash, BTC); dead-man/floor alert design | Functional Lead + Dev 2 | 12-05 |
| **P2 fidelity go/no-go on the 235 discovery trades, 5m bars** | QA 2 | **12-06** |
| Verify crypto-ETN ISA rule, IBKR ISA/SIPP, data costs | Dev 2 + Architect | 12-10 |
| B rule spec and pre-registered backtest bar; A1-A12 adapted for B | Researcher + QA 2 + QA 3 | 12-15 |
| P3-P5 walk-forward and family-wise correction on 08-28 to 10-19 | Dev 1 + QA 2 | 12-15 |
| Single holdout look (only if all earlier gates pass) | QA 2 | 12-22 |
| One-page day-30 decision, signed by PM, CEO and QA 2 | CEO | **12-26** |

## Success and kill criteria
**Futures replay (pre-registered under P0 by 12-02):**
- **Kill on 12-06** if replayed exits correlate below 0.90 with real exits, or win/loss agreement is below 90%. Dollars (±20%) are secondary.
- **Kill on 12-15** if no lead survives the family-wise correction. In that case the holdout is never opened.
- **Pass on 12-22** only if all of these hold: at least 60 independent day-blocks; mean net R of at least +0.10 after fees, funding, slippage and the $5 minimum; a day-block bootstrap 95% lower bound above 0; it beats both take-every-candidate and random entry on the same coin and side; and at least 95% of orders clear the $5 minimum.
- **Anything else on 12-26, "undecidable" included, is a kill.** No extension. Even a pass leads only to "archive as research" and puts no money on MEXC.

**Option B:**
- **Day 30:** frozen spec, named data source, wrapper rules confirmed.
- **Later pass bar, fixed before any backtest:** over 20+ years of walk-forward data, net of fees and tax, B is no more than about 1%/yr behind SWDA, its worst fall is at least one third shallower, and it beats cash (about 4%). Then 6+ months paper beside SWDA, A1-A12 green, live money in stages. If B fails, the product is SWDA plus the owner card.

**Churn rule (adopted):**
- The pre-registration is hashed. It can only be amended before new data is seen, signed by the CEO and QA 2.
- Any config change or cash move ends the trial as ABORTED and counts as a fail. Two aborts close that strategy family.
- Each trial has a fixed trade count and a calendar cap. Missing the cap means kill.
- No deposit before the pre-registered sample, a holdout pass, A1-A12 green and a 30-day wait.

## Open decisions for the owner
1. Pause the bot now, and whether to export, close, withdraw and delete the keys. We recommend yes. Withdrawal fee unknown.
2. Confirm UK residency and how the MEXC account was opened.
3. Confirm the live value of `FUTURES_RESUME_ON_BOOT`. Unknown whether a pause survives a restart.
4. Sign the holdout redefinition in P0.
5. Budget for cloud storage, market data and developer time. Costs unknown.
6. Whether to hold a plain tracker ISA in the meantime. His call; not advice.
7. The capital and loss cap for B, the crypto sleeve (default at most 5%, taxable or SIPP), and whether he accepts that trend can lag for years (SG Trend fell about 20% in 2024-25).
8. Tax treatment of the roughly $403 loss. Ask an accountant.

## Dissent recorded
- **Researcher, QA 3 and User A:** prefer B outright. They accept C only as paper-only with a fixed date.
- **User C and Researcher:** 30 days is too long. *Answer:* developer effort is capped at about 7 days, but the calendar stays at 30 so the holdout day-blocks can accumulate.
- **PM:** wanted 45 days; overruled (1m bars expire, drift risk).
- **Dev 1 vs QA 2 on the P2 dollar gate:** the R-based gate is primary and dollars are secondary.
- **Dev 1 (minimum stake):** overruled; the bot is paused.
- **Users vs QA 1 and Dev 1:** engineering scores (5-6) are not product scores (1-2.5).
- **Architect vs User B:** one monthly yes/no rebalance message, not per-order approval.
