"""MEXC LAST- and FAIR-price kline cache for replays: read the disk first, fetch only the gap.

WHY THIS EXISTS (assessment 2026-09-23, docs/DECISION_RULE.md "IMPARTIAL ASSESSMENT + REPLAY AUDIT").
Two of the replay's three biggest faults are data faults, not logic faults:

  * EXIT PRICE. Live stops rest on the FAIR price (marketdata._trigger_trends_for_order_side,
    lossTrend=2) and the software exits poll the fair price; every study read LAST-price wicks.
    That is ~+-0.1R per trade and flips the sign of H's baseline, the trail, the breakeven stop
    and the early stop. On fair-price 1m bars the exit types match live 70 of 70; on last-price
    wicks 66 of 70 (wc/ASSESS/A/a03_resolve.py).
  * THE DATA ROLLS OFF. MEXC serves only a sliding window of klines, and the window is the same
    for both feeds. Measured 2026-09-23 18:19Z on BTC_USDT, both feeds identical:
        Min1   earliest bar 2026-08-24 18:01Z   (30.0 days back)
        Min15  earliest bar 2025-09-27 20:15Z   (360.9 days back)
        Min60  >= 400 days back
    So the 1m exit tape of every live fill is gone ~30 days after the fill, and replay H's window
    (2025-10-01 ->) starts rolling off the 15m feed within days. Eight cited study folders had
    already vanished from %TEMP% when the assessment looked. A study run next month on the same
    code would read a different, shorter tape and nobody would know.

WHAT IT GUARANTEES
  * Only COMPLETED bars are ever stored. The API returns the forming bar at the end of every
    answer; caching it would freeze a half-built OHLC forever - the exact forming-vs-completed
    confusion that grades WILDCARD entries F. A bar is complete when open + interval <= fetch time.
  * An EMPTY answer is cached as "no bars exist" ONLY inside the authoritative window
    (measured history minus a one-day safety margin, `authoritative_horizon`). Older ranges are
    fetched opportunistically: whatever comes back is kept and covered from its first bar on, and
    the silence before it is recorded as UNOBTAINABLE (`beyond`, reported `beyond_history`, never
    re-asked because rolled-off data does not come back) - never as absence, because beyond the
    horizon silence means "rolled off", not "never traded". Confusing the two is how a cache
    quietly turns a data-retention limit into a fake listing date or a fake halt.
  * Every request spans <= 1,920 bars. The API answers a longer range with its LATEST 2,000 bars
    and drops the start without saying so (measured: a 3,000-bar request returned bars 1,001-3,000).
  * Coverage is explicit per chunk file (`covered` half-open ranges of bar-open times, `beyond`,
    and the fetch provenance), so a second call fetches only what the first did not prove.

LAYOUT  <root>/<feed>/<interval>/<SYMBOL>/<chunk>.json.gz
        chunk = UTC day (YYYY-MM-DD) for Min1, UTC month (YYYY-MM) for Min15.
        Columns are the API's own names (time, open, high, low, close; LAST adds vol, amount -
        FAIR returns zeros there, so they are not stored).

Public API, read-only (GET on contract.mexc.com). No credentials are used or accepted.
"""
from __future__ import annotations

import calendar
import gzip
import http.client
import json
import math
import os
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

BASE_URL = "https://contract.mexc.com/api/v1/contract/"
# Feed -> kline path. "index" (kline/index_price/) exists too; nothing in the bot reads it.
FEED_PATHS = {"last": "kline/", "fair": "kline/fair_price/"}
INTERVAL_S = {"Min1": 60, "Min15": 900}
# Bars per request. The API caps an answer at 2,000 bars and keeps the LATEST ones, so a span
# above that silently loses its start. 1,440 = one UTC day of Min1 (one request per day file);
# 1,920 = 20 days of Min15.
REQUEST_BARS = {"Min1": 1440, "Min15": 1920}
API_MAX_BARS = 2000
# Measured history depth, days (see module docstring). Both feeds share it.
HISTORY_DAYS = {"Min1": 30.0, "Min15": 360.9}
# The authoritative window stops this far short of the measured one, so a horizon that has
# drifted by hours since the measurement can never make an empty answer look authoritative.
HISTORY_SAFETY_S = 86400
# Columns stored per feed.
COLUMNS = {"last": ("open", "high", "low", "close", "vol", "amount"),
           "fair": ("open", "high", "low", "close")}
SCHEMA_VERSION = 1
# Code the API returns for a contract it does not know (unlisted or delisted-and-purged).
UNKNOWN_SYMBOL_CODES = {1001}


class UnknownSymbol(Exception):
    """The exchange does not know this contract (API code 1001)."""


def authoritative_horizon(interval: str, now: float) -> int:
    """Oldest bar-open time from which an EMPTY answer may be trusted as 'no bars exist'."""
    iv = INTERVAL_S[interval]
    h = now - HISTORY_DAYS[interval] * 86400.0 + HISTORY_SAFETY_S
    return int(math.ceil(h / iv) * iv)


def reachable_horizon(interval: str, now: float) -> int:
    """Oldest bar-open time worth ASKING for: one day past the measured depth. Anything older
    is not fetched at all - it is reported as `beyond_history`."""
    iv = INTERVAL_S[interval]
    h = now - HISTORY_DAYS[interval] * 86400.0 - 86400.0
    return int(math.floor(h / iv) * iv)


def last_complete_end(interval: str, now: float) -> int:
    """Exclusive upper bound on the open time of bars that are complete at `now`."""
    iv = INTERVAL_S[interval]
    return int(math.floor(now / iv) * iv)


# ---------------------------------------------------------------------------------------------
# half-open range arithmetic on integer bar-open times
# ---------------------------------------------------------------------------------------------
def _merge(ranges: Iterable[Iterable[int]]) -> list[list[int]]:
    out: list[list[int]] = []
    for a, b in sorted((int(a), int(b)) for a, b in ranges if int(b) > int(a)):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _subtract(a: int, b: int, covered: list[list[int]]) -> list[list[int]]:
    """[a, b) minus the union of `covered`."""
    gaps: list[list[int]] = []
    cur = a
    for x, y in covered:
        if y <= cur:
            continue
        if x >= b:
            break
        if x > cur:
            gaps.append([cur, min(x, b)])
        cur = max(cur, y)
        if cur >= b:
            break
    if cur < b:
        gaps.append([cur, b])
    return gaps


# ---------------------------------------------------------------------------------------------
# chunking
# ---------------------------------------------------------------------------------------------
def chunk_bounds(interval: str, t: int) -> tuple[str, int, int]:
    """(key, start, end) of the chunk file holding bar-open time t."""
    d = datetime.fromtimestamp(int(t), timezone.utc)
    if interval == "Min1":
        start = int(t) // 86400 * 86400
        return d.strftime("%Y-%m-%d"), start, start + 86400
    if interval == "Min15":
        start = calendar.timegm((d.year, d.month, 1, 0, 0, 0))
        ny, nm = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
        return d.strftime("%Y-%m"), start, calendar.timegm((ny, nm, 1, 0, 0, 0))
    raise ValueError(f"unsupported interval {interval!r}")


def _chunks(interval: str, a: int, b: int) -> list[tuple[str, int, int]]:
    out = []
    t = a
    while t < b:
        key, s, e = chunk_bounds(interval, t)
        out.append((key, s, e))
        t = e
    return out


# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
class _RateLimiter:
    """Process-wide request pacing. MEXC answers bursts with code 510; 5/s held for the
    E/H/B fetches (wc/WCF/E/e00_fetch.py, wc/ASSESS/B/m1.py at 6/s) without a single 510 streak."""

    def __init__(self, rate: float) -> None:
        self.rate = float(rate)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if self.rate <= 0:
            return
        with self._lock:
            now = time.monotonic()
            sleep = max(0.0, self._next - now)
            self._next = max(now, self._next) + 1.0 / self.rate
        if sleep:
            time.sleep(sleep)


def _http_get_json(url: str, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "futuresbot-replay/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


@dataclass
class Bars:
    """Bars with open time in [start, end), ascending, plus what could NOT be supplied.

    `unavailable` lists (a, b, why) sub-ranges with no stored answer:
        beyond_history  older than the exchange still serves and never cached
        not_closed      the bar has not completed yet
        fetch_failed    the request failed after retries (network / rate limit)
        unknown_symbol  the exchange does not know the contract
        offline         fetching disabled and not in the cache
    A range that WAS answered and simply has no bars (not listed yet, halted) is not listed:
    it is a fact about the market, not a hole in the data.
    """

    symbol: str
    feed: str
    interval: str
    start: int
    end: int
    time: list[int] = field(default_factory=list)
    open: list[float] = field(default_factory=list)
    high: list[float] = field(default_factory=list)
    low: list[float] = field(default_factory=list)
    close: list[float] = field(default_factory=list)
    vol: list[float] | None = None
    amount: list[float] | None = None
    unavailable: list[tuple[int, int, str]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.time)

    @property
    def complete(self) -> bool:
        return not self.unavailable

    def rows(self) -> list[tuple[int, float, float, float, float]]:
        """(t_open, open, high, low, close) tuples - the shape replay.exits walks."""
        return list(zip(self.time, self.open, self.high, self.low, self.close))

    def to_frame(self):  # pragma: no cover - thin convenience
        import pandas as pd

        cols = {"time": self.time, "open": self.open, "high": self.high, "low": self.low, "close": self.close}
        if self.vol is not None:
            cols["vol"] = self.vol
            cols["amount"] = self.amount
        return pd.DataFrame(cols)


class BarCache:
    """Disk-first MEXC kline loader. Thread-safe per chunk file.

    `fetch_json` (url -> decoded JSON) and `clock` (-> epoch seconds) are injectable so tests
    never touch the network; the defaults are urllib and time.time.
    """

    def __init__(self, root: str, *, rate: float = 5.0, fetch_json: Callable[[str], Any] | None = None,
                 clock: Callable[[], float] | None = None, retries: int = 8) -> None:
        self.root = str(root)
        self._fetch_json = fetch_json or _http_get_json
        self._clock = clock or time.time
        self._limiter = _RateLimiter(rate if fetch_json is None else 0.0)
        self._retries = int(retries)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self.stats = {"requests": 0, "retries": 0, "failed": 0, "bars_fetched": 0}

    # -- files ------------------------------------------------------------------------------
    def chunk_path(self, symbol: str, feed: str, interval: str, key: str) -> str:
        return os.path.join(self.root, feed, interval, symbol, key + ".json.gz")

    def _lock_for(self, path: str) -> threading.Lock:
        with self._locks_guard:
            lk = self._locks.get(path)
            if lk is None:
                lk = self._locks[path] = threading.Lock()
            return lk

    def _read_chunk(self, path: str, symbol: str, feed: str, interval: str, start: int, end: int) -> dict:
        if os.path.exists(path):
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                doc = json.load(fh)
            if doc.get("v") == SCHEMA_VERSION:
                return doc
        doc = {"v": SCHEMA_VERSION, "symbol": symbol, "feed": feed, "interval": interval,
               "start": start, "end": end, "covered": [], "beyond": [], "fetches": [], "time": []}
        for c in COLUMNS[feed]:
            doc[c] = []
        return doc

    @staticmethod
    def _write_chunk(path: str, doc: dict) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp%d" % threading.get_ident()
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fh:
            json.dump(doc, fh, separators=(",", ":"))
        os.replace(tmp, path)          # atomic: a crashed run never leaves half a file

    # -- network ----------------------------------------------------------------------------
    def _request(self, symbol: str, feed: str, interval: str, a: int, b: int) -> dict | None:
        """Bars with open time in [a, b) as {t: row}; None when the request failed.
        Raises UnknownSymbol on API code 1001."""
        iv = INTERVAL_S[interval]
        url = "%s%s%s?interval=%s&start=%d&end=%d" % (BASE_URL, FEED_PATHS[feed], symbol, interval, a, b - iv)
        back = 1.0
        for attempt in range(self._retries):
            self._limiter.wait()
            try:
                self.stats["requests"] += 1
                payload = self._fetch_json(url)
            except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError, TimeoutError):
                # HTTPException covers IncompleteRead: a chunked answer cut mid-body, seen on the
                # 2026-09-23 backfill after ~6,000 requests. It is a failed attempt, not a crash.
                payload = None
            if isinstance(payload, dict) and payload.get("success"):
                data = payload.get("data") or {}
                cols = COLUMNS[feed]
                out = {}
                ts = data.get("time") or []
                for i, t in enumerate(ts):
                    t = int(t)
                    if a <= t < b:
                        out[t] = tuple(float((data.get(c) or [0.0] * len(ts))[i]) for c in cols)
                if len(ts) >= API_MAX_BARS:
                    # Truncated from the START by the API. Never happens at REQUEST_BARS; kept so a
                    # future change to the span cannot silently thin the cache.
                    out["__truncated__"] = True  # type: ignore[index]
                return out
            if isinstance(payload, dict) and payload.get("code") in UNKNOWN_SYMBOL_CODES:
                raise UnknownSymbol(symbol)
            self.stats["retries"] += 1
            if attempt + 1 < self._retries and self._fetch_json is _http_get_json:
                time.sleep(back + random.random())
                back = min(30.0, back * 2)
        self.stats["failed"] += 1
        return None

    # -- the loader -------------------------------------------------------------------------
    def load(self, symbol: str, feed: str, interval: str, start: float, end: float, *,
             fetch: bool = True) -> Bars:
        """Bars with open time in [start, end). Reads the cache, fetches only uncovered ranges.

        `fetch=False` is the offline mode: cache only, every hole reported as `offline`."""
        if feed not in FEED_PATHS:
            raise ValueError(f"unknown feed {feed!r}")
        iv = INTERVAL_S[interval]
        a = int(math.ceil(float(start) / iv) * iv)
        b = int(math.ceil(float(end) / iv) * iv)
        bars = Bars(symbol, feed, interval, a, b)
        if feed == "last":
            bars.vol, bars.amount = [], []
        if b <= a:
            return bars
        unknown = False
        for key, cs, ce in _chunks(interval, a, b):
            lo, hi = max(a, cs), min(b, ce)
            path = self.chunk_path(symbol, feed, interval, key)
            # Holes are judged at the instant the fetch STARTED: a minute that closes while the
            # requests are in flight is "not closed yet", not a failed fetch.
            now = self._clock()
            with self._lock_for(path):
                doc = self._read_chunk(path, symbol, feed, interval, cs, ce)
                doc.setdefault("beyond", [])
                gaps = _subtract(lo, hi, _merge(doc["covered"] + doc["beyond"]))
                failed: list[list[int]] = []
                if gaps and fetch and not unknown:
                    try:
                        changed = self._fill(doc, symbol, feed, interval, gaps, failed)
                    except UnknownSymbol:
                        unknown, changed = True, False
                    if changed:
                        self._write_chunk(path, doc)
                holes = _subtract(lo, hi, _merge(doc["covered"]))
            self._append(bars, doc, lo, hi)
            beyond = _merge(doc["beyond"])
            for g0, g1 in holes:
                # Proven unobtainable (asked beyond the authoritative window, got silence). Data
                # that has rolled off never comes back, so this is never re-asked.
                for x0, x1 in beyond:
                    if x0 < g1 and x1 > g0:
                        bars.unavailable.append((max(g0, x0), min(g1, x1), "beyond_history"))
                for r0, r1 in _subtract(g0, g1, beyond):
                    bars.unavailable.extend(self._why(interval, r0, r1, now, fetch, unknown, failed))
        bars.unavailable.sort()
        return bars

    def _fill(self, doc: dict, symbol: str, feed: str, interval: str, gaps: list[list[int]],
              failed: list[list[int]]) -> bool:
        iv = INTERVAL_S[interval]
        span = REQUEST_BARS[interval] * iv
        changed = False
        for g0, g1 in gaps:
            now = self._clock()
            g1 = min(g1, last_complete_end(interval, now))
            g0 = max(g0, reachable_horizon(interval, now))
            s = g0
            while s < g1:
                e = min(g1, s + span)
                fetched_at = self._clock()
                got = self._request(symbol, feed, interval, s, e)
                if got is None:
                    failed.append([s, e])
                    s = e
                    continue
                truncated = bool(got.pop("__truncated__", False))
                done = min(e, last_complete_end(interval, fetched_at))
                rows = {t: r for t, r in got.items() if t < done}
                self._merge_rows(doc, feed, rows)
                auth = authoritative_horizon(interval, fetched_at)
                if rows and truncated:
                    lo = min(rows)                 # only what came back is proven
                elif rows:
                    # The part inside the authoritative window is proven whatever came back; older
                    # than that, only from the first bar served. Silence there is NOT absence.
                    # (A weekend-closed stock perp or a listing just after the horizon left an
                    # empty stretch between the two - on the first backfill it was mislabelled a
                    # failed fetch for COINBASE/NVIDIA/TESLA/ROBINHOOD/EDEN/FF/XAN.)
                    lo = min(max(s, auth), min(rows))
                else:
                    lo = max(s, auth)
                if lo < done:
                    doc["covered"] = _merge(doc["covered"] + [[lo, done]])
                silent_to = min(lo, done, auth)
                if s < silent_to:
                    doc["beyond"] = _merge(doc["beyond"] + [[s, silent_to]])
                doc["fetches"].append({"at": round(fetched_at, 1), "req": [s, e], "n": len(rows)})
                doc["fetches"] = doc["fetches"][-64:]
                self.stats["bars_fetched"] += len(rows)
                changed = True
                s = e
        return changed

    @staticmethod
    def _merge_rows(doc: dict, feed: str, rows: dict) -> None:
        if not rows:
            return
        cols = COLUMNS[feed]
        have = {t: tuple(doc[c][i] for c in cols) for i, t in enumerate(doc["time"])}
        have.update(rows)
        ts = sorted(have)
        doc["time"] = ts
        for j, c in enumerate(cols):
            doc[c] = [have[t][j] for t in ts]

    @staticmethod
    def _append(bars: Bars, doc: dict, lo: int, hi: int) -> None:
        for i, t in enumerate(doc["time"]):
            if lo <= t < hi:
                bars.time.append(int(t))
                bars.open.append(float(doc["open"][i]))
                bars.high.append(float(doc["high"][i]))
                bars.low.append(float(doc["low"][i]))
                bars.close.append(float(doc["close"][i]))
                if bars.vol is not None:
                    bars.vol.append(float(doc["vol"][i]))
                    bars.amount.append(float(doc["amount"][i]))

    @staticmethod
    def _why(interval: str, g0: int, g1: int, now: float, fetch: bool, unknown: bool,
             failed: list[list[int]]) -> list[tuple[int, int, str]]:
        if not fetch:
            return [(g0, g1, "offline")]
        if unknown:
            return [(g0, g1, "unknown_symbol")]
        out = []
        reach = reachable_horizon(interval, now)
        auth = authoritative_horizon(interval, now)
        done = last_complete_end(interval, now)
        if g0 < reach:
            out.append((g0, min(g1, reach), "beyond_history"))
        mid0, mid1 = max(g0, reach), min(g1, done)
        if mid0 < mid1:
            asked_and_failed = any(f0 < mid1 and f1 > mid0 for f0, f1 in failed)
            # Below the authoritative window a silent answer is a roll-off, not a failure.
            why = "fetch_failed" if asked_and_failed or mid0 >= auth else "beyond_history"
            out.append((mid0, mid1, why))
        if g1 > done:
            out.append((max(g0, done), g1, "not_closed"))
        return out

    def coverage(self, symbol: str, feed: str, interval: str) -> list[list[int]]:
        """Union of proven ranges across every chunk file on disk for this series."""
        d = os.path.join(self.root, feed, interval, symbol)
        if not os.path.isdir(d):
            return []
        ranges: list[list[int]] = []
        for name in sorted(os.listdir(d)):
            if name.endswith(".json.gz"):
                with gzip.open(os.path.join(d, name), "rt", encoding="utf-8") as fh:
                    ranges.extend(json.load(fh).get("covered", []))
        return _merge(ranges)


def load_bars(root: str, symbol: str, feed: str, interval: str, start: float, end: float, *,
              fetch: bool = True, cache: BarCache | None = None) -> Bars:
    """One-shot convenience around BarCache.load."""
    return (cache or BarCache(root)).load(symbol, feed, interval, start, end, fetch=fetch)
