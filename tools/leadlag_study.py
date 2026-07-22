"""Cross-exchange lead-lag study: does Bybit lead MEXC (or vice versa) at 5m
granularity on the convex band's movers? Tests the 'follow the leader at the
perfect moment' hypothesis at a horizon the bot can actually trade.

Per symbol: (a) contemporaneous return correlation; (b) lead-lag correlations
(who moves first); (c) EVENT test — when Bybit jumps >=1% in a 5m bar while
MEXC hasn't moved yet (<0.3%), what does MEXC do next bar(s)? Follow-through
must clear round-trip costs (~0.3%) to be tradable. (d) price-divergence stats.
"""
import json
import os
import time
import urllib.request

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient

SYMS = os.environ.get("LL_SYMS", "AKE_USDT,EVAA_USDT,US_USDT,VELVET_USDT,BANK_USDT,ALLO_USDT,ESPORTS_USDT,BILL_USDT,RAVE_USDT,TAC_USDT,KAITO_USDT,LDO_USDT").split(",")
DAYS = int(os.environ.get("LL_DAYS", "14"))
c = MexcFuturesClient(FuturesConfig.from_env())
now = int(time.time())
START = now - DAYS * 86400


def mexc_5m(sym):
    out = {}
    cur = START
    while cur < now:
        df = c.get_klines(sym, interval="Min5", start=cur, end=min(now, cur + 300 * 1999))
        if df is None or df.empty:
            break
        for t, cl in zip(df.index, df["close"]):
            out[int(t.timestamp())] = float(cl)
        nxt = int(df.index[-1].timestamp()) + 300
        if nxt <= cur:
            break
        cur = nxt
    return out


def bybit_5m(sym):
    out = {}
    cur = START * 1000
    psym = sym.replace("_", "")
    while cur < now * 1000:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={psym}&interval=5&start={cur}&limit=1000"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                rows = ((json.loads(r.read().decode()).get("result") or {}).get("list")) or []
        except Exception:
            return out
        if not rows:
            break
        rows = rows[::-1]  # newest-first -> oldest-first
        for row in rows:
            out[int(int(row[0]) / 1000)] = float(row[4])
        nxt = int(rows[-1][0]) + 300000
        if nxt <= cur:
            break
        cur = nxt
    return out


def corr(xs, ys):
    n = len(xs)
    if n < 30:
        return float("nan")
    mx = sum(xs) / n; my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = sum((a - mx) ** 2 for a in xs) ** 0.5
    dy = sum((b - my) ** 2 for b in ys) ** 0.5
    return num / (dx * dy) if dx > 0 and dy > 0 else float("nan")


print(f"{'symbol':13}{'bars':>6}{'c0':>6}{'B->M':>6}{'M->B':>6}{'|prem|>0.3%':>12}{'events':>7}{'follow1':>9}{'follow3':>9}{'hit%':>6}")
tot_ev = 0; tot_f1 = 0.0; tot_f3 = 0.0; tot_hit = 0
for sym in SYMS:
    m = mexc_5m(sym); b = bybit_5m(sym)
    ts = sorted(set(m) & set(b))
    if len(ts) < 200:
        print(f"{sym:13}  insufficient overlap ({len(ts)})")
        continue
    rm, rb, prem = [], [], []
    for i in range(1, len(ts)):
        t0, t1 = ts[i - 1], ts[i]
        if t1 - t0 != 300:
            rm.append(None); rb.append(None)
        else:
            rm.append(m[t1] / m[t0] - 1)
            rb.append(b[t1] / b[t0] - 1)
        prem.append(abs(b[t1] / m[t1] - 1))
    pairs0 = [(a, x) for a, x in zip(rb, rm) if a is not None and x is not None]
    pairsBM = [(rb[i - 1], rm[i]) for i in range(1, len(rm)) if rb[i - 1] is not None and rm[i] is not None]
    pairsMB = [(rm[i - 1], rb[i]) for i in range(1, len(rb)) if rm[i - 1] is not None and rb[i] is not None]
    c0 = corr([a for a, _ in pairs0], [x for _, x in pairs0])
    cBM = corr([a for a, _ in pairsBM], [x for _, x in pairsBM])
    cMB = corr([a for a, _ in pairsMB], [x for _, x in pairsMB])
    pd = 100.0 * sum(1 for p in prem if p > 0.003) / len(prem)
    # event test: Bybit moved >=1%, MEXC same bar <0.3% -> MEXC next-bar / next-3-bar signed follow
    evs = []
    for i in range(len(rm) - 3):
        if rb[i] is None or rm[i] is None:
            continue
        if abs(rb[i]) >= 0.01 and abs(rm[i]) < 0.003:
            sgn = 1 if rb[i] > 0 else -1
            nxt1 = rm[i + 1]
            nxt3 = [r for r in rm[i + 1:i + 4] if r is not None]
            if nxt1 is None or not nxt3:
                continue
            evs.append((sgn * nxt1, sum(sgn * r for r in nxt3)))
    n_ev = len(evs)
    f1 = sum(e[0] for e in evs) / n_ev * 100 if n_ev else float("nan")
    f3 = sum(e[1] for e in evs) / n_ev * 100 if n_ev else float("nan")
    hit = 100.0 * sum(1 for e in evs if e[0] > 0) / n_ev if n_ev else float("nan")
    tot_ev += n_ev
    if n_ev:
        tot_f1 += sum(e[0] for e in evs); tot_f3 += sum(e[1] for e in evs); tot_hit += sum(1 for e in evs if e[0] > 0)
    print(f"{sym:13}{len(pairs0):>6}{c0:>6.2f}{cBM:>6.2f}{cMB:>6.2f}{pd:>11.1f}%{n_ev:>7}{f1:>8.2f}%{f3:>8.2f}%{hit:>6.0f}")
print(f"\nALL: events={tot_ev} mean follow1={100*tot_f1/max(1,tot_ev):+.3f}% follow3={100*tot_f3/max(1,tot_ev):+.3f}% hit={100*tot_hit/max(1,tot_ev):.0f}% | round-trip cost ~0.30%")
print("B->M = corr(Bybit[t-1], MEXC[t]) — positive means Bybit LEADS. follow1/3 = MEXC's signed move after a Bybit-only jump.")
