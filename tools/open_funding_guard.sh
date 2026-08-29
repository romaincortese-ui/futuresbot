#!/usr/bin/env bash
# Arm the drawdown guard for the funded week. STAGED - does nothing without --confirm.
#
#   bash tools/open_funding_guard.sh              # dry run: current vs intended
#   bash tools/open_funding_guard.sh --confirm    # apply, verify, redeploy
#
#   FUTURES_CONVEX_DRAWDOWN_BRAKE  unset(off) -> 1     the missing wire; the convex
#                                                      sleeves have never been
#                                                      connected to the kill switch
#   DRAWDOWN_HALT_PCT              0.25 -> 0.10        halt new entries at -10%
#   DRAWDOWN_HALT_WINDOW_DAYS      30 -> 7             measure over the test week
#
#   DRAWDOWN_SOFT_PCT              0.08(default) -> 0.10   see below
#   DRAWDOWN_SOFT_WINDOW_DAYS      30(default) -> 7
#
# USE_DRAWDOWN_KILL=1 is already set - do not re-set it.
#
# WHY THE SOFT THROTTLE IS NEUTRALISED. At its 0.08 default, compute_drawdown_state
# returns label=THROTTLE with size_multiplier=0.5 - it HALVES position size, it does
# not merely warn. That is a fourth multiplier in the sizing chain and it was never
# measured; plan_halt.py measured the HALT only. Setting soft_pct equal to hard_pct
# means the halt (checked first) always wins, so the guard is exactly the mechanism
# that was measured and nothing more. Both windows are set to 7 so the guard reads
# the test week rather than 30 days of prior trials.
#
# MEASURED (tools/plan_halt.py, 2026-08-29, 228 rolling 7-day windows at $1072):
#   halt at -10% from window start costs $0.54 of median and cuts the worst week
#   from -$259.18 to -$148.61, firing in 18% of weeks. -8% saves $20 more but
#   fires in 26%, which ends one test in four - the test is for information, so
#   firing less matters. Force-closing the open book at the threshold was measured
#   at +$16.44 DESTROYED per firing and is deliberately NOT implemented; use
#   /close all by hand after looking at the positions.
#
# A 7-day window makes the halt self-sticky for a 7-day test: a drawdown on day 3
# stays inside the window until day 10, so it will not silently resume mid-test.
# That is the "until manual restart" property, without new state.
#
# TIMING. Read tools/../docs/DECISION_RULE.md before running this DURING trial 18.
# The soft brake (DRAWDOWN_SOFT_PCT, default 0.08) multiplies margin, which makes
# it a FOURTH size multiplier in a trial whose entire purpose is measuring realised
# risk through a known sizing chain. Trial 16 was voided by exactly that class of
# contamination. This script is built for FRIDAY, alongside the deposit.
set -euo pipefail

SVC="Futures-bot"
VARS=(
  "FUTURES_CONVEX_DRAWDOWN_BRAKE=1"
  "DRAWDOWN_HALT_PCT=0.10"
  "DRAWDOWN_HALT_WINDOW_DAYS=7"
  "DRAWDOWN_SOFT_PCT=0.10"
  "DRAWDOWN_SOFT_WINDOW_DAYS=7"
)

echo "=== CURRENT ==="
CUR="$(railway variables --service "$SVC" 2>/dev/null || true)"
for kv in "${VARS[@]}"; do
  k="${kv%%=*}"
  line="$(printf '%s\n' "$CUR" | grep -E "[[:space:]]${k}[[:space:]]" || true)"
  if [ -z "$line" ]; then
    echo "  ${k} = <unset, using code default>"
  else
    printf '  %s\n' "$(printf '%s' "$line" | tr -s ' ')"
  fi
done
for k in USE_DRAWDOWN_KILL DRAWDOWN_SOFT_PCT DRAWDOWN_SOFT_WINDOW_DAYS; do
  line="$(printf '%s\n' "$CUR" | grep -E "[[:space:]]${k}[[:space:]]" || true)"
  [ -z "$line" ] && echo "  ${k} = <unset, using code default>" \
                 || printf '  %s\n' "$(printf '%s' "$line" | tr -s ' ')"
done

echo
echo "=== INTENDED ==="
for kv in "${VARS[@]}"; do echo "  $kv"; done

if [ "${1:-}" != "--confirm" ]; then
  echo
  echo "DRY RUN. Nothing changed. Re-run with --confirm to apply."
  exit 0
fi

echo
echo "=== APPLYING ==="
railway variables --service "$SVC" \
  --set "FUTURES_CONVEX_DRAWDOWN_BRAKE=1" \
  --set "DRAWDOWN_HALT_PCT=0.10" \
  --set "DRAWDOWN_HALT_WINDOW_DAYS=7" \
  --set "DRAWDOWN_SOFT_PCT=0.10" \
  --set "DRAWDOWN_SOFT_WINDOW_DAYS=7"

echo
echo "=== VERIFY ==="
AFTER="$(railway variables --service "$SVC" 2>/dev/null || true)"
fail=0
for kv in "${VARS[@]}"; do
  k="${kv%%=*}"; v="${kv##*=}"
  if printf '%s\n' "$AFTER" | grep -E "[[:space:]]${k}[[:space:]]" | grep -q "$v"; then
    echo "  OK   ${k} = ${v}"
  else
    echo "  FAIL ${k} did not read back as ${v}"; fail=1
  fi
done
if [ "$fail" -ne 0 ]; then
  echo
  echo "Railway serves a cached read for ~30s after a write. Confirm from a fresh"
  echo "process before treating this as a failed write:"
  echo "  railway variables --service $SVC | grep DRAWDOWN"
  echo "ABORTING before redeploy."
  exit 1
fi

# --json is NOT cosmetic. Without it this exits 0, prints nothing and creates NO
# deployment - the container keeps the old environment (observed 2026-08-29).
echo
echo "=== REDEPLOY ==="
DEP="$(railway redeploy --service "$SVC" --yes --json 2>&1 | tail -1)"
echo "  deployment: $DEP"
case "$DEP" in
  *'"id"'*) echo "  queued. The container swap lagged ~50 min on 2026-08-29;" ;;
  *) echo "  WARNING: no deployment id - redeploy from the Railway dashboard" ;;
esac
echo "  confirm it landed by watching the cycle counter RESET:"
echo "    railway logs --service $SVC | grep -oE 'cycle=[0-9]+' | tail -1"
echo
echo "Guard armed: entries halt at -10% over a 7-day window. Open positions are"
echo "NOT closed automatically - that was measured as value-destroying. Use"
echo "/close all by hand if you want the book flat."
