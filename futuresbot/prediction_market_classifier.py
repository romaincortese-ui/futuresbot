from __future__ import annotations

import re
from typing import Iterable


SYMBOL_PATTERNS: dict[str, tuple[str, ...]] = {
    "BTC_USDT": (r"\bbitcoin\b", r"\bbtc\b"),
    "ETH_USDT": (r"\bethereum\b", r"\bether\b", r"\beth\b"),
    "SOL_USDT": (r"\bsolana\b", r"\bsol\b"),
    "BNB_USDT": (r"\bbnb\b", r"\bbinance coin\b"),
    "SEI_USDT": (r"\bsei\b",),
    "ZEC_USDT": (r"\bzec\b", r"\bzcash\b"),
}

BULLISH_PATTERNS = (
    r"\babove\b",
    r"\bover\b",
    r"\bgreater than\b",
    r"\bat least\b",
    r"\breach(?:es)?\b",
    r"\bhit(?:s)?\b",
    r"\bnew all[ -]?time high\b",
    r"\bath\b",
    r"\brise(?:s)?\b",
    r"\brally\b",
    r"\bclose(?:s)?\s*>",
    r">",
)
BEARISH_PATTERNS = (
    r"\bbelow\b",
    r"\bunder\b",
    r"\bless than\b",
    r"\bfall(?:s)?\b",
    r"\bdrop(?:s)?\b",
    r"\bcrash(?:es)?\b",
    r"\blower than\b",
    r"\bclose(?:s)?\s*<",
    r"<",
)
AMBIGUOUS_PATTERNS = (
    r"\bbetween\b",
    r"\brange\b",
    r"\bprice range\b",
    r"\bairdrop\b",
    r"\blaunch(?:es)?\b",
    r"\betf\b",
    r"\bapprove(?:s|d)?\b",
    r"\bapproval\b",
    r"\bmarket cap\b",
)


def classify_prediction_market(text: str, allowed_symbols: Iterable[str] = ()) -> tuple[str, str] | None:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not lowered:
        return None
    if any(re.search(pattern, lowered) for pattern in AMBIGUOUS_PATTERNS):
        return None
    allowed = {symbol.upper() for symbol in allowed_symbols if symbol}
    symbol = ""
    for candidate, patterns in SYMBOL_PATTERNS.items():
        if allowed and candidate not in allowed:
            continue
        if any(re.search(pattern, lowered) for pattern in patterns):
            symbol = candidate
            break
    if not symbol:
        return None
    bullish = any(re.search(pattern, lowered) for pattern in BULLISH_PATTERNS)
    bearish = any(re.search(pattern, lowered) for pattern in BEARISH_PATTERNS)
    if bullish == bearish:
        return None
    return symbol, "bullish" if bullish else "bearish"