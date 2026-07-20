"""Weekly learning digest — the compounding loop's self-report.

Summarises, propose-only: (1) graduate-or-kill trial progress (docs/
DECISION_RULE.md), (2) the conditional-expectancy engine's OOS-consistent
findings, (3) the shadow ledger's counterfactual scorecard (what the vetoes
cost/saved). Sent to Telegram on a marker-file throttle. Pure builders here;
the runtime owns paths/sending. Fail-soft everywhere.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from futuresbot.conditional_expectancy import default_conditions, rank_conditions

TRIAL_START = datetime(2026, 7, 13, 23, 0, tzinfo=timezone.utc).timestamp()  # docs/DECISION_RULE.md
TRIAL_TARGET_TRADES = 30


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
                          trial_target: int = TRIAL_TARGET_TRADES) -> str:
    convex = [r for r in store_rows if r.get("kind") in ("WILDCARD", "SQUEEZE") or r.get("is_wildcard")]
    trial = [r for r in convex if float(r.get("ts") or 0) >= trial_start]
    rs = [float(r.get("r_multiple") or 0) for r in trial]
    lines = ["🧭 <b>Weekly learning digest</b>", "━━━━━━━━━━━━━━━"]
    if rs:
        net_r = sum(rs)
        usd = sum(float(r.get("pnl_usdt") or 0) for r in trial)
        wins = sum(1 for r in rs if r > 0)
        lines.append(
            f"Trial: <b>{len(trial)}/{trial_target}</b> convex trades | netR <b>{net_r:+.2f}</b> "
            f"| exBest <b>{net_r - max(rs):+.2f}</b> | ${usd:+.2f} | win {100 * wins / len(rs):.0f}%"
        )
    else:
        lines.append(f"Trial: <b>0/{trial_target}</b> convex trades since the rule started")

    ranked = rank_conditions(store_rows, default_conditions(), min_n=6) if store_rows else []
    actionable = [p for p in ranked if p["verdict"] in ("AVOID", "FAVOR")][:3]
    if actionable:
        lines.append("Engine (propose-only):")
        for p in actionable:
            lines.append(f"• {p['verdict']} <b>{p['condition']}</b> gap ${p['gap_usd']:+.2f} (n={p['with']['n']})")
    else:
        lines.append("Engine: no OOS-consistent findings yet")

    resolved = [r for r in shadow_rows if r.get("outcome") is not None]
    if shadow_rows:
        by: dict[str, list[float]] = {}
        for r in resolved:
            key = str(r.get("reject_reason") or "?")
            agg = by.setdefault(key, [0, 0.0])
            agg[0] += 1
            agg[1] += float(r.get("outcome") or 0)
        parts = " | ".join(f"{k}: n={int(n)} cfR {tot:+.1f}" for k, (n, tot) in sorted(by.items()))
        lines.append(f"Shadow: {len(shadow_rows)} logged, {len(resolved)} resolved" + (f" — {parts}" if parts else ""))
    else:
        lines.append("Shadow: no vetoed/near-miss signals logged yet")
    lines.append("<i>counterfactuals are directional-only; nothing here auto-applies</i>")
    return "\n".join(lines)
