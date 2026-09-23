"""The replay exit resolver under T's TREND-only exit flags (EXP/T2, 2026-09-23).

EXP/T added FUTURES_TREND_TRAIL_ENABLED / _TRAIL_ARM_R / _BREAKEVEN_ARM_R to the live runtime so the
assessment's item 3 ("TREND without the retention trail, or arming at >= 2R") can be switched on without a
deploy. Pricing those variants needs the canonical resolver to express them the way the bot runs them:
the TREND switch stops the trail FIRING but keeps the peak and the breakeven stop (the master switch
FUTURES_CONVEX_RUNNER_TRAIL takes the breakeven stop with it), and the arms move only on TREND. A resolver
that got this wrong would price "no trail" as "no trail and no breakeven" - lane D's variant, not T's -
and the test lane's verdict would be about the wrong rule. These tests hold the resolver to the bot's own
patched exit methods (LiveCodeReference) and to the live env parse.
"""
from __future__ import annotations

import random

import pytest

from futuresbot.replay import exits as X
from futuresbot.replay.exits import ExitPolicy, LiveCodeReference, Trade, resolve_exit

T0 = 1_790_000_040.0          # a bar boundary


def _tape(rows, t0=T0):
    return [(t0 + 60 * i, *r) for i, r in enumerate(rows)]


def _pol(**kw):
    base = dict(sleeve="TREND", convex=True, trail=True, arm_r=1.0, retain=0.5, ratchet_r=3.0,
                ratchet_retain=0.75, early_stop_r=0.0, breakeven_arm_r=0.9, time_stop_hours=24.0,
                stop_feed="fair", tp_feed="last")
    base.update(kw)
    return ExitPolicy(**base)


def _same(a, b):
    return (a.kind == b.kind and a.gross_r == pytest.approx(b.gross_r, abs=1e-6)
            and a.exit_ts == pytest.approx(b.exit_ts, abs=1e-3))


# --- 1. hand-built paths: what each flag does ---------------------------------------------------

# LONG 100, stop 98 (1R = 2), target 106 (3R). Peak 2R in bar 1, then a fade through entry and the stop.
FADE = _tape([(100, 101, 99.8, 101), (101, 104, 100.8, 103.8), (103.8, 103.9, 99.0, 99.5),
              (99.5, 99.6, 97.0, 97.5)])
TR = Trade("LONG", 100.0, 98.0, 106.0, T0, "TREND", "SYN_USDT")


def test_trend_trail_off_keeps_the_breakeven_stop():
    """The owner's 09-20 breakeven stop must survive the TREND switch: with the trail on the fade exits
    at the 1R floor, with it off at breakeven (+cost), and only with BOTH off does it ride to -1R. If the
    switch took the breakeven stop with it, the test lane would price lane D's variant under T's name."""
    on = resolve_exit(TR, FADE, FADE, _pol())
    off = resolve_exit(TR, FADE, FADE, _pol(sleeve_trail=False))
    bare = resolve_exit(TR, FADE, FADE, _pol(sleeve_trail=False, breakeven_arm_r=0.0))
    master = resolve_exit(TR, FADE, FADE, _pol(trail=False))
    assert (on.kind, on.gross_r) == ("trail", pytest.approx(1.0))
    assert (off.kind, off.gross_r) == ("breakeven", pytest.approx(0.0019 / 0.02))
    assert (bare.kind, bare.gross_r) == ("stop", pytest.approx(-1.0))
    assert master.kind == "stop"            # the master switch still takes everything, as live
    assert off.peak_r == pytest.approx(2.0)  # the peak keeps running with the trail off


def test_the_trend_switch_is_read_on_trend_only():
    """A WILDCARD policy carrying sleeve_trail=False still trails: live reads the switch on TREND only."""
    wc = Trade("LONG", 100.0, 98.0, 110.0, T0, "WILDCARD", "SYN_USDT")
    res = resolve_exit(wc, FADE, FADE, _pol(sleeve="WILDCARD", sleeve_trail=False))
    assert res.kind == "trail"


def test_the_trend_arm_moves_only_the_gate():
    """Peak 1.6R then a fade: armed at 1.0R or 1.5R the floor is 0.5 x 1.6 = 0.8R either way; armed at
    2.0R there is no floor and the breakeven stop takes it."""
    path = _tape([(100, 103.2, 99.9, 103.0), (103.0, 103.1, 100.5, 100.6), (100.6, 100.7, 99.5, 99.6)])
    got = {a: resolve_exit(TR, path, path, _pol(arm_r=a)) for a in (1.0, 1.5, 2.0)}
    assert (got[1.0].kind, got[1.0].gross_r) == ("trail", pytest.approx(0.8))
    assert (got[1.5].kind, got[1.5].gross_r) == ("trail", pytest.approx(0.8))
    assert got[2.0].kind == "breakeven"


# --- 2. the env parse ---------------------------------------------------------------------------

def test_from_env_reads_the_trend_flags_like_the_live_runtime(monkeypatch):
    """Mapping mode and os.environ mode (the live _env_float/_flag) build the same policy; the TREND
    variables override on TREND only and fall back to the shared ones when unset or unparseable."""
    env = {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1", "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.50",
           "FUTURES_CONVEX_BREAKEVEN_ARM_R": "0.90", "FUTURES_TREND_TRAIL_ENABLED": "0",
           "FUTURES_TREND_TRAIL_ARM_R": "2.0"}
    for k in (list(X.LIVE_ENV_DEFAULTS) + list(X.LIVE_FLAG_DEFAULTS) + list(X.TREND_FALLBACKS)):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for sleeve in ("TREND", "WILDCARD"):
        assert ExitPolicy.from_env(sleeve, env) == ExitPolicy.from_env(sleeve)
    t = ExitPolicy.from_env("TREND", env)
    w = ExitPolicy.from_env("WILDCARD", env)
    assert (t.sleeve_trail, t.arm_r, t.breakeven_arm_r) == (False, 2.0, 0.9)
    assert (w.sleeve_trail, w.arm_r, w.breakeven_arm_r) == (True, 1.0, 0.9)
    assert ExitPolicy.from_env("TREND", {**env, "FUTURES_TREND_BREAKEVEN_ARM_R": "0"}).breakeven_arm_r == 0.0
    assert ExitPolicy.from_env("TREND", {**env, "FUTURES_TREND_TRAIL_ARM_R": "junk"}).arm_r == 1.0
    unset = {k: v for k, v in env.items() if not k.startswith("FUTURES_TREND_")}
    assert ExitPolicy.from_env("TREND", unset) == ExitPolicy(**{**w.__dict__, "sleeve": "TREND"})
    assert ExitPolicy.from_env("TREND", t.env()) == t


def test_drift_catches_a_live_trend_flag():
    """If the owner flips a TREND flag on the container, the daily archive's drift check must say so -
    until LIVE_TIMELINE gets the row, `live_now` replays the old stack."""
    live = {"FUTURES_CONVEX_BREAKEVEN_ARM_R": "0.90", "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.50",
            "FUTURES_TREND_EARLY_STOP_R": "0.0", "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1",
            "FUTURES_WILDCARD_EARLY_STOP_MINUTES": "30", "FUTURES_WILDCARD_EARLY_STOP_R": "0.5"}
    assert X.timeline_drift(live) == []
    assert X.timeline_drift({**live, "FUTURES_TREND_TRAIL_ENABLED": "0"}) == [
        "TREND.sleeve_trail: timeline True != live False"]
    assert X.timeline_drift({**live, "FUTURES_TREND_TRAIL_ARM_R": "2.0"}) == [
        "TREND.arm_r: timeline 1.0 != live 2.0"]


# --- 3. against the bot's own patched exit methods ----------------------------------------------

def _synthetic(rng):
    entry = 100.0
    sl_pct = rng.choice([0.6, 1.0, 1.8, 3.0])
    one_r = entry * sl_pct / 100.0
    tp_r = rng.choice([1.0, 3.0, 3.0, None])
    sigma = rng.choice([0.05, 0.15, 0.4])
    drift = rng.uniform(-0.02, 0.08)
    fair, last = [], []
    p = entry
    for k in range(rng.randint(30, 160)):
        t = T0 + 60 * k
        gap = rng.gauss(0, 0.8) * one_r if rng.random() < 0.03 else 0.0
        o = p + gap
        c = o + (rng.gauss(0, sigma) + drift) * one_r
        h = max(o, c) + abs(rng.gauss(0, sigma * 0.7)) * one_r
        l = min(o, c) - abs(rng.gauss(0, sigma * 0.7)) * one_r
        fair.append((t, o, h, l, c))
        wick = abs(rng.gauss(0, 0.3)) * one_r if rng.random() < 0.1 else 0.0
        last.append((t, o, h + wick, l - wick, c))
        p = c
    trade = Trade("LONG", entry, entry - one_r, (entry + tp_r * one_r) if tp_r else None, T0, "TREND", "SYN_USDT")
    pol = _pol(convex=rng.random() < 0.95, trail=rng.random() < 0.9, sleeve_trail=rng.random() < 0.5,
               arm_r=rng.choice([1.0, 1.5, 2.0]), breakeven_arm_r=rng.choice([0.0, 0.9, 0.9]),
               time_stop_hours=rng.choice([24.0, 1.0, 0.5]))
    return trade, fair, last, pol


def test_resolver_equals_the_live_methods_under_every_trend_flag():
    """300 random TREND paths under random switch/arm/breakeven settings, scored by the fast resolver
    and by the runtime's own (T-patched) exit methods. Any drift between the mirror and the bot fails."""
    rng = random.Random(20260924)
    kinds_off = set()
    kinds = set()
    for _ in range(300):
        trade, fair, last, pol = _synthetic(rng)
        a = resolve_exit(trade, fair, last, pol)
        b = LiveCodeReference(pol).resolve(trade, fair, last)
        assert a.kind == b.kind, (pol, a, b)
        if a.gross_r is not None:
            assert _same(a, b), (pol, a, b)
        kinds.add(a.kind)
        if pol.convex and pol.trail and not pol.sleeve_trail:
            kinds_off.add(a.kind)
    assert kinds >= {"stop", "tp", "trail", "timeout", "breakeven"}
    assert "trail" not in kinds_off and "breakeven" in kinds_off


def test_the_daily_archive_pulls_the_trend_flags():
    """The drift check only sees what the archive pulls from the container. Without these names on the
    whitelist the owner could flip FUTURES_TREND_TRAIL_ENABLED and every replay would keep the trail."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "tools" / "archive_evidence.py"
    spec = importlib.util.spec_from_file_location("archive_evidence_t2", path)
    A = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(A)
    for name in ("FUTURES_TREND_TRAIL_ENABLED", "FUTURES_TREND_TRAIL_ARM_R", "FUTURES_TREND_BREAKEVEN_ARM_R"):
        assert A.env_allowed(name), name
    assert not A.env_allowed("FUTURES_TREND_TRAIL_SECRET")
