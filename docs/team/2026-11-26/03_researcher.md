# Researcher prep memo — 2026-11-26

Web research done 2026-11-26. Dates are the source's own dates. Where I could not verify a number, I say so.

## 1. The benchmark to beat

**What a UK retail investor gets for doing nothing clever:**

| Product | Return | Fee | Bad years |
|---|---|---|---|
| Global index tracker (MSCI World, GBP, net) | **12.6%/yr over 10 yrs**, 11.9%/yr over 5 yrs (to 31 Jul 2026) [1] | ~0.1-0.2%/yr | about −34% in Feb-Mar 2020 (USD measure; GBP figure unknown) [2] |
| Vanguard LifeStrategy 80% (multi-asset) | 10.2%/yr over 10 yrs (to 31 May 2026) [3] | 0.20% OCF [3] | smaller than equities |
| Cash / T-bills | Bank Rate raised to **4%** in Nov 2026 [4] | ~0 | none |
| Active funds | **97%** of GBP global-equity funds lagged their index over 10 yrs (SPIVA, mid-2025) [5] | 0.6-1%+ | as equities |
| Managed futures / trend | SG Trend Index fell **20.4%** May 2024 → May 2025 [6]. Typical systematic-trend fund **−2.3%/yr** over 3 yrs to Aug 2025 [7] | 1-2%+ | long, flat stretches |
| Bitcoin (spot ETN, legal for UK retail since 8 Oct 2025) [8] | very high long-run, but ~**−50%** from the Oct 2025 peak (~$62k on 18 Nov 2026) [9] | 0.05-0.25% [10] | −50% to −80% |

The last 10 years were unusually good for equities. Vanguard's forward-looking 10-year projections (as at Dec 2025, USD) are much lower: 4-5% for US stocks and 4.9-6.9% for non-US [11].

**Benchmark to beat: about 10% a year, after all fees and UK tax, over a rolling 5 years, with a worst fall no deeper than about 35%.** That is roughly what a 0.2% global tracker held in a tax-free ISA has delivered. **The minimum bar is 4% a year (cash).** Anything below 4% is a loss of time and money. For comparison, the bot's lifetime result to 10-06 was −75% money-weighted (`01_pm.md`).

Tax matters. Gains outside an ISA pay 18% or 24% CGT above a £3,000 allowance [12]. A taxable strategy has to earn roughly a fifth more than the ISA tracker just to draw level with it.

## 2. What happens to retail algo and crypto-futures traders

- **Brazil futures day traders who persisted 300+ days: 97% lost money**; about 1% beat the minimum wage [13].
- **Hyperliquid perps, all trades Mar 2025-Jun 2026:** retail-like traders lost about **$1.11bn**, market makers made about $208m, algorithmic takers roughly broke even. Losses came from paying for speed, liquidations and fees [14], the same pattern as ours (fees were 65% of our loss, `01_pm.md`).
- **AI trading bots:** in Alpha Arena (Oct-Nov 2025, real money, crypto perps) most models lost, and GPT-5 lost 62.7%. The organiser said results "may be luck" and that handing money to an LLM "is not yet feasible" [15].
- **UK legality:** crypto derivatives remain banned for UK retail [8]. MEXC Global has been on the FCA warning list since 22 Mar 2024, with no Ombudsman and no FSCS cover [16]. See also `02_architect.md`.

## 3. Edges with real evidence, and whether they fit a one-person, small-capital setup

| Strategy | Evidence | Fit for us |
|---|---|---|
| Factor premia (value, momentum, quality) | Decades of academic support, but can lag for years | Easy to buy cheaply as ETFs. It is not a proprietary edge. |
| Trend-following, multi-asset | Long history of positive returns plus crash protection, but a −20% drawdown in 2024-25 [6][7] | Good, at low frequency (weekly or monthly), ETF-only, inside an ISA |
| Crypto trend / time-series momentum | Peer-reviewed crypto trend factor (JFQA, Nov 2025) [17]. Many preprints claim Sharpe 1.5-2.5, but several warn that out-of-sample results are weaker [18] | Promising on **spot** BTC/ETH ETNs: hold when trending, cash otherwise. The main benefit is avoiding −50% years. |
| Funding-rate / basis carry | Ethena's sUSDe yield fell from 20%+ to about 3.5-4.5% as the trade got crowded [19]. Returns have converged towards T-bill rates [20] | **No.** It pays about the same as 4% cash, carries exchange risk, and is a banned derivative for UK retail. |
| Market making | Market makers do win on Hyperliquid [14], but it needs low latency and fee rebates | **No** for retail. Home latency and taker fees rule it out. |
| Prediction markets | Mispricings are documented | **Not now.** Polymarket and Kalshi block UK users. The Gambling Commission says a licence is needed (Feb 2026). The FCA was only "weighing" a change (Sep 2026) [21]. Watch-list only. |

## 4. Where things are heading (2025-2026)

- **Crypto is mainstream and cheap to hold**: UK ETN fees down to 0.05% [10]; ISA treatment is changing (check HMRC) [8].
- **Easy crypto carry has been arbitraged away** by institutions [19][20].
- **AI is a research assistant, not a trader** (see Alpha Arena). Vanguard calls AI exuberance the main 2026 market risk [11].
- **Edge is moving to infrastructure** (speed, rebates, data). Our realistic advantages are discipline, low cost and tax efficiency.

## 5. Shortlist: 3 most promising directions

1. **UK-legal systematic allocator in an ISA or SIPP.** A global tracker forms the core, plus a trend and momentum overlay across equity ETFs, gilts, gold and crypto ETNs, rebalanced monthly. *Needs:* an FCA-authorised broker with an API (to be checked), an ISA, at least about £5k so fees stay small, 20+ years of daily data, and pre-registered rules tested against the tracker after fees and tax.
2. **Crypto trend sleeve on spot BTC/ETH ETNs, 5-15% of the portfolio:** in when trend is up, in cash when it is down. *Needs:* the same broker, a published rule tested out of sample on 2018-2026 data, and an honest goal of a smaller drawdown than buy-and-hold rather than beating it every year.
3. **Futures research lab, paper only.** Run Approach 2 replay once, test it against the locked holdout, with a 30-day kill date. *Needs:* no new money and a durable data store. If it ever passed, it would still need a legal venue, so it is an option, not an income source.

## My position for the meeting

**Pivot, keeping the futures bot only as a 30-day paper experiment.**
The evidence says retail perp traders lose and carry no longer pays, and for UK retail this product is banned and the venue unprotected.
The beatable target is about 10% a year net in an ISA. Our skills (discipline, holdouts, automation) are best spent on a legal, low-cost systematic allocator.

## Sources (accessed 2026-11-26)
[1] https://www.msci.com/documents/10199/255599/msci-world-index-gbp-net.pdf (MSCI factsheet, data to 31 Jul 2026)
[2] https://chartrow.com/msci-world/drawdown
[3] https://www.ajbell.co.uk/market-research/sub/FUND:B4PQW15/charts-performance ; https://fund-docs.vanguard.com/Global_LifeStrategy_80_Equity_Fund_E137_GBP_EN_UK.pdf
[4] https://www.bankofengland.co.uk/monetary-policy-report/2026/November-2026
[5] https://www.spglobal.com/spdji/en/spiva/article/spiva-europe-mid-year-2025
[6] https://publishedresearch.cambridgeassociates.com/?p=19140
[7] https://www.morningstar.com/alternative-investments/managed-futures-funds-look-rebound-can-they-help-diversify-your-portfolio
[8] https://www.fca.org.uk/news/press-releases/fca-opens-retail-access-crypto-etns (8 Oct 2025)
[9] https://en.coinotag.com/bitcoin-btc-falls-below-half-of-record-high (18 Nov 2026)
[10] https://cointelegraph.com/news/uk-crypto-etn-fee-war-after-rule-change
[11] https://corporate.vanguard.com/content/dam/corp/research/pdf/isg_vemo_2026.pdf (Dec 2025)
[12] https://www.gov.uk/guidance/capital-gains-tax-rates-and-allowances
[13] https://ideas.repec.org/p/fgv/eesptd/525.html (Chague, De-Losso, Giovannetti, 2019/2020)
[14] https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2026.36 (Jia, Moallemi et al., AFT 2026)
[15] https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/ ; https://news.bloomberglaw.com/banking-law/ai-bots-auditioning-for-wall-street-trading-are-mostly-losing
[16] https://www.fca.org.uk/news/warnings/mexc-global-ltd-https-wwwmexccom (updated 3 Jun 2024)
[17] https://www.cambridge.org/core/services/aop-cambridge-core/content/view/S0022109024000747
[18] https://arxiv.org/html/2602.11708v1 ; https://arxiv.org/pdf/2009.12155v1.pdf
[19] https://messari.io/report/ethena-s-next-act
[20] https://blockworks.com/newsletter/the-breakdown/issue/post_999b16ee-0fe0-4631-a1d0-2aa15a1d18a7
[21] https://www.gambling.com/uk/news/are-prediction-markets-legal-in-the-uk ; https://www.cryptotimes.io/2026/09/08/uk-fca-reviews-prediction-markets-as-kalshi-polymarket-gain-ground/
