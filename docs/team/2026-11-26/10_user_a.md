# End user A (average UK saver): my honest view

I have a Stocks & Shares ISA in a robo-advisor / global tracker. I don't trade. I judged this as someone
who would be asked to put money into it, using only what the owner sees: the results in the briefing
pack (`00_briefing_pack.md`), the last three daily reports (`docs/daily_audit.md`, runs 11-12, 11-10,
11-03), and the Telegram messages the bot sends (`futuresbot/runtime.py`, `_entry_message`,
`_close_message`, `_build_help_message`).

## What I see as a user

- **It has lost money.** About −$262 on the older strategy (Apr–Jul), results for Jul–Aug unknown, and
  −$5 over the last two months. The win rate is about 50% and the small gains are eaten by fees
  ($8.42 in fees against a $5.38 loss). Nothing in the pack says it has ever been ahead overall.
- **The team itself says there is no edge yet.** "Every trial's result was within noise."
- **The account is down to $34.62**, under the bot's own $140 "you should pause" floor, and most trades are
  refused because they are below the exchange's $5 minimum. So it is mostly sitting there failing to trade.
- **The daily report has been broken for over a month.** The last three reports all say the same thing:
  login expired, "trade count NOT VERIFIABLE", "owner actions: run `railway login`". As a user I would
  read that as "nobody is checking my money".
- **The messages are written for an engineer.** "Meteorite: 3h move +9.1% | RSI 71", "Cert 62%", "R",
  "SE > total", "TRIAL 27 ALERT (0-ter a)", "/arm ZEC 0.20 floors at 80% of the CURRENT value". I would not know
  whether a message is good news, bad news, or something I must act on.
- **It is leveraged crypto futures (up to x10, earlier x25) on an offshore exchange.** I would not get the UK
  protections I'm used to (FSCS, FCA-regulated platform, ISA tax wrapper). Whether that is even allowed for
  UK retail is something I'd need the Architect to confirm; I don't know.

## Scores

| Area | Score /10 | Why |
|---|---|---|
| Results | 1 | Lost money; best stretch was +$6.60 and that was noise. |
| Trust / safety | 2 | Real leverage, offshore, monitoring broken for 5 weeks. Credit for honesty and a pause floor. |
| Clarity of what it tells me | 3 | Lots of data, very little plain meaning. No simple "you are up/down £X vs your tracker". |
| Effort required from me | 3 | Owner must fix logins from a laptop, decide on alerts, watch Telegram. Not "set and forget". |
| **Overall** | **2** | Interesting project, but not a product I could use. |

## Would I put my own money in today?

**No.** Not even £100. My tracker fund needs zero effort, is inside an ISA, and has not lost me money
over the same months (I don't know the exact figure for 2026, but it is the bar this has to beat).

## What would make me use it

1. A **track record that beats a global tracker after fees**, for at least 6–12 months, on a sensible amount of money,
   checked by someone other than the bot.
2. One **weekly plain-English message**: "Balance £X. This week +/−£Y. Since start +/−Z% vs FTSE Global All Cap +W%.
   Nothing for you to do." Alerts only when I genuinely must act.
3. **Monitoring that doesn't depend on one laptop login.**
4. Clear answers on UK rules, tax and what happens if the exchange goes down.
5. Ideally, something I can hold inside an ISA or SIPP.

## What I'd rather do with the money

Leave it in my tracker (or top up my ISA), and keep cash savings in an easy-access account. If the team wants
to try for an edge, I'd rather they did it with small "research money" and only came to me once it has
clearly beaten the tracker.

## My view for the meeting

I'd **stop putting effort into this futures bot as a product** and use what was learned (the testing discipline,
the honest audits) on something new that a normal UK saver could actually use and compare against an index
fund. Keep the bot paused or on paper while you decide.
