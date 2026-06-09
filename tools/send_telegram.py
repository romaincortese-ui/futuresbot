#!/usr/bin/env python3
"""Send a Telegram message via the bot's existing TelegramClient.

Used by the 'Futures daily assessment' routine to push its report. Two modes:

  python tools/send_telegram.py --json '<payload>'   # pretty templated report
  python tools/send_telegram.py "raw text"           # send text as-is

Pretty-report JSON fields (all optional — absent lines are skipped, so the
message stays concise):
  date, equity, equity_change_pct, trades_24h, win_rate, pnl_24h,
  review (list[str] or str), bt_24h, bt_baseline, bt_7d,
  change (str), deploy ("deployed"|"none"|"rolled_back"), deploy_reason

Reads creds from FUTURES_TELEGRAM_TOKEN/TELEGRAM_TOKEN and
FUTURES_TELEGRAM_CHAT_ID/TELEGRAM_CHAT_ID via FuturesConfig.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from futuresbot.config import FuturesConfig
from futuresbot.telegram import TelegramClient


def _money(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _signed(v, decimals: int = 2) -> str:
    try:
        return f"{float(v):+,.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def _pnl_emoji(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "▫️"
    return "🟢" if f > 0 else ("🔴" if f < 0 else "⚪")


def render(p: dict) -> str:
    lines: list[str] = []
    date = p.get("date", "")
    lines.append(f"📊 <b>Futures Daily</b>{' — ' + date if date else ''}")

    # Account + 24h headline
    head = []
    if p.get("equity") is not None:
        eq = f"💰 {_money(p['equity'])}"
        if p.get("equity_change_pct") is not None:
            eq += f" {_pnl_emoji(p['equity_change_pct'])}{_signed(p['equity_change_pct'],1)}%"
        head.append(eq)
    if p.get("trades_24h") is not None:
        t = f"🎯 {p['trades_24h']} trades"
        if p.get("win_rate") is not None:
            t += f" · {round(float(p['win_rate']))}% win"
        if p.get("pnl_24h") is not None:
            t += f" · {_pnl_emoji(p['pnl_24h'])}{_signed(p['pnl_24h'])}"
        head.append(t)
    if head:
        lines.append("\n".join(head))

    # Trade review
    review = p.get("review")
    if review:
        items = review if isinstance(review, list) else [review]
        lines.append("\n🔍 <b>Trades</b>\n" + "\n".join(f"• {str(i)}" for i in items))

    # Backtest line (concise)
    if any(p.get(k) is not None for k in ("bt_24h", "bt_baseline", "bt_7d")):
        bt = []
        if p.get("bt_24h") is not None:
            bt.append(f"24h {_pnl_emoji(p['bt_24h'])}{_signed(p['bt_24h'],0)}")
        if p.get("bt_baseline") is not None:
            bt.append(f"base {_signed(p['bt_baseline'],0)}")
        if p.get("bt_7d") is not None:
            bt.append(f"7d {_signed(p['bt_7d'],0)}")
        lines.append("\n🧪 <b>Backtest</b>: " + " · ".join(bt))

    # Change
    change = p.get("change")
    if change:
        lines.append(f"🔧 <b>Change</b>: {change}")

    # Deploy status
    dep = (p.get("deploy") or "").lower()
    if dep:
        emoji = {"deployed": "🚀", "none": "⏸️", "rolled_back": "↩️"}.get(dep, "ℹ️")
        label = {"deployed": "Deployed", "none": "No change", "rolled_back": "Rolled back"}.get(dep, dep)
        line = f"{emoji} <b>{label}</b>"
        if p.get("deploy_reason"):
            line += f" — {p['deploy_reason']}"
        lines.append(line)

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", help="Raw message text (if not using --json)")
    ap.add_argument("--json", dest="payload", help="JSON payload for a pretty templated report")
    ap.add_argument("--json-file", dest="payload_file", help="Path to a JSON payload file")
    args = ap.parse_args()

    if args.payload or args.payload_file:
        raw = args.payload or open(args.payload_file, encoding="utf-8").read()
        message = render(json.loads(raw))
    elif args.text:
        message = args.text
    else:
        message = sys.stdin.read().strip()
    if not message:
        print("send_telegram: empty message", file=sys.stderr)
        return 2

    cfg = FuturesConfig.from_env()
    client = TelegramClient(cfg.telegram_token, cfg.telegram_chat_id)
    if not client.configured:
        print("send_telegram: TELEGRAM token/chat_id not configured", file=sys.stderr)
        return 3
    ok = client.send_message(message)
    print("send_telegram: sent" if ok else "send_telegram: FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
