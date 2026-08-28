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
    truncated: list[tuple[str, int]] = field(default_factory=list)
    retries: int = 0
    want_bars: int = 0
    median_bars: int = 0
    min_bars_seen: int = 0

    @property
    def coverage(self) -> float:
        return self.complete / self.requested if self.requested else 0.0

    def __str__(self) -> str:
        lines = ["universe: %d/%d symbols complete (%.1f%%), want %d bars, "
                 "median %d, min %d"
                 % (self.complete, self.requested, 100 * self.coverage,
                    self.want_bars, self.median_bars, self.min_bars_seen)]
        if self.retries:
            lines.append("  %d chunk retries absorbed" % self.retries)
        if self.missing:
            lines.append("  MISSING (%d): %s" % (len(self.missing),
                                                 ", ".join(self.missing[:8])
                                                 + (" ..." if len(self.missing) > 8 else "")))
        if self.truncated:
            worst = sorted(self.truncated, key=lambda x: x[1])[:6]
            lines.append("  TRUNCATED (%d) - API gave up mid-history, NOT a young listing: %s"
                         % (len(self.truncated),
                            ", ".join("%s@%d" % (s, n) for s, n in worst)))
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
    rep = FetchReport(requested=len(symbols), want_bars=want)
    counter = {"retries": 0}

    def one(sym):
        parts, end, cut = [], now, False
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
                        got, cut = None, True   # retries exhausted: TRUNCATED, not young
                        break
                    time.sleep((0.4 * (2 ** attempt)) + random.random() * 0.3)
            if got is None or not len(got):
                break
            parts.append(got)
            end = int(got.index[0].timestamp()) - BAR
        if not parts:
            return sym, None, cut
        o = pd.concat(parts[::-1])
        return sym, o[~o.index.duplicated(keep="first")].sort_index(), cut

    with ThreadPoolExecutor(max_workers=workers) as pool:
        res = list(pool.map(one, list(symbols)))
    got = {sym: (f, cut) for sym, f, cut in res}

    frames, lens = {}, []
    for sym in symbols:
        f, cut = got.get(sym, (None, True))
        if f is None or not len(f):
            rep.missing.append(sym)
            continue
        # A truncated fetch and a young listing both lack OLD history - the walk
        # runs backwards from now, so both are short at the same end and a
        # bar-count threshold cannot tell them apart. What separates them is WHY
        # the walk stopped: retries exhausted (our failure) vs the exchange
        # returning empty (there is genuinely nothing older). Only the first is
        # a defect, and it must not be forgiven for having enough recent bars.
        if cut:
            rep.truncated.append((sym, len(f)))
            continue
        if len(f) < min_bars:
            rep.short.append((sym, len(f)))
            continue
        frames[sym] = f
        lens.append(len(f))
    rep.complete = len(frames)
    rep.retries = counter["retries"]
    rep.median_bars = sorted(lens)[len(lens) // 2] if lens else 0
    rep.min_bars_seen = min(lens) if lens else 0

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
    NL = chr(10)
    class _Stub:
        """DEAD always fails; SHORT is a young listing; TRUNC dies mid-history."""

        def __init__(self):
            self.seen = {}

        def get_klines(self, symbol, interval="Min15", start=0, end=0):
            n = self.seen.get(symbol, 0)
            self.seen[symbol] = n + 1
            if symbol == "DEAD_USDT":
                raise RuntimeError("429 rate limited")
            if symbol == "TRUNC_USDT" and n >= 1:
                raise RuntimeError("429 rate limited")   # plenty of bars, but cut short
            if symbol == "SHORT_USDT" and n >= 1:
                return pd.DataFrame()                     # genuinely nothing older
            rows = 60 if symbol == "SHORT_USDT" else 2000
            idx = pd.to_datetime([end - i * BAR for i in range(rows)][::-1],
                                 unit="s", utc=True)
            return pd.DataFrame({"high": [1.0] * rows, "low": [1.0] * rows,
                                 "close": [1.0] * rows, "volume": [1.0] * rows},
                                index=idx)

    syms = ["A_USDT", "B_USDT", "C_USDT", "SHORT_USDT", "TRUNC_USDT", "DEAD_USDT"]
    try:
        fetch_frames(_Stub(), syms, days=20, min_coverage=0.90, retries=2)
        print("FAIL: should have raised on 3/6 coverage")
    except FetchIncomplete as exc:
        print("raised as expected:")
        print(str(exc).splitlines()[0])

    fr, rp = fetch_frames(_Stub(), syms, days=20, min_coverage=0.4, retries=2)
    print(NL + "non-strict path:")
    print(rp)
    assert set(fr) == {"A_USDT", "B_USDT", "C_USDT"}, fr.keys()
    assert rp.missing == ["DEAD_USDT"], rp.missing
    # THE DEFECT THE AUDIT FOUND: TRUNC has 2000 bars - more than min_bars=300 -
    # so a bar-count gate would call it complete. It must be TRUNCATED instead,
    # because its walk stopped on exhausted retries rather than on empty data.
    assert [x for x, _ in rp.truncated] == ["TRUNC_USDT"], rp.truncated
    assert rp.truncated[0][1] >= 300, "the point: it is short on WINDOW, not on bars"
    assert "TRUNC_USDT" not in fr, "a truncated symbol must not count as complete"
    # SHORT stopped on empty data - a young listing, not our failure
    assert [x for x, _ in rp.short] == ["SHORT_USDT"], rp.short
    assert rp.want_bars == int(20 * 86400 // BAR), rp.want_bars
    assert rp.min_bars_seen > 0 and rp.min_bars_seen <= rp.median_bars
    assert rp.retries >= 2, rp.retries
    print(NL + "self-test OK")
