"""Where would a trade be RIGHT NOW with no trail? Bar-by-bar, no guessing.

    railway run --service Futures-bot python tools/pit_mfe.py

For trades whose 24h convex clock has NOT yet expired, the counterfactual
"what would it have done with no trail" has no answer yet - resolve() correctly
refuses. This walks the real bars from entry to now and reports what IS known:
maximum favourable and adverse excursion, whether the -1R stop or the +5R target
was ever touched after the trail exited, and where the mark sits now.

READ-ONLY.
"""
from __future__ import annotations
import datetime as dt, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402

SRC = os.environ.get("MFE_TRADES") or "pair.json"


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    cl = MexcFuturesClient(FuturesConfig.from_env())
    now = int(time.time())
    syms = sorted({x["symbol"] for x in d})
    span = (now - min(x["entry_ts"] for x in d)) / 86400.0 + 2.0
    frames, rep = fetch_frames(cl, syms, days=span, workers=4, min_bars=50, now_ts=now)
    print(rep); print()
    for x in d:
        df = frames.get(x["symbol"])
        if df is None:
            print("%s: no klines" % x["symbol"]); continue
        e, slf = x["entry"], x["sl_frac"]
        sgn = 1.0 if x["side"] == "LONG" else -1.0
        one = e * slf
        tp_r = 3.0 if x["signal"].startswith("TREND") else 5.0
        sl_p = e * (1 - sgn * slf)
        tp_p = e * (1 + sgn * slf * tp_r)
        exit_ts = dt.datetime.fromisoformat(x["exit_time"]).timestamp()
        horizon = x["entry_ts"] + 24 * 3600
        rows = [(float(i.timestamp()), float(h), float(lo), float(c))
                for i, h, lo, c in zip(df.index, df["high"], df["low"], df["close"])
                if x["entry_ts"] <= float(i.timestamp()) <= min(horizon, now)]
        if not rows:
            print("%s: no bars in window" % x["symbol"]); continue
        mfe = max(((r[1] if sgn > 0 else -r[2]) - sgn * e) * sgn / one for r in rows)
        mae = min(((r[2] if sgn > 0 else -r[1]) - sgn * e) * sgn / one for r in rows)
        after = [r for r in rows if r[0] > exit_ts]
        hit_tp = any((r[1] >= tp_p) if sgn > 0 else (r[2] <= tp_p) for r in rows)
        hit_sl = any((r[2] <= sl_p) if sgn > 0 else (r[1] >= sl_p) for r in rows)
        mark = rows[-1][3]
        now_r = (mark - e) * sgn / one
        got = x["pnl"] / x["risk"] if x["risk"] else 0.0
        print("=== %s %s ===" % (x["symbol"], x["side"]))
        print("  entry %.6g   stop %.6g (-1R)   target %.6g (+%.0fR)" % (e, sl_p, tp_p, tp_r))
        print("  trail took          %+.2fR   at %.6g" % (got, x["exit"]))
        print("  peak while held     %+.2fR" % x["peak_r"])
        print("  MFE over the window %+.2fR      MAE %+.2fR" % (mfe, mae))
        print("  stop touched: %-5s   target touched: %s" % (hit_sl, hit_tp))
        print("  mark now %.6g = %+.2fR   (%d bars after the trail exit)"
              % (mark, now_r, len(after)))
        left = (horizon - now) / 3600.0
        print("  24h clock: %s" % ("EXPIRED - resolvable" if left <= 0
                                   else "%.1fh still to run - NOT yet resolvable" % left))
        print("  no-trail outcome so far: %s"
              % ("STOPPED -1.00R" if hit_sl else
                 ("TARGET +%.2fR" % tp_r) if hit_tp else
                 "still open, currently %+.2fR" % now_r))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
