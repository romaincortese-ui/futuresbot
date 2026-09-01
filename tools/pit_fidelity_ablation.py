"""WHICH lever makes the replay disagree with the live bot? One at a time.

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_fidelity_ablation.py

THE PROBLEM THIS EXISTS TO SOLVE. pit_trial_compare.py reconciled the replay
against the live book over trials 17-18 and found they share FOUR trades out of
about thirty-eight: 16 live entries, 26 simulated, 4 matched, 12 live-only,
22 sim-only, and 18 of those sim-only fills were never in live's candidate list
at all. That is not a calibrated model with error bars - it is a different book.
Until the base case reconciles, no replay delta is decision-grade.

METHOD. Each lever is toggled ALONE from the baseline, so the table attributes
the disagreement rather than just shrinking it. The metric is not dollars, it is
AGREEMENT with the 16 trades the bot actually took:

    matched     same symbol, entry within 1h of a live entry
    live-only   the bot took it, the replay never generated it
    sim-only    the replay took it, the bot did not

THE LEVERS

  L1  24h RANGE GATE. Live resolves this through the RANGE branch:
      FUTURES_WILDCARD_RANGE_PREFILTER defaults true, so the threshold is
      MIN_24H_RANGE which is unset and DEFAULTS TO min_roc = 8%. Replays read
      MIN_24H_MOVE=3% - the other branch, disabled live. Expected to be nearly
      inert on fills, because the gate is lossless by construction (a 3h move of
      8% forces a 24h range of 8%), but it is measured rather than assumed.

  L2  FRAME LENGTH. Live hands the detector FUTURES_WILDCARD_SCAN_BARS=672 bars;
      replays hand it 260. The sigma trigger and calm_ratio read long trailing
      windows, so the same bar can decide differently.

  L3  INTRA-BAR DETECTION - the one I expect to matter. Live scans every 450s
      and evaluates a PARTIALLY FORMED 15m candle; the replay only ever sees
      completed bars, so it cannot fire where live fires and fires where live
      would already have exited.

      5m bars CANNOT be fed to the detector directly: ROC_BARS=12 assumes 15m
      bars and would silently become a 1h lookback instead of 3h. So three
      PHASE-SHIFTED 15m grids are built from 5m data - bars ending at :00/:15/:30,
      at :05/:20/:35, at :10/:25/:40. Each grid is a proper NON-OVERLAPPING 15m
      series, so pullback-resume still compares genuinely distinct candles, while
      a signal can now fire every 5 minutes.

  L4  EXTERNAL VETO. Live refuses on a cross-exchange/funding check that cannot
      be reconstructed historically. Proxied here by dropping symbols the shadow
      ledger records as vetoed inside the window - a floor on its effect, not a
      model of it.

READ-ONLY. Reports agreement, not P&L.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

import pandas as pd  # noqa: E402

WIN_START = dt.datetime(2026, 8, 27, tzinfo=dt.UTC).timestamp()
STATE = "/data/futures_runtime_state.json"
MATCH_TOL = 3600.0


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def _ts(rec, key):
    try:
        return dt.datetime.fromisoformat(str(rec.get(key) or "")).timestamp()
    except Exception:
        return 0.0


def phase_grid(df5: pd.DataFrame, phase: int) -> pd.DataFrame:
    """Non-overlapping 15m bars from 5m data, starting at `phase` bars in.

    Keeps the detector's 15m semantics intact (ROC_BARS=12 stays a 3h lookback)
    while letting the grid land on :05 and :10 boundaries as well as :00.
    """
    n = len(df5)
    o, h, l, c, v, idx = [], [], [], [], [], []
    op = df5["open"].to_numpy() if "open" in df5 else df5["close"].to_numpy()
    hi = df5["high"].to_numpy()
    lo = df5["low"].to_numpy()
    cl_ = df5["close"].to_numpy()
    vo = df5["volume"].to_numpy() if "volume" in df5 else None
    ix = list(df5.index)
    k = phase
    while k + 3 <= n:
        o.append(float(op[k]))
        h.append(float(max(hi[k:k + 3])))
        l.append(float(min(lo[k:k + 3])))
        c.append(float(cl_[k + 2]))
        v.append(float(vo[k:k + 3].sum()) if vo is not None else 0.0)
        idx.append(ix[k + 2])
        k += 3
    cols = {"open": o, "high": h, "low": l, "close": c}
    if vo is not None:
        cols["volume"] = v
    return pd.DataFrame(cols, index=pd.DatetimeIndex(idx))


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    tp_r = _env("FUTURES_WILDCARD_TP_R", 5.0)
    scan_s = _env("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 450.0)
    slmp = _env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_to = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_n = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    calm_max = _env("FUTURES_WILDCARD_MAX_CALM_RATIO", 0.75)
    min_roc = _env("FUTURES_WILDCARD_MIN_ROC", 0.08)
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)
    days = _env("PJ_DAYS", 14)

    state = json.load(open(STATE))
    LIVE = [(str(t.get("symbol") or ""), _ts(t, "entry_time"),
             float(t.get("pnl_usdt") or 0))
            for t in (state.get("trade_history") or [])
            if str(t.get("entry_signal") or "").startswith(("WILDCARD", "SQUEEZE"))
            and _ts(t, "entry_time") >= WIN_START]
    print("LIVE WILDCARD entries in window: %d, net $%+.2f"
          % (len(LIVE), sum(x[2] for x in LIVE)))

    vetoed = set()
    try:
        for line in open("/data/futures_shadow_ledger.jsonl", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if (float(r.get("ts") or 0) >= WIN_START
                    and str(r.get("reject_reason") or "").startswith("veto")):
                vetoed.add(str(r.get("symbol") or ""))
    except Exception:
        pass
    print("symbols live vetoed in window: %d\n" % len(vetoed))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:int(_env("PJ_POOL", 170))]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    f15, rep15 = fetch_frames(cl, cand, days=days, workers=6, min_bars=300, now_ts=now)
    print("Min15:", rep15)
    f5, rep5 = fetch_frames(cl, cand, days=days, workers=6, min_bars=600,
                            interval="Min5", strict=False, now_ts=now)
    print("Min5 :", rep5)
    print()

    def prep(frames_map):
        ROLLS, PREP = {}, {}
        for s, df in frames_map.items():
            cs = sizes.get(s, 0.0)
            c = [float(x) for x in df["close"]]
            v = [float(x) for x in df["volume"]] if "volume" in df else [0.0] * len(c)
            raw = [c[k] * v[k] * cs for k in range(len(c))]
            roll, acc = [0.0] * len(c), 0.0
            for k, x in enumerate(raw):
                acc += x
                if k >= 96:
                    acc -= raw[k - 96]
                roll[k] = acc
            ts_all = [float(x.timestamp()) for x in df.index]
            ROLLS[s] = [(ts_all[k], roll[k]) for k in range(96, len(c))]
            PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                    [float(x) for x in df["low"]], c)), roll, c)
        return ROLLS, PREP

    R15, P15 = prep(f15)
    PIT15 = pit_majors(daily_turnover(R15), n=band_n)

    GRIDS = []
    for ph in (0, 1, 2):
        g = {}
        for s, df in f5.items():
            try:
                gg = phase_grid(df, ph)
                if len(gg) > 300:
                    g[s] = gg
            except Exception:
                continue
        GRIDS.append(g)
    print("phase grids built: %s symbols each\n" % [len(g) for g in GRIDS])

    def scan(PREP, PIT, tail, range_gate, veto):
        out = []
        for s, (df, bars, roll, c) in PREP.items():
            if veto and s in vetoed:
                continue
            for i in range(250, len(c)):
                if bars[i][0] < WIN_START or i <= W.ROC_BARS or roll[i] < floor_to:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                if range_gate > 0 and i >= 96:
                    wh, wl = max(c[i - 96:i + 1]), min(c[i - 96:i + 1])
                    if wl > 0 and (wh / wl - 1.0) < range_gate:
                        continue
                if band_n and PIT and s in PIT.get(day_key(bars[i][0]), ()):
                    continue
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - tail):i + 1], s)
                if sig is None:
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": sig.side}
                g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, sig.side,
                            shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fn,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                cr = getattr(sig, "calm_ratio", None)
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                out.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                            "exit_ts": float(g[1]),
                            "calm_ratio": (float(cr) if cr is not None else None),
                            "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                           floor_mult=flm)})
        return out

    def run(label, *, tail=260, range_gate=0.0, veto=False, intrabar=False):
        if not intrabar:
            C = scan(P15, PIT15, tail, range_gate, veto)
        else:
            C = []
            for g in GRIDS:
                Rg, Pg = prep(g)
                C += scan(Pg, pit_majors(daily_turnover(Rg), n=band_n),
                          tail, range_gate, veto)
        C.sort(key=lambda z: z["ts"])
        f = take(C, slots=3, equity=eq0, risk_pct=risk_pct, sl_margin_pct=slmp,
                 scan_s=scan_s, one_per_scan=True, calm_max=calm_max)
        used, matched = set(), 0
        for z in f:
            for k, (ly, lt, _) in enumerate(LIVE):
                if k not in used and ly == z["sym"] and abs(lt - z["ts"]) <= MATCH_TOL:
                    used.add(k)
                    matched += 1
                    break
        return {"label": label, "n": len(f), "m": matched,
                "lo": len(LIVE) - matched, "so": len(f) - matched,
                "usd": sum(z["usd"] for z in f)}

    rows = [run("BASELINE (today's replays)"),
            run("L1  24h range gate 8%", range_gate=min_roc),
            run("L2  frame 672 bars (live)", tail=672),
            run("L3  INTRA-BAR, 3 phase grids", intrabar=True),
            run("L4  external veto proxy", veto=True),
            run("ALL FOUR together", tail=672, range_gate=min_roc,
                veto=True, intrabar=True)]

    live_usd = sum(x[2] for x in LIVE)
    print("=" * 104)
    print("WHICH LEVER CLOSES THE GAP?  live took %d trades, net $%+.2f"
          % (len(LIVE), live_usd))
    print("=" * 104)
    print("%-32s %6s %8s %10s %9s %10s %10s"
          % ("configuration", "fills", "matched", "live-only", "sim-only",
             "net $", "vs live $"))
    print("-" * 104)
    for r in rows:
        print("%-32s %6d %5d/%-2d %10d %9d %+10.2f %+10.2f"
              % (r["label"], r["n"], r["m"], len(LIVE), r["lo"], r["so"],
                 r["usd"], r["usd"] - live_usd))
    print()
    base = rows[0]
    print("  Read the MATCHED column. A lever that raises it is closing the real")
    print("  gap; one that only cuts sim-only is just trading fewer wrong trades.")
    best = max(rows, key=lambda r: r["m"])
    print("  best agreement: %s at %d/%d (%.0f%% of live trades reproduced)"
          % (best["label"].strip(), best["m"], len(LIVE),
             100.0 * best["m"] / max(1, len(LIVE))))
    print("  baseline was %d/%d (%.0f%%)."
          % (base["m"], len(LIVE), 100.0 * base["m"] / max(1, len(LIVE))))
    if best["m"] < 0.6 * len(LIVE):
        print()
        print("  STILL BELOW 60%%. No lever tested here makes the replay a")
        print("  trade-level model of this bot. Treat replays as hypothesis")
        print("  generation and let the shadow ledger decide.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
