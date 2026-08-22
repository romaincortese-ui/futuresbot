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
simulate = _sim.simulate

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
    real = sum(float(r.get("pnl_usdt") or 0) for r in rows)
    eq0 = float(rows[0].get("equity_at_entry") or rows[0].get("equity_at_open_usdt") or 0)
    eq1 = float(rows[-1].get("equity_at_close_usdt") or 0)
    print(f"{len(rows)} closed convex trades | netR {net_r:+.3f} | realised ${real:+.2f}")
    if eq0 and eq1:
        print(f"live account ${eq0:.2f} -> ${eq1:.2f} ({(eq1/eq0-1)*100:+.2f}%)")
    print(f"mean risk/trade {sum(risk_fraction(r) for r in rows)/len(rows)*100:.2f}% of equity")

    print()
    print(f"{'opening':>10} {'equity':>12} {'P&L':>11} {'return':>9}")
    for b in SIM_BALANCES:
        s = simulate(rows, b)
        print(f"{b:>10,.0f} {s['equity']:>12,.2f} {s['realised']:>+11,.2f} "
              f"{s['return_pct']:>+8.2f}%")

    print()
    print(f"{'opening':>10} {'median notional':>16} {'max notional':>14}")
    for b in SIM_BALANCES:
        c = capacity_notional(rows, b)
        print(f"{b:>10,.0f} {c['median']:>16,.0f} {c['max']:>14,.0f}")
    print("\nMeasured median top-10 book depth in the wildcard band is ~$20k;")
    print("the thin tail holds a few hundred. Where max notional approaches that,")
    print("the simulated return is optimistic — it assumes fills stay free.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
