# CEO opening statement: status meeting, 2026-11-26

I read all 12 memos: 8 say hybrid, 4 say pivot, **none says keep going**. Scores run 2-6/10 (median 3). My job is to find an edge, not to defend the bot.

## 1. Where we are

- **Money: we lost, mostly to fees.** Lifetime to 10-06: -$403.53 (money-weighted -75%), and fees were $262 (65%) of it. The same cash in T-bills made +$8, and in BTC +$148 (`DECISION_RULE.md:19545-19555`). Last 90 days: -$185.57 on 276 trades, profit factor 0.74 (QA 2's figure; the briefing left out -$180.20 from 08-29 to 09-25). Equity is **$34.62**.
- **Edge: none shown.** We ran about 30 configs in 95 days, the largest sample was 66 closes, and every trial's standard error exceeded its total. A coin-flip side matched our signals. All three leads from today fail a multiple-testing correction (QA 2).
- **Legal: the venue is our biggest problem.** MEXC's terms (12 Nov 2026) list the UK as a Prohibited Jurisdiction. MEXC has been on the FCA Warning List since 2024-03-22 (no FSCS or Ombudsman cover). UK retail clients are still banned from crypto derivatives (Architect, Dev 2).
- **Operations: nobody is watching.** The audit has been dark since about 10-21. The $140 floor lives only in that audit. MEXC's $5 minimum rejected 12 of 36 trial-27 decisions. Our evidence sits on one laptop while MEXC deletes its copy after 30-90 days.
- **Worth keeping:** 2,095 passing tests, a replay exit engine at corr 0.999 against live exits, and the habits of pre-registration, a locked holdout and luck benchmarks.

## 2. The options

- **A. Keep the futures bot.** Code the $5 check and the floor into the bot, re-fund it to a tradeable size, and run one unchanged config for 250+ closes. This is only possible if the venue question is settled in our favour. Today it is not.
- **B. New project.** Close the futures work. Build a UK-legal systematic allocator in an ISA or SIPP through an FCA-authorised broker API (lead candidate: Interactive Brokers UK): a tracker core, a trend and momentum overlay, and a small crypto-ETN sleeve. Paper first. Live only if it beats about 10%/yr after fees and tax, worst fall under 35%, on at least £5-10k.
- **C. Hybrid.** No new money on MEXC (pausing is the owner's call). One 30-day, paper-only Approach 2 replay under QA 2's P0-P7 protocol, with the kill rule fixed in advance. In parallel, scope B and move the research kit off the laptop. Day 30: one written decision.

## 3. Questions this meeting must answer

1. **Architect and Dev 2:** If the owner is UK-resident, is there any lawful way to keep trading MEXC perps? If not, what should the owner do with the account and the $34.62?
2. **QA 2 and Dev 1:** The holdout needs about 60-75 independent trades and we have 35. Can Approach 2 reach a verdict in 30 days? Could replayed candidates from 10-20 onward serve as the holdout? State the pass and kill numbers now.
3. **Researcher:** Name one edge "never found before" that is testable on years of data and lawful for UK retail. If there is none, say plainly that the honest target is "match the tracker with smaller falls", and name the fund we benchmark against.
4. **PM and Functional Lead:** Churn and early funding wrecked every trial. What rule stops that next time: who may change a pre-registration, and what minimum sample comes before any deposit?
5. **QA 3:** Which acceptance criteria (A1-A12) must pass before a single pound goes live anywhere? And is B worth building at all, compared with simply buying the tracker?

I start at C, with a hard day-30 kill date. Convince me otherwise.
