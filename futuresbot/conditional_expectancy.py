"""Stage-2 conditional-expectancy engine — the honest 'learn from wins & losses'.

Given a corpus of closed-trade feature rows (Stage-1 tagger output + outcome),
find conditions whose PRESENCE reliably changes expectancy, validated OUT-OF-
SAMPLE (time-split). This is with-X vs without-X — NOT loss-frequency, NOT a
per-trade narrative (both are hindsight traps). PROPOSE only: it never trades or
auto-applies; a human/daily-routine decides whether to act on a proposal.
"""
from __future__ import annotations

import math
from statistics import mean


def _usd(r: dict) -> float:
    try:
        return float(r.get("pnl_usdt") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _r_mult(r: dict):
    v = r.get("r_multiple")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _ts(r: dict) -> float:
    try:
        return float(r.get("ts") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe(pred, r: dict) -> bool:
    try:
        return bool(pred(r))
    except Exception:
        return False


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "mean_usd": 0.0, "sum_usd": 0.0, "mean_R": None, "winrate": 0.0}
    usd = [_usd(r) for r in rows]
    rs = [_r_mult(r) for r in rows if _r_mult(r) is not None]
    wins = sum(1 for u in usd if u > 0)
    return {
        "n": len(rows),
        "mean_usd": round(mean(usd), 3),
        "sum_usd": round(sum(usd), 2),
        "mean_R": round(mean(rs), 3) if rs else None,
        "winrate": round(100.0 * wins / len(rows), 1),
    }


def conditional_expectancy(rows: list[dict], predicate, *, min_n: int = 8, min_oos_n: int = 4) -> dict:
    """Expectancy WITH vs WITHOUT the condition, plus an out-of-sample
    (time-split) check that the sign of the gap holds on unseen (later) trades.

    Metric: mean-R when >=80% of rows carry r_multiple, else mean-$. R is
    scale-invariant — deposits/withdrawals change $-at-risk per trade, so a
    $-gap across a deposit boundary would bias findings toward the bigger-
    account rows (2026-07-21 deposit roughly doubled equity)."""
    use_r = rows and sum(1 for r in rows if _r_mult(r) is not None) >= 0.8 * len(rows)
    def mean_metric(summary, sub_rows):
        if use_r:
            rs = [_r_mult(r) for r in sub_rows if _r_mult(r) is not None]
            return (sum(rs) / len(rs)) if rs else 0.0
        return summary["mean_usd"]
    w_rows = [r for r in rows if _safe(predicate, r)]
    wo_rows = [r for r in rows if not _safe(predicate, r)]
    w = summarize(w_rows)
    wo = summarize(wo_rows)
    gap_usd = round(w["mean_usd"] - wo["mean_usd"], 3)
    gap = round(mean_metric(w, w_rows) - mean_metric(wo, wo_rows), 3)

    srt = sorted(rows, key=_ts)
    half = len(srt) // 2
    def half_gap(hh):
        wn = [r for r in hh if _safe(predicate, r)]
        won = [r for r in hh if not _safe(predicate, r)]
        if len(wn) < min_oos_n or len(won) < min_oos_n:
            return None
        return mean_metric(summarize(wn), wn) - mean_metric(summarize(won), won)
    g_early = half_gap(srt[:half])
    g_late = half_gap(srt[half:])
    # Confirmed only if BOTH halves strictly agree in direction with the overall
    # gap (a neutral/zero half does NOT confirm).
    if g_early is None or g_late is None or gap == 0:
        oos_consistent = False
    elif gap > 0:
        oos_consistent = g_early > 0 and g_late > 0
    else:
        oos_consistent = g_early < 0 and g_late < 0
    return {
        "with": w, "without": wo, "gap_usd": gap_usd,
        "gap": gap, "metric": "R" if use_r else "usd",
        "oos": {
            "early_gap": round(g_early, 3) if g_early is not None else None,
            "late_gap": round(g_late, 3) if g_late is not None else None,
            "consistent": oos_consistent,
        },
        "enough": w["n"] >= min_n and wo["n"] >= min_n,
    }


def rank_conditions(rows: list[dict], conditions: dict, *, min_n: int = 8) -> list[dict]:
    """Rank candidate conditions. Verdict AVOID/FAVOR only when the gap is
    out-of-sample consistent AND both groups clear min_n; else weak/insufficient.
    Actionable proposals sort first, by |gap| * sqrt(sample)."""
    out = []
    for name, pred in conditions.items():
        ce = conditional_expectancy(rows, pred, min_n=min_n)
        if not ce["enough"]:
            verdict = "insufficient"
        elif ce["gap"] < 0 and ce["oos"]["consistent"]:
            verdict = "AVOID"
        elif ce["gap"] > 0 and ce["oos"]["consistent"]:
            verdict = "FAVOR"
        else:
            verdict = "weak"
        out.append({
            "condition": name, "verdict": verdict, "gap_usd": ce["gap_usd"],
            "gap": ce["gap"], "metric": ce["metric"],
            "with": ce["with"], "without": ce["without"], "oos": ce["oos"],
        })

    def keyf(p):
        actionable = p["verdict"] in ("AVOID", "FAVOR")
        return (actionable, abs(p["gap"]) * math.sqrt(p["with"]["n"] + 1))
    return sorted(out, key=keyf, reverse=True)


def default_conditions() -> dict:
    """Candidate conditions over a feature row. Missing features -> predicate False
    (that condition simply shows an empty/insufficient group). Grow this list as
    the feature store captures more context (e.g. mexc_only, crowded_funding)."""
    return {
        "kind=WILDCARD": lambda r: r.get("kind") == "WILDCARD" or bool(r.get("is_wildcard")),
        "kind=SQUEEZE": lambda r: r.get("kind") == "SQUEEZE",
        "kind=CONVEX(wc+sq+tr)": lambda r: r.get("kind") in ("WILDCARD", "SQUEEZE", "TREND") or bool(r.get("is_wildcard")),
        "kind=PMT": lambda r: r.get("kind") == "PMT",
        "side=SHORT": lambda r: r.get("side") == "SHORT",
        "side=LONG": lambda r: r.get("side") == "LONG",
        "roc>=12pct": lambda r: (r.get("entry_3h_roc_pct") or 0) >= 12,
        "roc<12pct": lambda r: 0 < (r.get("entry_3h_roc_pct") or 0) < 12,
        "leverage>=7": lambda r: (r.get("leverage") or 0) >= 7,
        "leverage<=4": lambda r: 0 < (r.get("leverage") or 0) <= 4,
        "hold<=30min": lambda r: (r.get("hold_min") or 1e9) <= 30,
        "hold>=120min": lambda r: (r.get("hold_min") or 0) >= 120,
        "fee_heavy>=30pct": lambda r: (r.get("fee_share_of_gross") or 0) >= 0.30,
        # Lateness zones (247-fire study, 60d): deep pullback was the gold bucket,
        # the stalled-reclaim middle was the suspect (n=27 — monitored, NOT a gate).
        "deep_pullback(lat 0.50-0.70)": lambda r: r.get("entry_lateness") is not None and 0.50 <= r["entry_lateness"] < 0.70,
        "stalled_reclaim(lat 0.85-0.99)": lambda r: r.get("entry_lateness") is not None and 0.85 <= r["entry_lateness"] < 0.99,
        "at_extreme(lat>=0.99)": lambda r: r.get("entry_lateness") is not None and r["entry_lateness"] >= 0.99,
        # Does the regime size-scaler earn its keep? It cut a live +3R winner to
        # ~32% of intended size; until 2026-07-22 its multiplier was applied but
        # never recorded, so this condition could never fire. AVOID here means
        # scaler-trimmed trades are WORSE (it works); FAVOR means it is costing
        # size on good trades.
        "regime_trimmed(mult<1)": lambda r: (r.get("regime_size_mult") or 1.0) < 0.999,
        "regime_trimmed_hard(<0.5)": lambda r: (r.get("regime_size_mult") or 1.0) < 0.5,
        "chop_regime": lambda r: (r.get("regime_size_mult") or 1.0) < 1.0,
        "exit=stop": lambda r: "STOP" in str(r.get("exit_reason") or "").upper(),
        "late_entry>=0.8": lambda r: (r.get("entry_lateness") if r.get("entry_lateness") is not None else -1) >= 0.8,
        "early_entry<=0.5": lambda r: 0 <= (r.get("entry_lateness") if r.get("entry_lateness") is not None else -1) <= 0.5,
    }
