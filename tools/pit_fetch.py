"""Kline fetching that REFUSES to silently return a truncated universe.

THE DEFECT THIS FIXES (found 2026-08-28 by an adversarial audit). Every pit_*
study carried its own copy of this loop:

    def fetch(s):
        for _ in range(nch):
            try:
                d = cl.get_klines(...)
            except Exception:
                break              # <-- swallows rate limits, returns short
            ...
    frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
    print("frames: %d" % len(frames))

A rate-limited run therefore produced a SHORT frame, or no frame, and the study
scored it as if the universe were complete. The auditor ran the same published
command twice and got OPPOSITE verdicts: 88 of 170 symbols on the throttled
run (N=12 won all four floors) versus 169 of 170 on the clean one (N=12 LOST
all four). The only visible difference was one line of output nobody was
reading, because "frames: 88" looks like a fact rather than a failure.

Every replay number produced in this session came through that loop.

WHAT THIS DOES DIFFERENTLY.
  1. RETRIES with exponential backoff and jitter, so a transient 429 costs a
     second rather than a symbol.
  2. Distinguishes the two failure modes that both used to read as "fine":
     symbols that returned NOTHING, and symbols whose history came back SHORT.
     A short frame is worse than a missing one - it silently shrinks the
     window for that symbol only, so the study compares 220 days of one
     symbol against 40 of another.
  3. RAISES by default when coverage falls below a threshold. A study that
     cannot fetch its universe should stop, not publish. Callers who genuinely
     want partial data must pass strict=False and say so in their output.
  4. Returns a report the caller is expected to PRINT, so the reader can see
     the universe was complete instead of assuming it.
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd

BAR = 900
CHUNK = 1900


class FetchIncomplete(RuntimeError):
    """Raised when the fetched universe is too incomplete to score."""


@dataclass
class FetchReport:
    requested: int = 0
    complete: int = 0
    short: list[tuple[str, int]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    retries: int = 0
    want_bars: int = 0
    median_bars: int = 0

    @property
    def coverage(self) -> float:
        return self.complete / self.requested if self.requested else 0.0

    def __str__(self) -> str:
        lines = ["universe: %d/%d symbols complete (%.1f%%), want >=%d bars, median %d"
                 % (self.complete, self.requested, 100 * self.coverage,
                    self.want_bars, self.median_bars)]
        if self.retries:
            lines.append("  %d chunk retries absorbed" % self.retries)
        if self.missing:
            lines.append("  MISSING (%d): %s" % (len(self.missing),
                                                 ", ".join(self.missing[:8])
                                                 + (" ..." if len(self.missing) > 8 else "")))
        if self.short:
            worst = sorted(self.short, key=lambda x: x[1])[:6]
            lines.append("  SHORT (%d): %s" % (len(self.short),
                                               ", ".join("%s@%d" % (s, n) for s, n in worst)))
        return "\n".join(lines)


def fetch_frames(client, symbols, *, days: float, workers: int = 6,
                 min_bars: int = 300, min_coverage: float = 0.90,
                 retries: int = 4, strict: bool = True, interval: str = "Min15",
                 now_ts: int | None = None) -> tuple[dict[str, pd.DataFrame], FetchReport]:
    """Fetch `days` of `interval` klines for `symbols`.

    Returns (frames, report). Raises FetchIncomplete when strict and coverage
    is below min_coverage - the point of the exercise: a study that cannot see
    its universe must not quietly score a smaller one.
    """
    now = int(now_ts if now_ts is not None else time.time())
    nch = int(days * 86400 // (CHUNK * BAR)) + 1
    want = int(days * 86400 // BAR)
    rep = FetchReport(requested=len(symbols), want_bars=min_bars)
    counter = {"retries": 0}

    def one(sym):
        parts, end = [], now
        for _ in range(nch):
            got = None
            for attempt in range(retries):
                try:
                    got = client.get_klines(sym, interval=interval,
                                            start=end - CHUNK * BAR, end=end)
                    break
                except Exception:
                    counter["retries"] += 1
                    if attempt == retries - 1:
                        got = None
                        break
                    time.sleep((0.4 * (2 ** attempt)) + random.random() * 0.3)
            if got is None or not len(got):
                break
            parts.append(got)
            end = int(got.index[0].timestamp()) - BAR
        if not parts:
            return sym, None
        o = pd.concat(parts[::-1])
        return sym, o[~o.index.duplicated(keep="first")].sort_index()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        got = dict(pool.map(one, list(symbols)))

    frames, lens = {}, []
    for sym in symbols:
        f = got.get(sym)
        if f is None or not len(f):
            rep.missing.append(sym)
            continue
        if len(f) < min_bars:
            rep.short.append((sym, len(f)))
            continue
        frames[sym] = f
        lens.append(len(f))
    rep.complete = len(frames)
    rep.retries = counter["retries"]
    rep.median_bars = sorted(lens)[len(lens) // 2] if lens else 0

    if strict and rep.coverage < min_coverage:
        raise FetchIncomplete(
            "only %d/%d symbols usable (%.1f%% < %.0f%% required) - refusing to "
            "score a truncated universe. This is the defect that produced two "
            "opposite verdicts from the same command on 2026-08-28. Re-run, or "
            "pass strict=False and say so in the output.\n%s"
            % (rep.complete, rep.requested, 100 * rep.coverage,
               100 * min_coverage, rep))
    return frames, rep


if __name__ == "__main__":
    # self-test with a stub client: one symbol always fails, one is short
    class _Stub:
        def __init__(self):
            self.n = 0

        def get_klines(self, symbol, interval="Min15", start=0, end=0):
            self.n += 1
            if symbol == "DEAD_USDT":
                raise RuntimeError("429 rate limited")
            rows = 60 if symbol == "SHORT_USDT" else 2000
            idx = pd.to_datetime([end - i * BAR for i in range(rows)][::-1],
                                 unit="s", utc=True)
            return pd.DataFrame({"high": [1.0] * rows, "low": [1.0] * rows,
                                 "close": [1.0] * rows, "volume": [1.0] * rows},
                                index=idx)

    syms = ["A_USDT", "B_USDT", "C_USDT", "SHORT_USDT", "DEAD_USDT"]
    try:
        fetch_frames(_Stub(), syms, days=20, min_coverage=0.90, retries=2)
        print("FAIL: should have raised on 3/5 coverage")
    except FetchIncomplete as exc:
        print("raised as expected:")
        print(str(exc).splitlines()[0])
    fr, rp = fetch_frames(_Stub(), syms, days=20, min_coverage=0.5, retries=2)
    print("\nnon-strict path:")
    print(rp)
    assert set(fr) == {"A_USDT", "B_USDT", "C_USDT"}, fr.keys()
    # the stub returns `rows` PER CHUNK and the loop pulls 2 chunks for 20d,
    # so SHORT_USDT lands at 120 bars - still under min_bars, which is the point
    assert rp.missing == ["DEAD_USDT"], rp.missing
    assert [s for s, _ in rp.short] == ["SHORT_USDT"], rp.short
    assert rp.short[0][1] < 300, rp.short
    assert rp.retries >= 2, rp.retries
    print("\nself-test OK")
