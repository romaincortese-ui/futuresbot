"""Would a LOWER trail arm help? Bar-level replay of the REAL trades.

    railway ssh -> /opt/venv/bin/python tools/pit_arm_sweep.py

THE QUESTION. Trial 18's arithmetic is mean win +0.569R against mean loss
-1.003R at a 55% win rate = -0.138R expected. It is only positive because three
trades reached 3R. And every loser peaked BELOW 1.0R - they never armed the
retention trail, so they paid the full stop while peaking as high as 0.96R.

THE NAIVE ANSWER IS WRONG, and it is worth recording why. Restating each loser
as "it peaked at 0.82R, so a 0.7R arm banks 0.5 x 0.82 = 0.41R" gives +$27 over
66 closes and is ONE-SIDED. A lower arm also puts a floor under every WINNER
earlier, so trades that dipped on the way up get cut short. The three ZEC/XRP
trades that reached 2.9R had no floor until 1.0R; armed at 0.5R, any retrace
through 0.5 x peak ends them near +0.6R instead.

So this replays each real trade BAR BY BAR from its own entry, under the live
exit stack with only the arm varied. Both effects are counted.

WHAT IT CANNOT DO. It uses the trade's actual entry and stop, so it is not a
counterfactual about WHICH trades were taken - only about how they would have
exited. Slot effects are therefore absent, which is the right scope: the arm
changes exits, not entries.

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

from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402

STATE = "/data/futures_runtime_state.json"
ARMS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def _ts(t, k):
    try:
        return dt.datetime.fromisoformat(str(t.get(k) or "")).timestamp()
    except Exception:
        return 0.0


def main() -> int:
    retain = _env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50)
    rat_r = _env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0)
    rat_hi = _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75)
    horizon = _env("FUTURES_CONVEX_TIME_STOP_HOURS", 24.0) * 3600.0
    start = float(os.environ.get("FUTURES_TRIAL_START_TS") or 0)

    d = json.load(open(STATE))
    tr = [t for t in (d.get("trade_history") or [])
          if str(t.get("entry_signal") or "").startswith(("WILDCARD", "TREND", "SQUEEZE"))
          and float(t.get("risk_usdt") or 0) > 0
          and float(t.get("entry_price") or 0) > 0
          and float(t.get("sl_frac_designed") or 0) > 0]
    tr.sort(key=lambda t: _ts(t, "exit_time"))
    print("real trades with reconstructable geometry: %d" % len(tr))

    syms = sorted({str(t.get("symbol") or "") for t in tr})
    cl = MexcFuturesClient(FuturesConfig.from_env())
    now = int(time.time())
    frames, rep = fetch_frames(cl, syms, days=_env("PJ_DAYS", 40), workers=6,
                               min_bars=200, now_ts=now, strict=False)
    print(rep)
    SER = {}
    for s, df in frames.items():
        SER[s] = ([float(x.timestamp()) for x in df.index],
                  [float(x) for x in df["high"]],
                  [float(x) for x in df["low"]],
                  [float(x) for x in df["close"]])

    def walk(t, arm):
        """Replay one trade under the live exit stack with `arm` varied."""
        s = str(t.get("symbol") or "")
        if s not in SER:
            return None
        ts_, hi, lo, cl_ = SER[s]
        e = float(t["entry_price"])
        slf = float(t["sl_frac_designed"])
        sgn = 1.0 if str(t.get("side")) == "LONG" else -1.0
        one = e * slf
        if one <= 0:
            return None
        t0 = _ts(t, "entry_time")
        i0 = None
        for k in range(len(ts_)):
            if ts_[k] >= t0:
                i0 = k
                break
        if i0 is None:
            return None
        tp_r = 3.0 if str(t.get("entry_signal") or "").startswith("TREND") else 5.0
        cost = 0.03
        peak = 0.0
        for k in range(i0, len(ts_)):
            if ts_[k] - t0 > horizon:
                return ((cl_[k - 1] - e) * sgn / one) - cost
            adverse = ((lo[k] if sgn > 0 else hi[k]) - e) * sgn / one
            favour = ((hi[k] if sgn > 0 else lo[k]) - e) * sgn / one
            if peak >= arm:
                lvl = (rat_hi if peak >= rat_r else retain) * peak
                if lvl < peak and adverse <= lvl:
                    return lvl - cost
            if adverse <= -1.0:
                return -1.0 - cost
            if favour >= tp_r:
                return tp_r - cost
            peak = max(peak, favour)
        return None

    for nm, sel in (("TRIAL 18", [t for t in tr if _ts(t, "entry_time") >= start]),
                    ("ALL HISTORY", tr)):
        usable = [t for t in sel if walk(t, 1.0) is not None]
        if len(usable) < 5:
            print("\n%s: only %d replayable" % (nm, len(usable)))
            continue
        live = sum(float(t["pnl_usdt"]) for t in usable)
        print()
        print("=" * 84)
        print("%s: %d trades replayable | LIVE net $%+.2f" % (nm, len(usable), live))
        print("=" * 84)
        print("  %-14s %9s %9s %10s %10s %9s"
              % ("arm", "rescued", "cut short", "net $", "vs replay", "mean R"))
        base_usd = None
        for arm in ARMS:
            rs, usd, resc, cut = [], 0.0, 0, 0
            for t in usable:
                r1 = walk(t, arm)
                r0 = walk(t, 1.0)
                if r1 is None or r0 is None:
                    continue
                if r1 > r0 + 1e-9:
                    resc += 1
                elif r1 < r0 - 1e-9:
                    cut += 1
                rs.append(r1)
                usd += r1 * float(t["risk_usdt"])
            if base_usd is None:
                base_usd = usd
            print("  %-14s %9d %9d %+10.2f %+10.2f %+9.3f"
                  % ("%.1fR%s" % (arm, "  LIVE" if arm == 1.0 else ""),
                     resc, cut, usd, usd - base_usd, sum(rs) / len(rs)))
        print("  (replay of the 1.0R arm should approximate the LIVE net above;")
        print("   the gap is harness error and bounds what the deltas are worth)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
