#!/usr/bin/env python3
"""V0 exit-gate: replay real fills minute-by-minute under the CURRENT exit
stack vs a CANDIDATE parameterization, scored in dollars.

This is the standing exit/sizing gate (replaces the bar-resolution engine for
exit-side changes): real entries, real Min1 paths, fee-aware. Usage:

  PYTHONPATH=. python tools/replay_exits.py --hours 168 \
      --candidate "FUTURES_PMT_STOP_FIRST_LOW_TIER_RISK_BUDGET_MARGIN_PCT=10,FUTURES_COLD_STREAK_FACTOR=0.5"

Candidate keys understood (subset relevant to exit/sizing replay):
  low_tier_budget (margin %% for score<95), base_budget, arm_r, floor_r,
  floor_cost_mult, pullback, bank_fraction, bank_trigger_r, tp_r,
  runner_lock_arm_r (>=95 tier), cold_streak_n, cold_streak_factor.
Scores per trade are taken from --scores SYM:TIME:SCORE overrides or assumed
sub-95 (conservative) when unknown.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient

FEE_LEG = 0.000594  # measured per-leg taker rate
SYMS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "SEI_USDT", "ZEC_USDT"]


def _g(p, *ks):
    for k in ks:
        if k in p and p[k] is not None:
            return p[k]
    return None


def pull_fills(client, hours: float):
    now = int(time.time() * 1000)
    fills = []
    for s in SYMS:
        for p in (client.get_historical_positions(s, page_size=30) or []):
            ot = int(_g(p, "createTime") or 0)
            if now - ot <= hours * 3600 * 1000:
                pr = _g(p, "profitRatio")
                realised = float(_g(p, "realised") or 0)
                margin = abs(realised) / abs(float(pr)) if pr and float(pr) != 0 else 55.0
                fills.append({
                    "symbol": s, "open": float(_g(p, "openAvgPrice")),
                    "side": 1 if int(_g(p, "positionType")) == 1 else -1,
                    "lev": float(_g(p, "leverage")), "margin": margin,
                    "ot_s": ot // 1000, "realised": realised,
                })
    return sorted(fills, key=lambda f: f["ot_s"])


def bars_for(client, fill, window_h=24):
    df = client.get_klines(fill["symbol"], interval="Min1", start=fill["ot_s"], end=fill["ot_s"] + 3600)
    df2 = client.get_klines(fill["symbol"], interval="Min15", start=fill["ot_s"] + 3600, end=fill["ot_s"] + window_h * 3600)
    out = []
    for d in (df, df2):
        if d is None or not len(d):
            continue
        out += [(float(h), float(l), float(c)) for h, l, c in zip(d["high"], d["low"], d["close"])]
    return out


def atr_pct_at(client, fill):
    pre = client.get_klines(fill["symbol"], interval="Min15", start=fill["ot_s"] - 20 * 900, end=fill["ot_s"])
    if pre is None or len(pre) < 6:
        return None
    H = [float(x) for x in pre["high"]]
    L = [float(x) for x in pre["low"]]
    C = [float(x) for x in pre["close"]]
    trs = [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, len(C))]
    return (sum(trs) / len(trs)) / fill["open"]


def simulate(fill, bars, atr_pct, P, score, streak):
    """Replay one fill under parameter set P. Returns net $ and exit kind."""
    o, fav = fill["open"], fill["side"]
    budget = P["low_tier_budget"] if score < 95 else P["base_budget"]
    stop_frac = 3.0 * atr_pct
    lev = min(25.0, max(1.0, (budget / 100.0) / stop_frac))
    one_r = stop_frac * lev * 100.0          # margin % at stop
    margin = fill["margin"]
    if streak >= P["cold_streak_n"]:
        margin *= P["cold_streak_factor"]
    rt_fee = 2 * FEE_LEG * lev * 100.0
    if score < 95:
        arm = P["arm_r"] * one_r
        floor = max(P["floor_r"] * one_r, P["floor_cost_mult"] * rt_fee)
    else:
        arm = P["runner_lock_arm_r"] * one_r
        floor = 0.5 * P["tp_r"] * one_r
    peak, banked = -99.0, False
    result_r = None
    for h, l, _c in bars:
        # favorable excursion uses the bar extreme in the trade's direction
        hi = ((h - o) / o if fav > 0 else (o - l) / o) * lev * 100
        lo = ((l - o) / o if fav > 0 else (o - h) / o) * lev * 100
        stop = -one_r
        if peak >= arm:
            stop = max(floor, peak * (1 - P["pullback"]))
        if lo <= stop:
            result_r = stop / one_r
            break
        if not banked and hi >= P["bank_trigger_r"] * one_r:
            banked = True
        if hi >= P["tp_r"] * one_r:
            result_r = P["tp_r"]
            break
        peak = max(peak, hi)
    if result_r is None:
        result_r = 0.0  # timeout flat-ish (conservative)
    gross_pct = (0.5 * P["bank_trigger_r"] + 0.5 * result_r) * one_r if banked else result_r * one_r
    net = margin * (gross_pct - rt_fee) / 100.0
    sl_hit = (not banked) and result_r <= -0.99
    return net, sl_hit


DEFAULTS = dict(base_budget=20.0, low_tier_budget=20.0, arm_r=0.30, floor_r=0.15,
                floor_cost_mult=1.5, pullback=0.30, bank_trigger_r=1.0, tp_r=5.0,
                runner_lock_arm_r=4.0, cold_streak_n=99, cold_streak_factor=1.0)


def run(hours: float, candidate: dict, scores: dict):
    client = MexcFuturesClient(FuturesConfig.from_env())
    fills = pull_fills(client, hours)
    base = dict(DEFAULTS)
    cand = dict(DEFAULTS); cand.update(candidate)
    tot_b = tot_c = 0.0
    streak_b = streak_c = 0
    print(f"fills replayed: {len(fills)} (window {hours:.0f}h)")
    for f in fills:
        bars = bars_for(client, f)
        ap = atr_pct_at(client, f)
        if not bars or ap is None:
            continue
        sc = scores.get(f"{f['symbol']}:{f['ot_s']}", 93.0)
        nb, slb = simulate(f, bars, ap, base, sc, streak_b)
        nc, slc = simulate(f, bars, ap, cand, sc, streak_c)
        streak_b = streak_b + 1 if slb else 0
        streak_c = streak_c + 1 if slc else 0
        tot_b += nb; tot_c += nc
        when = datetime.fromtimestamp(f["ot_s"], timezone.utc).strftime("%m-%d %H:%M")
        print(f"  {when} {f['symbol']:9} score~{sc:.0f} | current ${nb:+7.2f} | candidate ${nc:+7.2f}")
    print(f"\nTOTAL  current ${tot_b:+.2f}  candidate ${tot_c:+.2f}  delta ${tot_c - tot_b:+.2f}")
    return tot_c - tot_b


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=168)
    ap.add_argument("--candidate", default="", help="k=v,k=v overrides of DEFAULTS keys")
    ap.add_argument("--scores", default="", help="SYM:epoch:score,... known entry scores")
    a = ap.parse_args()
    cand = {}
    for kv in a.candidate.split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            cand[k.strip()] = float(v)
    scores = {}
    for it in a.scores.split(","):
        parts = it.split(":")
        if len(parts) == 3:
            scores[f"{parts[0]}:{parts[1]}"] = float(parts[2])
    run(a.hours, cand, scores)
