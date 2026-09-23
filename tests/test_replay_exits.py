"""The canonical replay exit resolver (futuresbot/replay/exits.py).

The assessment of 2026-09-23 found 63 separate copies of the exit logic across the studies, none
of them the bot's own code, all reading LAST-price wicks while the live stop rests on FAIR price
and the software exits poll FAIR price - a +-0.1R/fill bias that flipped the sign of four exit
verdicts. These tests pin the one resolver to (1) what live actually booked, (2) the bot's own
exit methods, and (3) the parameter names and defaults in runtime.py, so the next change to a
live exit rule fails here instead of silently forking the replay a 64th time.
"""
from __future__ import annotations

import ast
import gzip
import json
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

import pytest

from futuresbot.replay import exits as X
from futuresbot.replay.exits import (ExitPolicy, LiveCodeReference, Trade, breakeven_r, live_exit_kind,
                                     resolve_exit)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "replay_exits_live_fills.json.gz"
UTC = timezone.utc


def _utc(*a):
    return datetime(*a, tzinfo=UTC).timestamp()


@pytest.fixture(scope="module")
def fills():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as fh:
        return json.load(fh)["fills"]


def _trade(f):
    return Trade(f["side"], f["entry"], f["sl"], f["tp"], f["t_entry"], f["sleeve"], f["symbol"])


# --- 1. against what live booked ---------------------------------------------------------------

def test_fair_price_resolver_reproduces_every_live_exit_type(fills):
    """70 live fills 08-30 -> 09-22 on frozen MEXC fair/last 1m bars: every exit type must match
    (the assessment's 70/70). A resolver on the wrong feed or with a wrong rule drops to 66/70 or
    worse - that is exactly how the wick bias flipped four verdicts unseen."""
    assert len(fills) == 70
    mismatches = []
    for f in fills:
        tr = _trade(f)
        pol = ExitPolicy.live_at(f["sleeve"], f["side"], f["t_entry"])
        res = resolve_exit(tr, f["fair"], f["last"], pol)
        g_live = tr.r(f["exit_price"])
        live = live_exit_kind(f["exit_rule"], g_live, tr.r(tr.tp), breakeven_r(pol, tr.sl_frac),
                              pol.breakeven_arm_r > 0)
        if res.kind != live:
            mismatches.append((f["symbol"], live, res.kind))
    assert mismatches == []


def test_fair_price_resolver_reproduces_live_r_and_timing(fills):
    """Gross R within slippage of the live fill, and the exit at the right minute. Measured:
    median |dR| 0.015, worst 0.298 (a market exit on an illiquid short), timing median -19 s.
    The tolerances catch a resolver that exits at the wrong level or a bar late."""
    dg, dts, dn = [], [], []
    for f in fills:
        tr = _trade(f)
        res = resolve_exit(tr, f["fair"], f["last"], ExitPolicy.live_at(f["sleeve"], f["side"], f["t_entry"]))
        dg.append(abs(res.gross_r - tr.r(f["exit_price"])))
        dts.append(res.exit_ts - f["t_exit"])
        dn.append(res.net_r - f["pnl_usdt"] / f["risk_usdt"])
    assert statistics.median(dg) < 0.03
    assert max(dg) < 0.35
    assert all(abs(x) <= 300 for x in dts)
    # Unmodelled market-exit slippage makes the replay slightly kind; it must stay small.
    assert abs(statistics.mean(dn)) < 0.05


def test_no_fixture_fill_spans_a_policy_switch(fills):
    """live_at(t_entry) is only right if the position closed before the next deployment."""
    for f in fills:
        assert ExitPolicy.live_switches_between(f["sleeve"], f["side"], f["t_entry"], f["t_exit"]) == []


# --- 2. against the bot's own exit methods ------------------------------------------------------

def _same(a, b):
    return (a.kind == b.kind and a.gross_r == pytest.approx(b.gross_r, abs=1e-6)
            and a.exit_ts == pytest.approx(b.exit_ts, abs=1e-3))


def test_resolver_equals_the_live_exit_methods_on_the_live_fills(fills):
    """The fast resolver mirrors the rules; LiveCodeReference RUNS them (runtime.FuturesRuntime's
    early stop, trail + breakeven, clock). They must agree exactly, fill for fill."""
    for f in fills[::3]:
        tr = _trade(f)
        pol = ExitPolicy.live_at(f["sleeve"], f["side"], f["t_entry"])
        a = resolve_exit(tr, f["fair"], f["last"], pol)
        b = LiveCodeReference(pol).resolve(tr, f["fair"], f["last"])
        assert _same(a, b), (f["symbol"], a, b)


def _synthetic(rng):
    side = rng.choice(["LONG", "SHORT"])
    s = 1.0 if side == "LONG" else -1.0
    entry = 100.0
    sl_pct = rng.choice([0.4, 1.0, 3.0, 8.0])
    one_r = entry * sl_pct / 100.0
    tp_r = rng.choice([1.0, 3.0, 5.0, None])
    t0 = 1_790_000_040.0                              # a bar boundary
    sigma = rng.choice([0.05, 0.15, 0.4])
    drift = rng.uniform(-0.03, 0.08)                 # up-bias: reach the 3R ratchet often enough
    fair, last = [], []
    p = entry
    for k in range(rng.randint(30, 140)):
        t = t0 + 60 * k
        gap = rng.gauss(0, 0.8) * one_r if rng.random() < 0.03 else 0.0
        o = p + gap
        c = o + (rng.gauss(0, sigma) + drift * s) * one_r
        h = max(o, c) + abs(rng.gauss(0, sigma * 0.7)) * one_r
        l = min(o, c) - abs(rng.gauss(0, sigma * 0.7)) * one_r
        fair.append((t, o, h, l, c))
        wick = abs(rng.gauss(0, 0.3)) * one_r if rng.random() < 0.1 else 0.0
        last.append((t, o, h + wick, l - wick, c))
        p = c
    trade = Trade(side, entry, entry - s * one_r, (entry + s * tp_r * one_r) if tp_r else None, t0,
                  rng.choice(["WILDCARD", "TREND"]), "SYN_USDT")
    pol = ExitPolicy(sleeve=trade.sleeve, convex=rng.random() < 0.9, trail=rng.random() < 0.85,
                     arm_r=rng.choice([1.0, 0.5, 2.0]), retain=rng.choice([0.3, 0.5, 0.0]),
                     ratchet_r=rng.choice([3.0, 0.0, 1.5]), ratchet_retain=0.75,
                     early_stop_r=rng.choice([0.0, 0.5, 0.3]), early_stop_minutes=rng.choice([30.0, 10.0, 5.0]),
                     breakeven_arm_r=rng.choice([0.0, 0.9, 0.5]), time_stop_hours=rng.choice([24.0, 1.0, 0.5]),
                     stop_feed=rng.choice(["fair", "last"]), tp_feed=rng.choice(["last", "fair"]))
    return trade, fair, last, pol


def test_resolver_equals_the_live_exit_methods_on_randomised_paths():
    """Every rule and branch - early stop, trail with ratchet, cost floor that refuses to trail,
    legacy giveback, breakeven arm and wrong-side guard, clock, gaps, either feed on either order,
    trail or convex switched off - scored by the fast resolver and by the live methods. If a live
    exit rule changes and this module does not, this fails."""
    rng = random.Random(20260923)
    kinds = set()
    for _ in range(300):
        trade, fair, last, pol = _synthetic(rng)
        a = resolve_exit(trade, fair, last, pol)
        b = LiveCodeReference(pol).resolve(trade, fair, last)
        assert a.kind == b.kind, (pol, a, b)
        if a.gross_r is not None:
            assert _same(a, b), (pol, a, b)
        kinds.add(a.kind)
    assert kinds >= {"stop", "tp", "trail", "early", "timeout", "breakeven", "open"}


# --- 3. the live parameters -------------------------------------------------------------------

_EXIT_METHODS = ("_convex_early_stop_exit", "_convex_runner_trail_exit", "_maybe_breakeven_stop",
                 "_convex_time_stop_exit", "_trail_retain_for", "_is_wildcard_convex",
                 # EXP/T moved the arm reads here and added the TREND switch
                 "_trail_enabled_for", "_trail_arm_r_for", "_breakeven_arm_r_for")


def _name(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        return _name(node.left) + _name(node.right)
    if isinstance(node, ast.Name):
        return "{" + node.id + "}"
    raise AssertionError(ast.dump(node))


@pytest.fixture(scope="module")
def runtime_ast():
    return ast.parse((REPO / "futuresbot" / "runtime.py").read_text(encoding="utf-8"))


def _live_reads(tree):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "FuturesRuntime")
    floats, flags = {}, {}
    for fn in cls.body:
        if not (isinstance(fn, ast.FunctionDef) and fn.name in _EXIT_METHODS):
            continue
        # `shared = self._env_float("X", 1.0)` then `self._env_float("Y", shared)`: Y falls back to X.
        local = {st.targets[0].id: _name(st.value.args[0]) for st in ast.walk(fn)
                 if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
                 and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute)
                 and st.value.func.attr == "_env_float"}
        for call in ast.walk(fn):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                continue
            if call.func.attr == "_env_float":
                d = call.args[1]
                if isinstance(d, ast.Constant):
                    floats[_name(call.args[0])] = d.value
                elif isinstance(d, ast.Name):
                    floats[_name(call.args[0])] = local[d.id]
                else:
                    floats[_name(call.args[0])] = _name(d.args[0])
            elif call.func.attr == "_flag":
                kw = {k.arg: k.value.value for k in call.keywords}
                flags[_name(call.args[0])] = kw.get("default", False)
    return floats, flags


def test_live_exit_parameters_and_defaults_match_the_resolver(runtime_ast):
    """The resolver's parameter table IS runtime.py's. A new variable read by any live exit
    method, a renamed one, or a changed default fails here until exits.py is updated."""
    floats, flags = _live_reads(runtime_ast)
    expected = dict(X.LIVE_ENV_DEFAULTS)
    expected["FUTURES_{kind}_EARLY_STOP_R"] = "FUTURES_CONVEX_EARLY_STOP_R"
    expected["FUTURES_{kind}_EARLY_STOP_MINUTES"] = "FUTURES_CONVEX_EARLY_STOP_MINUTES"
    expected.update(X.TREND_FALLBACKS)
    assert floats == expected
    assert flags == X.LIVE_FLAG_DEFAULTS


def test_the_live_poll_order_is_early_then_trail_then_clock(runtime_ast):
    """_hourly_exit's first three exits, in order, behind only the retire-everything switch
    (FUTURES_STRATEGIES_RETIRED, off live). The resolver and the reference assume this order."""
    fn = next(n for n in ast.walk(runtime_ast) if isinstance(n, ast.FunctionDef) and n.name == "_hourly_exit")
    calls = [n.test.func.attr for n in fn.body
             if isinstance(n, ast.If) and isinstance(n.test, ast.Call) and isinstance(n.test.func, ast.Attribute)]
    assert calls[:4] == ["_strategies_retired", "_convex_early_stop_exit", "_convex_runner_trail_exit",
                         "_convex_time_stop_exit"]


def test_order_feeds_come_from_the_live_order_builder():
    """Stop on FAIR (lossTrend=2), target on LAST (profitTrend=1), both sides, since baa28b2."""
    assert X.live_order_feeds(1) == ("fair", "last")
    assert X.live_order_feeds(3) == ("fair", "last")
    pol = ExitPolicy.from_env("WILDCARD", {})
    assert (pol.stop_feed, pol.tp_feed) == ("fair", "last")


def test_from_env_reads_like_the_live_runtime(monkeypatch):
    """Mapping mode and os.environ mode (the live _env_float/_flag) must build the same policy."""
    env = {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1", "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.50",
           "FUTURES_WILDCARD_EARLY_STOP_R": "0.5", "FUTURES_CONVEX_BREAKEVEN_ARM_R": "0.90",
           "FUTURES_CONVEX_TIME_STOP_HOURS": "-3", "FUTURES_CONVEX_TRAIL_ARM_R": " ",
           "FUTURES_CONVEX_COST_PCT": "junk"}
    for k in list(X.LIVE_ENV_DEFAULTS) + list(X.LIVE_FLAG_DEFAULTS) + ["FUTURES_WILDCARD_EARLY_STOP_R",
                                                                      "FUTURES_WILDCARD_EARLY_STOP_MINUTES"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    a = ExitPolicy.from_env("WILDCARD", env)
    b = ExitPolicy.from_env("WILDCARD")
    assert a == b
    assert (a.convex, a.retain, a.early_stop_r, a.breakeven_arm_r) == (True, 0.5, 0.5, 0.9)
    assert a.time_stop_hours == 0.0 and a.arm_r == 1.0 and a.cost_pct == 0.19
    assert ExitPolicy.from_env("WILDCARD", a.env()) == a


def test_the_deployed_timeline():
    """What ran when: retain 0.50 from 08-29, WILDCARD-only early stop from 09-08, shorts' stop
    moved LAST -> FAIR on 09-16, breakeven at 0.90R from 09-20. Before 08-29: refused."""
    with pytest.raises(ValueError):
        ExitPolicy.live_at("WILDCARD", "LONG", _utc(2026, 8, 20))
    p = ExitPolicy.live_at("WILDCARD", "LONG", _utc(2026, 9, 1))
    assert (p.retain, p.early_stop_r, p.breakeven_arm_r, p.convex) == (0.5, 0.0, 0.0, True)
    assert ExitPolicy.live_at("WILDCARD", "LONG", _utc(2026, 9, 9)).early_stop_r == 0.5
    assert ExitPolicy.live_at("TREND", "LONG", _utc(2026, 9, 9)).early_stop_r == 0.0
    short = ExitPolicy.live_at("WILDCARD", "SHORT", _utc(2026, 9, 10))
    assert (short.stop_feed, short.tp_feed) == ("last", "fair")
    short = ExitPolicy.live_at("WILDCARD", "SHORT", _utc(2026, 9, 17))
    assert (short.stop_feed, short.tp_feed) == ("fair", "last")
    assert ExitPolicy.live_at("TREND", "LONG", _utc(2026, 9, 21)).breakeven_arm_r == 0.9
    # A TREND long is untouched by the WILDCARD early stop and the short feed fix.
    assert ExitPolicy.live_switches_between("TREND", "LONG", _utc(2026, 9, 8), _utc(2026, 9, 17)) == []
    assert ExitPolicy.live_switches_between("WILDCARD", "SHORT", _utc(2026, 9, 8), _utc(2026, 9, 17)) == [
        _utc(2026, 9, 8, 18, 20), _utc(2026, 9, 16, 6, 15)]


def test_the_timeline_ends_at_the_live_exit_env():
    """The container's exit env on 2026-09-23 (archive/2026-09-23/container/exit_env.json, the
    exit keys only). If this starts failing after a dial change, add the LIVE_TIMELINE row."""
    live = {"FUTURES_CONVEX_BREAKEVEN_ARM_R": "0.90", "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.50",
            "FUTURES_TREND_EARLY_STOP_R": "0.0", "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1",
            "FUTURES_WILDCARD_EARLY_STOP_MINUTES": "30", "FUTURES_WILDCARD_EARLY_STOP_R": "0.5"}
    assert X.timeline_drift(live) == []
    assert X.timeline_drift({**live, "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.30"}) == [
        "WILDCARD.retain: timeline 0.5 != live 0.3", "TREND.retain: timeline 0.5 != live 0.3"]


def test_the_default_policy_is_the_live_stack_not_the_code_defaults():
    """Code defaults have the convex exits OFF; a study that omits the policy must not silently
    replay a bot with no trail, no early stop and no clock."""
    tr = Trade("LONG", 100.0, 95.0, None, 1_790_000_040.0)
    fair = [(1_790_000_040.0 + 60 * i, 100.0, 100.5, 99.5, 100.0) for i in range(24 * 60 + 5)]
    assert resolve_exit(tr, fair, fair).kind == "timeout"


# --- 4. the feed convention on a hand-built tape -----------------------------------------------

def _tape(rows, t0=1_790_000_040.0):
    return [(t0 + 60 * i, *r) for i, r in enumerate(rows)]


def test_a_last_price_wick_the_fair_price_never_reached_does_not_stop_the_trade():
    """MARSCOIN 2026-09-08: stopped for -$11.64 by a last-price spike fair never reached. The
    live stop now rests on FAIR; a replay reading LAST would book that loss on every such wick."""
    pol = ExitPolicy.from_env("WILDCARD", {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1"})
    tr = Trade("LONG", 100.0, 95.0, 125.0, 1_790_000_040.0)
    fair = _tape([(100, 101, 97, 100)] * 5)
    last = _tape([(100, 101, 97, 100), (100, 101, 94, 100), (100, 101, 97, 100), (100, 101, 97, 100),
                  (100, 101, 97, 100)])
    assert resolve_exit(tr, fair, last, pol).kind == "open"
    wick_policy = ExitPolicy(**{**pol.__dict__, "stop_feed": "last"})
    assert resolve_exit(tr, fair, last, wick_policy).kind == "stop"


def test_the_target_triggers_on_last_price():
    """profitTrend=1: a favourable LAST print fills the target even if fair stops short of it."""
    pol = ExitPolicy.from_env("WILDCARD", {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1",
                                           "FUTURES_CONVEX_RUNNER_TRAIL": "0"})
    tr = Trade("LONG", 100.0, 95.0, 110.0, 1_790_000_040.0)
    fair = _tape([(100, 109, 99, 108)])
    last = _tape([(100, 110.5, 99, 108)])
    res = resolve_exit(tr, fair, last, pol)
    assert (res.kind, res.gross_r) == ("tp", pytest.approx(2.0))


def test_a_trail_armed_and_breached_inside_one_bar_exits_at_the_floor():
    """Peak then fade to the close in the same minute: the floor was crossed after the peak, so
    live exits AT the floor in that minute - not a bar later at a worse open."""
    pol = ExitPolicy.from_env("WILDCARD", {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1",
                                           "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.5"})
    tr = Trade("LONG", 100.0, 90.0, None, 1_790_000_040.0)
    res = resolve_exit(tr, _tape([(100, 120, 99, 105)]), _tape([(100, 120, 99, 105)]), pol)
    assert (res.kind, res.gross_r) == ("trail", pytest.approx(1.0))
    assert res.exit_ts < 1_790_000_040.0 + 60


def test_a_gap_through_the_stop_fills_at_the_open():
    pol = ExitPolicy.from_env("WILDCARD", {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1"})
    tr = Trade("SHORT", 100.0, 105.0, 75.0, 1_790_000_040.0)
    fair = _tape([(100, 101, 99, 100), (107, 108, 106, 107)])
    res = resolve_exit(tr, fair, fair, pol)
    assert (res.kind, res.gross_r) == ("stop", pytest.approx(-1.4))


def test_bars_that_open_before_the_fill_are_not_walked():
    """The fill minute's range includes pre-fill prices; a stop 'hit' there never happened."""
    pol = ExitPolicy.from_env("WILDCARD", {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1"})
    tr = Trade("LONG", 100.0, 95.0, None, 1_790_000_040.0 + 30)
    fair = _tape([(100, 101, 90, 100), (100, 101, 99, 100)])
    assert resolve_exit(tr, fair, fair, pol).kind == "open"


def test_a_policy_that_reads_last_price_refuses_to_run_without_it():
    with pytest.raises(ValueError):
        resolve_exit(Trade("LONG", 100.0, 95.0, 110.0, 0.0), _tape([(100, 101, 99, 100)]), None,
                     ExitPolicy(convex=True))
