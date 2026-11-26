# WS4: Target architecture for Option B (Architect + Dev 2, 2026-11-26)

**In short:** a small, cheap system for research and paper trading first. It holds no broker keys and needs no always-on server: scheduled cloud jobs do the work, and the data lives off the laptop. Real money comes later, through IBKR UK in a Stocks & Shares ISA. The owner answers one yes/no on each monthly trade list, and nothing ever trades unattended. Running cost is about £0-20 a month until live, then about £3+ a month at IBKR. The Option C futures replay runs inside the same kit.

## 1. Components

| # | Component | Job | Reuses |
|---|---|---|---|
| 1 | Data store | Append-only files in object storage, each with a manifest (sha256, source, date). Raw bars, ledgers, reports and the sealed holdout | `archive_evidence.py` pattern (WS2) |
| 2 | Research kit (`edgekit`) | Data adapters, point-in-time universe, features, holdout guard, luck controls. **No private keys, no order code** | WS2 §3 |
| 3 | Backtest / walk-forward | Monthly-rebalance simulator with fees, FX, spread and the tax of each wrapper. Day-block bootstrap and family-wise correction; compares against SWDA, cash and BTC | `walk_forward.py`, `realistic_costs.py`, WS1 stages 1-5 |
| 4 | Paper trader | At each month-end, target weights become a paper order ticket and a paper ledger entry. Live trading will use the same code | new, small |
| 5 | Owner reporting | Weekly five-line owner card (WS1 §4), plus a monthly yes/no rebalance message | `scorecard.py` reconcile |
| 6 | Monitoring / dead-man switch | Every job pings an outside checker. A missed ping, or any failure, alerts the owner's phone. A daily check covers credential expiry | WS1 L10/N6; QA3 A8-A9 |
| 7 | Broker (later) | First, read-only IBKR statements (Flex) for reconciliation and tax export. Then orders placed by the owner | `marketdata.py` lessons: client order IDs, minimum checks before sending |

Option B needs 20+ years of daily data. SWDA only launched in 2009, so the earlier years need index proxies. The source and licence for these are **unknown**; due 12-10.

## 2. Hosting (off the laptop)

- **Scheduler:** GitHub Actions cron in a private repo. A few minutes a day fits within the included usage; beyond that, Linux runs at about $0.006 a minute [9].
- **Storage:** Backblaze B2. The first 10 GB are free, then $6.95 per TB per month [10]. We hold a few GB, so this costs about £0-1 a month.
- **Dead-man switch:** healthchecks.io, whose free plan covers 20 checks [11].
- **VPS:** only if a broker gateway ever has to run. Hetzner is about €5.50-6 a month, but availability is unconfirmed [12].
- **The owner owns every account** (GitHub, storage, alerting) and grants the team scoped access. Nothing should hang on one person's login, as Railway did on 10-21.

## 3. Credentials and key expiry

- **Secrets register in the repo.** It holds names, never values: purpose, scope, created date, expiry and next rotation. A daily job alerts 14, 7 and 1 day before each expiry, and on the **first** authentication failure.
- **Research and paper phases hold no trading keys.** The only secrets are a storage key limited to one bucket, an alert token and the ping URLs.
- **IBKR does not let individual clients automate login.** Sessions need daily re-authentication, and its OAuth is for organisations and advisers only [6]. Tools that store the password on a server are rejected. As a result, the system never holds a trading login. The owner places the approved ticket in the IBKR app (A12) or logs in briefly with 2FA. Read-only Flex statements use a token that expires (term to be confirmed), which goes in the register.
- **Unreadable means unknown.** The system stops and alerts. It never substitutes a fallback value (the `equity=77.85` case, `05_dev2.md` §2).

## 4. Venues for a UK resident (checked 2026-11-26)

| Need | Option | Costs and minimums | Notes |
|---|---|---|---|
| Core ETFs | **IBKR UK Stocks & Shares ISA** | **No minimum deposit.** £3 a month minimum activity fee, which commissions count towards. From £3 per UK trade. Cash only [1] | FCA FRN 208159. API and free paper account |
| Crypto ETN sleeve | **Not in a Stocks & Shares ISA.** From **2026-04-06**, crypto ETNs qualify only for an Innovative Finance ISA. No new purchases or transfers into a Stocks & Shares ISA; existing holdings may stay [2][3] | Stratiphy was reported (2026-04-22) as the first IFISA offering 21Shares ETNs [4]. Fees unknown | Otherwise a taxable account (CGT) |
| SIPP at IBKR | Third-party administrators | Westerby: **£40k minimum**, no crypto ETFs, **no API trading**. @sipp: **£75k minimum** [5] | Does not fit. Other SIPPs not checked |
| Crypto futures or perps | None for UK retail | none | FCA ban, PS20/10 [7] |
| MEXC | Public data only | none | UK prohibited under MEXC's terms; on the FCA warning list (`02_architect.md`) |

**Correction to the minutes:** "IBKR needs at least £5k" is our cost estimate, not an IBKR rule. The £36 a year minimum fee is 0.7% of £5k, 0.36% of £10k and 0.18% of £20k. Each extra trade costs £3.

## 5. UK guardrails, coded as checks

- **No leverage, derivatives or margin.** The code refuses them.
- **Checked before every order:** the £20k ISA limit and the asset's wrapper eligibility (for example, no crypto ETN in a Stocks & Shares ISA).
- **Every report is after tax.** CGT is 18% or 24% above £3,000 outside a wrapper. A tax-year export is produced from day one.
- **Owner's money only.** Managing other people's money is FCA-regulated.
- **Not financial advice.** MEXC losses go to an accountant.

## 6. Running costs per month

| Phase | Item | Estimate | Basis |
|---|---|---|---|
| Research and paper | Actions, storage, health checks, alerts | £0-2 | Free tiers above, a few GB of data |
| | Daily ETF/index data | £0-17 | Free sources (reliability unknown) or EODHD at $19.99 a month for personal use [8]. LSE coverage still to be checked |
| Live (IBKR ISA) | Activity fee and commissions | £3 minimum, plus £3 a trade beyond it | [1]. Market-data fees unknown |
| Old bot, until stopped | Railway | At least $5 (Hobby minimum); actual bill unknown | [13] |

Developer time is the main cost; see WS2/WS3.

## 7. Build order (paper first)

1. **By 11-30:** set up the storage bucket, health checks and secrets register. Archive the public bars and the scratchpad history, checked against `ws2_scratchpad_sha256.txt`.
2. **By 12-04:** `edgekit` with CI on Python 3.12 and the holdout guard.
3. **12-06 to 12-22:** run the futures replay inside the kit, as research only.
4. **By 12-26:** choose the data source, freeze the B spec and its pass bar, and ship owner card v1. **Owner decision.**
5. **2027, at least 6 months:** paper-trade B beside SWDA, with monthly yes/no messages and the A11 drills.
6. **Then:** connect IBKR read-only (paper account, Flex reconciliation), then go live in stages with the owner approving each ticket. **Owner decision.**
7. Semi-automated order placement only if the manual step proves a burden. Never unattended.

## 8. The live MEXC bot keeps running

**Legal.** The bot is breaching MEXC's terms for UK residents. The account could be frozen, with no route to the Ombudsman or FSCS. The FCA ban binds firms. We found no rule making the owner's own use an offence, but this is not legal advice. Trades made in 2026/27 still need records for Self Assessment, and MEXC deletes them after about 90 days.

**Operational.**
- **Unmonitored since about 10-21.** No $140 floor is enforced.
- **Mostly cannot trade.** At $34.62, most orders are refused (MEXC's $5 minimum). The worst loss is about the balance; liquidation is unchecked.
- **Key expiry.** The key was renewed on about 10-14. If it has no linked IP, MEXC's 90-day rule (`futuresbot/key_health.py`) gives an estimated expiry of **2027-01-12**. After that, open positions rely only on their resting stops.
- **Hosting cost.** At least $5 a month, which may exceed anything the bot earns. If billing lapses, `/data` is lost.
- **No dependency.** The new system does not depend on the bot.

**Recommendation only; the owner decides.** One wind-down session of about 30 minutes:
1. Read-only export of the MEXC history and `/data` (WS2 §6).
2. Close any position and withdraw. The fee is unknown.
3. Delete the MEXC API key. This stops the bot whatever `FUTURES_RESUME_ON_BOOT` says.
4. Stop the Railway service.

Otherwise, the owner accepts the risk in writing (WS1-D3), and the team treats MEXC as a data source only.

## 9. Decisions for the owner

- **WS4-D1:** Approve this architecture and a pre-live running-cost cap of £25 a month, with all accounts in the owner's name.
- **WS4-D2:** Crypto sleeve wrapper: IFISA, taxable or none. Defer until B passes on paper.
- **WS4-D3:** Do the MEXC wind-down in §8, or accept its risk in writing.

## Sources (read 2026-11-26)
[1] https://www.interactivebrokers.co.uk/en/accounts/isa-accounts.php · [2] https://www.gov.uk/government/publications/amendment-to-individual-savings-account-regulations-2026/individual-savings-account-amendment-regulation-2026 (9 Mar 2026) · [3] https://www.gov.uk/government/publications/tax-free-savings-newsletter-21/tax-free-savings-newsletter-21-june-2026 · [4] https://www.theblock.co/amp/post/398415/uk-investors-regain-tax-free-access-to-crypto-etns-via-innovative-finance-isa-route · [5] https://www.interactivebrokers.co.uk/en/general/sipp-administrators.php · [6] https://www.interactivebrokers.com/docs/web-api/authentication/faq · [7] https://www.fca.org.uk/publications/policy-statements/ps20-10-prohibiting-sale-retail-clients-investment-products-reference-cryptoassets · [8] https://eodhd.com/pricing · [9] https://docs.github.com/en/billing/concepts/product-billing/github-actions · [10] https://www.backblaze.com/cloud-storage/pricing · [11] https://healthchecks.io/pricing · [12] https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/ · [13] https://docs.railway.com/pricing/plans
