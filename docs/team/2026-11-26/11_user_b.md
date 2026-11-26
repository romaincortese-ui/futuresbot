# End user B (retail crypto holder): my honest take — 2026-11-26

**Who I am:** I buy and hold crypto on a mainstream app. I tried a trading bot once and lost money. I like upside, but I want clear results, I want to trust it, and I don't want to babysit it.

## What I saw as a user

- **Results.** Over roughly seven months the bot lost money. It lost $261.54 on the older strategy (Apr–Jul), then $5.38 over the last two months on 160 trades. Wins and losses are about the same size (avg win $0.95, avg loss $0.99), and fees ($8.42) ate more than the whole loss. The team's own conclusion is "no demonstrated edge" (briefing pack, section 3). The account now holds **$34.62**. If I had left my money in BTC or a savings account I would have done better, and with less stress.
- **What I receive.** The last three reports I'd have got (`docs/daily_audit.md`, runs 11-03, 11-10, 11-12) are all "DATA GAPPED – aborted safely". They say things like "`railway whoami` still fails: OAuth invalid_grant", "Trade count NOT VERIFIABLE", "SE $3.33 (SE > total: not a result)", "Shadow: stale". I can't follow most of that. What I did understand: nobody has been able to check the bot for about a month, and it may not have been able to open trades for about 22 days because the account is below MEXC's $5 minimum order. That is the opposite of reassuring.
- **Notifications.** The Telegram texts in `futuresbot/` show lots of alert types: "MEXC API key EXPIRED", "MEXC auth failure — bot cannot trade", "Futures Stop Not Restored", "The order was likely filled. The position is live but NOT tracked locally", "Random mode: invalid settings". A few are friendly ("PROFIT TAKEN", "Futures P&L"), but the scary ones are about the bot losing track of my money. As a retail user, one "position is live but NOT tracked" message would be enough to make me pull out.
- **Effort.** The owner has had to: renew API keys, free up laptop disk space, log back into Railway, decide on "trial 27", and watch a $140 budget floor rule. That is a part-time job, not a set-and-forget product.

## Scores

| Area | Score /10 |
|---|---|
| Results | 1 |
| Trust / safety | 4 (the team is honest and careful, with pre-registered rules and "abort safely" behaviour, but it runs on high-leverage futures and has had real outages) |
| Clarity of what it tells me | 3 |
| Effort required from me | 2 |
| **Overall** | **2.5** |

## Would I put my own money in today?

**No.** Not a pound. Nothing here shows it beats doing nothing.

## What would make me use it

1. Six or more months of results, checked by someone independent, that beat simply holding BTC or a low-cost index fund **after fees**. It should be shown on one simple chart: "your money vs. just holding".
2. One plain weekly message, along the lines of: "Balance £X, up/down Y% this week, vs BTC Z%. Nothing needs your attention." Engineering alerts should go to the engineers, not to me.
3. No leverage above about x2–x3, a hard cap on how much I can lose that I set myself, and nothing that stops working when someone's laptop login expires.
4. A regulated, UK-friendly setup. Sooner or later I'll ask, "Is my money protected?"

## What I'd do with the money instead

Mostly a stocks and shares ISA in a global index tracker, plus a small monthly buy of BTC/ETH that I hold. It's boring, needs no babysitting, and right now it beats this bot.

## My view on direction

Stop putting real money into this futures bot. Keep the lessons, especially the honest testing discipline, and point the team at something a normal person could actually trust and hand off. If the team wants one last go with crypto, it should be paper-only, and only until the "replay" study shows something real. I don't want my money paying for the experiment.
