"""Live trials 17-18 against the proposed config, with the harness error shown.

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_trial_compare.py

THE PROPOSED CONFIG, from today's factorials:
    TREND     MIN_ROC 4% -> 5%, clock 24h -> 48h, MAX_POSITIONS 2 -> 3
              the cell carrying a genuine +$10.97 three-way term
    WILDCARD  MIN_ROC 8% -> 7%
              the only WILDCARD dial worth anything (+$29.44/234d alone; every
              combination involving it scored WORSE than it does by itself)

WHY THERE ARE FOUR COLUMNS AND NOT TWO. A table of "live actual" beside
"simulated proposal" invites a comparison that is not valid, because the two
numbers differ for TWO reasons at once: the config, and the simulator. So the
simulator is also run on the LIVE config over the identical window. That column
is the control:

    SIM(live) - LIVE ACTUAL   =  HARNESS ERROR. What the replay gets wrong even
                                 when modelling the bot as it actually runs.
    SIM(prop) - SIM(live)     =  the config effect, the only clean number here.

If the harness error is LARGER than the config effect, the comparison cannot
support a decision, and the table says so rather than leaving it to be inferred.

KNOWN, UNMODELLED, and all in the same direction: the external cross-exchange
veto is absent (live refuses at -0.565R, so the replay carries trades live would
decline); sizing uses today's equity rather than the equity path; entry lateness
and real fills are not reproduced. Two live carryover positions were also SIZED
under trial 17's regime floor and exited under trial 18's trail.

SAMPLE. 2026-08-27 to now is about 5 days and ~17 convex closes. That cannot
support any inference at all. This table is DESCRIPTIVE, produced because it was
asked for, and it must not be used to choose a config - the 220-day factorials
are the evidence, and they rejected these cells.

READ-ONLY.
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

os.environ["FUTURES_WILDCARD_MIN_ROC"] = "0.07"

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

WIN_START = dt.datetime(2026, 8, 27, tzinfo=dt.UTC).timestamp()
STATE = "/data/futures_runtime_state.json"
TAIL_W, TAIL_T = 260, 300


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


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)
    days = _env("PJ_DAYS", 16)

    # ---------------- LIVE ----------------
    state = json.load(open(STATE))
    live = [t for t in (state.get("trade_history") or [])
            if str(t.get("entry_signal") or "").startswith(("WILDCARD", "TREND", "SQUEEZE"))
            and _ts(t, "entry_time") >= WIN_START]
    L = {"TREND": [t for t in live if str(t.get("entry_signal") or "").startswith("TREND")],
         "WILDCARD": [t for t in live if not str(t.get("entry_signal") or "").startswith("TREND")]}
    print("LIVE convex closes with entry >= 2026-08-27: %d (TREND %d, WILDCARD %d)"
          % (len(live), len(L["TREND"]), len(L["WILDCARD"])))
    print("equity $%.2f | window %.1f days\n"
          % (eq0, (now - WIN_START) / 86400.0))

    # ---------------- TREND sim ----------------
    tsyms = tuple(s.strip() for s in
                  (os.environ.get("FUTURES_TREND_SYMBOLS") or
                   "ETH_USDT,XRP_USDT,ZEC_USDT").split(",") if s.strip())
    tf, rep = fetch_frames(cl, tsyms, days=days, workers=3, min_bars=300,
                           now_ts=now, strict=False)
    print("TREND fetch:", rep)
    tp_rT = _env("FUTURES_TREND_TP_R", 3.0)

    def trend_sim(trig, clock, slots):
        os.environ["FUTURES_TREND_MIN_ROC"] = str(trig)
        os.environ["FUTURES_TREND_SL_ATR_MULT"] = "3.0"
        from futuresbot.trend import detect_trend_signal, lookback_bars
        lb = lookback_bars()
        C = []
        for s, df in tf.items():
            c = [float(x) for x in df["close"]]
            ts_all = [float(x.timestamp()) for x in df.index]
            bars = list(zip(ts_all, [float(x) for x in df["high"]],
                            [float(x) for x in df["low"]], c))
            for i in range(lb + 40, len(c)):
                if bars[i][0] < WIN_START:
                    continue
                sig = detect_trend_signal(df.iloc[max(0, i - TAIL_T):i + 1], s)
                if sig is None or sig.side != "LONG":
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": "LONG"}
                g = resolve(bars, i, e, sl, float(sig.tp_price), tp_rT, "LONG",
                            clock * 3600, shadow.cost_r(row), fn,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                          "exit_ts": float(g[1]),
                          "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                         floor_mult=flm)})
        C.sort(key=lambda z: z["ts"])
        return take(C, slots=slots, equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=_env("FUTURES_TREND_MAX_SL_MARGIN_PCT", 20.0),
                    scan_s=_env("FUTURES_TREND_SCAN_INTERVAL_SECONDS", 900.0),
                    one_per_scan=True, calm_max=0.0)

    T_live = trend_sim(0.04, 24, 2)
    T_prop = trend_sim(0.05, 48, 3)

    # ---------------- WILDCARD sim ----------------
    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:int(_env("PJ_POOL", 170))]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    wf, rep2 = fetch_frames(cl, cand, days=days, workers=6, min_bars=300, now_ts=now)
    print("WILDCARD fetch:", rep2)

    floor_to = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_n = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    calm_max = _env("FUTURES_WILDCARD_MAX_CALM_RATIO", 0.75)
    tp_rW = _env("FUTURES_WILDCARD_TP_R", 5.0)
    ROLLS, PREP = {}, {}
    for s, df in wf.items():
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
        ts_all = [float(x.timestamp()) for x in df.index]
        ROLLS[s] = [(ts_all[k], roll[k]) for k in range(96, len(c))]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), roll, c)
    PIT = pit_majors(daily_turnover(ROLLS), n=band_n)

    WC = []
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if bars[i][0] < WIN_START or i <= W.ROC_BARS or roll[i] < floor_to:
                continue
            roc = abs(c[i] / c[i - W.ROC_BARS] - 1.0)
            if roc < 0.07:
                continue
            if band_n and s in PIT.get(day_key(bars[i][0]), ()):
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL_W):i + 1], s)
            if sig is None:
                continue
            e, sl = float(sig.entry_price), float(sig.sl_price)
            if abs(e - sl) <= 0 or e <= 0:
                continue
            row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(bars, i, e, sl, float(sig.tp_price), tp_rW, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fn,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            cr = getattr(sig, "calm_ratio", None)
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            WC.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                       "exit_ts": float(g[1]), "roc": roc,
                       "calm_ratio": (float(cr) if cr is not None else None),
                       "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_, floor_mult=flm)})
    WC.sort(key=lambda z: z["ts"])

    def wild_sim(trig):
        return take([z for z in WC if z["roc"] >= trig], slots=3, equity=eq0,
                    risk_pct=risk_pct,
                    sl_margin_pct=_env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0),
                    scan_s=_env("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 450.0),
                    one_per_scan=True, calm_max=calm_max)

    W_live, W_prop = wild_sim(0.08), wild_sim(0.07)

    def lv(g):
        return len(g), sum(float(t.get("pnl_usdt") or 0) for t in g)

    def sv(f):
        return len(f), sum(z["usd"] for z in f)

    tl_n, tl_u = lv(L["TREND"])
    wl_n, wl_u = lv(L["WILDCARD"])
    ts_n, ts_u = sv(T_live)
    ws_n, ws_u = sv(W_live)
    tp_n, tp_u = sv(T_prop)
    wp_n, wp_u = sv(W_prop)

    print()
    print("=" * 104)
    print("TRIALS 17-18 (entry >= 2026-08-27, %.1f days) - LIVE vs SIMULATED"
          % ((now - WIN_START) / 86400.0))
    print("=" * 104)
    print("%-12s %-8s %14s %14s %14s %14s"
          % ("sleeve", "metric", "LIVE ACTUAL", "SIM(live cfg)", "SIM(proposed)",
             "config effect"))
    print("-" * 104)
    for name, (ln, lu), (sn, su), (pn, pu) in (
            ("TREND", (tl_n, tl_u), (ts_n, ts_u), (tp_n, tp_u)),
            ("WILDCARD", (wl_n, wl_u), (ws_n, ws_u), (wp_n, wp_u))):
        print("%-12s %-8s %14d %14d %14d %14s" % (name, "closes", ln, sn, pn, "-"))
        print("%-12s %-8s %+14.2f %+14.2f %+14.2f %+14.2f"
              % ("", "net $", lu, su, pu, pu - su))
    print("-" * 104)
    print("%-12s %-8s %14d %14d %14d %14s"
          % ("TOTAL", "closes", tl_n + wl_n, ts_n + ws_n, tp_n + wp_n, "-"))
    print("%-12s %-8s %+14.2f %+14.2f %+14.2f %+14.2f"
          % ("", "net $", tl_u + wl_u, ts_u + ws_u, tp_u + wp_u,
             (tp_u + wp_u) - (ts_u + ws_u)))

    # ---------------- per-trade reconciliation ----------------
    # Two guesses at the fill gap have now failed (MAX_SCAN does not bind; the
    # 24h range prefilter is lossless by construction). So instead of a third,
    # match the books trade by trade and classify every discrepancy.
    print()
    print("=" * 104)
    print("RECONCILIATION - where do the 2 books actually diverge?")
    print("=" * 104)
    shadow_rows = []
    try:
        for line in open("/data/futures_shadow_ledger.jsonl", encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if float(r.get("ts") or 0) >= WIN_START:
                    shadow_rows.append(r)
    except Exception:
        pass
    refused = {}
    for r in shadow_rows:
        refused.setdefault(str(r.get("symbol") or ""), []).append(
            (float(r.get("ts") or 0), str(r.get("reject_reason") or "?")))

    live_w = [(str(t.get("symbol") or ""), _ts(t, "entry_time")) for t in L["WILDCARD"]]
    sim_w = [(z["sym"], z["ts"]) for z in W_live]
    TOL = 3600.0

    matched, sim_only, live_only = [], [], []
    used = set()
    for sy, st in sim_w:
        hit = None
        for k, (ly, lt) in enumerate(live_w):
            if k in used or ly != sy:
                continue
            if abs(lt - st) <= TOL:
                hit = k
                break
        if hit is None:
            sim_only.append((sy, st))
        else:
            used.add(hit)
            matched.append((sy, st))
    live_only = [live_w[k] for k in range(len(live_w)) if k not in used]

    print("  live WILDCARD entries      : %d" % len(live_w))
    print("  sim  WILDCARD entries      : %d" % len(sim_w))
    print("  MATCHED (same symbol, 1h)  : %d" % len(matched))
    print("  LIVE ONLY (sim missed)     : %d" % len(live_only))
    print("  SIM ONLY  (sim invented)   : %d" % len(sim_only))
    print()
    if sim_only:
        print("  the SIM-ONLY fills, and whether live SAW and REFUSED them:")
        for sy, st in sorted(sim_only, key=lambda z: z[1]):
            tag = "live never logged it"
            for rts, why in refused.get(sy, []):
                if abs(rts - st) <= 6 * 3600:
                    tag = "live REFUSED: %s" % why
                    break
            print("    %-14s %s   %s"
                  % (sy.replace("_USDT", ""),
                     dt.datetime.fromtimestamp(st, dt.UTC).strftime("%m-%d %H:%M"), tag))
    if live_only:
        print()
        print("  the LIVE-ONLY fills the sim never generated:")
        for sy, st in sorted(live_only, key=lambda z: z[1]):
            print("    %-14s %s"
                  % (sy.replace("_USDT", ""),
                     dt.datetime.fromtimestamp(st, dt.UTC).strftime("%m-%d %H:%M")))
    print()
    n_ref = sum(1 for sy, st in sim_only
                if any(abs(r - st) <= 6 * 3600 for r, _ in refused.get(sy, [])))
    print("  VERDICT: %d of %d sim-only fills were seen and refused by live;"
          % (n_ref, len(sim_only)))
    print("           %d were never in live's candidate list at all."
          % (len(sim_only) - n_ref))
    print("  The first group is a MISSING FILTER. The second is a UNIVERSE")
    print("  mismatch - the replay is scanning symbols live never considers.")

    harness = (ts_u + ws_u) - (tl_u + wl_u)
    effect = (tp_u + wp_u) - (ts_u + ws_u)
    print()
    print("=" * 104)
    print("HOW MUCH OF THIS IS REAL?")
    print("=" * 104)
    print("  HARNESS ERROR   SIM(live) - LIVE ACTUAL  = $%+.2f" % harness)
    print("     the replay's error modelling the bot AS IT ACTUALLY RUNS")
    print("  CONFIG EFFECT   SIM(prop) - SIM(live)    = $%+.2f" % effect)
    print("     the only clean number in the table")
    print()
    if abs(harness) >= abs(effect):
        print("  THE HARNESS ERROR IS LARGER THAN THE CONFIG EFFECT (%.2f vs %.2f)."
              % (abs(harness), abs(effect)))
        print("  This comparison cannot support a decision. The simulator does not")
        print("  reproduce the live bot closely enough over %.0f days for a %.2f"
              % ((now - WIN_START) / 86400.0, abs(effect)))
        print("  dollar difference to be readable.")
    else:
        print("  Config effect exceeds harness error - but on ~%d closes that is"
              % (tl_n + wl_n))
        print("  still descriptive, not evidence. The 220-day factorials rejected")
        print("  these cells and remain the decision-grade measurement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
