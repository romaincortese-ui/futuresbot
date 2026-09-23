"""Offline replay tooling that runs the BOT'S OWN mechanics instead of a per-study copy of them.

Why this package exists (impartial assessment 2026-09-23, docs/DECISION_RULE.md "IMPARTIAL ASSESSMENT + REPLAY
AUDIT"): the replay graded D. Every study booked a FIXED stake (sizing grade F) although live sizes off the free
margin and compounds, and 63 separate re-implementations of the exit logic existed, none of them the bot's code. A
path-faithful sizing chain that reproduced the live book to -$1.85 over 151 trades was built in a temp folder and
used by no study. This package makes that chain, and the acceptance scorer that grades a replay against live, repo
code with tests, so the next study imports them instead of writing a 64th copy.

Modules
  sizing      - the live sizing chain as a pure function of a trade stream: cash, isolated margin locked by open
                positions, available = cash - locked, per-sleeve dial SCHEDULES, the 25% margin cap, the regime
                scaler, integer contracts with per-symbol minimums, the per-trade risk cap, deposits/withdrawals as
                explicit events; plus the fixed-stake comparison every study must report beside the compounded one.
  acceptance  - the weekly acceptance scorer: grades a replay against live on ENTRIES, EXITS and SIZING/DOLLARS
                with PASS/FAIL per layer against thresholds defined in one place.
Other replay-repair modules (fair-price exits, data preservation) sit beside these in the same package.

Nothing here is imported by the live runtime; nothing here places orders or writes /data.
"""
