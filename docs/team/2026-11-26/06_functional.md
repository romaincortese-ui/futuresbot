# 06 — Functional Lead prep memo (2026-11-26)

The question: does what the owner sees today answer **"do we have an edge?"** and **"is my money safe?"**, and what is the minimum he needs under each option?

## 1. What the owner gets today

- **Automatic Telegram messages** (`futuresbot/runtime.py`):
  - a ping on every entry and close (`_entry_message`, `_close_message`, ~line 4902-4960);
  - a status "heartbeat" every 6 h (`futuresbot/config.py:478`);
  - a weekly learning digest (`futuresbot/learning_digest.py`);
  - ~20 ops alerts: API-key expiry and auth failure (`futuresbot/key_health.py`), drawdown halt, failed stop or close, unresolved orders, loop errors, bad trial config.
- **13 commands** (`runtime.py:5548-5620`, `futuresbot/commands.py`): `/status /pnl /report /daily /why /logs /simulation /pause /resume /close /arm /reconcile /help`.
- **From the owner's laptop:** the daily audit (`docs/daily_audit.md`) and a templated Telegram report (`tools/send_telegram.py`). Both have been **down since ~2026-10-21**.
- **Calculations the owner sees:**
  - R multiples (profit measured in units of risk taken) and net R per trial;
  - "netR ex-best" (the result without the best trade) and standard error ("SE > total: not a result");
  - tail losses worse than −1.1R, and drawdown off peak;
  - margin as a % of equity against a 45% kill line;
  - ledger-vs-exchange reconciliation (`futuresbot/scorecard.py`; `/status` at `runtime.py:4315`).

## 2. Useful, noise, missing

**Useful (worth carrying into any project)**
- The ledger integrity check, which confirms our records match the exchange's closes (`scorecard.py:156-164`).
- Pre-registered thresholds and "SE > total: not a result". These stop a lucky week being read as an edge.
- Risk at the stop-loss for each position and in total: "what can I lose right now?".

**Noise**
- `/status` is a developer console. Slots, sleeves, regime, calibration flags, trail and time stops all sit on one card.
- **Three P&L figures that disagree by design:**
  - `/pnl` covers the last 200 trades;
  - `/status` covers the current trial;
  - `/report` "Lifetime" covers only what MEXC still keeps (~90 days).

  The code explains this in italic footnotes (`runtime.py:4839`, `4705`).
- Entry and close pings at $1-2 per trade. They are emotional noise with no value as evidence.
- Trial jargon (FX90, ratchet, convex retention trail). `docs/DECISION_RULE.md` runs to 19,787 lines.

**Missing (the important part)**
1. **No benchmark.** Nothing compares results with cash (4%), a global tracker in an ISA (~10%/yr) or BTC buy-and-hold. The bar is set in `03_researcher.md` §1.
2. **No money-weighted return.** Deposits and withdrawals (+$915.72, −$715, −$150) are never netted into "what did my money do?". The PM estimates about −75% to 10-06 (`01_pm.md`). No bot message says this.
3. **No edge verdict with a confidence interval** pooled across trials. Nothing says "not enough data: N more trades needed".
4. **The $140 budget floor is not in the bot.** It is a rule in the laptop audit (`docs/DECISION_RULE.md:19299`; audit 10-19). When the audit died, so did the floor alert. Equity is $34.62 and entries are still not paused.
5. **No "cannot trade" alert.** MEXC's $5 minimum-order refusals (error 7008) starved trial 27 for weeks, and only the audit noticed (`daily_audit.md` 10-19). I found no bot alert for it.
6. **No dead-man switch.** Monitoring has been down for 5 weeks. The only sign was a desktop notification on a laptop the owner is not near.
7. **`/pause` may not survive a restart.** `docs/LIVE_CONFIG.md:128` says `FUTURES_RESUME_ON_BOOT=1` (a restart undoes `/pause`). `DECISION_RULE.md:19119` says it is 0. Which is live: **unknown**.
8. **No UK tax export** (disposals, fees and funding per tax year; `02_architect.md` §d).

**Verdict:** the outputs answer "is the machine behaving?" well. They answer neither "is there an edge?" nor "is my money safe?" in a form the owner can read in 10 seconds.

## 3. Minimum feature set per option

**Common core, for every option:** a weekly **owner card** with five lines:
1. money-weighted return after fees, funding and flows;
2. the same period for cash, a global tracker and BTC;
3. edge per trade with a 95% interval and a plain verdict: edge / none / need N more trades;
4. max drawdown and money at risk now;
5. ops health (green or red).

Add two alerts: a **dead-man switch** (no heartbeat or audit for 24 h) and **budget floor hit**.

**A. Continue the futures bot**
- Make the floor a hard automatic pause that survives restarts. Only the owner can resume.
- Add a "starved" alert: more than 50% of order attempts refused in 24 h.
- State the sample size before each trial: "needs N trades; at the current pace that is D days".
- Move the audit to a cloud scheduler.
- Turn per-trade pings off by default.

**B. New project**
- The owner card is the product. Build it first, against a named UK fund in an ISA, before any strategy goes live.
- Paper and live use the same card, so they are judged the same way.
- Tax-year export from day one.
- Holdout status shown on the card ("holdout untouched: yes").

**C. Hybrid**
- Futures stays paused live. Approach 2 delivers a one-page replay report:
  - first, how well the replay tracks real fills;
  - then the three leads, each with an interval;
  - then a single holdout result.

  The acceptance criteria are written before the run.
- The new side gets the owner card and benchmark from B. Both use the same format, so the day-30 decision compares like with like.

**For QA:** every verdict rule (floor pause, starved alert, dead-man switch, edge verdict) should be a pure function with fixed test inputs, as `scorecard.py` already is.

## My position for the meeting

**Hybrid.** The bot proves the machine runs. It never shows an edge against a benchmark, and its money-safety rules lived on a laptop that has been dead for 5 weeks.
Pause live futures (it cannot trade at $35 anyway) and let the pre-registered replay study settle the edge question once.
Whatever wins, build the five-line owner card first. It works for any project.
