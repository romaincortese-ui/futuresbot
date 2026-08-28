"""The LIVE dollar model. Import this instead of writing `net * risk * equity`.

THE GAP THIS CLOSES (owner, 2026-08-28). Every gate and tilt study in this repo
priced trades at a FLAT 1R: `dollars = net_R * risk_pct * equity`. The live bot
has never sized that way. runtime._entry_margin sizes by the risk dial and then
multiplies by regime_size_multiplier(symbol efficiency) - full size on a clean
trend, floored at 0.25 in chop - and by the cold-streak throttle. Realised risk
per trade on the live book runs 1.0-1.5% against a 2.41% nominal, so a flat
model overstates every dollar figure AND, worse, misprices any comparison whose
arms hold different mixes of trades.

WHY IT MATTERS MOST FOR GATES. A gate changes WHICH trades are taken, so the
two arms end up with different scaler distributions. Measured on the BTC72
gate: mean scaler 0.834 when the gate is open vs 0.700 when shut. A flat model
silently assumes those are equal, which is exactly the assumption the owner's
"but the winners are sized bigger" argument attacks - correctly.

WHY IT MATTERS LESS FOR EXIT STUDIES. An exit change keeps the same entries, so
each trade carries the SAME multiplier in both arms. The comparison is then a
scaler-weighted version of the flat one; it only flips if the exit's benefit
correlates with the scaler. Worth checking, not assumed.

WHY IT DOES NOT MATTER AT ALL IN R. netR is scale-invariant. Any conclusion
stated purely in R - "no entry feature predicts the tail", "streaks carry no
information" - is untouched by this.

THREE MODELS, because the difference between them is itself informative:
  flat      net_R * risk_pct * equity0                  (what prior studies did)
  scaler    net_R * risk_pct * equity0 * mult           (what the bot does now)
  compound  net_R * risk_pct * equity_t  * mult         (what the account does)
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any


def live_multiplier(efficiency: float, *, lo: float = 0.20, hi: float = 0.45,
                    floor_mult: float = 0.25) -> float:
    """The shipped regime scaler. Thin re-export so studies cannot drift from
    the runtime's own shape by copying the numbers wrong."""
    from futuresbot.risk_controls import regime_size_multiplier
    return regime_size_multiplier(efficiency, lo=lo, hi=hi, floor_mult=floor_mult)


def price(fills: Sequence[dict[str, Any]], *, risk_pct: float, equity0: float,
          model: str = "scaler", mult_key: str = "mult",
          net_key: str = "net", tilt: Callable[[dict], float] | None = None,
          normalise: bool = False) -> dict[str, float]:
    """Price a list of fills in dollars under one of the three models.

    Each fill needs `net` (net R) and, for the scaler models, `mult` (that
    trade's regime multiplier at entry). `tilt` optionally applies a further
    per-trade size multiplier - a size-tilt policy under test.

    `normalise=True` rescales the tilt so the AVERAGE deployed size matches the
    untilted arm. Without it a tilt that simply sizes everything up scores
    better purely by leverage, which is how a +$159 calm-tilt headline turned
    out to be +$45 of selection and $114 of leverage.
    """
    k = 1.0
    if tilt is not None and normalise and fills:
        avg = sum(tilt(f) for f in fills) / len(fills)
        k = (1.0 / avg) if avg > 0 else 1.0
    eq = equity0
    tot = 0.0
    peak = equity0
    mdd = 0.0
    wins = 0
    for f in fills:
        m = 1.0 if model == "flat" else float(f.get(mult_key, 1.0) or 1.0)
        if tilt is not None:
            m *= k * tilt(f)
        base = equity0 if model != "compound" else eq
        d = float(f[net_key]) * risk_pct * base * m
        tot += d
        if model == "compound":
            eq += d
            peak = max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak if peak > 0 else 0.0)
        if float(f[net_key]) > 0:
            wins += 1
    return {"net": tot, "n": len(fills), "equity_end": eq,
            "max_dd": mdd, "win_pct": 100.0 * wins / max(1, len(fills))}


def compare(arms: dict[str, Sequence[dict[str, Any]]], *, risk_pct: float,
            equity0: float) -> str:
    """Render every arm under all three models, so the reader can see whether a
    verdict depends on the sizing assumption. If flat and scaler disagree, the
    flat number was never the answer."""
    out = ["%-22s %-16s %10s %7s %6s %9s" %
           ("model", "arm", "net $", "fills", "win%", "max DD")]
    for model, lbl in (("flat", "flat 1R (old studies)"),
                       ("scaler", "+ regime scaler (live)"),
                       ("compound", "+ compounding")):
        for name, fills in arms.items():
            r = price(fills, risk_pct=risk_pct, equity0=equity0, model=model)
            out.append("%-22s %-16s %+10.2f %7d %5.0f%% %8s"
                       % (lbl if name == list(arms)[0] else "", name,
                          r["net"], r["n"], r["win_pct"],
                          ("%.1f%%" % (100 * r["max_dd"])) if model == "compound" else "-"))
        out.append("")
    return "\n".join(out)
