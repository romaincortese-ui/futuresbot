# Architect prep memo — 2026-11-26

Summary: **the software works but its operations are fragile, and MEXC's own terms now exclude UK residents.** That outweighs every tuning question.

## (a) Current architecture and its weaknesses

| Part | What it does | Where |
|---|---|---|
| Live trader | One Python process, one MEXC account, 24/7 on Railway with a `/data` volume. `main.py` sets about 140 defaults, then hands over to `FuturesRuntime` | `main.py`, `futuresbot/runtime.py` (15,361 lines of the package's 36k) |
| Strategy and exits | Wildcard and trend detectors, the PMT exit stack, sizing | `strategy.py`, `wildcard.py`, `exits.py`, `pmt_strategy.py` |
| Side jobs | Calibration on a cron schedule, Redis publishers | `railway.calibration.toml`, `railway.pmt-core-weight.toml`, `funding_publisher.py` |
| Owner interface | Telegram commands and alerts | `telegram.py`, `commands.py` |
| Audit and evidence | Daily audit plus the evidence archive (Windows scheduled task "FuturesEvidenceArchive") | owner's laptop, `tools/archive_evidence.py`, `docs/daily_audit.md` |

Weaknesses, most serious first:
1. **The audit runs from one laptop.** It needs a Railway CLI login on that laptop. The login expired around 10-21, and no day since has been graded (`docs/daily_audit.md`). The MEXC keys live only in Railway, so the audit cannot read the exchange on its own.
2. **Our record depends on how long MEXC keeps data.** Position history lasts about 90 days and 1-minute bars about 30. Data from July and August, and late-October bars, are already gone (briefing §3–4). We have no durable ledger of our own.
3. **Protection when the process is down is weak.** The exchange-side stop and take-profit are anchored to the signal price, not the fill price, and are never moved after entry. A restart drops the software trail. Deploys that should not have happened restarted the bot with positions open 34 times (`railway.toml` comments, `docs/LIVE_CONFIG.md` §2).
4. **Config sprawl.** About 785 env names exist, 199 are set, and roughly 30 matter. `README.md` is out of date. Nothing caps risk across sleeves, so up to about 12% of the account can be at risk at once (`docs/LIVE_CONFIG.md`).
5. **One venue, one key, one person.** The API key expiring caused an outage on 10-14. The $5 MEXC minimum order means a $35 account cannot produce data.
6. **Underpowered research.** In all 27 trials the standard error was larger than the result (`docs/DECISION_RULE.md`). No trial planned its sample size in advance.

## (b) UK legal and tax constraints (assuming the owner is a UK resident; not confirmed)

- **MEXC excludes the UK.** MEXC's User Agreement ("Last Updated: 12 November 2026") lists "the United Kingdom" under Prohibited Jurisdiction (https://www.mexc.com/terms, read 2026-11-26). An older 2023 version did not list it. The FCA warns that MEXC Global is not authorised and may be targeting UK consumers: no Ombudsman, no FSCS (https://www.fca.org.uk/news/warnings/mexc-global-ltd-https-wwwmexccom, updated 2024-06-03). **Implication:** the account could be frozen and there is no route to recover funds. When and how the account was opened is unknown and needs checking.
- **Crypto derivatives are still banned for UK retail.** This covers futures, CFDs, options and spread bets on crypto, and has applied since January 2021. The FCA confirmed it "will remain in place" when it opened crypto ETNs to retail on 2025-10-08 (https://fca.org.uk/news/press-releases/fca-opens-retail-access-crypto-etns). The new crypto regime starts on 2027-10-25, and the FCA says it keeps derivatives access "under review", which is not a promise to change it (https://www.fca.org.uk/publications/policy-statements/cryptoasset-regime, 2026-06-30). **Implication:** no FCA-authorised firm will sell a UK retail client a leveraged crypto perpetual. Opting up to professional-client status is theoretically possible. Whether the owner qualifies is unknown, and it looks unlikely.
- **Crypto ETNs are legal.** They are available on UK recognised exchanges, with no FSCS cover. They can be held in an ISA or SIPP. Reports disagree on whether they moved from the Stocks & Shares ISA to the Innovative Finance ISA on 2026-04-06, so check HMRC before acting.
- **Tax.** CGT has a £3,000 annual exempt amount and rates of 18% or 24% in 2026/27 (https://www.gov.uk/guidance/capital-gains-tax-rates-and-allowances). HMRC's crypto manual says its guidance "will not generally apply" to crypto derivatives (https://www.gov.uk/hmrc-internal-manuals/cryptoassets-manual/crypto10150). Whether perpetual profits are capital gains or miscellaneous income is **unknown and disputed**, and funding payments are unresolved. Losses may not offset other gains. Spread-bet profits are generally free of CGT, but only on non-crypto assets, and losses cannot be offset (broker guides, e.g. https://www.ig.com/uk/spread-betting/spread-betting-vs-cfds/tax, so not primary sources).
- **Wrappers.** The Stocks & Shares ISA allowance is £20k a year, and from April 2027 the cash ISA is capped at £12k (https://www.gov.uk/government/publications/fiscal-events-2026-factsheets/isa-reform-2027-anti-circumvention-rules-factsheet). Gains inside an ISA or SIPP are tax-free, a guaranteed 18–24% head start over taxable trading.
- **Other people's money.** Running other people's accounts (an aim in `docs/MULTI_ACCOUNT_DESIGN.md`) would be FCA-regulated "managing investments". Do not go there without legal advice.

**Bottom line:** any "edge" has to be measured **after tax and inside a legal wrapper**, against a global index fund held in an ISA. On that test the current MEXC setup starts at a structural disadvantage.

## (c) Target architectures

**A — Crypto research lab, paper trading only.** Keep the detectors. Feed public market data into our own append-only store (Parquet or SQLite on cloud storage). Run Approach-2 replays and a paper ledger, with the audit on a cloud scheduler. No real money until a pre-registered, powered test passes on the locked holdout.
*Pros:* reuses the code, cheap, no legal exposure. *Cons:* no returns, and a proven edge still has no legal UK venue.

**B — UK-legal systematic allocator.** A low-frequency rules engine covering global ETFs, gilts and crypto ETNs, using trend, momentum and volatility targeting, rebalanced weekly or monthly inside an ISA or SIPP. Trades go through an FCA-authorised broker with an API (candidates to be checked: IBKR UK and others). Every order needs human approval.
*Pros:* legal, tax-free, scalable, and a realistic chance of beating fund fees. *Cons:* the edge is modest and well known, and the broker integration is new work.

**C — Hybrid.** Make B the capital engine, and run A beside it on the same market-data store, ledger and reporting. A research idea gets real money only after passing the holdout, and only on a venue that is legal for the owner.
*Cons:* two products to maintain. Mitigation: they share the Market, Account and Event layers already drafted in `MULTI_ACCOUNT_DESIGN.md` §3.

## (d) Guidance for developers and the functional lead

- **Developers:** (1) Make no new real-money changes on MEXC until the owner has resolved the UK point. (2) Move the audit and evidence archive off the laptop onto a cloud scheduler, with its own read-only credentials and an alert when it fails. (3) Build our own durable ledger of fills, funding and fees, plus market bars, so we stop losing history. (4) Split `runtime.py` along the Market / Account / Event seam, so paper, live and other brokers share one code path. (5) Cut the env vars down to the roughly 30 that matter, and fail loudly on any unknown name.
- **Functional lead:** (1) Every report shows net-of-fees, net-of-tax return against a benchmark, a global tracker held in an ISA. (2) Produce a tax-ready export: disposals, funding and fees per tax year. (3) Before each trial, add a sample-size calculation that says how many trades are needed to tell an edge from noise. (4) Make the kill-switch and budget-floor behaviour explicit and testable for QA.

## My position for the meeting

**Hybrid (C), with real-money crypto futures paused.**
Trading MEXC perpetuals from the UK is now against the venue's own terms and outside FCA protection, and 27 trials have shown no edge, so more live tuning is the wrong risk.
Keep the futures code as a paper research lab, and build the real-money side as a UK-legal, tax-wrapped systematic allocator benchmarked against an index fund.
