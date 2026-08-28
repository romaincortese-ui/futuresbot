#!/usr/bin/env bash
# Open convex trial 18. STAGED - does nothing without --confirm.
#
#   bash tools/open_trial18.sh              # dry run: show current vs intended
#   bash tools/open_trial18.sh --confirm    # apply, verify, redeploy
#
# Under test:      FUTURES_REGIME_FLOOR_MULT      0.25 -> 0.50
# Shipped with it: FUTURES_CONVEX_TRAIL_RETAIN_FRAC 0.30 -> 0.50
# See docs/DECISION_RULE.md "CONVEX TRIAL 18" for why both move in one reset.
#
# Two failure modes this guards against, both of which have actually happened:
#   1. Railway marks variable-only changes SKIPPED and the running process keeps
#      the OLD environment. The redeploy is not optional.
#   2. Trial 17 was opened with TRIAL_START_TS bumped and TRIAL_LABEL left
#      behind, so /status reported the wrong trial for days.
set -euo pipefail

SVC="Futures-bot"
VARS=(
  "FUTURES_REGIME_FLOOR_MULT=0.50"
  "FUTURES_CONVEX_TRAIL_RETAIN_FRAC=0.50"
  "FUTURES_TRIAL_LABEL=18"
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
printf '  %s\n' "$(printf '%s\n' "$CUR" | grep -E 'FUTURES_TRIAL_START_TS' | tr -s ' ' || true)"

echo
echo "=== INTENDED ==="
for kv in "${VARS[@]}"; do echo "  $kv"; done
echo "  FUTURES_TRIAL_START_TS=<now>"

if [ "${1:-}" != "--confirm" ]; then
  echo
  echo "DRY RUN. Nothing changed. Re-run with --confirm to apply."
  exit 0
fi

TS="$(date +%s)"
echo
echo "=== APPLYING (trial 18, start_ts=$TS) ==="
railway variables --service "$SVC" \
  --set "FUTURES_REGIME_FLOOR_MULT=0.50" \
  --set "FUTURES_CONVEX_TRAIL_RETAIN_FRAC=0.50" \
  --set "FUTURES_TRIAL_START_TS=$TS" \
  --set "FUTURES_TRIAL_LABEL=18"

echo
echo "=== VERIFY (read back before redeploy) ==="
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
if printf '%s\n' "$AFTER" | grep -q "$TS"; then
  echo "  OK   FUTURES_TRIAL_START_TS = $TS"
else
  echo "  FAIL FUTURES_TRIAL_START_TS did not read back"; fail=1
fi
if [ "$fail" -ne 0 ]; then
  echo
  echo "ABORTING before redeploy - the environment is not what was intended."
  exit 1
fi

echo
echo "=== REDEPLOY (required: variable-only changes are marked SKIPPED) ==="
railway redeploy --service "$SVC" --yes

echo
echo "Trial 18 open. Confirm in /status that the label reads 18 and the window"
echo "starts now - _trial_label_drift() warns if the two disagree."
echo
echo "NEXT GATE: Friday 2026-09-04, funding decision. It is a SIZING check -"
echo "realised mean risk in [1.6%, 2.2%] at n>=10 funds; under 1.5% does not."
echo "Not a P&L check. See docs/DECISION_RULE.md 'PRE-REGISTERED FUNDING GATE'."
