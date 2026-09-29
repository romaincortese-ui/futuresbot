"""Restricted entry area ("envelope") - owner request 2026-09-29.

Take a WILDCARD or TREND candidate only when the bot's OWN values at the decision sit
inside the box drawn around the winners of the 84-trade study (wc/ENVELOPE; the frozen
spec is entry_envelope.json next to this file). One box per cell:

  TREND LONG     new_high_margin_pct, ETH 12h, ETH 24h, majors calm score
  WILDCARD LONG  |3h ROC|, RSI14, ATR14/price, SOL 72h
  WILDCARD SHORT RSI14, ticker 24h range

Bounds are inclusive. A box variable that is missing at the decision fails the box.
A cell with no box (e.g. TREND SHORT) fails. The calm score counts only when all nine
BTC/ETH/SOL returns are present, because the bot computes it from whichever returned.

IN-SAMPLE ONLY. On held-out data stop-losses land inside the area about as often as
winners do (wc/ENVELOPE/measure): it cuts volume to roughly a third; it has not been
shown to filter stop-losses. It ships because the owner chose to restrict entries.

FUTURES_ENTRY_ENVELOPE_ENABLED (default 0):
  0  today's decisions; the verdict is only stamped on shadow rows and fills.
  1  a candidate outside its box is refused ("envelope") after every other gate and
     before any order, and shadow-logged like every other refusal.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

SPEC_PATH = Path(__file__).with_name("entry_envelope.json")
SLEEVES = ("TREND", "WILDCARD")
# Every variable the frozen spec uses, all computable from the bot's own values.
VARS = ("new_high_margin_pct", "bot_eth_12h", "bot_eth_24h", "bot_calm_score",
        "roc3h_abs", "rsi14", "atr_pct", "bot_sol_72h", "range_24h")
MAJORS_KEYS = tuple("%s_%dh" % (t, h) for t in ("btc", "eth", "sol") for h in (12, 24, 72))
STAMP_KEYS = (("envelope_pass", "envelope_cell", "envelope_reason", "envelope_enabled",
               "envelope_majors_age_s") + tuple("envelope_" + v for v in VARS))

_SPEC: dict[str, Any] | None = None


def enabled() -> bool:
    """FUTURES_ENTRY_ENVELOPE_ENABLED; blank reads as unset (off)."""
    raw = os.environ.get("FUTURES_ENTRY_ENVELOPE_ENABLED", "").strip() or "0"
    return raw.lower() in {"1", "true", "yes", "y", "on"}


def load_spec() -> dict[str, Any]:
    """The frozen spec, read once. Unreadable -> {}: every cell then has no box,
    so an enabled envelope refuses everything rather than admitting everything."""
    global _SPEC
    if _SPEC is None:
        try:
            with open(SPEC_PATH, encoding="utf-8") as fh:
                spec = json.load(fh)
            _SPEC = spec if isinstance(spec, dict) else {}
        except Exception:
            _SPEC = {}
    return _SPEC


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def candidate_values(sig: Any, kind: str, *, range_24h: Any = None,
                     majors: dict[str, Any] | None = None) -> dict[str, float | None]:
    """The box variables for one candidate, as the bot computes them at the decision.

    new_high_margin_pct  TREND: (gate close / prior 24h closing high - 1) x 100, as
                         stamped in trend_extreme_margin_pct (unrounded here)
    roc3h_abs, rsi14     WILDCARD: the detector's own |roc_pct| and rsi
    atr_pct              the detector's atr_pct
    range_24h            WILDCARD: ticker (high24 - low24) / low24 at the scan
    bot_*                _majors_state(): latest 15m close vs 48/96/288 bars earlier
    """
    kind = str(kind).upper()
    side = str(getattr(sig, "side", "")).upper()
    maj = majors or {}
    complete = all(_num(maj.get(k)) is not None for k in MAJORS_KEYS)
    vals: dict[str, float | None] = {v: None for v in VARS}
    vals["bot_eth_12h"] = _num(maj.get("eth_12h"))
    vals["bot_eth_24h"] = _num(maj.get("eth_24h"))
    vals["bot_sol_72h"] = _num(maj.get("sol_72h"))
    vals["bot_calm_score"] = _num(maj.get("calm_score")) if complete else None
    vals["atr_pct"] = _num(getattr(sig, "atr_pct", None))
    if kind == "TREND":
        prior = _num(getattr(sig, "prior_close_extreme", None))
        gate = _num(getattr(sig, "gate_close", None) or getattr(sig, "entry_price", None))
        if prior and gate and prior > 0 and gate > 0:
            vals["new_high_margin_pct"] = ((gate / prior - 1.0) if side == "LONG"
                                           else (prior / gate - 1.0)) * 100.0
    elif kind == "WILDCARD":
        roc = _num(getattr(sig, "roc_pct", None))
        vals["roc3h_abs"] = abs(roc) if roc is not None else None
        vals["rsi14"] = _num(getattr(sig, "rsi", None))
        rng = _num(range_24h)
        vals["range_24h"] = rng if rng is not None and rng > 0 else None   # 0.0 = unreadable
    return vals


def evaluate(cell: str, values: dict[str, Any],
             spec: dict[str, Any] | None = None) -> tuple[bool, str]:
    """(inside, reason). reason is "inside", "no_box", or every failure joined by ';'
    ("missing:<var>", "<var><lo", "<var>>hi")."""
    spec = load_spec() if spec is None else spec
    boxes = spec.get(cell) if isinstance(spec, dict) else None
    if not isinstance(boxes, list) or not boxes:
        return False, "no_box"
    fails: list[str] = []
    for box in boxes:
        var = str(box.get("var"))
        v = _num(values.get(var))
        if v is None:
            fails.append("missing:" + var)
            continue
        lo, hi = _num(box.get("lo")), _num(box.get("hi"))
        if lo is not None and v < lo:
            fails.append("%s<%g" % (var, lo))
        if hi is not None and v > hi:
            fails.append("%s>%g" % (var, hi))
    return (not fails), (";".join(fails) if fails else "inside")


def verdict(sig: Any, kind: str, *, range_24h: Any = None, majors: dict[str, Any] | None = None,
            majors_age_s: float | None = None,
            spec: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The stamp for one candidate: pass (1.0/0.0), cell, reason, whether the switch was
    on, and the cell's box values. None for sleeves the area does not cover."""
    kind = str(kind).upper()
    if kind not in SLEEVES:
        return None
    spec = load_spec() if spec is None else spec
    cell = "%s %s" % (kind, str(getattr(sig, "side", "")).upper())
    vals = candidate_values(sig, kind, range_24h=range_24h, majors=majors)
    ok, reason = evaluate(cell, vals, spec)
    out: dict[str, Any] = {"envelope_pass": 1.0 if ok else 0.0, "envelope_cell": cell,
                           "envelope_reason": reason,
                           "envelope_enabled": 1.0 if enabled() else 0.0}
    for box in (spec.get(cell) if isinstance(spec.get(cell), list) else []):
        var = str(box.get("var"))
        out["envelope_" + var] = vals.get(var)
    if majors_age_s is not None:
        out["envelope_majors_age_s"] = round(float(majors_age_s), 1)
    return out
