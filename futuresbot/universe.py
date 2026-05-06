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


def _is_crypto_usdt_symbol(symbol: str, detail: Mapping[str, Any] | None) -> bool:
    if not symbol.endswith("_USDT"):
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
