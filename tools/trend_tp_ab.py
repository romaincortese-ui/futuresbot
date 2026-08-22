"""Is the TREND sleeve's 3R target leaving money on the table?

    railway run --service Futures-bot python tools/trend_tp_ab.py

FUTURES_TREND_TP_R=3.0 while the wildcard runs to 5R. The 3R was a design choice
carried in when the sleeve was built on 2026-08-20 and never measured. Trial 15
suggests it BINDS: ZEC closed +2.98R and XRP closed +2.98R, which is a 3R target
net of cost, on a sleeve that went 7/7 and carried 76% of the trial's P&L.

Two reasons this is worth asking NOW rather than earlier:

  1. The trend sleeve's whole job is riding a sustained move on a major. Capping
     it at 3R is the opposite of that thesis, and the wildcard — which hunts a
     3-hour impulse, a far shorter-lived thing — is allowed 5R.
  2. The retention ratchet shipped today changes the trade-off. Above a 3R peak
     the floor is now 0.75 x peak, so reaching for a further target risks much
     less than it did under the flat 0.30 floor: the downside of NOT taking 3R is
     now bounded near 2.25R instead of 0.9R.

So the sweep runs with the ratchet in force, which is the live exit stack.

RESULT, 2026-08-22 -- 70 symbols, 208 days, 1002 trend candidates.
KEEP 3R. The cap binds, and widening it does not survive the half-split.

     trend TP     book $     vs 3R   pos wk  trend n   trend $   TP hit    recent     older
         3.0R    +410.28     +0.00   17/29       172   +192.74    17.4%     +0.00     +0.00
         4.0R    +413.39     +3.11   19/29       165   +195.85     6.1%    -19.36    +22.47
         5.0R    +417.63     +7.35   19/29       163   +200.09     3.1%    -16.40    +23.75
         6.0R    +427.76    +17.48   19/29       164   +210.22     2.4%    -21.70    +39.18
         8.0R    +425.97    +15.69   19/29       165   +208.43     1.2%    -21.70    +37.39

THE CAP IS REAL: TP completion falls 17.4% -> 6.1% the moment the target moves to
4R, so at 3R a meaningful share of trend trades are genuinely being stopped at
the target rather than running out of move. Trial 15 showed the same thing live —
ZEC and XRP both closed +2.98R, which is a 3R target net of cost.

AND WIDENING IT STILL DOES NOT PAY. Every wider target is NEGATIVE in the recent
half (-$16 to -$22) and positive in the older one, so all four fail the
half-split. The +$17.48 headline at 6R is ~$2.5/month over 208 days and comes
entirely from the older half.

The mechanism is the retention ratchet shipped the same day: above a 3R peak the
floor is 0.75 x peak, so a trade that would have run past 3R now gets banked near
its high by the trail instead of by the target. The runway a wider TP opens is
already being harvested — TP completion at 6R is 2.4%, meaning the target is
almost never the thing that closes the trade. Moving it mostly swaps a certain
3R for a trail exit at a similar level, plus variance.

ONE HONEST TENSION: positive weeks IMPROVE 17/29 -> 19/29 at every wider target.
Consistency and total dollars disagree here. The half-split is the tiebreaker
that has been applied all session, and it says no.

Read-only. Places nothing.

Env: TT_DAYS (190) TT_POOL (70) TT_SLOTS (3) TT_TREND_SLOTS (2)
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace as dc_replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal
from peak_fate_ab import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
# The live exit stack as of 2026-08-22: 0.30 base, ratcheting to 0.75 above 3R.
LIVE_TRAIL = ratchet(3.0, 0.75)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("TT_DAYS", 190), int(_env("TT_POOL", 70))
    slots, tr_slots = int(_env("TT_SLOTS", 3)), int(_env("TT_TREND_SLOTS", 2))
    eq = rt._last_known_equity() or 181.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(wc) | set(TREND_SYMS))
    print(f"equity ${eq:.2f} | {len(syms)} symbols | slots wc {slots} / tr {tr_slots}")

    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    nch = int(days * 86400 // (CHUNK * BAR)) + 1

    def fetch(s):
        parts, end = [], now
        for _ in range(nch):
            try:
                d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
            except Exception:
                break
            if d is None or not len(d):
                break
            parts.append(d)
            end = int(d.index[0].timestamp()) - BAR
        if not parts:
            return s, None
        o = pd.concat(parts[::-1])
        return s, o[~o.index.duplicated(keep="first")].sort_index()

    with ThreadPoolExecutor(max_workers=6) as p:
        F = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 400}
    span = len(next(iter(F.values()))) * BAR / 86400
    print(f"frames: {len(F)} symbols, {span:.0f}d")

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates...")
    cands = []
    for s, df in F.items():
        cs = sizes.get(s, 0.0)
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[k] * v[k] * cs for k in range(len(c))]
        roll, acc = [0.0] * len(c), 0.0
        for k, x in enumerate(raw):
            acc += x
            if k >= 96:
                acc -= raw[k - 96]
            roll[k] = acc
        bars = list(zip([float(x.timestamp()) for x in df.index],
                        [float(x) for x in df["high"]],
                        [float(x) for x in df["low"]], c))
        ts = [b[0] for b in bars]
        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars, "TREND"))
        if s in wc:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "WILDCARD"))
    cands.sort(key=lambda x: x[0])
    n_tr = sum(1 for c_ in cands if c_[5] == "TREND")
    print(f"candidates: {len(cands)} (trend {n_tr})")

    def retarget(sig, tp_r):
        """Same entry and stop, target moved to tp_r. LONG-only sleeve, so no
        short clamp is needed here."""
        e = float(sig.entry_price)
        slf = abs(e - float(sig.sl_price)) / e
        return dc_replace(sig, tp_price=e * (1.0 + slf * tp_r))

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def book(tp_r, k_lo=0, k_hi=None):
        tot = 0.0
        pos = 0
        tr_n = tr_pnl = 0.0
        tr_tp = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            wc_live, tr_live, per, wt = [], [], {}, 0.0
            for ts0, sym, sig, i, bars, kind in cands:
                if not (lo_t <= ts0 < hi_t):
                    continue
                use = retarget(sig, tp_r) if kind == "TREND" else sig
                wc_live[:] = [x for x in wc_live if x > ts0]
                tr_live[:] = [x for x in tr_live if x > ts0]
                per[sym] = [x for x in per.get(sym, []) if x > ts0]
                bk = tr_live if kind == "TREND" else wc_live
                cap = tr_slots if kind == "TREND" else slots
                if per[sym] or len(bk) >= cap:
                    continue
                row = {"entry": float(use.entry_price), "sl": float(use.sl_price),
                       "tp": float(use.tp_price), "side": use.side}
                g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                            tp_r if kind == "TREND" else shadow.signal_tp_r(use),
                            use.side, shadow.CONVEX_HORIZON_S, shadow.cost_r(row),
                            LIVE_TRAIL, float(getattr(use, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                bk.append(g[1])
                per[sym].append(g[1])
                usd = g[0] * eq * 0.12 * float(use.sl_margin_pct) / 100.0
                wt += usd
                if kind == "TREND":
                    tr_n += 1
                    tr_pnl += usd
                    tr_tp += 1 if g[2] == "tp" else 0
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, pos, tr_n, tr_pnl, tr_tp

    print()
    print("=== TREND TAKE-PROFIT SWEEP (live ratchet trail in force) ===")
    print(f"{'trend TP':>9} {'book $':>10} {'vs 3R':>9} {'pos wk':>8} "
          f"{'trend n':>8} {'trend $':>9} {'TP hit':>8} {'recent':>9} {'older':>9}  halves")
    base = None
    for tp_r in (3.0, 4.0, 5.0, 6.0, 8.0):
        tot, pos, tr_n, tr_pnl, tr_tp = book(tp_r)
        rec = book(tp_r, 0, mid)[0]
        old = book(tp_r, mid, n_win)[0]
        if tp_r == 3.0:
            base = (tot, rec, old)
        d_rec = rec - base[1]
        d_old = old - base[2]
        ok = "(live)" if tp_r == 3.0 else (
            "YES" if d_rec > 0 and d_old > 0 else
            ("no" if d_rec < 0 and d_old < 0 else "one half only"))
        print(f"{tp_r:8.1f}R {tot:+10.2f} {tot-base[0]:+9.2f} {pos:4d}/{n_win:<3d} "
              f"{int(tr_n):8d} {tr_pnl:+9.2f} {100*tr_tp/tr_n if tr_n else 0:7.1f}% "
              f"{d_rec:+9.2f} {d_old:+9.2f}  {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
