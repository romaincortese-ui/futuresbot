"""Weekly learning digest — the compounding loop's self-report.

Summarises, propose-only: (1) graduate-or-kill trial progress (docs/
DECISION_RULE.md), (2) the conditional-expectancy engine's OOS-consistent
findings, (3) the shadow ledger's counterfactual scorecard (what the vetoes
cost/saved). Sent to Telegram on a marker-file throttle. Pure builders here;
the runtime owns paths/sending. Fail-soft everywhere.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from futuresbot.conditional_expectancy import default_conditions, rank_conditions
from futuresbot.shadow_ledger import CONVEX_SLEEVES, cost_r


def _net(row: dict) -> float:
    """Counterfactual R after round-trip cost.

    Rows resolved before 2026-08-09 carry no ``outcome_net``; deriving it from
    the row's own stop geometry keeps the historical rows comparable instead of
    silently reporting them as free."""
    if row.get("outcome_net") is not None:
        try:
            return float(row["outcome_net"])
        except (TypeError, ValueError):
            pass
    try:
        return float(row.get("outcome") or 0.0) - cost_r(row)
    except (TypeError, ValueError):
        return 0.0


def _trial_start() -> float:
    """Start of the CURRENT trial, epoch seconds. docs/DECISION_RULE.md is the
    authoritative record; this is the machine-readable pointer at it.

    Was a hardcoded 2026-07-13 (trial 4) and never moved through trials 5, 6,
    6.5 and 7 — so every "n/30" the digest reported was counting four trials as
    one. Bumping FUTURES_TRIAL_START_TS IS the reset operation now.
    """
    raw = os.environ.get("FUTURES_TRIAL_START_TS", "").strip()
    try:
        if raw:
            return float(raw)
    except (TypeError, ValueError):
        pass
    # Trial 7 deploy, 2026-08-07 19:22 UTC.
    return datetime(2026, 8, 7, 19, 22, tzinfo=timezone.utc).timestamp()


TRIAL_START = _trial_start()
TRIAL_TARGET_TRADES = 30
TRIAL_LABEL = os.environ.get("FUTURES_TRIAL_LABEL", "7").strip() or "7"


def load_jsonl(path) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return rows


def build_learning_digest(store_rows: list[dict], shadow_rows: list[dict], *,
                          trial_start: float = TRIAL_START,
                          trial_target: int = TRIAL_TARGET_TRADES,
                          missed_lines: list[str] | None = None) -> str:
    # Trial 7 is scored on WILDCARD closes (docs/DECISION_RULE.md). Counting
    # SQUEEZE here made the digest disagree with /status on the same "n/30".
    convex = [r for r in store_rows if str(r.get("kind") or "").upper() == "WILDCARD"]
    trial = [r for r in convex if float(r.get("ts") or 0) >= trial_start]
    rs = [float(r.get("r_multiple") or 0) for r in trial]
    lines = ["🧭 <b>Weekly learning digest</b>", "━━━━━━━━━━━━━━━"]
    if rs:
        net_r = sum(rs)
        usd = sum(float(r.get("pnl_usdt") or 0) for r in trial)
        wins = sum(1 for r in rs if r > 0)
        lines.append(
            f"Trial: <b>{len(trial)}/{trial_target}</b> WC closes | netR <b>{net_r:+.2f}</b> "
            f"| exBest <b>{net_r - max(rs):+.2f}</b> | ${usd:+.2f} | win {100 * wins / len(rs):.0f}%"
        )
    else:
        lines.append(f"Trial: <b>0/{trial_target}</b> WC closes since the rule started")

    # TP completion (trial 4): the 3.0xATR stop doubled the price move +5R needs
    # (~75%). If completions collapse, the stop/TP pairing is too demanding and
    # the fix is scaling TP down at wide stops — not reverting the stop.
    kinds = [r.get("exit_kind") for r in trial if r.get("exit_kind")]
    if kinds:
        tp = kinds.count("TP"); stop = kinds.count("STOP"); other = kinds.count("OTHER")
        lines.append(f"Exits: TP <b>{tp}</b> ({100 * tp / len(kinds):.0f}%) | stop {stop} | other {other}")

    ranked = rank_conditions(store_rows, default_conditions(), min_n=6) if store_rows else []
    actionable = [p for p in ranked if p["verdict"] in ("AVOID", "FAVOR")][:3]
    if actionable:
        lines.append("Engine (propose-only):")
        for p in actionable:
            unit = "R" if p.get("metric") == "R" else "$"
            lines.append(f"• {p['verdict']} <b>{p['condition']}</b> gap {p.get('gap', p['gap_usd']):+.2f}{unit} (n={p['with']['n']})")
    else:
        lines.append("Engine: no OOS-consistent findings yet")

    # The Sniper's rows are a deliberate shadow STUDY, not vetoed near-misses —
    # folded into the generic scorecard they would render as a cryptic
    # "shadow_only: n=8". Split them out and answer the actual question:
    # what would this sleeve have done if it were live?
    # Scope the veto scorecard to the trial. It used to read the whole file, so
    # it pooled trials 4-7 — regimes, sleeve configs and exit policies mixed
    # into one cfR that no decision could safely rest on.
    in_trial = [r for r in shadow_rows if float(r.get("ts") or 0) >= trial_start]
    sniper = [r for r in in_trial if str(r.get("sleeve") or "").startswith("SNIPER")]
    other = [r for r in in_trial if not str(r.get("sleeve") or "").startswith("SNIPER")]
    if sniper:
        by_variant: dict[str, list[dict]] = {}
        for r in sniper:
            sleeve = str(r.get("sleeve") or "SNIPER")
            by_variant.setdefault(sleeve.split("_", 1)[1] if "_" in sleeve else "SWING", []).append(r)
        lines.append("🎯 Sniper SHADOW (would-be trades, never traded):")
        for name, rows in sorted(by_variant.items()):
            res = [r for r in rows if r.get("outcome") is not None]
            net = sum(float(r.get("outcome") or 0) for r in res)
            wins = sum(1 for r in res if float(r.get("outcome") or 0) > 0)
            kinds: dict[str, int] = {}
            for r in res:
                k = str(r.get("outcome_kind") or "?")
                kinds[k] = kinds.get(k, 0) + 1
            net_after = sum(_net(r) for r in res)
            line = f"• <b>{name}</b>: {len(rows)} logged, {len(res)} resolved | cfR <b>{net:+.1f}</b>"
            if res:
                line += (f" (net of cost <b>{net_after:+.1f}</b>) | win {100 * wins / len(res):.0f}% "
                         f"| tp {kinds.get('tp', 0)} stop {kinds.get('stop', 0)} timeout {kinds.get('timeout', 0)}")
            lines.append(line)
        lines.append("<i>cfR is fee-free; read the net figure — a 0.37% stop pays ~0.5R "
                     "per round trip</i>")

    resolved = [r for r in other if r.get("outcome") is not None]
    if other:
        by: dict[str, list[float]] = {}
        for r in resolved:
            key = str(r.get("reject_reason") or "?")
            agg = by.setdefault(key, [0, 0.0, 0.0])
            agg[0] += 1
            agg[1] += float(r.get("outcome") or 0)
            agg[2] += _net(r)
        parts = " | ".join(f"{k}: n={int(n)} cfR {tot:+.1f} net {net:+.1f}"
                           for k, (n, tot, net) in sorted(by.items()))
        lines.append(f"Shadow (this trial): {len(other)} logged, {len(resolved)} resolved"
                     + (f" — {parts}" if parts else ""))

        # A convex row with no exit_policy tag was scored under the retired 48h
        # bracket. Saying so is the difference between a stale number and a
        # number that is quietly wrong.
        legacy = sum(1 for r in resolved
                     if not r.get("exit_policy") and str(r.get("sleeve") or "") in CONVEX_SLEEVES)
        if legacy:
            lines.append(f"<i>⚠️ {legacy} row(s) still scored under the retired 48h bracket "
                         f"— awaiting re-resolution under the live exit</i>")
    # Trial-scoping is right for a verdict and useless for a sample: at ~1 veto
    # a week the in-trial scorecard reads almost nothing, and at every trial
    # reset it reads zero. Both blocks sit OUTSIDE `if other:` — inside it, an
    # empty trial window made the digest assert "no signals logged yet" over a
    # ledger holding 34 of them, and suppressed the pooled line that exists for
    # exactly that case.
    pooled = [r for r in shadow_rows
              if not str(r.get("sleeve") or "").startswith("SNIPER")
              and r.get("outcome") is not None]
    if not other:
        lines.append(f"Shadow (this trial): 0 logged"
                     + (f" — {len(pooled)} resolved in earlier trials" if pooled
                        else "; none logged yet"))
    if len(pooled) > len(resolved):
        tot = sum(float(r.get("outcome") or 0) for r in pooled)
        lines.append(f"<i>pooled across trials (n={len(pooled)}): cfR {tot:+.1f}, "
                     f"net {sum(_net(r) for r in pooled):+.1f} — regimes and gate "
                     f"configs differ; not a verdict</i>")
    lines.append("<i>counterfactuals are directional-only; nothing here auto-applies</i>")
    if missed_lines:
        lines.append("━━━━━━━━━━━━━━━")
        lines.extend(missed_lines)
    return "\n".join(lines)
