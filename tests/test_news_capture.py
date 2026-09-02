"""News capture must be forward-only, editorially neutral, and unable to trade.

Added 2026-09-02. The bot already carries a full event/news overlay that is
enabled in the live environment and structurally unreachable - every call site
sits inside `_fetch_signal`, the PMT path, gated off by
FUTURES_ENTRY_MIN_SCORE=1000. Across 187 shadow-ledger rejects there has never
been an event-related refusal.

This module does not revive it. The properties that matter are all NEGATIVE:
it must never write the overlay's Redis key, never block a scan, and never
raise. A capture that can halt trading is worse than no capture.
"""
from __future__ import annotations

import time

from futuresbot.news import (Headline, big_stories, cluster_stories, fetch_feeds,
                             parse_feed)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Alpha Corp sells altcoins for bitcoin</title>
<link>https://a.example/1</link>
<pubDate>Tue, 02 Sep 2026 10:00:00 +0000</pubDate></item>
<item><title>Unrelated stablecoin regulation filing</title>
<link>https://a.example/2</link>
<pubDate>Tue, 02 Sep 2026 10:05:00 +0000</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Alpha Corp sells altcoins for bitcoin holdings</title>
<link href="https://b.example/9"/>
<published>2026-09-02T10:02:00Z</published></entry>
</feed>"""


def test_parses_rss():
    hs = parse_feed(RSS, "alpha")
    assert len(hs) == 2
    assert hs[0].title.startswith("Alpha Corp")
    assert hs[0].url == "https://a.example/1"
    assert hs[0].source == "alpha"


def test_parses_atom_including_link_href():
    hs = parse_feed(ATOM, "beta")
    assert len(hs) == 1
    assert hs[0].url == "https://b.example/9", "Atom puts the url in an attribute"


def test_both_timestamps_are_kept():
    """THE LOAD-BEARING FIELD PAIR. A strategy can only act on a story once WE
    have it, so a backtest keyed on published_at alone is fantasy. Storing both
    makes the lag measurable instead of assumed."""
    from email.utils import parsedate_to_datetime
    now = parsedate_to_datetime("Tue, 02 Sep 2026 10:00:00 +0000").timestamp() + 600
    h = parse_feed(RSS, "alpha", now=now)[0]
    assert h.fetched_at == now
    assert h.published_at != now, "published_at must come from the feed"
    assert h.published_at < h.fetched_at
    assert "published_at" in h.as_row() and "fetched_at" in h.as_row()


def test_malformed_feed_yields_nothing_and_does_not_raise():
    assert parse_feed("<<<not xml", "x") == []
    assert parse_feed("", "x") == []


def test_missing_pubdate_falls_back_to_now_rather_than_zero():
    """A 1970 timestamp would silently poison any later time-based analysis."""
    from email.utils import parsedate_to_datetime
    now = parsedate_to_datetime("Tue, 02 Sep 2026 12:00:00 +0000").timestamp()
    feed = ('<?xml version="1.0"?><rss><channel><item><title>No date here</title>'
            '<link>https://c.example/1</link></item></channel></rss>')
    h = parse_feed(feed, "c", now=now)[0]
    assert h.published_at == now


def test_clustering_groups_the_same_story_across_outlets():
    items = parse_feed(RSS, "alpha") + parse_feed(ATOM, "beta")
    cs = cluster_stories(items)
    multi = [c for c in cs if len(c.items) > 1]
    assert len(multi) == 1, "the two altcoin stories should merge"
    assert set(multi[0].sources) == {"alpha", "beta"}


def test_big_requires_DISTINCT_sources():
    """Corroboration is the test. One outlet running a story twice is not news
    being important, it is a feed repeating itself."""
    now = time.time()
    same = [Headline(id=str(i), source="alpha", title="Alpha Corp sells altcoins bitcoin",
                     url="u%d" % i, published_at=now, fetched_at=now) for i in range(4)]
    assert big_stories(same, min_sources=2) == []
    same.append(Headline(id="x", source="beta",
                         title="Alpha Corp sells altcoins bitcoin holdings",
                         url="ux", published_at=now, fetched_at=now))
    assert len(big_stories(same, min_sources=2)) == 1


def test_unrelated_headlines_do_not_cluster():
    now = time.time()
    items = [Headline(id="1", source="a", title="Ethereum staking withdrawals queue grows",
                      url="1", published_at=now, fetched_at=now),
             Headline(id="2", source="b", title="Solana validator client release notes",
                      url="2", published_at=now, fetched_at=now)]
    assert big_stories(items, min_sources=2) == []


def test_stories_far_apart_in_time_do_not_cluster():
    now = time.time()
    a = Headline(id="1", source="a", title="Alpha Corp sells altcoins bitcoin",
                 url="1", published_at=now, fetched_at=now)
    b = Headline(id="2", source="b", title="Alpha Corp sells altcoins bitcoin",
                 url="2", published_at=now + 40 * 3600, fetched_at=now)
    assert big_stories([a, b], min_sources=2, window_s=6 * 3600) == []


def test_a_dead_feed_does_not_lose_the_others(monkeypatch):
    import futuresbot.news as N

    class _Resp:
        def __init__(self, body): self._b = body
        def read(self): return self._b.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=0):
        if "dead" in req.full_url:
            raise OSError("connection refused")
        return _Resp(RSS)

    monkeypatch.setattr(N.urllib.request, "urlopen", fake)
    got = fetch_feeds((("dead", "https://dead.example/f"),
                       ("alive", "https://alive.example/f")), timeout=1.0)
    assert len(got) == 2 and {h.source for h in got} == {"alive"}


def test_capture_never_writes_the_overlay_redis_key():
    """The overlay is enabled but unreachable dead code on the PMT path.
    Populating its key would silently activate it. Capture stays separate."""
    import inspect

    import ast

    import futuresbot.news as N
    from futuresbot.runtime import FuturesRuntime

    # Check the AST, not the text: this module DOCUMENTS that it avoids the
    # overlay key, so a substring search matches its own explanation.
    def identifiers(obj):
        tree = ast.parse(inspect.getsource(obj).lstrip())
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                out.add(node.id)
            elif isinstance(node, ast.Attribute):
                out.add(node.attr)
            elif isinstance(node, ast.alias):
                out.add(node.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                out.add(node.module.split(".")[0])
        return out

    names = (identifiers(N) | identifiers(FuturesRuntime._news_worker)
             | identifiers(FuturesRuntime._news_alert))
    assert "redis" not in names, "capture must not touch redis"
    for banned in ("crypto_event_redis_key", "_refresh_crypto_event_state",
                   "_apply_crypto_event_overlay", "evaluate_crypto_event_overlay"):
        assert banned not in names, "capture must not reach the overlay: %s" % banned


def test_the_scan_fires_capture_without_awaiting_it():
    """A third-party fetch must not sit in the scan's critical path."""
    import inspect

    from futuresbot.runtime import FuturesRuntime
    assert "self._maybe_capture_news()" in inspect.getsource(
        FuturesRuntime._maybe_scan_wildcard)
    starter = inspect.getsource(FuturesRuntime._maybe_capture_news)
    assert "daemon=True" in starter, "must not keep the process alive"
    assert "join" not in starter, "must not block the scan"


# --- regression: the real story that broke the first matcher ------------------

REMIXPOINT = (
    ("cointelegraph",
     "Japan\u2019s Remixpoint dumps altcoins, leaves 1,506 BTC as sole crypto bet"),
    ("theblock",
     "Japan-listed Remixpoint sells all ETH, SOL, XRP and DOGE holdings in "
     "shift to bitcoin-only crypto treasury"),
    ("forklog",
     "DAT-\u043a\u043e\u043c\u043f\u0430\u043d\u0438\u044f Remixpoint "
     "\u0440\u0430\u0441\u043f\u0440\u043e\u0434\u0430\u043b\u0430 "
     "\u0430\u043b\u044c\u0442\u043a\u043e\u0438\u043d\u044b"),
)


_VOCAB = ("staking custody rollup oracle validator bridge auction lending "
          "settlement airdrop mining wallet exchange treasury futures options "
          "liquidity governance protocol network testnet mainnet upgrade audit "
          "consensus mempool sequencer collateral vault yield swap perpetual "
          "clearing depositary brokerage escrow issuance redemption").split()


def _noise(n):
    """Filler that is genuinely UNLIKE itself.

    An earlier version used one template with a changing number, so all 60
    items clustered together across three sources and registered as a story -
    the filler drowned the signal it was meant to isolate. Each item now draws
    distinct vocabulary so nothing here corroborates anything else.
    """
    now = time.time()
    out = []
    for i in range(n):
        w = [_VOCAB[(i * 7 + k * 13) % len(_VOCAB)] for k in range(5)]
        out.append(Headline(id="n%d" % i, source=["a", "b", "c"][i % 3],
                            title=" ".join(w), url="n%d" % i,
                            published_at=now, fetched_at=now))
    return out


def test_remixpoint_clusters_across_three_outlets_including_russian():
    """The story that exposed the bug. Plain Jaccard scored the two ENGLISH
    headlines at 0.21 - they share only {japan, remixpoint, crypto} of ~14
    tokens - and the Russian item shares no ordinary words at all. What ties
    all three together is one rare proper noun."""
    now = time.time()
    items = _noise(60) + [
        Headline(id="r%d" % i, source=src, title=title, url="r%d" % i,
                 published_at=now, fetched_at=now)
        for i, (src, title) in enumerate(REMIXPOINT)]
    big = big_stories(items, min_sources=3)
    assert len(big) == 1, "the three outlets must form one story"
    assert set(big[0].sources) == {"cointelegraph", "theblock", "forklog"}


def test_a_shared_NUMBER_does_not_fuse_unrelated_stories():
    """1,506 appears in one Remixpoint headline. Rare-token matching is limited
    to alphabetic tokens so a coincidental figure cannot merge two stories."""
    now = time.time()
    items = _noise(60) + [
        Headline(id="x1", source="a", title="Some firm holds 1506 units of gold",
                 url="x1", published_at=now, fetched_at=now),
        Headline(id="x2", source="b", title="Unrelated venue reports 1506 outages",
                 url="x2", published_at=now, fetched_at=now)]
    # assert the SPECIFIC property, not "no clusters anywhere" - filler can
    # legitimately group without saying anything about numeric fusion.
    home = {}
    for c in cluster_stories(items):
        for h in c.items:
            home[h.id] = id(c)
    assert home["x1"] != home["x2"], "a shared figure must not fuse two stories"


def test_default_threshold_is_three():
    """5 is unreachable: only five feeds exist and no story has been carried by
    all of them, so a higher threshold silences the alert rather than filtering."""
    import inspect

    from futuresbot.news import DEFAULT_FEEDS, big_stories as bs
    assert len(DEFAULT_FEEDS) == 5
    assert inspect.signature(bs).parameters["min_sources"].default == 3
