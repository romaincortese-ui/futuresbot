from futuresbot.universe import select_major_usdt_symbols


def test_select_major_usdt_symbols_preserves_core_and_filters_non_crypto():
    tickers = [
        {"symbol": "XAUT_USDT", "amount24": 999_000_000},
        {"symbol": "BCH_USDT", "amount24": 500_000_000},
        {"symbol": "NVIDIA_USDT", "amount24": 450_000_000},
        {"symbol": "NICKEL_USDT", "amount24": 425_000_000},
        {"symbol": "PAXG_USDT", "amount24": 410_000_000},
        {"symbol": "LINK_USDT", "amount24": 400_000_000},
        {"symbol": "ETH_USDT", "amount24": 300_000_000},
    ]
    details = [
        {"symbol": "XAUT_USDT", "quoteCoin": "USDT", "baseCoin": "XAUT", "state": 0},
        {"symbol": "BCH_USDT", "quoteCoin": "USDT", "baseCoin": "BCH", "state": 0},
        {"symbol": "NVIDIA_USDT", "quoteCoin": "USDT", "baseCoin": "NVIDIA", "state": 0},
        {"symbol": "NICKEL_USDT", "quoteCoin": "USDT", "baseCoin": "NICKEL", "state": 0},
        {"symbol": "PAXG_USDT", "quoteCoin": "USDT", "baseCoin": "PAXG", "state": 0},
        {"symbol": "LINK_USDT", "quoteCoin": "USDT", "baseCoin": "LINK", "state": 0},
        {"symbol": "ETH_USDT", "quoteCoin": "USDT", "baseCoin": "ETH", "state": 0},
    ]

    selected = select_major_usdt_symbols(tickers, details, top_n=4, include_symbols=("BTC_USDT", "SOL_USDT"))

    assert selected == ("BTC_USDT", "SOL_USDT", "BCH_USDT", "LINK_USDT")
