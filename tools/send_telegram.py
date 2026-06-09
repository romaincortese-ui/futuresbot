#!/usr/bin/env python3
"""Send a Telegram message via the bot's existing TelegramClient.

Used by the 'Futures daily assessment' routine to push its report. Two modes:

  python tools/send_telegram.py --json '<payload>'   # pretty templated report
  python tools/send_telegram.py "raw text"           # send text as-is

Pretty-report JSON fields (all optional — absent lines are skipped):
  date, equity, equity_change_pct, trades_24h, win_rate, pnl_24h,
  review   : list of CLOSED-trade objects (preferred) or strings. A trade
             object: {side, symbol, reason, entry, exit, pnl_usd, pnl_pct,
             acct_pct} — rendered as a clear multi-line block.
  scan_context : str shown when there are 0 closed trades (why nothing opened).
  notes    : list[str] of flags/observations (e.g. concentration warnings).
  bt_24h, bt_baseline, bt_7d, change,
  deploy ("deployed"|"none"|"rolled_back"), deploy_reason

Emoji are added inside Python and sent as UTF-8, so callers pass ASCII payloads
(avoids Windows console encoding issues). Creds from
FUTURES_TELEGRAM_TOKEN/TELEGRAM_TOKEN + FUTURES_TELEGRAM_CHAT_ID/TELEGRAM_CHAT_ID.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from futuresbot.config import FuturesConfig
from futuresbot.telegram import TelegramClient

DIV = "━━━━━━━━━━━━━━━"


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _money(v) -> str:
    f = _f(v)
    return f"${f:,.2f}" if f is not None else str(v)


def _signed(v, d: int = 2) -> str:
    f = _f(v)
    return f"{f:+,.{d}f}" if f is not None else str(v)


def _price(v) -> str:
    f = _f(v)
    if f is None:
        return str(v)
    if f >= 100:
        return f"${f:,.2f}"
    if f >= 1:
        return f"${f:,.4f}"
    return f"${f:,.6f}".rstrip("0").rstrip(".")


def _pnl_emoji(v) -> str:
    f = _f(v)
    if f is None:
        return "▫️"
    return "🟢" if f > 0 else ("🔴" if f < 0 else "⚪")


def _side_label(side) -> str:
    s = str(side or "").upper()
    if s in ("1", "LONG", "BUY"):
        return "LONG"
    if s in ("2", "SHORT", "SELL"):
        return "SHORT"
    return s or "?"


def _render_trade(t: dict) -> str:
    side = _side_label(t.get("side"))
    sym = t.get("symbol", "?")
    head = f"{_pnl_emoji(t.get('pnl_usd'))} <b>{side} {sym}</b>"
    if t.get("reason"):
        head += f" — {t['reason']}"
    lines = [head]
    if t.get("entry") is not None or t.get("exit") is not None:
        lines.append(f"   Entry {_price(t.get('entry'))} | Exit {_price(t.get('exit'))}")
    pnl_bits = []
    if t.get("pnl_usd") is not None:
        pnl_bits.append(f"{_money(t['pnl_usd'])}")
    pct = []
    if t.get("pnl_pct") is not None:
        pct.append(f"{_signed(t['pnl_pct'],1)}% margin")
    if t.get("acct_pct") is not None:
        pct.append(f"~{abs(_f(t['acct_pct'])):.0f}% acct")
    if pnl_bits or pct:
        lines.append(f"   PnL {' '.join(pnl_bits)}{(' (' + ', '.join(pct) + ')') if pct else ''}")
    return "\n".join(lines)


def render(p: dict) -> str:
    out = [f"📊 <b>Futures Daily</b>{' — ' + p['date'] if p.get('date') else ''}", DIV]

    head = []
    if p.get("equity") is not None:
        eq = f"💰 {_money(p['equity'])}"
        if p.get("equity_change_pct") is not None:
            eq += f" {_pnl_emoji(p['equity_change_pct'])}{_signed(p['equity_change_pct'],1)}%"
        head.append(eq)
    if p.get("trades_24h") is not None:
        t = f"🎯 {p['trades_24h']} trades"
        if p.get("win_rate") is not None:
            t += f" · {round(_f(p['win_rate']) or 0)}% win"
        if p.get("pnl_24h") is not None:
            t += f" · {_pnl_emoji(p['pnl_24h'])}{_signed(p['pnl_24h'])}"
        head.append(t)
    if head:
        out.append("  ·  ".join(head))

    # Trades (24h closed) — clear blocks
    out.append("\n🔍 <b>Trades (24h)</b>\n" + DIV)
    review = p.get("review") or []
    if review:
        blocks = [_render_trade(i) if isinstance(i, dict) else f"• {i}" for i in review]
        out.append("\n".join(blocks))
    else:
        ctx = p.get("scan_context")
        out.append(f"• No closed trades{(' — ' + ctx) if ctx else ''}")

    # Notes / flags
    notes = p.get("notes") or []
    if notes:
        out.append("\n⚠️ <b>Notes</b>\n" + DIV + "\n" + "\n".join(f"• {n}" for n in notes))

    # Backtest
    if any(p.get(k) is not None for k in ("bt_24h", "bt_baseline", "bt_7d")):
        bt = []
        if p.get("bt_24h") is not None:
            bt.append(f"24h {_pnl_emoji(p['bt_24h'])}{_signed(p['bt_24h'],0)}")
        if p.get("bt_baseline") is not None:
            bt.append(f"base {_signed(p['bt_baseline'],0)}")
        if p.get("bt_7d") is not None:
            bt.append(f"7d {_signed(p['bt_7d'],0)}")
        out.append("\n🧪 <b>Backtest</b>: " + " · ".join(bt))

    if p.get("change"):
        out.append(f"🔧 <b>Change</b>: {p['change']}")

    dep = (p.get("deploy") or "").lower()
    if dep:
        emoji = {"deployed": "🚀", "none": "⏸️", "rolled_back": "↩️"}.get(dep, "ℹ️")
        label = {"deployed": "Deployed", "none": "No change", "rolled_back": "Rolled back"}.get(dep, dep)
        line = f"{emoji} <b>{label}</b>"
        if p.get("deploy_reason"):
            line += f" — {p['deploy_reason']}"
        out.append(line)

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", help="Raw message text (if not using --json)")
    ap.add_argument("--json", dest="payload", help="JSON payload for a pretty report")
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
