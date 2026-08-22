"""What a trial would have paid on a bigger opening balance. Read-only.

    railway ssh --service Futures-bot "python3 tools/simulation_report.py"

The CLI twin of the /simulation Telegram command, and the way to price a trial
that has already closed. Reads the feature store directly and imports only
futuresbot.simulation (stdlib-only), so it runs inside the container where pandas
is unavailable.

    SR_START  unix ts to scope from (default: FUTURES_TRIAL_START_TS)
    SR_LABEL  label for the header
    SR_STORE  store path (default /data/futures_feature_store.jsonl)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Load simulation.py BY PATH rather than importing the package: futuresbot/
# __init__.py pulls in config -> dotenv, which the container's system python does
# not have. simulation.py is deliberately stdlib-only so this works anywhere.
import importlib.util

_sim_path = Path(__file__).resolve().parents[1] / "futuresbot" / "simulation.py"
_spec = importlib.util.spec_from_file_location("_fb_simulation", _sim_path)
_sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sim)
SIM_BALANCES = _sim.SIM_BALANCES
capacity_notional = _sim.capacity_notional
risk_fraction = _sim.risk_fraction
realised_pnl = _sim.realised_pnl
simulate = _sim.simulate
trial_opening_equity = _sim.trial_opening_equity

CONVEX = {"WILDCARD", "SQUEEZE", "TREND"}


def main() -> int:
    store = os.environ.get("SR_STORE") or "/data/futures_feature_store.jsonl"
    start = float(os.environ.get("SR_START") or os.environ.get("FUTURES_TRIAL_START_TS") or 0)
    end = float(os.environ.get("SR_END") or 9e18)
    label = os.environ.get("SR_LABEL") or "current"

    rows = []
    try:
        with open(store, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                ts = float(r.get("ts") or 0)
                if start <= ts < end and str(r.get("kind") or "").upper() in CONVEX:
                    rows.append(r)
    except OSError as exc:
        print(f"cannot read {store}: {exc}")
        return 1
    rows.sort(key=lambda r: float(r.get("ts") or 0))

    print(f"=== SIMULATION — {label} ===")
    if not rows:
        print("no convex trades in scope")
        return 0
    net_r = sum(float(r.get("r_multiple") or 0) for r in rows)
    real = realised_pnl(rows)
    eq_start = trial_opening_equity(rows)
    print(f"{len(rows)} closed convex trades | netR {net_r:+.3f} | realised ${real:+.2f}")
    print(f"mean risk/trade {sum(risk_fraction(r) for r in rows)/len(rows)*100:.2f}% of available")
    if eq_start > 0:
        print(f"account ${eq_start:.2f} -> ${eq_start + real:.2f} "
              f"({real/eq_start*100:+.2f}%) over the trial")
        chk = simulate(rows, eq_start, actual_opening=eq_start)
        err = chk["realised"] - real
        tag = "OK" if abs(err) < 0.01 else "** MODEL ERROR **"
        print(f"self-check at k=1: ${chk['realised']:+.2f} vs ${real:+.2f} actual  {tag}")

    print()
    print(f"{'opening':>10} {'equity':>12} {'P&L':>11} {'return':>9}")
    for b in SIM_BALANCES:
        sm = simulate(rows, b, actual_opening=eq_start)
        print(f"{b:>10,.0f} {sm['equity']:>12,.2f} {sm['realised']:>+11,.2f} "
              f"{sm['return_pct']:>+8.2f}%")

    print()
    print(f"{'opening':>10} {'median notional':>16} {'max notional':>14}")
    for b in SIM_BALANCES:
        c = capacity_notional(rows, b, actual_opening=eq_start)
        print(f"{b:>10,.0f} {c['median']:>16,.0f} {c['max']:>14,.0f}")
    print("\nMeasured median top-10 book depth in the wildcard band is ~$20k;")
    print("the thin tail holds a few hundred. Where max notional approaches that,")
    print("the simulated return is optimistic — it assumes fills stay free.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
