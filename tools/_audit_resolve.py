"""(d) Does the bar walk in retention_trail_ab.resolve use post-entry-bar info?

Synthetic bar sequences, hand-checked expectations. bars = (ts, high, low, close).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

FLOOR = ratchet(3.0, 0.75)          # live: retain 0.30 below 3R, 0.75 above, arm 1R
H = 24 * 3600
NOW = 10_000_000


def B(*rows):
    return [(1_000_000 + k * 900, hi, lo, cl) for k, (hi, lo, cl) in enumerate(rows)]


def show(name, bars, i0, e, sl, tp, side="LONG", cost=0.0, expect=""):
    g = resolve(bars, i0, e, sl, tp, abs(tp - e) / abs(e - sl), side, H, cost, FLOOR, 0.02, NOW)
    print("  %-52s -> %s   [expect %s]" % (name, g, expect))
    return g


print("=== D1. is the ENTRY bar itself used for exits? ===")
# entry 100, stop 90, tp 150. The ENTRY bar (index 0) has low 50 and high 200:
# if the walk included it, it would stop out (or TP) immediately.
bars = B((200.0, 50.0, 100.0), (101.0, 99.0, 100.0), (101.0, 99.0, 100.0))
show("entry bar low 50 / high 200, later bars flat", bars, 0, 100.0, 90.0, 150.0,
     expect="None (unresolved, horizon not elapsed) - NOT a stop/tp")

print("\n=== D2. is peak_r taken from PRIOR bars only? ===")
# bar1: high 130 (=+3.0R) and low 100 (=0.0R) in the SAME bar.
# retain at peak>=3.0 is 0.75 -> level 2.25R = price 122.5.
# If the peak from bar1 were usable inside bar1, the low of 100 would trip a
# trail at +2.25R. Correct behaviour: bar1 sets peak AFTER its own checks, so
# nothing books on bar1; bar2 (low 100) then trails at 0.75*3.0 = 2.25R.
bars = B((100.0, 100.0, 100.0), (130.0, 100.0, 130.0), (130.0, 100.0, 100.0))
show("bar1 high=+3R & low=0R same bar; bar2 low=0R", bars, 0, 100.0, 90.0, 150.0,
     expect="trail +2.25R at bar2 ts 1001800, not bar1 ts 1000900")

print("\n=== D3. same-bar STOP and TP: which wins? ===")
bars = B((100.0, 100.0, 100.0), (160.0, 85.0, 100.0))
show("bar1 high 160 (>tp 150) AND low 85 (<sl 90)", bars, 0, 100.0, 90.0, 150.0,
     expect="stop -1R (adverse-first, conservative)")

print("\n=== D4. same-bar TRAIL and STOP: which wins? ===")
# arm at +1R on bar1 (high 110 = +1R -> peak 1.0). bar2 low 85 goes through the
# hard stop 90 AND through the 0.30*1.0 = +0.30R trail level of 103.
bars = B((100.0, 100.0, 100.0), (110.0, 100.0, 110.0), (110.0, 85.0, 85.0))
show("armed +1R, bar2 low 85 (through both trail 103 and stop 90)",
     bars, 0, 100.0, 90.0, 150.0,
     expect="trail +0.30R -- books ABOVE the stop on a bar that traded through it")

print("\n=== D5. TRAIL FILL: booked at the level or at the bar's real extreme? ===")
# armed at +4R (peak 4.0 -> retain 0.75 -> level 3.0R = price 130).
# bar3 collapses to a low of 91 (= +0.1R). A resting stop at 130 that gapped
# would fill far below 130.
bars = B((100.0, 100.0, 100.0), (140.0, 100.0, 140.0), (140.0, 91.0, 91.0))
show("peak +4R then a bar with low +0.1R", bars, 0, 100.0, 90.0, 900.0,
     expect="trail +3.00R -- the modelled fill, NOT the +0.1R the bar traded")

print("\n=== D6. unresolved trades: marked to market or dropped? ===")
bars = B((100.0, 100.0, 100.0), (101.0, 99.0, 101.0))
g = resolve(bars, 0, 100.0, 90.0, 150.0, 5.0, "LONG", H, 0.0, FLOOR, 0.02, NOW)
print("  data ends inside horizon, now-t0 >> horizon        -> %s" % (g,))
g = resolve(bars, 0, 100.0, 90.0, 150.0, 5.0, "LONG", H, 0.0, FLOOR, 0.02, 1_000_100)
print("  data ends inside horizon, now-t0 <  horizon        -> %s   [expect None]" % (g,))

print("\n=== D7. SHORT geometry sanity (clamped target) ===")
# short from 100 with a 6.7% stop -> nominal 5R target is -33.5%, unclamped.
# a clamped short: stop 20% -> nominal target -100%, clamped to -50% = price 50.
bars = B((100.0, 100.0, 100.0), (100.0, 49.0, 49.0))
show("short e100 sl120 tp50 (clamped), bar1 low 49", bars, 0, 100.0, 120.0, 50.0,
     side="SHORT", expect="tp at tp_r=2.5 (reachable), NOT 5.0")
