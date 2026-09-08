"""The owner's %-of-margin arm, on the same Min1 paths as the arm sweep.

A %-of-margin arm is NOT a flat R arm. Profit as % of margin = r * sl_margin_pct,
and sl_margin_pct = sl_frac * leverage * 100, so the rule arms at

    r_arm = P / (sl_frac * leverage * 100)

which varies per position with the stop width and the (integer-truncated) leverage.
"""
import eng, random, statistics as st, datetime as dt
R = 15.49
C = dict(res="Min1", order="favour_first", cost_guard=True)

def slmp(t):
    """1R as a % of margin for this position."""
    try:
        return float(t["sl_frac_designed"]) * float(t["leverage"]) * 100.0
    except (KeyError, TypeError, ValueError):
        return None

U = [t for t in eng.TR if eng.walk(t, 1.0, **C) is not None and slmp(t)]
base = {id(t): eng.walk(t, 1.0, **C) for t in U}
print("population: %d trades with a Min1 path and a usable stop geometry" % len(U))
sm = [slmp(t) for t in U]
print("1R as %% of margin: min %.2f  median %.2f  max %.2f\n" % (min(sm), st.median(sm), max(sm)))

def run(P):
    """Arm at P% of margin. Returns (delta_R, per-trade rows)."""
    rows = []
    for t in U:
        a = P / slmp(t)
        v = eng.walk(t, a, **C)
        if v is None:
            continue
        rows.append((t, a, base[id(t)], v))
    return rows

def report(P):
    rows = run(P)
    d = [(t, a, b, v, v - b) for t, a, b, v in rows]
    arms = [a for _, a, _, _, _ in d]
    resc = [x for x in d if x[4] > 1e-9]
    cut  = [x for x in d if x[4] < -1e-9]
    tot = sum(x[4] for x in d)
    # ex-top-5%: drop the 5% largest BASELINE outcomes (the runners)
    k = max(1, int(round(0.05 * len(d))))
    order = sorted(d, key=lambda x: -x[2])
    extop = sum(x[4] for x in order[k:])
    print("  %5.1f%% of margin -> arm %.2f-%.2fR (median %.2f) | resc %2d cut %2d | "
          "netR %+7.3f  $%+8.2f/32d  $%+7.2f/mo | ex-top5%% $%+7.2f"
          % (P, min(arms), max(arms), st.median(arms), len(resc), len(cut),
             tot, tot * R, tot * R * 30.0 / 32.1, extop * R))
    return tot, d

print("THE OWNER'S RULE, SWEPT  (baseline = live arm 1.0R, retain 0.50)")
res = {}
for P in (8, 10, 12, 14, 15, 16, 17, 18, 20, 22, 25):
    res[P] = report(P)

print("\nFLAT-R COMPARISON, same engine, same population")
for a in (0.8, 0.85, 0.9, 0.95, 1.0, 1.25, 1.5):
    d = [(t, eng.walk(t, a, **C) - base[id(t)]) for t in U if eng.walk(t, a, **C) is not None]
    tot = sum(x for _, x in d)
    print("  arm %.2fR (flat)          | resc %2d cut %2d | netR %+7.3f  $%+8.2f/32d  $%+7.2f/mo"
          % (a, sum(1 for _, x in d if x > 1e-9), sum(1 for _, x in d if x < -1e-9),
             tot, tot * R, tot * R * 30.0 / 32.1))

print("\nWHICH TRADES MOVE at 15%% of margin")
_, d15 = res[15]
for t, a, b, v, x in sorted(d15, key=lambda z: z[4]):
    if abs(x) > 1e-9:
        print("   %-14s %-5s arm %.3fR (1R=%.1f%% of margin) | %+.3fR -> %+.3fR  = $%+7.2f"
              % (str(t["symbol"])[:14], str(t.get("side")), a, slmp(t), b, v, x * R))

print("\nPLACEBO: shift every entry +/-12h and re-measure the SAME rule")
random.seed(11)
for P in (15,):
    real = res[P][0] * R
    sims = []
    for _ in range(60):
        s = 0.0
        for t in U:
            sh = random.uniform(-12, 12) * 3600
            t2 = dict(t)
            t2["entry_time"] = (dt.datetime.fromisoformat(t["entry_time"])
                                + dt.timedelta(seconds=sh)).isoformat()
            a = eng.walk(t2, P / slmp(t), **C); b = eng.walk(t2, 1.0, **C)
            if a is None or b is None:
                continue
            s += a - b
        sims.append(s * R)
    sims.sort()
    hits = sum(1 for s in sims if abs(s) >= abs(real))
    print("  %d%%: real $%+.2f | placebo median $%+.2f, 5-95%% [$%+.2f, $%+.2f], "
          "|placebo|>=|real| in %d/60" % (P, real, st.median(sims), sims[3], sims[56], hits))
