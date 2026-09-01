"""Price context at entry for every convex close - losers AND winners.

    railway run --service Futures-bot python tools/pit_loss_context.py

THE QUESTION: the 28 losses in the last 28 days all share one mechanical cause
(peak < 1.0R, so the trail never armed). Is there anything in the PRICE PICTURE
at entry that separates them from the 32 winners?

WHY WINNERS ARE IN THIS TABLE. A feature found only in losers is unfalsifiable -
if 80% of losers entered above their 4h average, that means nothing until you
know what share of WINNERS did too. Every column below is reported for both
groups, and the only line worth reading is the separation.

SIDE-ADJUSTED COLUMNS. 4 of the 28 losers are SHORTs. A raw "-2% over 4h" is
bearish for a long and bullish for a short, so the raw columns cannot be pooled.
Columns prefixed `s.` are signed TOWARD the trade: positive = the move was
running in the trade's favour before entry.

OVERFITTING WARNING. 60 trades against ~12 features. Some separation WILL appear
by chance; a t-like gap of one standard error on n=60 is noise. Nothing here is
a decision - it is a hypothesis to put to the shadow ledger, which carries the
untaken signals and is the only place a cut can be tested without selection bias.

READ-ONLY.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402

STATE = "/data/futures_runtime_state.json"
FEATS = "/data/futures_feature_store.jsonl"
BAR = 900          # Min15
H4, H8, H24 = 16, 32, 96


def _ts(rec, key):
    try:
        return dt.datetime.fromisoformat(str(rec.get(key) or "")).timestamp()
    except Exception:
        return 0.0


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def _sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    now = time.time()
    cut = now - 28 * 86400

    state = json.load(open(STATE))
    only = (os.environ.get("PLC_SLEEVE") or "").strip().upper()
    kinds = ((only,) if only else ("WILDCARD", "TREND", "SQUEEZE"))
    trades = [t for t in (state.get("trade_history") or [])
              if str(t.get("entry_signal") or "").startswith(kinds)
              and _ts(t, "exit_time") >= cut]
    if only:
        print("SLEEVE FILTER: %s only" % only)
    trades.sort(key=lambda t: _ts(t, "entry_time"))

    fs = {}
    try:
        for line in open(FEATS, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            fs[round(float(row.get("ts") or 0))] = row
    except Exception:
        pass

    syms = sorted({str(t.get("symbol") or "") for t in trades})
    print("convex closes in the window: %d over %d symbols" % (len(trades), len(syms)))
    frames, rep = fetch_frames(cl, syms, days=32, workers=6, min_bars=200,
                               now_ts=int(now), strict=False)
    print(rep)
    print()

    PREP = {}
    for s, df in frames.items():
        PREP[s] = ([float(x.timestamp()) for x in df.index],
                   [float(x) for x in df["close"]],
                   [float(x) for x in df["high"]],
                   [float(x) for x in df["low"]])

    rows = []
    for t in trades:
        s = str(t.get("symbol") or "")
        if s not in PREP:
            continue
        ts_all, c, hi, lo = PREP[s]
        e_ts = _ts(t, "entry_time")
        i = None
        for k in range(len(ts_all) - 1, -1, -1):
            if ts_all[k] <= e_ts:
                i = k
                break
        if i is None or i < H24 + 2:
            continue
        px = float(t.get("entry_price") or c[i]) or c[i]
        side = str(t.get("side") or "LONG")
        sgn = 1.0 if side == "LONG" else -1.0
        risk = float(t.get("risk_usdt") or 0.0)
        pnl = float(t.get("pnl_usdt") or 0.0)

        def trend(nb):
            base = c[i - nb]
            return (px / base - 1.0) * 100.0 if base else float("nan")

        def avg(nb):
            return _mean(c[i - nb:i])

        a4, a8, a24 = avg(H4), avg(H8), avg(H24)
        w = c[i - H24:i + 1]
        wh, wl = max(hi[i - H24:i + 1]), min(lo[i - H24:i + 1])
        rng = (wh / wl - 1.0) * 100.0 if wl else float("nan")
        pos = (px - wl) / (wh - wl) * 100.0 if wh > wl else float("nan")
        rets = [c[k] / c[k - 1] - 1.0 for k in range(i - H24 + 1, i + 1) if c[k - 1]]
        vol = _sd(rets) * 100.0 if rets else float("nan")
        # straightness of the 24h move: net travel over gross travel
        gross = sum(abs(c[k] - c[k - 1]) for k in range(i - H24 + 1, i + 1))
        eff = abs(c[i] - c[i - H24]) / gross if gross else float("nan")
        fr = fs.get(round(_ts(t, "exit_time"))) or {}

        rows.append({
            "sym": s.replace("_USDT", ""), "side": side,
            "sleeve": str(t.get("entry_signal") or "")[:5],
            "in": dt.datetime.fromtimestamp(e_ts, dt.UTC).strftime("%m-%d %H:%M"),
            "px": px, "win": pnl > 0, "usd": pnl,
            "R": (pnl / risk) if risk else float("nan"),
            "peak": float(t.get("peak_r") or 0.0),
            "t4": trend(H4), "t8": trend(H8), "t24": trend(H24),
            "a4": a4, "a8": a8, "a24": a24,
            "e4": (px / a4 - 1.0) * 100.0 if a4 else float("nan"),
            "e8": (px / a8 - 1.0) * 100.0 if a8 else float("nan"),
            "e24": (px / a24 - 1.0) * 100.0 if a24 else float("nan"),
            "rng": rng, "pos": pos, "vol": vol, "eff": eff, "sgn": sgn,
            "roc3": fr.get("entry_3h_roc_pct"), "calm": fr.get("calm_score"),
            "mult": fr.get("regime_size_mult"),
        })

    L = [r for r in rows if not r["win"]]
    W = [r for r in rows if r["win"]]

    def fmt(x, w=7, p=2):
        return (" " * w if x is None or (isinstance(x, float) and math.isnan(x))
                else ("%*.*f" % (w, p, x)))

    print("=" * 150)
    print("THE 28 LOSSES, WITH PRICE CONTEXT AT ENTRY  (trends and averages from Min15 closes)")
    print("=" * 150)
    hdr = ("%-9s %-5s %-5s %-11s %10s %7s %7s %7s %9s %9s %9s %6s %6s %6s %6s %6s %6s"
           % ("symbol", "side", "slv", "entered", "entry px", "4h %", "8h %", "24h %",
              "avg4h", "avg8h", "avg24h", "vs a4", "vs a8", "vsa24", "pos24", "rng24", "$"))
    print(hdr)
    print("-" * 150)
    for r in sorted(L, key=lambda z: z["usd"]):
        print("%-9s %-5s %-5s %-11s %10.6g %s %s %s %9.6g %9.6g %9.6g %s %s %s %s %s %6.2f"
              % (r["sym"], r["side"], r["sleeve"], r["in"], r["px"],
                 fmt(r["t4"]), fmt(r["t8"]), fmt(r["t24"]),
                 r["a4"], r["a8"], r["a24"],
                 fmt(r["e4"], 6, 1), fmt(r["e8"], 6, 1), fmt(r["e24"], 6, 1),
                 fmt(r["pos"], 6, 0), fmt(r["rng"], 6, 1), r["usd"]))

    print()
    print("=" * 150)
    print("THE CONTROL: same columns, the %d WINNERS" % len(W))
    print("=" * 150)
    print(hdr)
    print("-" * 150)
    for r in sorted(W, key=lambda z: -z["usd"]):
        print("%-9s %-5s %-5s %-11s %10.6g %s %s %s %9.6g %9.6g %9.6g %s %s %s %s %s %6.2f"
              % (r["sym"], r["side"], r["sleeve"], r["in"], r["px"],
                 fmt(r["t4"]), fmt(r["t8"]), fmt(r["t24"]),
                 r["a4"], r["a8"], r["a24"],
                 fmt(r["e4"], 6, 1), fmt(r["e8"], 6, 1), fmt(r["e24"], 6, 1),
                 fmt(r["pos"], 6, 0), fmt(r["rng"], 6, 1), r["usd"]))

    print()
    print("=" * 96)
    print("SEPARATION - side-adjusted, so positive always means 'running in the trade's favour'")
    print("=" * 96)
    print("%-34s %9s %9s %9s %9s  %s"
          % ("feature", "losers", "winners", "gap", "gap/SE", "reading"))
    print("-" * 96)
    FE = (("4h trend before entry (s.)", lambda r: r["t4"] * r["sgn"]),
          ("8h trend before entry (s.)", lambda r: r["t8"] * r["sgn"]),
          ("24h trend before entry (s.)", lambda r: r["t24"] * r["sgn"]),
          ("entry vs 4h average (s.)", lambda r: r["e4"] * r["sgn"]),
          ("entry vs 8h average (s.)", lambda r: r["e8"] * r["sgn"]),
          ("entry vs 24h average (s.)", lambda r: r["e24"] * r["sgn"]),
          ("position in 24h range (s.)",
           lambda r: r["pos"] if r["sgn"] > 0 else 100.0 - r["pos"]),
          ("24h range %", lambda r: r["rng"]),
          ("15m return vol %", lambda r: r["vol"]),
          ("24h straightness 0-1", lambda r: r["eff"]),
          ("3h ROC at entry %",
           lambda r: float(r["roc3"]) if r["roc3"] is not None else float("nan")),
          ("calm score", lambda r: float(r["calm"]) if r["calm"] is not None else float("nan")),
          ("regime size mult",
           lambda r: float(r["mult"]) if r["mult"] is not None else float("nan")))
    flags = []
    for name, fn in FE:
        lv = [fn(r) for r in L if not math.isnan(fn(r))]
        wv = [fn(r) for r in W if not math.isnan(fn(r))]
        if len(lv) < 4 or len(wv) < 4:
            continue
        ml, mw = _mean(lv), _mean(wv)
        se = math.sqrt(_sd(lv) ** 2 / len(lv) + _sd(wv) ** 2 / len(wv))
        z = (mw - ml) / se if se else 0.0
        tag = ("SEPARATES" if abs(z) >= 2.0 else
               "weak" if abs(z) >= 1.3 else "no")
        if abs(z) >= 2.0:
            flags.append((name, ml, mw, z))
        print("%-34s %9.3f %9.3f %+9.3f %+9.2f  %s" % (name, ml, mw, mw - ml, z, tag))
    print()
    print("gap/SE is winners minus losers in standard errors. On n=%d/%d with 13"
          % (len(L), len(W)))
    print("features, expect ~1 spurious |gap/SE| >= 2 by chance alone.")
    if not flags:
        print()
        print("NOTHING SEPARATES at 2 SE. The price picture at entry does not")
        print("distinguish the losers from the winners in this window.")
    else:
        print()
        print("Candidates to put to the shadow ledger (NOT to act on here):")
        for name, ml, mw, z in flags:
            print("  %-32s losers %.3f vs winners %.3f (%+.2f SE)" % (name, ml, mw, z))
    print()
    print("=" * 96)
    print("FOLLOW-UP 1: does the calm gate leak? live refuses WILDCARD at calm_ratio >= 0.75")
    print("=" * 96)
    leak = [r for r in rows if r["sleeve"] == "WILDC" and r["calm"] is not None
            and float(r["calm"]) >= 0.75]
    print("WILDCARD closes with a recorded calm score >= 0.75: %d of %d"
          % (leak, len([r for r in rows if r["sleeve"] == "WILDC"]))
          if False else
          "WILDCARD closes with a recorded calm score >= 0.75: %d of %d"
          % (len(leak), len([r for r in rows if r["sleeve"] == "WILDC"])))
    if leak:
        print("  (if calm_score is the gated calm_ratio, these should not exist)")
        for r in sorted(leak, key=lambda z: -float(z["calm"]))[:8]:
            print("    %-9s %-11s calm %.3f  %s  $%+.2f"
                  % (r["sym"], r["in"], float(r["calm"]),
                     "WIN " if r["win"] else "LOSS", r["usd"]))

    print()
    print("=" * 96)
    print("FOLLOW-UP 2: distance above the sleeve's own trigger")
    print("  TREND fires at 24h ROC >= 4%.  WILDCARD fires at 3h ROC >= 8%.")
    print("=" * 96)
    for slv, key, trig, label in (("TREND", lambda r: abs(r["t24"]), 4.0, "24h ROC"),
                                  ("WILDC", lambda r: abs(r["t4"] * 0 + (
                                      float(r["roc3"]) if r["roc3"] is not None
                                      else float("nan"))), 8.0, "3h ROC")):
        g = [r for r in rows if r["sleeve"] == slv and not math.isnan(key(r))]
        if not g:
            continue
        print()
        print("%s sleeve, %d closes, by %s at entry:" % (slv, len(g), label))
        print("  %-22s %6s %6s %9s %9s %9s"
              % ("bucket", "n", "wins", "net $", "$/trade", "mean R"))
        g.sort(key=key)
        edges = [(trig, trig * 1.25), (trig * 1.25, trig * 2.0),
                 (trig * 2.0, trig * 4.0), (trig * 4.0, 1e9)]
        for lo_e, hi_e in edges:
            b = [r for r in g if lo_e <= key(r) < hi_e]
            if not b:
                continue
            rs = [r["R"] for r in b if not math.isnan(r["R"])]
            print("  %-22s %6d %6d %+9.2f %+9.3f %+9.3f"
                  % ("%.1f - %.1f%%" % (lo_e, hi_e) if hi_e < 1e8
                     else ">= %.1f%%" % lo_e,
                     len(b), sum(1 for r in b if r["win"]),
                     sum(r["usd"] for r in b),
                     sum(r["usd"] for r in b) / len(b),
                     _mean(rs) if rs else float("nan")))
    print()
    print("Small n per bucket. This is the shape of a hypothesis, not a result -")
    print("the shadow ledger holds the untaken signals needed to test a cut without")
    print("selection bias, and it is the only place this can be settled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
