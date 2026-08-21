from __future__ import annotations

from typing import Any, Iterable, Mapping


NON_CRYPTO_BASES: frozenset[str] = frozenset(
    {
        "XAUT",
        "SILVER",
        "GOLD",
        "USOIL",
        "UKOIL",
        "US30",
        "NAS100",
        "SPX500",
        "NVIDIA",
        "AMD",
        "MSTR",
        "NICKEL",
        "PAXG",
        "SNDK",
        "COIN",
        "TSLA",
        "AAPL",
        "META",
        "MSFT",
        "GOOGL",
    }
)


def select_major_usdt_symbols(
    tickers: Iterable[Mapping[str, Any]],
    contract_details: Iterable[Mapping[str, Any]] | None = None,
    *,
    top_n: int = 60,
    include_symbols: Iterable[str] = (),
) -> tuple[str, ...]:
    """Select a liquid crypto-only MEXC USDT futures universe by 24h turnover."""

    details_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in (contract_details or [])
        if isinstance(row, Mapping) and row.get("symbol")
    }
    rows: list[tuple[float, str]] = []
    for ticker in tickers:
        if not isinstance(ticker, Mapping):
            continue
        symbol = str(ticker.get("symbol") or "").upper()
        if not _is_crypto_usdt_symbol(symbol, details_by_symbol.get(symbol)):
            continue
        amount = _float_from(ticker, "amount24", "turnover24", "quoteVolume", "volume24")
        if amount <= 0:
            continue
        rows.append((amount, symbol))
    rows.sort(key=lambda item: item[0], reverse=True)

    result: list[str] = []
    for symbol in include_symbols:
        normalized = str(symbol or "").upper()
        if normalized and normalized not in result:
            result.append(normalized)
    for _amount, symbol in rows:
        if symbol not in result:
            result.append(symbol)
        if len(result) >= max(1, int(top_n)):
            break
    return tuple(result)


# MEXC tags every listing with `conceptPlate`, and its own tags separate the
# tokenised equities, FX and commodity synthetics from real crypto perfectly:
# TESLA/COINBASE/COPPER/ANTHROPIC/EUR/JPY carry a tradfi tag, while SPK, SPELL,
# HOODRAT and SPACE — which a name-based rule would flag — do not.
#
# This replaced NON_CRYPTO_BASES as the primary filter because that hand-kept
# list was structurally unmaintainable: an audit on 2026-08-21 found 68 non-
# crypto perps still passing it, including the leveraged equity ETFs (TQQQ,
# SQQQ, TSLL, SOXX), FX (EUR, JPY, GBP, TRY) and commodities (ALUMINUM, COPPER,
# USO). They gap across equity-market closes and weekends, which is exactly the
# hazard an ATR-derived stop cannot price. The static list is kept as the
# fallback for when the refresh has not run.
_TRADFI_TAGS: tuple[str, ...] = (
    "tradfi", "-stock", "forex", "commodit", "metalsfutures", "preipo",
)
_EXCHANGE_NON_CRYPTO: set[str] = set()


def _detail_is_tradfi(detail: Mapping[str, Any] | None) -> bool:
    if not detail:
        return False
    plates = " ".join(str(x) for x in (detail.get("conceptPlate") or [])).lower()
    return any(tag in plates for tag in _TRADFI_TAGS)


def refresh_non_crypto_universe(details: Iterable[Mapping[str, Any]] | None) -> int:
    """Learn the non-crypto perps from the exchange's own category tags.

    Replaces the set wholesale, but only when the fetch returned something, so a
    failed or empty call leaves the previous universe standing rather than
    silently reopening the gate.
    """
    found = {
        str(d.get("symbol") or "").upper()
        for d in (details or [])
        if str(d.get("symbol") or "").endswith("_USDT") and _detail_is_tradfi(d)
    }
    if found:
        _EXCHANGE_NON_CRYPTO.clear()
        _EXCHANGE_NON_CRYPTO.update(found)
    return len(_EXCHANGE_NON_CRYPTO)


def _is_crypto_usdt_symbol(symbol: str, detail: Mapping[str, Any] | None) -> bool:
    if not symbol.endswith("_USDT"):
        return False
    if symbol.upper() in _EXCHANGE_NON_CRYPTO or _detail_is_tradfi(detail):
        return False
    base = symbol.rsplit("_", 1)[0]
    if base in NON_CRYPTO_BASES or "STOCK" in base:
        return False
    if detail:
        quote = str(detail.get("quoteCoin") or detail.get("quote") or "USDT").upper()
        if quote and quote != "USDT":
            return False
        state = detail.get("state")
        try:
            if state is not None and int(float(state)) != 0:
                return False
        except (TypeError, ValueError):
            pass
    return True


def _float_from(row: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        raw = row.get(key)
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0.0
