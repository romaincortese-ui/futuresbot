# Team briefing pack — 2026-11-26

Everything the team needs to know before the status meeting. Facts here were read from the
exchange (MEXC), the repo, and the bot's own audit log on 2026-11-26. Where something is an
estimate or an opinion it says so.

## 1. The goal

The owner wants an **investment edge**: a way to put money to work that grows it more than the
commercial funds available to them online. The MEXC crypto futures bot in this repo is the current
attempt. The owner is open to keeping it, changing it, or using the experience to start something
new, in crypto or elsewhere. The owner appears to be **UK-based** (the request mentions UK
limitations); treat UK rules as binding.

## 2. What the bot is, in one paragraph

A Python bot (`main.py`, package `futuresbot/`, ~36k lines across 68 modules, 116 test files)
running 24/7 on **Railway** (project "Futures bot", service `Futures-bot`, state on a `/data`
volume). It trades **MEXC USDT perpetual futures** with real money and reports to the owner via
**Telegram**. It has gone through ~27 numbered "trials" (each a config change with a
pre-registered decision rule, `docs/DECISION_RULE.md`). A daily automated audit
(`docs/daily_audit.md`, newest first) ran from the owner's Windows laptop until its Railway login
expired on ~2026-10-21.

Current live design (see `docs/LIVE_CONFIG.md`, written from source; `README.md` describes an
older design):
- **WILDCARD sleeve** (3 slots): scans small/mid-cap alt perps outside the top 24 by turnover,
  triggers on a >=8% 3-hour move with a pullback-then-resume pattern, long and short, x1-x10.
- **TREND sleeve** (2 slots): long-only on a few majors (ETH, XRP, ZEC). **Turned off in trial 27**
  (logged, not traded).
- Exits: exchange stop-loss/take-profit plus software exits ("convex retention trail", time stop,
  early stop, FX90 floor). Only 9 trades in the bot's whole recorded history ever hit take-profit.
- Risk ~1% of equity per trade; a $140 budget floor rule says the owner should pause below it.

## 3. Money and results (from the MEXC exchange, 2026-11-26)

| Period | Closed trades | Net P&L (after fees + funding) | Win rate | Notes |
|---|---|---|---|---|
| 2026-04-17 → 07-13 (older PMT strategy, 6 big coins, x5-x25) | 226 | **−$261.54** | 35% | repo file `_position_history_full.jsonl` |
| 2026-07-13 → 08-29 | ? | ? | ? | no longer available on the exchange (MEXC keeps ~90 days) |
| 2026-09-26 → 11-26 (last 2 months) | 160 | **−$5.38** | 49% | profit factor 0.93, fees $8.42 > net loss, avg win $0.95 / avg loss $0.99 |
| of which 09-26 → 10-21 | 126 | −$5.38 | 50% | worst week 10-05: 60 trades, −$10.71; best stretch trial 26 (+$6.60) |
| of which 10-21 → 11-26 | 34 | $0.00 | 47% | ~1 trade/day at a few $ each |

Capital flows: +$915.72 deposited 2026-09-04; **−$715** withdrawn 2026-09-25; **−$150** withdrawn
2026-10-17. Equity today: **$34.62**, no open positions. Longs lost (110 trades, −$13.32), shorts
made money (50, +$7.94). Worst coins: XRP (−$10.53 / 11 trades), ZEC (−$7.67 / 15).

**Bottom line so far: no demonstrated edge.** Every trial's result was within noise
(the audits note "standard error > total" for every trial).

## 4. Operational state today

- Bot is running and still trading tiny size. At a ~$35 stake most picks are refused by MEXC's
  **$5 minimum order** (error 7008), so trial 27 is starved of data.
- The **daily audit is down**: Railway CLI login expired on the owner's laptop around 10-21; the
  owner is travelling and can only fix it from the laptop. MEXC 1-minute bars for late October are
  probably already lost (30-day retention).
- 2026-11-26: this session logged into Railway (browserless, owner-approved) and pulled exchange
  history **read-only**. Nothing was deployed or changed.
- Earlier ops incidents in the log: MEXC API key expiry outage (10-14), laptop disk full aborting the
  evidence archive (10-21), Railway SSH refusals.

## 5. The edge study done today (Approach 1)

Question asked by the owner: which entry-time conditions gave a high (ideally >90%) chance of a
winning trade?

Three approaches were proposed:
1. **Bucket tables on real trades** — rebuild ~30 entry inputs per trade from hourly price bars
   (token and BTC returns over 1h-7d, volatility, volume ratios, position in 24h/7d range,
   funding, hour, side, leverage) and compare win rate / return per bucket.
2. **Replay every candidate the scanner ever saw** (thousands, incl. the ~900-row shadow ledger of
   skipped candidates) under one fixed exit rule, validated first against the real trades.
3. **A simple model** (logistic regression / shallow tree) with walk-forward testing.

Decision: run 1 now on an exploration set, then 2, then one final test on a locked holdout.
- Exploration set: entries 2026-08-28 → 10-19, 241 trades (235 with inputs).
- **Locked holdout: entries from 2026-10-20 (35 trades + all future trades). Nobody looks at its
  outcomes until the final test.** File `holdout_LOCKED.json` — do not open it.

Results (`report.txt`):
- **No 80-90% rule is real.** The best pair-of-inputs cells win ~80% but the same search on
  shuffled (random) outcomes gives ~85% best cells. They are luck.
- Three leads worth testing (each stable across both halves of the exploration set; not proven):
  1. Don't chase: entries after a 4-12% move already in the trade's direction over the last 10h won
     only 37% (78 trades).
  2. Avoid trading when BTC 24h is below ~−0.15%: 40% wins, and it hurts shorts too (37%).
  3. 00-07 UTC entries did better (58% wins).
- Applying leads 1+2 in hindsight keeps 96 of 235 trades at 66% wins — in-sample, so optimistic.
- Why Approach 2 is considered more relevant than it sounds: the outcome is decided by the price
  path, not by whether we were filled; the real trades are a biased sample (the shadow ledger's
  skipped-because-slots-were-full candidates resolved at +28.1R while taken trades lost); and the
  replay can be validated against real trades before being trusted.

Working files (temporary, in this session's scratchpad):
`/tmp/claude-0/-home-user-futuresbot/b7320ff0-05a5-5b6b-aac4-d653804aadfc/scratchpad/a1/`
(`report.txt`, `features_all.csv`, `discovery_with_outcomes.csv`, `build_features.py`, `analyze.py`).
Full 90-day exchange history: `.../scratchpad/hist_all.json`.

## 6. Owner's stated concerns

- Wants a real, convincing edge, not backtest fiction; skeptical of "theoretical" replayed trades
  until shown they track reality.
- Wants direction: keep working on this futures bot, or use the experience for a new project?

## 7. Rules for every team member

- **Read-only on production.** No Railway commands, no MEXC private API calls, no deploys, no
  config changes, no orders, no Telegram messages. Public market data and web research are fine.
- Do not open `holdout_LOCKED.json` or analyse trades entered on/after 2026-10-20.
- Do not commit or push. Write only inside `docs/team/2026-11-26/` or the scratchpad.
- Never put the owner's name, email or account details in web searches or external requests.
- Be honest about uncertainty. Say "unknown" rather than guess. Cite file paths or URLs for claims.
