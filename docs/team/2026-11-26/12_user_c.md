# End user C (advanced investor) — memo, 2026-11-26

I run my own money through Interactive Brokers, test ideas in TradingView, and use ETFs and options.
I judge any strategy by net return after costs, drawdown, and how much evidence sits behind it.
I only looked at what a user sees: the results in the briefing pack, the last three daily audits
(`docs/daily_audit.md`, runs 11-03, 11-10, 11-12), and the Telegram message templates.

## What I see as a user

- **Results.** About 386 recorded closed trades (226 on the old strategy, 160 in the last two months,
  with a July-August gap nobody can check now). Net: −$261.54, then −$5.38. Profit factor 0.93. Fees
  ($8.42) were bigger than the net loss, so even "breakeven before costs" is not proven. The briefing
  says it plainly: "no demonstrated edge"; every trial was within noise (`00_briefing_pack.md` §3).
- **Size.** Equity is $34.62. At that size MEXC's $5 minimum order blocks most entries, so the
  current trial cannot even collect data. To me that is a demo account, not an investment.
- **What I receive.** The last three audits all say the same thing: "DATA GAPPED – aborted safely",
  the Railway login expired ~10-21, nothing verified for weeks, "owner action: run `railway login`". They
  are honest, which I respect, but they are full of in-house terms ("0-ter a", "SE", "R", "card",
  "shadow resync"). Telegram has 30+ message types (WILDCARD opened, Heartbeat, Tripwires, Missed-opportunity
  check, Weekly learning digest, API key expiring...). Lots of activity, but no single line saying
  "this is your return vs. a simple benchmark, and this is your max drawdown".
- **Effort.** Higher than it should be: API key expiry outages, a laptop disk filling up, a laptop-only
  login, a $140 floor rule I'd have to enforce myself. A tool that earns nothing still needs babysitting.

## Scores (out of 10)

| Area | Score | Why |
|---|---|---|
| Results | 1 | Net negative across ~386 trades; no edge shown; costs exceed the gross. |
| Trust / safety | 4 | Small risk per trade, pre-registered decision rules, holdout discipline, honest audits. But leverage up to x10 on small alts, and monitoring has been blind for 5 weeks. |
| Clarity | 3 | Honest but jargon-heavy; no equity curve, drawdown or benchmark comparison. |
| Effort for me | 3 | Too many manual fixes and outages for a tool that should run itself. |
| **Overall** | **2.5** | Well-engineered process around a strategy that does not make money. |

## Would I put my own money in today?

No. Not a pound. I don't fund something with a negative track record and a "leads worth testing" list.
The three leads in the edge study (don't chase, avoid weak-BTC days, night hours) are in-sample;
the same search on shuffled data found "better" cells, so I treat them as hypotheses, not edges.

## What would make me use it

1. A replay (Approach 2) that first reproduces the real trades, then shows a positive result on the
   locked holdout after fees and funding, with drawdown and a confidence range.
2. A one-screen monthly report: net return, max drawdown, Sharpe-like ratio, fees paid, versus a
   simple benchmark (a global index tracker, and plain buy-and-hold BTC).
3. Monitoring that does not depend on one laptop.
4. Paper or minimum size until 1 is met. No real money scaling before.

## What I'd do with the money instead

A low-cost global equity tracker in a Stocks & Shares ISA (tax-free in the UK), plus at most a small,
deliberate BTC/ETH holding if I want crypto exposure. That is the bar this project has to beat, after
costs and taxes, and it currently doesn't. I have not checked this year's returns for those, so I
don't quote numbers.

## My view on direction

Stop putting real money into the futures bot. Keep its useful parts (the testing discipline, the
holdout, the replay/data tooling) and run the replay test cheaply in paper mode. If it fails on the
holdout, close it and use the experience for something whose edge can be tested on years of data,
not 60 days. Either way, always report against a passive benchmark.
