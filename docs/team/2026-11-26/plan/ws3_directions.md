# WS3: Candidate directions for the next project

Author: Researcher, 2026-11-26. Status: recommendation for the owner's decision. This is research, not personal financial advice.
Inputs: `30_meeting_minutes.md` (Option B, pass bar), `03_researcher.md`, `05_dev2.md`, `02_architect.md`, `plan/ws1_lessons_playbook.md`. Web sources at the end, with dates.

## The question
The owner will not touch the futures bot again and wants the experience reused. Which next project gives a one-person, small-capital, UK-resident operation the best chance of an honest, lawful result? Every option is judged against the benchmark set in the minutes: **SWDA (iShares Core MSCI World, 0.20%/yr [1]) held in a Stocks & Shares ISA, after fees and tax.** Cash (about 4%) is the floor.

## Four directions compared

| | 1. Systematic allocator in ISA/SIPP (meeting's Option B) | 2. Plain tracker + owner card | 3. Tracker + off-the-shelf trend ETF | 4. Spot-crypto trend sleeve |
|---|---|---|---|---|
| What it is | SWDA-style core plus a rules-based trend/momentum overlay (equities, gilts, gold, cash), checked monthly | Buy SWDA (or similar) monthly; our tooling only reports and alerts | Core tracker plus 10-20% in a listed managed-futures UCITS ETF | BTC/ETH held only while trending, cash otherwise; at most 5% of the total |
| Return/drawdown evidence | Faber's 10-month rule, out of sample 2006-16: 8.5%/yr vs 7.7%, max fall 16.7% vs 51%, but **trailed stocks in 6 of 8 years after 2009** [2]. An independent test on 1927-77 found it no better than a fixed 60/40 [3]. Trend worked in 8 of the 10 worst 60/40 drawdowns since 1880, with its own falls of ~25% [4] | MSCI World 12.6%/yr over 10 yrs to Jul 2026 [5]; falls of ~34% (2020) [6]. Forward 10-yr projections are lower, ~4-7%/yr [7] | SG Trend Index −20.4% May 2024-May 2025 [8], +2.4% in 2025 [9]. DBMF UCITS line listed in London only on 10 Sep 2025 [10], so its UK track record is short | Strong time-series momentum in BTC/ETH/XRP (Liu & Tsyvinski, RFS 2021) [11]; peer-reviewed crypto trend factor (JFQA) [12]. A 50-day filter scored Sharpe 1.9 vs 1.3 for buy-and-hold, 2012-23 (vendor research) [13]. Several studies say out-of-sample is weaker [14] |
| Why an edge might persist | Behavioural under/over-reaction and hedging demand [4]; it is painful to hold through years of lag, which deters arbitrage. But it is published, and published anomalies lose ~58% of their return after publication [15]. **We have no private signal; our advantages are discipline, low cost and tax** | No edge over the market, by design. It beats ~97% of active GBP global funds over 10 yrs [16] | Same as 1, run by a professional for a fee (0.57-0.75%/yr [17][18]) | Crypto is young and retail-driven, so trends may persist longer. Only ~3-4 big cycles since 2013, so few independent episodes, the same small-sample trap as the bot |
| Capital needed | ~£5-10k+, rebalanced quarterly or less often; at £3/trade monthly rebalancing on £5k costs ~4%/yr (`05_dev2.md`) | Any amount | Any amount | Small (a 5% sleeve of £10k = £500), but taxable or SIPP only (see legal row) |
| Legal route (UK) | ETFs/gilts in ISA or SIPP via an FCA-authorised broker (IBKR UK candidate, `05_dev2.md`) | Any ISA platform | ISA eligibility of DBMF/JPM ETFs **unknown**; must check the platform's list [17][18] | Crypto ETNs **cannot be newly bought in a Stocks & Shares ISA since 6 Apr 2026**; only an Innovative Finance ISA, which few or no platforms offer [19][20]. SIPP (if the provider allows) or a taxable account; spot on Kraken/Coinbase is taxable. No FSCS on ETNs |
| Time to first evidence | Backtest on 20+ yrs: ~4-6 weeks of work. Real-money evidence of crash protection: only when a bear market comes, possibly 5-10 yrs | Immediate; nothing to prove | Immediate to buy; years to judge | Backtest: weeks. Proof beyond luck: probably never at this sample size |
| Main risks | Lags SWDA for years (2009-2016 pattern); overfitting; small-account costs; building what an ETF already sells | Equity falls of 30-50%; ~70% US weight (to verify on the factsheet [1]); selling in a crash | Fees; short UK history; trend drawdowns | Falls of 50-80%; each switch is a CGT disposal outside a wrapper; platform/rule changes; it reuses the bot's code, so it is the easiest place to slip back into churn |

### Money arithmetic (playbook Stage 0, at £10k; basis stated)
- **Direction 1:** if it met the minutes' pass bar (at most 1%/yr behind, falls one third shallower), a 34% crash becomes ~23%, saving ~£1,100 once, while the lag costs up to ~£100/yr. That is worthwhile only if the protection is real out of sample.
- **Direction 2:** the certain gains come from wrappers and costs, not signals. An ISA avoids 18-24% CGT above £3,000 (`02_architect.md`). Pension relief at source adds £250 for every £1,000 paid into a SIPP [21]. No strategy we can name reliably adds 25%.
- **Direction 4:** 5% of £10k is £500. Even a perfect trend rule that halved a 60% crash would save ~£150. It is small money for a lot of engineering.

### Ruled out (briefly)
Funding/basis carry pays about cash rates now and is a banned derivative for UK retail. Market making needs latency and rebates. Prediction markets block UK users. Spread betting on indices is legal but leveraged, which is lesson N2/N3 territory (`03_researcher.md` §3; `02_architect.md`).

## Recommendation

**Primary: Direction 1 (Option B), run as "the overlay must earn its place against two cheap alternatives".**
1. Start with the tracker core and the owner card (Direction 2's deliverable). That is useful whatever happens.
2. Pre-register one simple trend rule (for example, the 10-month average on 4-6 ETFs, quarterly rebalancing) using the minutes' bar. **Add a second comparator: SWDA plus a 15% off-the-shelf trend ETF (Direction 3).** If our rule cannot beat that after costs, we buy the ETF or nothing, and build no broker adapter.
3. A crypto sleeve is an optional module of at most 5%, tested inside the same framework. It can live only in a SIPP or a taxable account, and is never a separate project.
4. Honest odds: **I would not put a pass above 50%.** Basis: the 2006-16 out-of-sample evidence would pass the drawdown test, but the 1927-77 test and the 2009-16 lag suggest it may fail "no more than 1%/yr behind" a 100% equity benchmark [2][3].

*Why this and not Direction 2 outright:* it reuses the bot's real assets: the pre-registration and holdout method, luck benchmarks, replay/backtest discipline (L3-L7), the ledger, reconcile and alerting plumbing (`05_dev2.md` §2), and the owner card. A failed test is a cheap, written answer. *Why not Direction 4 as primary:* the legal route is worse since April 2026, the money is small, and the sample is too short to tell skill from luck.

**Fallback: Direction 2, plain tracker + owner card.** It is also the default if Direction 1 fails its bar. It needs no edge, works at any capital, and beats almost all commercial funds [16].

## Is the paper-only futures replay still worth doing?
**Yes, but only the cheap first gate. Then stop unless it passes.**
- It does not touch the bot. It uses public bars and the 235 discovery trades already held.
- **Keep the P2 fidelity check (due 12-06, ~1-2 developer-days).** Its lasting value is not the futures answer. It tests whether our simulator matches reality (lesson L7). We will need that skill to trust any Direction 1 backtest.
- **Do P3-P5 and the single holdout look only if P2 passes, inside the 7-day cap, and never at the expense of the B spec due 12-15.** The result cannot change any money decision: MEXC fails the legal test either way (minutes, Decision §1). Its only purpose is to close the question in writing, so it does not reopen later.
- Side effect: because the bot keeps running, real trades from 10-20 onward keep feeding the holdout. QA 2 should still treat replayed day-blocks as the primary holdout.

## Risks to flag to the owner (not actions for the team)
- The bot keeps trading ~$34.62 on a venue whose terms list the UK as prohibited, with the audit dark since ~10-21. The worst realistic loss is the balance itself. The larger risks are legal/account status and an unattended key or auth failure (incident 10-14). This is the owner's call. The team's recommendation to pause still stands.
- MEXC history (~90 days) and 1m bars (~30 days) keep expiring. Archiving public data (Dev 2, 11-30) protects the research. Exporting private history needs the owner.

## Decisions needed from the owner (at the day-30 point, 12-26)
1. Approve Direction 1 as primary with Direction 2 as fallback (or choose Direction 2 now).
2. Capital range and wrapper for any eventual live stage (ISA, SIPP or both), and the loss cap.
3. Whether a crypto sleeve (at most 5%, SIPP or taxable only) may be tested at all.
4. Whether the futures replay stops after P2 if P2 fails (recommended: yes).

## Sources (accessed 2026-11-26; source dates in brackets)
[1] https://www.ishares.com/uk/individual/en/products/251882/ishares-core-msci-world-ucits-etf-swda (TER 0.20%, net assets to 13 Nov 2026)
[2] https://www.etf.com/sections/index-investor-corner/swedroe-why-financial-trends-persist (Swedroe summary of Faber, JPM 2018; secondary)
[3] https://alphaarchitect.com/2014/09/are-uber-simple-asset-allocation-systems-robust/ (20 Sep 2014)
[4] https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing (Hurst, Ooi, Pedersen, JPM 2017); https://alphaarchitect.com/time-series-momentum-aka-trend-following-the-historical-evidence/
[5] https://www.msci.com/documents/10199/255599/msci-world-index-gbp-net.pdf (data to 31 Jul 2026)
[6] https://chartrow.com/msci-world/drawdown
[7] https://corporate.vanguard.com/content/dam/corp/research/pdf/isg_vemo_2026.pdf (Dec 2025)
[8] https://publishedresearch.cambridgeassociates.com/?p=19140
[9] https://www.toptradersunplugged.com/?p=20381 (Dec 2025 report; secondary, not checked against SG's own data)
[10] https://www.londonstockexchange.com/en/news/new-listings/2025/im-global-partner-and-dbi-celebrate-listing-first-active-ucits-etf-its-kind (10 Sep 2025)
[11] https://econpapers.repec.org/RePEc:oup:rfinst:v:34:y:2021:i:6:p:2689-2727. ; https://nber.org/papers/w24877
[12] https://www.cambridge.org/core/services/aop-cambridge-core/content/view/S0022109024000747
[13] https://research.grayscale.com/reports/the-trend-is-your-friend-managing-bitcoins-volatility-with-momentum-signals (Aug 2023; vendor research)
[14] https://arxiv.org/html/2602.11708v1 ; https://arxiv.org/pdf/2009.12155v1.pdf
[15] https://academicnewsletter.sufe.edu.cn/info/359722 (McLean & Pontiff, J. Finance 2016, abstract)
[16] https://www.spglobal.com/spdji/en/spiva/article/spiva-europe-mid-year-2025
[17] https://www.justetf.com/uk/etf-profile.html?isin=LU2951555585 (DBMF UCITS, TER 0.75%); https://www.ajbell.co.uk/market-research/LSE:DBMF
[18] https://www.justetf.com/uk/etf-profile.html?isin=IE00BF4G7290 (JPM Managed Futures UCITS, TER 0.57%)
[19] https://www.gov.uk/government/publications/amendment-to-individual-savings-account-regulations-2026/individual-savings-account-amendment-regulation-2026 (9 Mar 2026; in force 6 Apr 2026)
[20] https://cointelegraph.com/news/stratiphy-crypto-etns-uk-isa-offering (Apr 2026); https://www.finder.com/uk/share-trading/invest-in/exchange-traded-products/should-you-hold-crypto-etns-in-pension
[21] https://www.gov.uk/tax-on-your-private-pension/pension-tax-relief
