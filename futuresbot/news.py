"""Forward-only capture of crypto headlines, and neutral detection of big ones.

Added 2026-09-02. The bot has a full event/news overlay (event_overlay.py,
event_policy.py, event_quality.py) which is enabled in the live environment and
STRUCTURALLY UNREACHABLE: all three of its call sites sit inside `_fetch_signal`,
the PMT path, which is gated off by FUTURES_ENTRY_MIN_SCORE=1000. Across 187
shadow-ledger rejects there has never been an event-related refusal. It was built
for a strategy that is no longer run.

This module does NOT revive it. It captures only. Nothing here writes
`mexc:crypto_event_intelligence`; populating that key would silently activate
dead code on the PMT path. Capture and consumption stay separate until there is
evidence to justify wiring them.

WHY FORWARD-ONLY IS THE WHOLE POINT. The owner asked whether news predicts
WILDCARD outcomes. It cannot be answered from the 66 closes on hand, because no
headline corpus exists and assembling one now - after the outcomes are known -
is hindsight selection, which is exactly the class of error that produced and
then destroyed half of this week's findings. An append-only store that never
backfills is the only version of this question that can be answered honestly.

The nearest thing that COULD be measured today - the price signature of the
rotation, BTC strong while alts are weak - was measured (2026-09-02) and points
the other way: the sleeve's entire profit sits in the quintile where alts
strongly OUTPERFORM BTC (mean R +0.737, n=13), while the alt-dumping quintile
runs mean R +0.117 on a 62% win rate. So no gate is implied by anything known,
and this module implements none.

STDLIB ONLY. urllib and xml.etree, no new dependency. Yesterday `redis` being
absent from the image made an entire subsystem silently inert; a capture module
that cannot import is worse than none.

WHAT "BIG" MEANS HERE. Cross-source corroboration, not an editorial keyword
list. A story carried by >= N distinct outlets inside a time window is treated
as notable. That judgement is made by the newsrooms, not by a list I would be
choosing after seeing which trades lost.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Iterable

log = logging.getLogger(__name__)

DEFAULT_FEEDS: tuple[tuple[str, str], ...] = (
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("cointelegraph", "https://cointelegraph.com/rss"),
    ("theblock", "https://www.theblock.co/rss.xml"),
    ("decrypt", "https://decrypt.co/feed"),
    ("forklog", "https://forklog.com/feed/"),
)

_UA = "Mozilla/5.0 (compatible; futuresbot-news/1.0)"
_STOP = frozenset("""
the a an and or of for to in on at by with from as is are was were be been will
that this these those it its his her their our your not no but if then than so
new says say said report reports about after before over under into out up down
""".split())
_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class Headline:
    id: str
    source: str
    title: str
    url: str
    published_at: float
    fetched_at: float

    def as_row(self) -> dict[str, Any]:
        return {"id": self.id, "source": self.source, "title": self.title,
                "url": self.url, "published_at": round(self.published_at, 1),
                "fetched_at": round(self.fetched_at, 1)}


@dataclass
class Cluster:
    """One story as carried by several outlets."""
    key: str
    items: list[Headline] = field(default_factory=list)

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(sorted({h.source for h in self.items}))

    @property
    def title(self) -> str:
        # the shortest title is usually the least editorialised
        return min((h.title for h in self.items), key=len)

    @property
    def published_at(self) -> float:
        return min(h.published_at for h in self.items)

    @property
    def fetched_at(self) -> float:
        return min(h.fetched_at for h in self.items)


def _tokens(title: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(title.lower())
                     if len(w) >= 4 and w not in _STOP)


def _ts(value: str | None, fallback: float) -> float:
    if not value:
        return fallback
    try:
        return parsedate_to_datetime(value).timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return time.mktime(time.strptime(value[:19] + ("+0000" if "%z" in fmt else ""),
                                             fmt))
        except Exception:
            continue
    return fallback


def parse_feed(xml_text: str, source: str, *, now: float | None = None) -> list[Headline]:
    """RSS or Atom -> Headlines. Never raises; a malformed feed yields nothing."""
    now = time.time() if now is None else now
    out: list[Headline] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        log.debug("news: %s did not parse: %s", source, exc)
        return out
    nodes = root.iter("item")
    items = list(nodes)
    if not items:                      # Atom
        items = [e for e in root.iter() if e.tag.endswith("}entry")]
    for it in items:
        title = link = pub = None
        for ch in it:
            tag = ch.tag.split("}")[-1]
            if tag == "title" and title is None:
                title = (ch.text or "").strip()
            elif tag == "link" and link is None:
                link = (ch.text or "").strip() or ch.attrib.get("href", "").strip()
            elif tag in ("pubDate", "published", "updated") and pub is None:
                pub = (ch.text or "").strip()
        if not title:
            continue
        url = link or ""
        hid = hashlib.sha1((url or title).encode("utf-8")).hexdigest()[:16]
        out.append(Headline(id=hid, source=source, title=title, url=url,
                            published_at=_ts(pub, now), fetched_at=now))
    return out


def fetch_feeds(feeds: Iterable[tuple[str, str]] = DEFAULT_FEEDS, *,
                timeout: float = 5.0, now: float | None = None) -> list[Headline]:
    """Fetch every feed. One bad feed must not lose the others."""
    now = time.time() if now is None else now
    out: list[Headline] = []
    for source, url in feeds:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            out.extend(parse_feed(text, source, now=now))
        except Exception as exc:
            log.debug("news: feed %s failed: %s", source, exc)
    return out


def cluster_stories(items: Iterable[Headline], *, window_s: float = 6 * 3600,
                    min_overlap: float = 0.34) -> list[Cluster]:
    """Group headlines that are plausibly the same story.

    Jaccard overlap on content words, inside a time window. Deliberately crude:
    the point is to notice that several outlets ran the same thing, not to
    understand what it says.
    """
    ordered = sorted(items, key=lambda h: h.published_at)
    clusters: list[Cluster] = []
    toks: list[frozenset[str]] = []
    for h in ordered:
        t = _tokens(h.title)
        if not t:
            continue
        placed = False
        for idx, c in enumerate(clusters):
            if abs(c.published_at - h.published_at) > window_s:
                continue
            inter = len(t & toks[idx])
            union = len(t | toks[idx])
            if union and inter / union >= min_overlap:
                c.items.append(h)
                toks[idx] = toks[idx] | t
                placed = True
                break
        if not placed:
            clusters.append(Cluster(key=h.id, items=[h]))
            toks.append(t)
    return clusters


def big_stories(items: Iterable[Headline], *, min_sources: int = 2,
                window_s: float = 6 * 3600) -> list[Cluster]:
    """Clusters carried by at least `min_sources` DISTINCT outlets.

    Corroboration is the whole test. It contains no opinion about which topics
    matter, which is the property that keeps this usable as evidence later.
    """
    return [c for c in cluster_stories(items, window_s=window_s)
            if len(c.sources) >= min_sources]
