"""Every regime hypothesis this project has entertained, through the placebo control.

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_regime_audit.py

All of these were already refuted on effect size or significance. Re-running them
through tools/pit_placebo.py serves two purposes, and the second is the more
important one:

  1. It puts every regime verdict on the same, higher, standard rather than
     leaving the older ones resting on weaker reasoning.

  2. IT VALIDATES THE CONTROL. These are known-null hypotheses. If the placebo
     reports SURVIVES for one of them, the control is too lenient and its
     verdict on anything else is worthless. A control is only trustworthy once
     it has been pointed at cases whose answer is already known.

Applied to the REAL live trades - each row is an actual fill with an actual
outcome, and the gate only decides which to keep. No replay, so none of the
fidelity problems apply.

READ THE VERDICT COLUMN, NOT THE DOLLARS. A gate can add dollars and still be
reading nothing but the calendar; that is exactly what happened to the majors-up
gate that passed a permutation test at p<1% on 2026-09-02.

READ-ONLY.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import trend_efficiency  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_placebo import placebo_test  # noqa: E402

STORE = "/data/futures_feature_store.jsonl"
MAJORS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")


def main() -> int:
    rows = []
    for line in open(STORE, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("pnl_usdt") is None or not r.get("risk_usdt"):
            continue
        r["_t"] = float(r["ts"]) - float(r.get("hold_hours") or 0) * 3600.0
        rows.append(r)
    rows.sort(key=lambda r: r["_t"])
    base = sum(float(r["pnl_usdt"]) for r in rows)
    print("real live closes: %d   ungated net $%+.2f" % (len(rows), base))

    cl = MexcFuturesClient(FuturesConfig.from_env())
    now = int(time.time())
    fr, rep = fetch_frames(cl, MAJORS, days=60, workers=3, min_bars=500,
                           now_ts=now, strict=False)
    print(rep)
    SER = {s: ([float(x.timestamp()) for x in d.index], [float(x) for x in d["close"]])
           for s, d in fr.items()}

    def idx(sym, t):
        ts_, _ = SER[sym]
        for k in range(len(ts_) - 1, -1, -1):
            if ts_[k] <= t:
                return k
        return None

    def ret(sym, t, hours):
        i = idx(sym, t)
        _, c = SER[sym]
        n = int(hours * 4)
        if i is None or i < n or not c[i - n]:
            return None
        return (c[i] / c[i - n] - 1.0) * 100.0

    def calm(t):
        """The bot's own majors-agitation measure (runtime.py:1095)."""
        best = None
        for sym in MAJORS:
            for hours, thr in ((12, 2.0), (24, 5.0), (72, 10.0)):
                v = ret(sym, t, hours)
                if v is None:
                    continue
                best = abs(v) / thr if best is None else max(best, abs(v) / thr)
        return best

    def diverge(t):
        b, e, s = (ret("BTC_USDT", t, 24), ret("ETH_USDT", t, 24), ret("SOL_USDT", t, 24))
        if None in (b, e, s):
            return None
        return b - (e + s) / 2.0

    def eff(t):
        i = idx("BTC_USDT", t)
        _, c = SER["BTC_USDT"]
        if i is None or i < 100:
            return None
        return trend_efficiency(c[:i + 1], 96)

    effs = [x for x in (eff(r["_t"]) for r in rows) if x is not None]
    med_eff = statistics.median(effs) if effs else 0.0
    divs = [x for x in (diverge(r["_t"]) for r in rows) if x is not None]
    hi_div = sorted(divs)[int(0.8 * len(divs))] if divs else 0.0
    lo_div = sorted(divs)[int(0.2 * len(divs))] if divs else 0.0

    def anyup(t, hours, thr):
        v = [ret(s, t, hours) for s in MAJORS]
        v = [x for x in v if x is not None]
        return bool(v) and max(v) >= thr

    def duty_cycle(open_h, cool_h, hours=72, thr=1.0):
        """The owner's design (2026-09-02): the gate opens only when the
        condition holds, stays open for a FIXED window, then forces a cooldown
        regardless of the condition, then re-checks.

        The forced cooldown is the interesting part - it caps how much of any
        single favourable stretch the bot can exploit, which is a different
        mechanism from a condition-following gate. Built once and cached,
        because the schedule is global rather than per-trade.
        """
        t0 = min(r["_t"] for r in rows) - 40 * 86400
        t1 = max(r["_t"] for r in rows) + 86400
        spans, t = [], t0
        step = 6 * 3600.0
        while t < t1:
            if anyup(t, hours, thr):
                spans.append((t, t + open_h * 3600.0))
                t += (open_h + cool_h) * 3600.0      # open, then forced cooldown
            else:
                t += step                             # keep checking
        spans.sort()
        def gate(q):
            for a, b in spans:
                if a <= q < b:
                    return True
                if a > q:
                    break
            return False
        return gate

    HYPOTHESES = (
        ("1. majors GATE: calm_score <= 1.0",
         lambda t: (calm(t) or 9.0) <= 1.0),
        ("2. majors TILT: calm_score >= 1.0",
         lambda t: (calm(t) or 0.0) >= 1.0),
        ("3. divergence: alts DUMPING (top quintile)",
         lambda t: (diverge(t) if diverge(t) is not None else -9) >= hi_div),
        ("4. divergence: alts LEADING (bottom quintile)",
         lambda t: (diverge(t) if diverge(t) is not None else 9) <= lo_div),
        ("5. direction: BTC 24h >= +1%",
         lambda t: (ret("BTC_USDT", t, 24) or -9) >= 1.0),
        ("6. direction: BTC 24h >= 0%",
         lambda t: (ret("BTC_USDT", t, 24) or -9) >= 0.0),
        ("7. choppiness: BTC eff >= median (CLEAN)",
         lambda t: (eff(t) or 0.0) >= med_eff),
        ("8. choppiness: BTC eff < median (CHOPPY)",
         lambda t: (eff(t) or 9.0) < med_eff),
        ("9. stateful gate: ANY of 3, 72h >= 1%",
         lambda t: anyup(t, 72, 1.0)),
        ("10. slow majors: ANY of 3, 48h >= 1%",
         lambda t: anyup(t, 48, 1.0)),
        ("11. OWNER: 72h>=1%, open 12h, cooldown 12h", duty_cycle(12, 12)),
        ("12. duty cycle: open 6h, cooldown 12h", duty_cycle(6, 12)),
        ("13. duty cycle: open 24h, cooldown 12h", duty_cycle(24, 12)),
        ("14. duty cycle: open 12h, cooldown 24h", duty_cycle(12, 24)),
        ("15. duty cycle: open 12h, cooldown 6h", duty_cycle(12, 6)),
    )

    print()
    print("=" * 104)
    print("EVERY REGIME HYPOTHESIS, THROUGH THE PLACEBO CONTROL")
    print("=" * 104)
    print("%-42s %5s %10s %10s %7s  %s"
          % ("hypothesis", "kept", "net $", "vs ungated", "beaten", "verdict"))
    print("-" * 104)
    survivors = []
    for name, gate in HYPOTHESES:
        res = placebo_test(rows, gate, time_of=lambda x: x["_t"],
                           value_of=lambda x: float(x["pnl_usdt"]), min_n=5)
        v = res.verdict.split(" - ")[0]
        print("%-42s %5d %+10.2f %+10.2f %3d/%-3d  %s"
              % (name, res.real_n, res.real, res.real - base,
                 len(res.beaten_by), len(res.usable), v))
        if v == "SURVIVES":
            survivors.append((name, res))
    print()
    print("=" * 104)
    print("VALIDATION: these are all KNOWN-NULL. A SURVIVES here would mean the")
    print("control is too lenient and its verdict on anything else is worthless.")
    print("=" * 104)
    if not survivors:
        print("  0 survivors of %d. The control is behaving as intended." % len(HYPOTHESES))
    else:
        print("  %d SURVIVED - inspect these before trusting the control:" % len(survivors))
        for name, res in survivors:
            print()
            print("  %s" % name)
            print("    real %+.2f (n=%d) vs placebos %s"
                  % (res.real, res.real_n,
                     ", ".join("%+.0f" % v for _, v, n in res.usable)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
