"""The MEXC kline cache (futuresbot/replay/bars.py).

Every test the 2026-09-23 assessment ranked depends on bars MEXC stops serving: 1m after ~30
days, 15m after ~361. A cache that stores the forming bar, mistakes a roll-off for "no trading",
re-fetches what it already holds, or silently thins a long request corrupts every study built on
it without an error. These tests run against a fake exchange with the real API's quirks: the
forming bar at the end of every answer, a sliding history window, the latest-2000-bars cap, and
code 1001 for an unknown contract. No network.
"""
from __future__ import annotations

import gzip
import json
import os
import re
from urllib.parse import parse_qs, urlparse

import pytest

from futuresbot.replay import bars as B
from futuresbot.replay.bars import BarCache, authoritative_horizon, chunk_bounds

NOW = 1_790_188_230.0                          # 2026-09-23 18:30:30Z, mid-bar for both intervals
DAY = 86400


class FakeExchange:
    """MEXC's kline endpoint: bars exist from `listed` (or the history horizon, whichever is
    later) up to and INCLUDING the forming bar; answers keep the latest 2000 bars."""

    def __init__(self, clock, *, listed=0.0, delisted=None, unknown=(), fail=0):
        self.clock = clock
        self.listed = listed
        self.delisted = delisted
        self.unknown = set(unknown)
        self.fail = fail
        self.requests = []

    def __call__(self, url):
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        m = re.search(r"/kline/(fair_price/)?([A-Z0-9_]+)$", u.path)
        feed = "fair" if m.group(1) else "last"
        sym, iv = m.group(2), q["interval"]
        a, b = int(q["start"]), int(q["end"])
        self.requests.append((sym, feed, iv, a, b))
        if self.fail:
            self.fail -= 1
            raise OSError("connection reset")
        if sym in self.unknown:
            return {"success": False, "code": 1001, "message": "contract not exist"}
        step = B.INTERVAL_S[iv]
        now = self.clock()
        oldest = now - B.HISTORY_DAYS[iv] * DAY
        forming = int(now // step * step)
        ts = [t for t in range(a - a % step, b + 1, step)
              if a <= t <= b and t >= oldest and t >= self.listed and t <= forming
              and (self.delisted is None or t < self.delisted)]
        ts = ts[-2000:]
        px = [1.0 + (t % 7919) / 1e4 for t in ts]
        data = {"time": ts, "open": px, "high": [p * 1.01 for p in px], "low": [p * 0.99 for p in px],
                "close": px, "vol": [5.0] * len(ts), "amount": [5.0] * len(ts)}
        if feed == "fair":
            data["vol"] = data["amount"] = [0.0] * len(ts)
        return {"success": True, "code": 0, "data": data}


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _cache(tmp_path, **kw):
    clock = Clock(NOW)
    ex = FakeExchange(clock, **kw)
    return BarCache(str(tmp_path), fetch_json=ex, clock=clock), ex, clock


def test_second_load_is_served_from_disk(tmp_path):
    cache, ex, _ = _cache(tmp_path)
    a = cache.load("BTC_USDT", "fair", "Min1", NOW - 3 * 3600, NOW - 600)
    n = len(ex.requests)
    b = cache.load("BTC_USDT", "fair", "Min1", NOW - 3 * 3600, NOW - 600)
    assert len(ex.requests) == n, "a proven range must never be fetched twice"
    assert a.time == b.time and a.close == b.close and len(a) == 170 and a.complete


def test_only_the_missing_range_is_fetched(tmp_path):
    cache, ex, _ = _cache(tmp_path)
    cache.load("BTC_USDT", "last", "Min15", NOW - 40 * DAY, NOW - 20 * DAY)
    ex.requests.clear()
    cache.load("BTC_USDT", "last", "Min15", NOW - 50 * DAY, NOW - 20 * DAY)
    assert ex.requests and all(b < NOW - 40 * DAY for _s, _f, _i, _a, b in ex.requests)


def test_the_forming_bar_is_never_stored(tmp_path):
    """The API returns the half-built bar at the end of every answer. Caching it would freeze a
    wrong OHLC forever - the forming-vs-completed confusion that grades WILDCARD entries F."""
    cache, ex, clock = _cache(tmp_path)
    got = cache.load("BTC_USDT", "last", "Min15", NOW - DAY, NOW + 900)
    forming = int(NOW // 900 * 900)
    assert forming not in got.time
    assert got.time[-1] == forming - 900
    assert (forming, forming + 1800, "not_closed") in got.unavailable
    clock.t = forming + 900 + 5                   # the bar has closed
    again = cache.load("BTC_USDT", "last", "Min15", NOW - DAY, NOW + 900)
    assert forming in again.time
    assert ex.requests[-1][3] == forming           # and only the new bar was asked for


def test_an_empty_answer_inside_the_window_is_a_fact_not_a_hole(tmp_path):
    """Not listed yet / delisted / halted: cached as covered, never re-asked, not reported."""
    cache, ex, _ = _cache(tmp_path, listed=NOW - 5 * DAY)
    got = cache.load("NEW_USDT", "fair", "Min15", NOW - 60 * DAY, NOW - DAY)
    assert got.complete and got.time[0] >= NOW - 5 * DAY
    n = len(ex.requests)
    cache.load("NEW_USDT", "fair", "Min15", NOW - 60 * DAY, NOW - DAY)
    assert len(ex.requests) == n


def test_silence_beyond_the_history_window_is_never_recorded_as_no_trading(tmp_path):
    """MEXC's window slides forward daily (15m: ~361 days). An empty answer older than the
    authoritative horizon means ROLLED OFF - recording it as 'no bars existed' would invent a
    listing date. It is reported as beyond_history, kept out of `covered`, and not re-asked."""
    cache, ex, _ = _cache(tmp_path)
    start = NOW - 380 * DAY
    got = cache.load("OLD_USDT", "fair", "Min15", start, NOW - 350 * DAY)
    first = got.time[0]
    assert first >= NOW - B.HISTORY_DAYS["Min15"] * DAY
    assert any(why == "beyond_history" for _a, _b, why in got.unavailable)
    assert not any(why == "fetch_failed" for _a, _b, why in got.unavailable)
    covered = cache.coverage("OLD_USDT", "fair", "Min15")
    assert covered[0][0] == first, "coverage starts at the first bar actually served"
    n = len(ex.requests)
    cache.load("OLD_USDT", "fair", "Min15", start, NOW - 350 * DAY)
    assert len(ex.requests) == n, "a roll-off is permanent: never re-asked"


def test_an_empty_stretch_straddling_the_horizon_is_not_a_hole(tmp_path):
    """Listed (or reopened after a weekend) just after the authoritative horizon: the stretch from
    the horizon to the first bar was answered authoritatively and is a fact, not a failed fetch.
    Only the part OLDER than the horizon is unobtainable."""
    listed = authoritative_horizon("Min15", NOW) + 3 * DAY
    cache, ex, _ = _cache(tmp_path, listed=listed)
    got = cache.load("NEW_USDT", "last", "Min15", NOW - 365 * DAY, NOW - 300 * DAY)
    assert got.time[0] == listed
    assert {w for *_x, w in got.unavailable} == {"beyond_history"}
    assert max(b for _a, b, _w in got.unavailable) <= authoritative_horizon("Min15", NOW)
    n = len(ex.requests)
    cache.load("NEW_USDT", "last", "Min15", NOW - 365 * DAY, NOW - 300 * DAY)
    assert len(ex.requests) == n


def test_requests_never_exceed_the_api_cap(tmp_path):
    """A longer span is answered with its LATEST 2000 bars; the start vanishes silently."""
    cache, ex, _ = _cache(tmp_path)
    cache.load("BTC_USDT", "last", "Min15", NOW - 200 * DAY, NOW)
    cache.load("BTC_USDT", "last", "Min1", NOW - 3 * DAY, NOW)
    for _s, _f, iv, a, b in ex.requests:
        assert (b - a) // B.INTERVAL_S[iv] + 1 <= B.REQUEST_BARS[iv] < B.API_MAX_BARS


def test_a_failed_request_is_reported_and_retried_next_time(tmp_path):
    cache, ex, _ = _cache(tmp_path, fail=10 ** 6)
    got = cache.load("BTC_USDT", "fair", "Min1", NOW - 3600, NOW - 120)
    assert len(got) == 0 and {w for *_x, w in got.unavailable} == {"fetch_failed"}
    ex.fail = 0
    ok = cache.load("BTC_USDT", "fair", "Min1", NOW - 3600, NOW - 120)
    assert len(ok) == 58 and ok.complete


def test_a_body_cut_mid_transfer_is_a_failed_attempt_not_a_crash(tmp_path):
    """http.client.IncompleteRead killed the first E/H backfill after ~6,000 requests."""
    import http.client

    clock = Clock(NOW)
    ex = FakeExchange(clock)
    state = {"n": 0}

    def flaky(url):
        state["n"] += 1
        if state["n"] == 1:
            raise http.client.IncompleteRead(b"partial")
        return ex(url)
    got = BarCache(str(tmp_path), fetch_json=flaky, clock=clock).load("BTC_USDT", "fair", "Min1", NOW - 3600, NOW - 120)
    assert len(got) == 58 and got.complete and state["n"] == 2


def test_a_minute_that_closes_mid_fetch_is_not_a_failed_fetch(tmp_path):
    """The first live archive run labelled STRK/SYN's last minute fetch_failed: the clock crossed
    a minute boundary between the request and the hole check."""
    clock = Clock(NOW)
    ex = FakeExchange(clock)

    def slow(url):
        out = ex(url)
        clock.t += 45.0                           # the request straddles a minute boundary
        return out
    got = BarCache(str(tmp_path), fetch_json=slow, clock=clock).load("BTC_USDT", "fair", "Min1", NOW - 600, NOW + 60)
    assert {w for *_x, w in got.unavailable} == {"not_closed"}


def test_an_unknown_contract_is_reported_and_writes_nothing(tmp_path):
    cache, ex, _ = _cache(tmp_path, unknown={"GONE_USDT"})
    got = cache.load("GONE_USDT", "last", "Min15", NOW - 90 * DAY, NOW - DAY)
    assert len(got) == 0 and {w for *_x, w in got.unavailable} == {"unknown_symbol"}
    assert len(ex.requests) == 1, "one 1001 stops the whole call"
    assert not os.path.exists(os.path.join(str(tmp_path), "last", "Min15", "GONE_USDT"))


def test_offline_mode_reads_the_disk_only(tmp_path):
    cache, ex, _ = _cache(tmp_path)
    cache.load("BTC_USDT", "fair", "Min1", NOW - 7200, NOW - 3600)
    ex.requests.clear()
    got = cache.load("BTC_USDT", "fair", "Min1", NOW - 10800, NOW - 3600, fetch=False)
    assert ex.requests == []
    assert len(got) == 60 and got.unavailable == [(int(NOW - 10800) // 60 * 60 + 60, int(NOW - 7200) // 60 * 60 + 60,
                                                   "offline")]


def test_layout_is_one_file_per_utc_day_or_month_and_writes_are_atomic(tmp_path):
    cache, _ex, _ = _cache(tmp_path)
    cache.load("BTC_USDT", "last", "Min1", NOW - 2 * DAY, NOW - DAY)
    cache.load("BTC_USDT", "fair", "Min15", NOW - 45 * DAY, NOW - DAY)
    m1 = sorted(os.listdir(tmp_path / "last" / "Min1" / "BTC_USDT"))
    m15 = sorted(os.listdir(tmp_path / "fair" / "Min15" / "BTC_USDT"))
    assert m1 == ["2026-09-21.json.gz", "2026-09-22.json.gz"]
    assert m15 == ["2026-08.json.gz", "2026-09.json.gz"]
    assert not [p for p, _d, fs in os.walk(tmp_path) for f in fs if ".tmp" in f]
    with gzip.open(tmp_path / "last" / "Min1" / "BTC_USDT" / "2026-09-22.json.gz", "rt") as fh:
        doc = json.load(fh)
    assert set(B.COLUMNS["last"]) <= set(doc)
    assert doc["covered"] == [[doc["start"], int(-(-(NOW - DAY) // 60) * 60)]], "exactly what was asked"
    with gzip.open(tmp_path / "fair" / "Min15" / "BTC_USDT" / "2026-09.json.gz", "rt") as fh:
        assert "vol" not in json.load(fh), "fair price has no volume; zeros are not stored"


def test_chunk_bounds_and_range_arithmetic():
    assert chunk_bounds("Min15", 1_790_188_230) == ("2026-09", 1_788_220_800, 1_790_812_800)
    assert chunk_bounds("Min1", 1_790_188_230) == ("2026-09-23", 1_790_121_600, 1_790_208_000)
    assert B._merge([[5, 9], [0, 3], [3, 4], [8, 12]]) == [[0, 4], [5, 12]]
    assert B._subtract(0, 20, [[2, 5], [8, 30]]) == [[0, 2], [5, 8]]
    assert authoritative_horizon("Min15", NOW) > NOW - B.HISTORY_DAYS["Min15"] * DAY


def test_bars_rows_feed_the_exit_resolver(tmp_path):
    cache, _ex, _ = _cache(tmp_path)
    got = cache.load("BTC_USDT", "fair", "Min1", NOW - 600, NOW - 120)
    rows = got.rows()
    assert rows[0][0] == got.time[0] and len(rows[0]) == 5
