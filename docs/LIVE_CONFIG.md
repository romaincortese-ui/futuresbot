# Live configuration — snapshot 2026-08-29

199 non-secret variables are set on Railway. **About 30 change live behaviour.** The rest
are inert (sleeves that are off), dead (never read), or actively misleading. This maps
what is set onto what the bot actually does, and is written from source rather than from
the variable list.

Trial 18 is running: `FUTURES_REGIME_FLOOR_MULT=0.50` and
`FUTURES_CONVEX_TRAIL_RETAIN_FRAC=0.50`, opened 2026-08-29 00:37Z.

---

## What actually trades

| sleeve | live | slots | direction | universe |
|---|---|---|---|---|
| **WILDCARD** | **yes** | **3** | LONG **and SHORT** | all crypto `*_USDT` perps outside the top 24 by turnover |
| **TREND** | **yes** | **2** | long only | `ETH_USDT, XRP_USDT, ZEC_USDT` |
| SQUEEZE | no | — | — | `FUTURES_SQUEEZE_ENABLED=0` |
| SNIPER | no | — | — | `FUTURES_SNIPER_ENABLED=0` |
| PMT | entries off | — | — | killed by `FUTURES_ENTRY_MIN_SCORE=1000` |
| BREAKAWAY | dead | — | — | reads ON, cannot fire |

**The real concurrency ceiling is 5 positions, not 3.** `FUTURES_MAX_CONCURRENT_POSITIONS=2`
does *not* bind the convex sleeves — it gates only the dead PMT path. There is no
cross-sleeve concurrency check and no portfolio-level margin or VaR cap anywhere on the
convex path. Five simultaneous positions at ~2.41% risk each is ~12% of the account at
risk at once.

**PMT is off only for ENTRIES.** The PMT exit stack manages 100% of live positions — a
wildcard's software stop lives inside a function called `_pmt_hard_exit`.

---

## 1. Entry — the wildcard funnel, in the order the code applies it

| # | filter | value | source |
|---|---|---|---|
| 1 | scan interval | 450s | `FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS` |
| 2 | free margin > 0 | hard guard | code — **scan dies silently at zero, no log, no telemetry** |
| 3 | `*_USDT` only | — | code |
| 4 | crypto only | tradfi tags + prefix list | code |
| 5 | symbol not already held | — | code |
| 6 | **exclude top 24 by turnover** | 24 | code default (`EXCLUDE_TOP_TURNOVER`) |
| 7 | turnover floor | **$2M** | `MIN_TURNOVER_USDT` — *code default is $3M; env is looser* |
| 8 | 24h range | **8%** | range pre-filter |
| 9 | top N by range scanned | 90 | `MAX_SCAN` — *code default 25* |
| 10 | signal: \|3h ROC\| ≥ 8% | 0.08 | `MIN_ROC` |
| 11 | pullback-then-resume | on | code default — **rejects ~76% of triggers, never measured** |
| 12 | calm-shock ratio | 0.75 | `MAX_CALM_RATIO` — equals code default, so setting it is a no-op |
| 13 | external cross-exchange veto | on | `EXTERNAL_GATE_ENABLED` |
| 14 | free slot (of 3) | 3 | `MAX_POSITIONS` — *code default 2* |

Turnover ranking is **deflated**: `amount24 × min(1, median(7 prior days)/trailing 24h)`,
so a one-day spike cannot promote a small cap into the excluded band. The deflator
fails **open** to 1.0 on kline errors — if every symbol reads 1.000 the ranking has
silently reverted to raw turnover.

---

## 2. Exit stack — precedence, per ~1s tick

Only **four** software exits are reachable for a convex position:

| order | exit | trigger | tuning |
|---|---|---|---|
| 1 | **convex retention trail** | peak ≥ 1.0R, then floor at 0.50 × peak; above 3R the floor ratchets to 0.75 × peak | `CONVEX_TRAIL_ARM_R` 1.0, `RETAIN_FRAC` **0.50**, `RATCHET_R` 3.0, `RATCHET_RETAIN` 0.75 |
| 2 | **time stop** | 24h since entry | `CONVEX_TIME_STOP_HOURS` 24 |
| 3 | hard SL | −1R, stop = 3.0 × ATR14(15m) capped at 20% of margin | `SL_ATR_MULT` 3.0, `MAX_SL_MARGIN_PCT` 20 |
| 4 | TP | +5R wildcard / +3R trend | `WILDCARD_TP_R` 5.0, `TREND_TP_R` 3.0 |

Plus **exchange-side TP/SL** attached at entry, and the wildcard **preempt** (evicts a
wildcard below +0.3R, min age 15 min, ≤6/day; a TREND position is never preempted).

Three things worth knowing about this stack:

- **The hard stop is evaluated LAST.** On a tick where both the trail and the stop are
  eligible, the trail wins.
- **The exchange TP/SL is anchored to the SIGNAL price, not the fill**, and is never
  moved after entry. If the Railway process is down, that original −1R/+5R bracket is
  the *only* protection. Convex has no fill-anchored bracket; PMT does.
- **Nothing banks profit before the trail floor.** No breakeven arm, no partial, no
  profit lock — all dead for convex (see §5).

---

## 3. Sizing chain — order of operations

```
available free margin  (NOT equity — 1R shrinks as slots fill)
  -> leverage = floor(20 / (3 x ATR% x 100)), clamped 1..5      <- an OUTPUT, not a dial
  -> margin targeted at 2.41% risk                              FUTURES_WILDCARD_RISK_PCT
  -> cap: 25% of available                                      MAX_MARGIN_PCT 0.25
  -> x regime efficiency scaler, floor 0.50                     REGIME_FLOOR_MULT (trial 18)
  -> int() contract truncation                                  ~6% mean loss, measured
  -> cap: 1R <= 5% of available                                 MAX_TRADE_RISK_PCT 5
  -> min_vol skip
  -> exchange balance guard, then exchange-confirmed volume
```

- **`FUTURES_WILDCARD_LEVERAGE=5` is a seed, not a setting.** Real leverage is derived
  from ATR to keep the stop inside the 20% margin cap, and lands at 1–4× in practice.
- **Risk is a % of *available* margin, not equity.** The third concurrent position sizes
  off a smaller base than the first, so "fixed dollar 1R" is not true.
- `RISK_PCT=0.0241` is **29% above** the 0.0187 code default.
- **No streak throttle** (`CONVEX_STREAK_THROTTLE_ENABLED=0`) and **no drawdown brake**
  on the live path.

---

## 4. Safety — what is actually protecting the account

| control | status |
|---|---|
| **equity drawdown brake** | **NONE.** `FUTURES_CONVEX_DRAWDOWN_BRAKE` is unset → False. This is the only route from the convex sleeves to the drawdown kill. |
| `USE_DRAWDOWN_KILL=1` | **misleading** — set, printed at boot among "overlays actually live", structurally unreachable |
| `IGNORE_HALT=True` | armed but neutralised by `FUTURES_ALLOW_LIVE_HALT_OVERRIDE=false` in live mode |
| external cross-exchange gate | **live** — fails open on venue errors, fails **closed** when Bybit says "not listed" and the OKX fallback throws |
| 25%-of-balance margin cap | live |
| 5%-of-available 1R cap | live |
| regime size scaler | live |
| streak throttle, liq buffer, portfolio VaR, session leverage caps | all off |
| `FUTURES_RESUME_ON_BOOT=1` | **a restart silently undoes `/pause`** |

---

## 5. Reads ON, does nothing

The whole profit-lock / breakeven / micro-lock family is unreachable for convex sleeves —
`_skips_discretionary_locks` short-circuits the locks and `_pmt_hard_exit` returns before
the rest. These are set on Railway and do nothing:

`FUTURES_BREAKEVEN_ARM_PCT`, `FUTURES_BREAKEVEN_FLOOR_PCT`, `FUTURES_PROFIT_LOCK_*` (4),
`FUTURES_PMT_PROFIT_LOCK_*` (6), `FUTURES_PMT_EXCHANGE_PROFIT_LOCK_*` (3),
`FUTURES_ADVERSE_PEAK_TRAIL_TRIGGER_PCT`, `FUTURES_NO_PROGRESS_EXIT_*` (2),
`FUTURES_STAGNATION_EXIT_*`, `FUTURES_MARGIN_LOSS_EXIT_ENABLED`,
`FUTURES_PMT_STOP_CHASE_*`, `FUTURES_ROUND_LEVEL_ENABLED`, `FUTURES_BREAKAWAY_*`,
`FUTURES_OPPORTUNITY_BUCKET_SIZING_ENABLED`, `NAV_LEVERAGE_*`, `SESSION_*_LEVERAGE_CAP`.

Also dead: **`FUTURES_WILDCARD_MIN_24H_MOVE=0.03`** — unread while the range pre-filter is
on. The variable list reads like a 3% gate; the live gate is **8%**.

---

## 6. Landmines — one flag from harm

Both of the first two are now announced at boot with a loud `[BOOT] WARNING`, and
pinned by `tests/test_exit_stack_guards.py`. Before 2026-08-29 nothing in the suite
failed when either was cleared -- the suite's own default posture was the dangerous
configuration, so 1046 tests stayed green while live trades would have been cut.

| variable | why it matters |
|---|---|
| **`FUTURES_WILDCARD_CONVEX_EXIT_ENABLED=1`** | **Code default is FALSE.** Gates the retention trail (runtime.py:1933), the 24h time stop (1855) AND `_skips_discretionary_locks` (1496). Clearing it removes two of the four live exits and re-arms the margin-percent profit-lock and micro-lock stack, on WILDCARD, SQUEEZE **and TREND** despite the name. Same blast radius as `FUTURES_STRATEGY_MODE`, and it was undocumented until 2026-08-29. |
| **`FUTURES_STRATEGY_MODE=pmt_threshold`** | Looks like leftover PMT config. It is **the only thing keeping the legacy exit stack off the wildcard**. Clear it and a 1.5%/30-minute no-progress exit starts cutting convex trades at ~−0.1R. Most dangerous tidy-up target in the file. |
| `FUTURES_ENTRY_MIN_SCORE=1000` | The only thing disabling PMT entries. Code default is 0.0 = fully enabled. |
| `FUTURES_MIN_RISK_PCT / MAX_RISK_PCT = 0.10 / 0.20` | 10–20% risk per trade — the ruin zone this project already measured. Held off only by the PMT gate above. |
| `FUTURES_FULL_BALANCE_SIZING_ENABLED=1` + `RISK_PCT=1.0` | 100% risk sizing, armed, inert only because PMT entries are off. |
| `FUTURES_SNIPER_ENABLED=0` | `SHADOW_ONLY=0` and `LIVE_VARIANTS=FAST` are already set — one flag from real orders, at `MAX_NOTIONAL_PCT=5`. |
| `FUTURES_STRATEGIES_RETIRED=0` | Setting to 1 disables **every** software exit — trail, clock and stop — leaving only the exchange bracket. |
| `IGNORE_HALT=True` | Harmless today; becomes a full halt bypass the moment the brake is wired and the override flag flips. |

---

## 7. Known inconsistencies

- **Shadow ledger scores counterfactuals at retain 0.30 while the live trail runs 0.50.**
  Every counterfactual produced since 2026-08-29 compares against the wrong arm.
- **`FUTURES_TREND_SYMBOLS = ETH, XRP, ZEC`** — the sleeve was designed, sized and
  measured on BTC/ETH/SOL. Two of three live symbols are off-spec and two measured ones
  are absent.
- **`FUTURES_TREND_MAX_POSITIONS=2`** while the sleeve's own docstring says 3 slots beat 2
  on both return and drawdown.
- `accounts.py` carries a second, disagreeing source of truth for sleeve enablement and
  slot caps. Dead, but it disagrees with the live one.
- Values captured from `railway variables` are **truncated by table width**. Anything
  ending mid-token here was re-read in-process; treat any other long value with suspicion.

---

## 8. What changes when $900 lands on Friday

Sizing is proportional, so **1R goes from ~$4.19 to ~$21** — the 7-day test runs at
roughly **5× the absolute dollar risk of trial 18 on identical settings**, with five
possible concurrent positions and no portfolio cap. The drawdown guard staged in
`tools/open_funding_guard.sh` is the only thing that changes that, and it is not applied
yet (see `DECISION_RULE.md`, funding gate).
