#!/usr/bin/env python3
"""V2 promotion-significance check: bootstrap the per-trade $ ledger.

Given two per-trade result lists (current vs candidate, e.g. from
tools/replay_exits.py or champion/shadow fills), answer:
  - P(candidate beats current) under resampling
  - 5th/50th/95th percentile outcome per config
  - ruin odds (equity path below floor) at the given starting balance

Usage:
  PYTHONPATH=. python tools/mc_ledger.py --current "-12.06,2.77,-0.19,-10.96,7.04" \
      --candidate "-6.0,1.4,-0.1,-5.5,7.04" --balance 100 --floor 50 --n 20000
Seeded RNG: deterministic, reproducible.
"""
from __future__ import annotations

import argparse
import random


def _parse(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def bootstrap(trades: list[float], n_paths: int, path_len: int, balance: float, floor: float, rng: random.Random):
    finals, ruins = [], 0
    for _ in range(n_paths):
        eq = balance
        ruined = False
        for _ in range(path_len):
            eq += rng.choice(trades)
            if eq <= floor:
                ruined = True
                break
        finals.append(eq)
        ruins += ruined
    finals.sort()
    pct = lambda q: finals[int(q * (len(finals) - 1))]
    return pct(0.05), pct(0.50), pct(0.95), ruins / n_paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--balance", type=float, default=100.0)
    ap.add_argument("--floor", type=float, default=50.0)
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--horizon", type=int, default=30, help="trades per simulated path")
    a = ap.parse_args()
    cur, cand = _parse(a.current), _parse(a.candidate)
    rng = random.Random(42)
    # P(candidate beats current): resample equal-length sums
    wins = 0
    for _ in range(a.n):
        sc = sum(rng.choice(cur) for _ in range(a.horizon))
        sd = sum(rng.choice(cand) for _ in range(a.horizon))
        wins += sd > sc
    p_better = wins / a.n
    rng = random.Random(42)
    c5, c50, c95, cruin = bootstrap(cur, a.n, a.horizon, a.balance, a.floor, rng)
    rng = random.Random(42)
    d5, d50, d95, druin = bootstrap(cand, a.n, a.horizon, a.balance, a.floor, rng)
    print(f"P(candidate > current) over {a.horizon} trades: {p_better*100:.1f}%")
    print(f"current  : p5 ${c5:7.1f}  median ${c50:7.1f}  p95 ${c95:7.1f}  ruin(<=${a.floor:.0f}) {cruin*100:.1f}%")
    print(f"candidate: p5 ${d5:7.1f}  median ${d50:7.1f}  p95 ${d95:7.1f}  ruin(<=${a.floor:.0f}) {druin*100:.1f}%")


if __name__ == "__main__":
    main()
