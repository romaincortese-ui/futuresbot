"""What would FUTURES_CONVEX_DRAWDOWN_BRAKE=1 have done through trials 17 and 18?

    railway ssh -> /opt/venv/bin/python tools/pit_drawdown_brake.py

THE MECHANISM BEING REPLAYED (futuresbot/runtime.py:7566-7574, drawdown_kill.py).
At every convex ENTRY the bot rebuilds an equity curve from closed trades,
anchored to live equity so cash flows do not register, and reads the
peak-to-current drawdown inside a rolling window:

    dd over 30d >= 8%   -> THROTTLE, size x0.5
    dd over 30d >= 25%  -> HALT,     size x0   (entry blocked; open positions untouched)

Live env: DRAWDOWN_SOFT_PCT=0.08, DRAWDOWN_HALT_PCT=0.25, both windows 30d.
Stateless: recomputed on each entry, clears the instant dd falls back under.

TWO PASSES, because they answer different questions.
  A. READ-ONLY: given the ACTUAL history, what state would the brake have read
     at each entry? Tells you WHEN it would have fired and how close it came.
  B. PATH-DEPENDENT: apply the multiplier to each gated trade's P&L and feed the
     adjusted P&L back into the curve and the equity anchor for every later
     entry. Tells you what it would have COST or SAVED in dollars.

WHAT IT CANNOT DO, stated so the number is not over-read.
- A HALTED entry does not open, which frees a slot a different signal might
  have filled. That reshuffling is NOT modelled; a halt is scored as P&L = 0.
- x0.5 is applied to P&L directly. Live it halves margin, which halves
  contracts with integer truncation, so the real multiplier is <= 0.5.
- The equity anchor at each entry is the most recent `equity_at_close_usdt`
  before it, not the live exchange snapshot the bot would have read. Between
  closes that is stale by the open positions' unrealised P&L.

READ-ONLY.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os

STATE = os.environ.get("PJ_STATE", "/data/futures_runtime_state.json")
FEATURES = os.environ.get("PJ_FEATURES", "/data/futures_feature_store.jsonl")
T17 = dt.datetime(2026, 8, 27, 9, 32, tzinfo=dt.UTC).timestamp()
T18 = float(os.environ.get("FUTURES_TRIAL_START_TS") or 1787960778)
SOFT = float(os.environ.get("DRAWDOWN_SOFT_PCT") or 0.08)
HARD = float(os.environ.get("DRAWDOWN_HALT_PCT") or 0.25)
WIN = float(os.environ.get("DRAWDOWN_SOFT_WINDOW_DAYS") or 30.0) * 86400.0
CONVEX = ("WILDCARD", "TREND", "SQUEEZE")


def _f(x, d=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else d
    except (TypeError, ValueError):
        return d


def _iso(s):
    try:
        return dt.datetime.fromisoformat(str(s)).timestamp()
    except Exception:
        return 0.0


def _state(dd):
    if dd >= HARD:
        return "HALT", 0.0
    if dd >= SOFT:
        return "THROTTLE", 0.5
    return "NORMAL", 1.0


def main() -> int:
    hist = json.load(open(STATE))["trade_history"]
    trades = []
    for i, t in enumerate(hist):
        et, xt = _iso(t.get("entry_time")), _iso(t.get("exit_time"))
        if et <= 0 or xt <= 0:
            continue
        trades.append({"i": i, "sym": str(t.get("symbol") or ""),
                       "sig": str(t.get("entry_signal") or ""),
                       "entry": et, "exit": xt, "pnl": _f(t.get("pnl_usdt")),
                       "convex": str(t.get("entry_signal") or "").startswith(CONVEX)})
    trades.sort(key=lambda z: z["exit"])

    anchors = []
    try:
        for line in open(FEATURES, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts, eq = _f(r.get("ts")), _f(r.get("equity_at_close_usdt"))
            if ts > 0 and eq > 0:
                anchors.append((ts, eq))
    except FileNotFoundError:
        pass
    anchors.sort()

    def equity_before(T):
        eq = None
        for ts, e in anchors:
            if ts < T:
                eq = e
            else:
                break
        return eq

    gated = sorted([t for t in trades if t["convex"] and t["entry"] >= T17],
                   key=lambda z: z["entry"])
    print("=" * 80)
    print("DRAWDOWN BRAKE REPLAY  -  trials 17+18, %d convex entries" % len(gated))
    print("  soft %.0f%% -> x0.5   hard %.0f%% -> x0   window %.0fd" % (SOFT * 100, HARD * 100, WIN / 86400))
    print("=" * 80)

    def dd_at(T, pnl_of, eq_shift):
        """Peak-to-current drawdown over [T-WIN, T) as the bot computes it."""
        E = equity_before(T)
        if E is None:
            return None, None
        E += eq_shift
        window = [t for t in trades if T - WIN <= t["exit"] < T]
        # NAV at each close = E minus everything that closed after it (before T)
        navs = [E]
        for k, t in enumerate(window):
            later = sum(pnl_of(u) for u in window[k + 1:])
            navs.append(E - later)
        peak = max(navs)
        return (max(0.0, (peak - E) / peak) if peak > 0 else 0.0), E

    for label, path_dependent in (("A. READ-ONLY (actual history)", False),
                                  ("B. PATH-DEPENDENT (brake P&L fed back)", True)):
        print()
        print("-" * 80)
        print(label)
        print("-" * 80)
        adj = {}                      # trade index -> adjusted pnl
        rows = []
        for t in gated:
            def pnl_of(u):
                return adj.get(u["i"], u["pnl"]) if path_dependent else u["pnl"]
            shift = (sum(adj[u["i"]] - u["pnl"] for u in trades
                         if u["i"] in adj and u["exit"] < t["entry"])
                     if path_dependent else 0.0)
            dd, E = dd_at(t["entry"], pnl_of, shift)
            if dd is None:
                continue
            st, mult = _state(dd)
            new_pnl = t["pnl"] * mult
            if path_dependent and mult < 1.0:
                adj[t["i"]] = new_pnl
            rows.append((t, dd, E, st, mult, new_pnl))

        print("  %-16s %-9s %-8s %7s %8s %-9s %8s %8s"
              % ("entry (UTC)", "symbol", "trial", "dd30", "equity", "state", "pnl $", "brake $"))
        for t, dd, E, st, mult, new_pnl in rows:
            when = dt.datetime.fromtimestamp(t["entry"], dt.UTC).strftime("%m-%d %H:%M")
            tr = "18" if t["entry"] >= T18 else "17"
            flag = "" if st == "NORMAL" else "  <-- " + st
            print("  %-16s %-9s %-8s %6.1f%% %8.2f %-9s %+8.2f %+8.2f%s"
                  % (when, t["sym"].replace("_USDT", ""), tr, dd * 100, E, st,
                     t["pnl"], new_pnl, flag))

        dds = [dd for _, dd, _, _, _, _ in rows]
        n_thr = sum(1 for r in rows if r[3] == "THROTTLE")
        n_halt = sum(1 for r in rows if r[3] == "HALT")
        actual = sum(r[0]["pnl"] for r in rows)
        braked = sum(r[5] for r in rows)
        print()
        print("  entries gated: %d | THROTTLE fired: %d | HALT fired: %d" % (len(rows), n_thr, n_halt))
        if dds:
            k = max(range(len(dds)), key=lambda i: dds[i])
            print("  max dd30 at any entry: %.1f%%  (on %s, %s)  -> %.1f pts from the %.0f%% throttle line"
                  % (dds[k] * 100,
                     dt.datetime.fromtimestamp(rows[k][0]["entry"], dt.UTC).strftime("%m-%d %H:%M"),
                     rows[k][0]["sym"].replace("_USDT", ""),
                     (SOFT - dds[k]) * 100, SOFT * 100))
        print("  P&L actual $%+.2f | with brake $%+.2f | brake effect $%+.2f"
              % (actual, braked, braked - actual))
        for tr, lo, hi in (("17", T17, T18), ("18", T18, float("inf"))):
            sub = [r for r in rows if lo <= r[0]["entry"] < hi]
            if sub:
                print("    trial %s: %d entries, actual $%+.2f, with brake $%+.2f"
                      % (tr, len(sub), sum(r[0]["pnl"] for r in sub), sum(r[5] for r in sub)))

    print()
    print("=" * 80)
    print("READING")
    print("=" * 80)
    print("  If neither state fired, the brake was a no-op across both trials and")
    print("  enabling it changes nothing about this history. The number that")
    print("  matters is then max dd30 vs the 8% line: how much worse a stretch")
    print("  would have had to be before the brake bit at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
