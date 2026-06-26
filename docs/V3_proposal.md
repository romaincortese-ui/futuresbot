I have all the interfaces confirmed. Writing the proposal now.

---

# V3 Strategy Proposal — Cross-Sectional Early-Trend Momentum Bot (MEXC USDT Perps)

> **Honesty banner up front:** every number in Section 3 is fit to one 48h risk-on rally. This is overfit by construction. The R-multiples assume clean trailing fills and 60–70% capture, both optimistic. Treat Section 3 as an *upper-bound illustration of the design's logic*, not an expected forward return. The hard forward-validation gate in Section 5 is non-negotiable before real capital.

---

## 1. Thesis

**V3 is a long-only, BTC-gated, cross-sectional momentum breakout bot that holds a small basket of the strongest liquid movers concurrently.** Instead of trading one name on a round-number cross (the old PMT logic) or hunting microcap extremes (wildcard), V3 every 15 minutes ranks the liquid USDT-perp universe by short-horizon relative strength, and — only when BTC confirms a broad risk-on ignition — goes long the top 3–4 names that are *outperforming BTC* and breaking out on expanding volatility. It banks partials early and trails a runner, then flattens and disarms when BTC tops.

This fits *this* window precisely because the failure was structural, not tactical. The old bot caught only BTC's +1.6% tail, went long the **BNB laggard** (+0.4%, −$19.94 at ~95% balance / x16), shorted a **microcap** (SIREN) into a pump, missed **SOL/XRP/ETH/ZEC** entirely, and over-traded the post-top chop — net **−$25.6 / −26%** in the best possible tape for a trend bot. V3 inverts all four failures by design: (a) **multi-asset concurrency** (3–4 slots, not 1) forces broad participation; (b) **rank-by-relative-strength** mechanically buys the leaders and *forbids* the laggard; (c) a **24h-turnover floor** structurally excludes EVAA/BSB/SIREN; (d) a **regime-roll disarm** stops new entries once BTC stops making highs at the 06-15 15:00 top.

---

## 2. The Core Strategy

### 2.1 Universe (liquid filter) — *likely-general*
Reuse `universe.select_major_usdt_symbols(top_n=15)` and add a hard floor:
- **24h quote turnover ≥ $50M**, **maxLeverage ≥ 25x**, **listed ≥ 14 days**, crypto-only (existing `NON_CRYPTO_BASES` + `state==0`).
- Admits BTC/ETH/SOL/XRP/SUI/ZEC; **structurally excludes** EVAA/BSB/SIREN (sub-$10M turnover).
- Trade only the **top 12–15 by turnover** as the ranking pool. ZEC is the borderline admit (passes turnover here, but its move is news-driven — flagged window-specific).

### 2.2 Regime gate (deploy vs stand aside) — *core fix for over-trading*
Longs are **armed only** when **both** hold on BTC (Min15):
1. **BTC Supertrend(10, 3.5) is green**, AND
2. **BTC printed a fresh 20-bar (5h) Donchian high within the last ~12h** (= confirmed broad risk-on ignition).

When BTC prints **no new Donchian high for ~3h (12 bars)** → **disarm new entries** and collapse to 1 slot. This is the explicit "top detector": it fires at the 06-15 15:00 top and keeps V3 *flat through the 66.1–66.7K pre-FOMC chop*.

### 2.3 Ranking — trade the strongest, never the laggard — *the single highest-impact choice*
Every 15m, across the eligible universe compute **3h ROC** (12-bar return). Eligible = **top 4 by ROC AND positive relative strength vs BTC** (`ROC_asset > ROC_BTC`).
- On this window: ranks **ZEC > SOL > XRP > ETH** at top; **BNB (+0.4%) and DOGE (+1.3%) at the bottom — never selected.**
- This is the mechanical rule that forbids the exact BNB-laggard trade that lost money.

### 2.4 Signal / entry trigger (concrete) — *catch the move early*
Once the gate is open, enter a long on an eligible name when **ALL** fire on a Min15 close:
1. **Close breaks its 20-bar (5h) Donchian high** (no ambiguity — new high or not).
2. **ATR(14) expanded ≥ 25%** vs its value 20 bars prior (contraction → expansion; filters flat-ATR fake-outs).
3. **Bar volume ≥ 1.8× its 20-bar average** (real participation).

This is what enters **near the start of each leg** — the 06-14 18:00 BTC ignition off the flat base, SOL's 06-15 00:00 thrust, ETH's 06-15 13:15 leg — not the tail.

### 2.5 Exit (balanced: partial + trail + top/regime exit) — *bank small wins, leave a runner*
Define **R = entry → initial stop**. Initial stop = swing-low (last Min15 higher-low) **or** 1.5×ATR(22) below entry, whichever is **tighter, but never < 1.0×ATR** (so ZEC-class vol isn't hair-triggered).

Three-part scale-out:
1. **Bank 1/3 at +1R**, move stop on remaining 2/3 to **breakeven** → round-trip protection (the thing SIREN/BNB lacked).
2. **Bank 1/3 at +2R.**
3. **Trail final 1/3 on a Chandelier Exit**: `HighestHigh_since_entry − 3×ATR(22)` (ratchets up only).

**Wide→tight overlay on the runner** (banks near the top):
- Making higher-highs & higher-lows → keep Chandelier at 3×ATR (lets ZEC's 30.7% range run).
- **TOP TRIGGER → tighten to 1.5×ATR** the moment *either*: (a) no new higher-high for **8 bars (2h)** after a fresh high, or (b) a confirmed lower-high prints.
- **HARD EXIT**: close the runner if price **closes below the most recent confirmed higher-low** (market-structure break = trend over).

**Time stop:** not at +1R within **12 bars (3h)** → close at market. Edges are front-loaded; laggard/chop entries get flushed, not bled.

> Rejected: **Parabolic SAR** as the trail — always-on dots whipsaw in exactly the post-15:00 chop. Chandelier + structure-break gives "trail-until-reversal" with far fewer false flips.

### 2.6 Sizing — risk-based and basket-aware — *fix the −$19.94*
- **Per trade:** `risk_controls.risk_capped_contracts(...)` so a 1R stop loses at most **1.0–1.5% of equity** (~$0.75–$1.10 on $74), scaled by `regime_size_multiplier(trend_efficiency(...))` (full size eff≥0.45, 0.25× floor eff≤0.20 — *scaler, never a hard block*).
- **Basket caps (two, independent):**
  - **Aggregate open 1R heat ≤ 4% of equity** (~$3). At 1–1.5%/trade this naturally allows 3–4 longs and throttles the 4th.
  - **Total posted margin ≤ 50–60% of NAV** (never the ~95% the BNB trade used).
- **Correlation backstop:** feed `portfolio_var.check_new_position` an **assumed ρ ≈ 0.7–0.9** among majors in risk-on (do *not* trust a calm-tape estimate) so a 4th co-moving long is sized down or rejected. In a risk-on rally four 1.5% longs behave like **one 6% bet** — the heat cap treats the basket as one position.
- **Leverage 8–12x effective** for liquid majors. Leverage is *not* the source of return here (participation + breadth is); high leverage on a correlated book is how one topping bar becomes a ruin event.

---

## 3. How V3 Would Have Traded This 48h (trade-by-trade, honest estimate)

Assumptions stated plainly: ATR stops ≈ 2–2.5% (ZEC ≈ 4%), **60–70% capture** of each leg via trailing, 1R risk ≈ 1.5% equity ≈ **$1.10/trade**, $74 account, 8–12x. These are optimistic-but-plausible *for a clean trend*; they would not hold in chop.

| Asset | Entry trigger (this window) | Net move | Capture | R-multiple | Est. P&L |
|---|---|---|---|---|---|
| **SOL** | Donchian break on 06-15 00:00 +5.4% leg | +9.5% | ~65% → 6.2% / 2.2% stop | ~2.8R | **+$3.1** |
| **XRP** | Break during early rally | +8.2% | ~65% → 5.3% / 2.2% | ~2.4R | **+$2.7** |
| **ETH** | Break on 06-15 13:15 +5.6% leg | +7.4% | ~65% → 4.8% / 2.2% | ~2.2R | **+$2.4** |
| **ZEC** | Break off washed base 06-14 23:30 (**½ size**, news-vol) | +22.1% | ~55% → 12.2% / 4% stop | ~3R @ 0.5 | **+$1.7** |
| **BTC** (optional) | 06-14 18:00 ignition break off 63.7–64.6K base | +3.0% | ~60% → 1.8% / 1.5% | ~1.2R | **+$1.3** |
| **BNB** | *Ranked bottom — never opened* | +0.4% | — | — | **$0.00** |
| **SIREN/EVAA/BSB** | *Below turnover floor — never armed* | — | — | — | **$0.00** |

**What V3 does at the top:** by 06-15 15:00 BTC stops printing new Donchian highs → **new entries disarmed**; Chandelier trails tighten on the fail-to-make-higher-high → runners exit into the fade; **no chop re-entries** in the 66.1–66.7K pre-FOMC range.

**Estimated book P&L:**
- **Conservative 3-leader book (SOL/XRP/ETH):** ≈ **+$8–9** at 1.5% risk → scale to the research's 3% band ⇒ **~+$19–22 (~+26%)**.
- **Full book (+ZEC +BTC, a couple of re-entries):** **~+$28–38 (~+38–51%)** at the 3% band.

**Versus the actual −$25.6 / −26%, a swing of ~+$54–64.**

> **The honesty caveat that matters most:** the entire basket is **one correlated long bet**. The reason these five rows all win is that *every name trended the same direction off the same driver*. In a chop or risk-off tape the identical breakout logic round-trips, the time-stop bleeds small losses, and the heat cap is what stops a synchronized reversal from compounding. The +$28–38 is the design working *in the regime it was fit to* — not proof of edge.

---

## 4. Architecture & Build Sketch

**Reuse-first. Add only three new things: a breakout-entry signal, a cross-asset breadth/ranking gate, and a 3–4 concurrent-position portfolio cap.**

| Component | Reuses (existing, confirmed) | New work |
|---|---|---|
| **Universe** | `universe.select_major_usdt_symbols(top_n=15)`; `NON_CRYPTO_BASES` filter | Add $50M turnover / maxLev≥25x / age≥14d floor |
| **Ranking + breadth** | `risk_controls.trend_efficiency()` | 3h-ROC cross-sectional rank; `ROC_asset > ROC_BTC`; BTC Supertrend/Donchian regime gate |
| **Entry signal** | `indicators.py` (ATR), bar data | Donchian-high break + ATR-expansion(≥25%) + volume(≥1.8×) trigger |
| **Sizing** | `risk_controls.risk_capped_contracts(contracts, entry_price, sl_price, contract_size, equity_usdt, max_risk_pct)` + `regime_size_multiplier()`; `nav_risk_sizing.compute_nav_risk_sizing` | Aggregate 1R-heat cap (≤4%) + margin cap (≤60% NAV) across slots |
| **Correlation gate** | `portfolio_var.check_new_position()` | Assumed ρ≈0.7–0.9 default for risk-on majors |
| **Exit** | `exits.evaluate_trailing_bar`, `evaluate_profit_lock_bar`, `price_for_margin_pnl_pct`, `partial_bank.py`; `evaluate_stagnation_exit` (→ time stop) | Chandelier(22,3.0/1.5) trail; structure-break hard exit; fail-to-HH top trigger |
| **Circuit breaker** | `drawdown_kill.compute_drawdown_state` (30d/8% throttle, 90d/15% halt) | **Fast intraday breaker**: NAV −6/−8% day or 3 consecutive stops → 1 slot + floor; −12/−15% → halt new entries |
| **Execution / ticks** | `maker_ladder._snap_price`, `runtime._snap_price_to_tick`, `runtime` TICK_SIZE auto-pop from priceUnit on boot; `exchange_spec.validate_specs()` | Register `ExpectedContract` (contractSize/minVol) for SOL/XRP/SUI/ZEC in `DEFAULT_EXPECTATIONS` (currently only BTC/ETH/TAO/SILVER/XAUT/PEPE) |
| **Concurrency** | `config.max_concurrent_positions` (env `FUTURES_MAX_CONCURRENT_POSITIONS`) | Raise **1 → 3–4** (the single most important config change) |

**MEXC execution (hard correctness gate, non-negotiable):** every computed price — breakout entry, +1R/+2R TP levels, Chandelier/structure stop prices from `price_for_margin_pnl_pct` — **must route through `_snap_price` / `_snap_price_to_tick`** before submit, or MEXC rejects with **codes 2015/5003**. `exchange_spec.validate_specs()` must refuse-start on a priceUnit/contractSize/minVol mismatch.

**Scan cadence:** re-rank the universe **every 60–120s on the latest 15m closes**; run a **30s fill/exit lane** through `maker_ladder` so a fresh top-N entry isn't delayed a full bar (catches the 06-14 18:00 ignition within 1–2 bars). **Maker-first entries**, taker-cross fallback; do **not** initiate a momentum long into an adverse funding print near the funding timestamp (round-trip taker at 8–12x ≈ 0.6–1.0% of margin — over-trading the chop is doubly punished).

**Concurrency math on $74:** 3–4 liquid longs at 1–1.5% risk/trade, 8–12x ⇒ ~$20–25 margin each, ≤60% NAV aggregate — feasible without full commitment.

---

## 5. Honest Risks

### 5.1 Overfitting — window-specific vs general
**Likely-general (keep regardless of regime):**
- Turnover-ranked **liquid-only universe** + age/leverage floor.
- **Tick-snapping** + boot spec validation.
- **Relative-strength-vs-BTC leader selection** (rank-as-*filter*).
- **Donchian + ATR-expansion + volume** ignition trigger (contraction→expansion is regime-robust).
- **Chandelier trail + structure-break hard exit + the existence of a time stop.**
- **Risk-capped per-trade sizing**, aggregate-heat budget, `portfolio_var` correlation gate, intraday drawdown breaker.

**Likely window-specific (must NOT ship to real money unvalidated):**
- The **long-only / long-basket bias** (this window was one-directional risk-on).
- **ZEC inclusion** (news-driven relief rally off a washed base — a clean momentum bot ranks it high *only because of the move itself*).
- The exact **constants**: $50M floor level, 8–12x band, 3h/12-bar time stop, 8-bar fail-to-HH window, 1.5× vs 3.0× ATR switch, the breadth-unlock threshold, and **ranking-as-a-standalone-edge at intraday horizon**.
- **Academic flag:** crypto momentum evidence is strong for *time-series*, **weak/regime-dependent for cross-sectional**, and validated at a *weekly* horizon (top-quintile ~69% annualized in-sample 2018–21 but **−2.35% out-of-sample** 2021–22 bear). The intraday application here is **not** academically supported. Ranking-as-selection-filter is defensible; ranking-as-edge is not proven.

### 5.2 Correlation risk (all-longs) — the genuine residual
A basket of 3–4 correlated longs is, on the downside, **one concentrated bet**. If BTC reverses, every long gaps through its stop *together* and slippage stacks — the 4% heat cap can realize as a **6–8% loss** in a fast wick. Mitigations are baked in (margin ≤60% NAV, ρ≈0.8 sizing that refuses phantom diversification, fast intraday breaker that cuts the *whole* basket), but this tail **cannot be fully removed** for a long-only basket — it's the price of broad participation.

### 5.3 Regimes that would hurt this design
- **Sideways chop:** every breakout round-trips; the time stop turns into a steady bleed of small losses + fees. (The regime gate is *supposed* to keep V3 flat here — that's the thing forward-validation must prove.)
- **Sharp synchronized reversal / liquidation cascade:** correlated stops fill worse than 1R; the intraday breaker is the only thing between the book and a ruin event.
- **Low-dispersion tape:** if everything moves together with no clear leaders, the ranking adds no signal and you're just long beta with extra steps.
- **Risk-off / bear:** long-only design stands aside *by construction* (BTC Supertrend red, no Donchian highs) — but if the gate is mis-tuned it bleeds via false ignitions.

### 5.4 Forward-validation gate — HARD, before any real money
This is a 48h fit, not an edge. Required before live capital:
1. **Shadow/paper across ≥2 non-rally regimes** — one **sideways chop** and one **drawdown/risk-off** leg.
2. Confirm empirically that (a) the **regime gate actually stands aside in chop** (few/no entries), (b) the **intraday breaker fires** on a synchronized reversal, and (c) **basket realized drawdown stays within the 4% heat budget** under correlated stops.
3. Do **not** treat 48h P&L as edge under any circumstance.

**Relevant files:** `C:\Users\Rocot\Claude session\futuresbot\futuresbot\` — `universe.py`, `risk_controls.py`, `nav_risk_sizing.py`, `portfolio_var.py`, `exits.py`, `partial_bank.py`, `drawdown_kill.py`, `exchange_spec.py`, `maker_ladder.py`, `runtime.py`, `config.py`, `indicators.py`.