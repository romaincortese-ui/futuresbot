"""futuresbot.replay.acceptance + tools/replay_acceptance.py - the weekly replay-vs-live scorer.

What these prevent: a scorer that passes a replay trading a different population (the completed-bar replay booked 2.1x
live's fills at precision 0.26), that misses a wick-price exit bias, that grades dollars at a replay's own fixed stake,
or that cannot be run on the files a read-only pull returns."""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

from futuresbot.replay import acceptance as acc
from futuresbot.replay.sizing import ContractSpec, Trade, live_config, simulate

FIXTURE = Path(__file__).parent / "fixtures" / "replay_live_book_0813_0923.json"
T0 = 1_788_000_000.0          # 2026-08-29, inside the fixed-dial part of LIVE_DIALS (both sleeves 2.41%)


def _live_book(n_wc=30, n_tr=24, seed=1, start_cash=1000.0, t0=T0):
    """Synthetic live history whose recorded 1R, dollars and available balance are exactly what the live chain gives,
    i.e. what the bot would have written to the feature store."""
    rng = random.Random(seed)
    trades = []
    for k, (sleeve, n) in enumerate((("WILDCARD", n_wc), ("TREND", n_tr))):
        for i in range(n):
            ts = t0 + i * 7200.0 + k * 1800.0
            trades.append(Trade(t_open=ts, t_close=ts + 3000.0, sleeve=sleeve, r=rng.choice([-1.0, -0.5, 0.4, 2.0]),
                                stop_frac=0.04 + 0.01 * (i % 3), leverage=3.0, entry_price=1.0 + i,
                                spec=ContractSpec(0.01, 1), regime_mult=1.0, symbol=f"S{k}{i}_USDT", side="LONG"))
    res = simulate(trades, start_cash, live_config())
    live = [acc.Fill(sym=t.symbol, side=t.side, sleeve=t.sleeve, t_open=t.t_open, t_close=t.t_close, r=t.r,
                     usd=f.pnl_usdt, risk_usdt=f.risk_usdt, stop_frac=t.stop_frac, leverage=t.leverage,
                     entry_price=t.entry_price, contract_size=t.spec.contract_size, available_at_entry=f.available)
            for t, f in zip(trades, res.fills)]
    return sorted(live, key=lambda f: f.t_open)


def _as_replay(live, **over):
    return [acc.Fill(**{**f.__dict__, "usd": None, "risk_usdt": None, "available_at_entry": None, **over}) for f in live]


def _grade(live, replay, **kw):
    return acc.grade(live, replay, since=T0 - 60, until=T0 + 400000.0, n_boot=200, **kw)


def _layer(rep, name, scope=None):
    return next(x for x in rep.layers if x.layer == name and (scope is None or x.scope == scope))


def test_a_replay_identical_to_live_passes_every_layer_with_zero_dollar_gap():
    """The scorer's zero point: live's own trades, live's own exits, re-priced through the engine, must PASS all layers
    and the dollar gap must be ~0 - otherwise the dollar bar would be charging the scorer's own error to the replay."""
    live = _live_book()
    # the replay IS live's own fills, so it read what live read at T0 (08-29): the forming bar on both sleeves (D3)
    rep = _grade(live, _as_replay(live), replay_conventions={"WILDCARD": acc.FORMING, "TREND": acc.FORMING})
    assert [x.verdict for x in rep.layers] == ["PASS"] * 5
    d = _layer(rep, "DOLLARS")
    assert abs(d.info["gap_usd"]) < 1e-6
    assert _layer(rep, "SIZING").info["cash_gap"] == pytest.approx(0.0, abs=1e-6)


def test_the_frozen_live_book_grades_itself_pass():
    """Same zero point on 151 REAL fills: the fixture's own trades as the replay pass sizing and dollars, i.e. the
    engine inside the scorer is the one that reproduces live."""
    d = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = [dict(zip(d["columns"], r)) for r in d["trades"]]
    live = [acc.Fill(sym=x["symbol"], side=x["side"], sleeve=x["sleeve"], t_open=x["t_open"], t_close=x["t_close"],
                     r=x["r"], usd=x["live_pnl_usdt"], risk_usdt=x["live_risk_usdt"],
                     stop_frac=x["sl_margin_pct"] / (100 * x["leverage"]), leverage=x["leverage"],
                     entry_price=x["entry_price"], contract_size=x["contract_size"], regime_mult=x["regime_mult"],
                     streak_mult=x["streak_mult"]) for x in rows]
    rep = acc.grade(live, _as_replay(live), since=d["start_ts"], until=max(x["t_close"] for x in rows) + 1,
                    start_cash=d["start_cash"], flows=d["flows"], n_boot=200)
    assert {x.layer: x.verdict for x in rep.layers if x.layer in ("SIZING", "DOLLARS")} == \
        {"SIZING": "PASS", "DOLLARS": "PASS"}
    assert abs(_layer(rep, "DOLLARS").info["gap_usd"]) < 3.0          # the reproduction's own -$1.66


def test_a_completed_bar_style_replay_with_twice_the_fills_fails_entries():
    """Today's replay books 2.1x live at precision 0.26: extra fills on symbols live never traded must fail ratio and
    precision even though every live fill is also present (recall 1.0)."""
    live = _live_book()
    extra = [acc.Fill(sym=f"X{i}_USDT", side="LONG", sleeve="WILDCARD", t_open=T0 + 600.0 + i * 3600.0,
                      t_close=T0 + 1800.0 + i * 3600.0, r=0.5, stop_frac=0.05, leverage=3.0) for i in range(40)]
    rep = _grade(live, _as_replay(live) + extra)
    e = _layer(rep, "ENTRIES", "WILDCARD")
    assert e.verdict == "FAIL"
    ok = {c.name: c.ok for c in e.checks}
    assert ok == {"fill ratio replay/live": False, "recall": True, "precision": False}


def test_match_tolerance_is_one_15m_bar():
    """Live fills land ~16 s after their scan; a replay entry 16 minutes away is a different trade and must not count
    as a match, while a 10-minute offset still does."""
    live = _live_book(n_wc=20, n_tr=0)
    near = [acc.Fill(**{**f.__dict__, "t_open": f.t_open + 600.0}) for f in _as_replay(live)]
    far = [acc.Fill(**{**f.__dict__, "t_open": f.t_open + 960.0}) for f in _as_replay(live)]
    assert acc.score_entries(live, near, "WILDCARD").info["matched"] == 20
    assert acc.score_entries(live, far, "WILDCARD").info["matched"] == 0


def test_an_exit_bias_fails_while_correlation_still_passes():
    """The wick flaw: replay exits a steady 0.05R worse than live. Correlation stays ~1, so only the bias check can
    catch it - the reason the layer has three checks, not one."""
    live = _live_book()
    rep = _grade(live, _as_replay(live), exits=[acc.Fill(**{**f.__dict__, "r": f.r - 0.05}) for f in live])
    x = _layer(rep, "EXITS")
    ok = {c.name.split()[0]: c.ok for c in x.checks}
    assert x.verdict == "FAIL" and ok["R"] is True and ok["bias"] is False
    assert x.checks[2].value == pytest.approx(0.05)


def test_wick_like_scatter_fails_the_within_share():
    """Half the fills off by 0.2R in both directions: mean bias ~0, but the share within 0.10R collapses."""
    live = _live_book()
    ex = [acc.Fill(**{**f.__dict__, "r": f.r + (0.2 if i % 4 == 0 else -0.2 if i % 4 == 1 else 0.0)})
          for i, f in enumerate(live)]
    x = acc.score_exits(live, ex)
    assert {c.name: c.ok for c in x.checks}["share within 0.10R"] is False


def test_small_samples_report_insufficient_not_a_grade():
    """At n < 20 a 0.75 share has a +/-0.19 interval: the layer must refuse to grade rather than PASS or FAIL."""
    live = _live_book(n_wc=10, n_tr=5)
    rep = _grade(live, _as_replay(live))
    assert _layer(rep, "ENTRIES", "WILDCARD").verdict == "INSUFFICIENT"
    assert _layer(rep, "EXITS").verdict == "INSUFFICIENT"


def test_a_missing_deposit_fails_sizing_and_names_where():
    """Deposits are not in the bot's files. A missing one must fail SIZING loudly (with the first fill where live's
    available departs from the engine's), not quietly shift the dollar grade."""
    live = _live_book(start_cash=1000.0)
    t_dep = live[10].t_open - 1.0
    # re-record live as if $2,000 arrived before fill 10
    trades = [Trade(t_open=f.t_open, t_close=f.t_close, sleeve=f.sleeve, r=f.r, stop_frac=f.stop_frac,
                    leverage=f.leverage, entry_price=f.entry_price, spec=ContractSpec(f.contract_size, 1),
                    symbol=f.sym, side=f.side) for f in live]
    res = simulate(trades, 1000.0, live_config(), flows=[(t_dep, 2000.0)])
    live2 = [acc.Fill(**{**f.__dict__, "usd": fr.pnl_usdt, "risk_usdt": fr.risk_usdt, "available_at_entry": fr.available})
             for f, fr in zip(live, res.fills)]
    bad = _grade(live2, _as_replay(live2))
    s = _layer(bad, "SIZING")
    assert s.verdict == "FAIL" and any("differs from the engine" in n for n in s.notes)
    good = _grade(live2, _as_replay(live2), flows=[(t_dep, 2000.0, "deposit")])
    assert _layer(good, "SIZING").verdict == "PASS"


def test_dollars_reprice_every_replay_through_the_engine_and_ignore_its_own_stake():
    """Compounding by default: a replay that declares a fixed $23.50 1R gets the same dollars as one that declares
    nothing, and the report says the declared stake was ignored."""
    live = _live_book()
    plain = _layer(_grade(live, _as_replay(live)), "DOLLARS")
    fixed = _layer(_grade(live, _as_replay(live, risk_usdt=23.5, usd=99.0)), "DOLLARS")
    assert fixed.info["replay_usd_compounded"] == pytest.approx(plain.info["replay_usd_compounded"])
    assert any("declares its own 1R" in n for n in fixed.notes)


def test_a_single_sleeve_replay_carries_live_fills_of_the_other_sleeve():
    """A WILDCARD-only replay must still see TREND's margin and P&L in the account it sizes from; without the carried
    live fills, an otherwise perfect WILDCARD replay would show a dollar gap."""
    live = _live_book()
    wc_only = [f for f in _as_replay(live) if f.sleeve == "WILDCARD"]
    rep = _grade(live, wc_only, sleeves=("WILDCARD",))
    d = _layer(rep, "DOLLARS")
    assert d.info["carried_live_fills"] == sum(1 for f in live if f.sleeve == "TREND")
    assert abs(d.info["gap_usd"]) < 1e-6 and d.verdict == "PASS"


def test_thresholds_live_in_one_place(monkeypatch):
    """Every bar is read from THRESHOLDS at call time: tightening one entry there must flip the verdict."""
    live = _live_book()
    rep = acc.score_entries(live, _as_replay(live)[:-3], "WILDCARD")
    assert rep.verdict == "PASS"
    monkeypatch.setitem(acc.THRESHOLDS["entries"], "recall_min", 0.99)
    assert acc.score_entries(live, _as_replay(live)[:-3], "WILDCARD").verdict == "FAIL"


def test_flat_start_moves_the_path_to_the_latest_flat_instant():
    """The dollar path must start where nothing is open, so its cash is live's exact cash."""
    f = lambda a, b, cash=None: acc.Fill(sym="A", side="LONG", sleeve="WILDCARD", t_open=a, t_close=b, r=0.0,
                                         available_at_entry=cash)
    fills = [f(0, 50, 100.0), f(40, 120, 90.0), f(130, 200, 111.0), f(150, 300, 95.0)]
    assert acc.flat_start(fills, 160) == (130, 111.0)      # 130: nothing open just before it
    assert acc.flat_start(fills, 125) == (130, 111.0)      # flat at 125 -> path starts at the next entry
    assert acc.flat_start(fills, 60) == (0, 100.0)


def test_feature_store_loader_takes_r_from_the_bots_own_1r_and_spec_from_trade_history():
    rows = [{"ts": 1790000000, "hold_min": 60.0, "symbol": "SAGA_USDT", "side": "LONG", "kind": "WILDCARD",
             "leverage": 2, "pnl_usdt": 10.0, "risk_usdt": 20.0, "r_multiple": 0.44, "sl_margin_pct": 15.0,
             "regime_size_mult": 0.9, "streak_multiplier": 1.0, "equity_at_entry": 945.0},
            {"ts": 1790000500, "hold_min": 5.0, "symbol": "ETH_USDT", "side": "LONG", "kind": "PMT", "leverage": 10,
             "pnl_usdt": -1.0, "r_multiple": -0.3, "sl_margin_pct": 10.0}]
    th = [{"symbol": "SAGA_USDT", "side": "LONG", "entry_time": "2026-09-21T13:13:00+00:00",
           "exit_time": "2026-09-21T14:13:30+00:00", "entry_price": 0.05, "contracts": 3000, "margin_usdt": 7.5,
           "leverage": 2}]
    fills = acc.live_fills_from_feature_store(rows, th)
    saga = next(x for x in fills if x.sym == "SAGA_USDT")
    assert saga.r == pytest.approx(0.5)                          # pnl / risk_usdt, not the rounded r_multiple
    assert saga.stop_frac == pytest.approx(0.075)
    assert saga.contract_size == pytest.approx(7.5 * 2 / (3000 * 0.05))
    assert saga.t_open == pytest.approx(1789996380.0)           # trade_history entry_time wins over hold_min
    assert saga.regime_mult == 0.9 and saga.available_at_entry == 945.0
    pmt = next(x for x in fills if x.sleeve == "PMT")
    assert pmt.r == pytest.approx(-0.3)                         # no risk_usdt -> r_multiple


def test_replay_loader_accepts_the_study_conventions():
    rows = [{"sym": "ENA_USDT", "side": "LONG", "sleeve": "WILDCARD", "ts": 1787479200, "exit_ts": 1787524200.0,
             "net": -1.03, "sl_frac": 0.066, "lev": 3, "mult": 0.8, "entry": 0.17},
            {"symbol": "XRP_USDT", "side": "LONG", "kind": "trend", "t_open": "2026-09-01T00:00:00Z",
             "t_close": 1788225000000, "R": 1.5}]
    a, b = acc.replay_fills_from_rows(rows)
    assert (a.r, a.stop_frac, a.leverage, a.regime_mult, a.entry_price) == (-1.03, 0.066, 3.0, 0.8, 0.17)
    assert b.sleeve == "TREND" and b.t_open == 1788220800.0 and b.t_close == 1788225000.0 and b.r == 1.5


def test_tool_runs_end_to_end_on_pulled_files(tmp_path, capsys):
    """The weekly path: files as the read-only pull writes them, a replay fills file, a flows file -> a report."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import replay_acceptance as tool

    live = _live_book()
    fs = tmp_path / "futures_feature_store.jsonl"
    fs.write_text("\n".join(json.dumps({
        "ts": f.t_close, "hold_min": (f.t_close - f.t_open) / 60.0, "symbol": f.sym, "side": f.side, "kind": f.sleeve,
        "leverage": f.leverage, "pnl_usdt": f.usd, "risk_usdt": f.risk_usdt, "sl_margin_pct": f.stop_frac * f.leverage * 100,
        "regime_size_mult": 1.0, "equity_at_entry": f.available_at_entry, "entry_price": f.entry_price}) for f in live)
        + "\n{torn line", encoding="utf-8")
    rp = tmp_path / "replay.json"
    rp.write_text(json.dumps({"fills": [{"sym": f.sym, "side": f.side, "sleeve": f.sleeve, "ts": f.t_open,
                                         "exit_ts": f.t_close, "net": f.r, "sl_frac": f.stop_frac, "lev": f.leverage}
                                        for f in live]}), encoding="utf-8")
    fl = tmp_path / "flows.json"
    fl.write_text("[]", encoding="utf-8")
    out = tmp_path / "rep.json"
    rc = tool.main(["--feature-store", str(fs), "--replay", str(rp), "--flows", str(fl), "--since", str(T0 - 60),
                    "--until", str(T0 + 400000), "--n-boot", "50", "--json-out", str(out)])
    text = capsys.readouterr().out
    assert rc == 0 and "== SUMMARY" in text and "ENTRIES WILDCARD: PASS" in text
    assert json.loads(out.read_text())["layers"][0]["verdict"] == "PASS"


# ---- release gate D1 / D2 (2026-09-23) -----------------------------------------------------------------------------

def test_a_biased_sleeve_fails_even_when_the_pooled_bias_passes():
    """D1: pooled, TREND's -0.007R/fill diluted WILDCARD's -0.047R/fill (~$56/mo of overstatement) into a pass."""
    live = _live_book(n_wc=30, n_tr=60)
    exits = [acc.Fill(**{**f.__dict__, "r": f.r - (0.047 if f.sleeve == "WILDCARD" else 0.0)}) for f in live]
    pooled = sum(a.r - b.r for a, b in zip(live, exits)) / len(live)
    assert abs(pooled) <= acc.THRESHOLDS["exits"]["bias_max_abs"]          # the pooled check alone would pass
    ex = acc.score_exits(live, exits, n_boot=0)
    assert ex.verdict == "FAIL"
    failed = [c.name for c in ex.checks if c.ok is False]
    assert failed == ["bias live-replay R/fill [WILDCARD]"]


def test_a_sleeve_below_the_pair_minimum_is_reported_not_graded():
    live = _live_book(n_wc=30, n_tr=5)
    ex = acc.score_exits(live, list(live), n_boot=0)
    assert ex.info["bias_not_graded"] == ["TREND"]
    assert not any("[TREND]" in c.name for c in ex.checks)


def test_dollars_are_graded_on_the_interval_not_the_point_estimate():
    """D2: a point estimate inside the bar with an interval wider than it is INSUFFICIENT, not PASS - the interval on
    one month of live runs about +-$180/mo against a $35 bar."""
    live = _live_book()
    d = _layer(_grade(live, _as_replay(live)), "DOLLARS")
    assert d.verdict == "PASS" and d.info["gap_ci95_mo"] == pytest.approx((0.0, 0.0), abs=1e-6)
    no_ci = _layer(acc.grade(live, _as_replay(live), since=T0 - 60, until=T0 + 400000.0, n_boot=0), "DOLLARS")
    assert no_ci.verdict == "INSUFFICIENT"                                  # no interval, no grade
    # a replay that halves every winner: the gap is real but the interval straddles the bar on this sample
    half = _as_replay(live)
    half = [acc.Fill(**{**f.__dict__, "r": (f.r / 2 if f.r and f.r > 0 else f.r)}) for f in half]
    wide = _layer(_grade(live, half), "DOLLARS")
    lo, hi = wide.info["gap_ci95_mo"]
    bar = acc.THRESHOLDS["dollars"]["gap_max_per_month"]
    want = "PASS" if (-bar <= lo and hi <= bar) else ("FAIL" if (hi < -bar or lo > bar) else "INSUFFICIENT")
    assert wide.verdict == want


# ---- release gate D3 (2026-09-24): live's bar convention changed over time; a replay reads one ---------------------
CUT = datetime(2026, 9, 19, 9, 43, tzinfo=timezone.utc).timestamp()      # df0192e live: TREND on completed bars


def _trend_fills(t_first, n, step=7200.0):
    return [acc.Fill(sym=f"T{i}_USDT", side="LONG", sleeve="TREND", t_open=t_first + i * step,
                     t_close=t_first + i * step + 3000.0, r=0.5) for i in range(n)]


def test_the_live_convention_schedule_at_its_boundaries():
    """Each entry is in force from its start (the LIVE_DIALS rule): the cutover instant itself is completed-bar."""
    assert acc.LIVE_CONVENTIONS["TREND"][1] == (CUT, acc.COMPLETED)
    assert acc.live_convention("TREND", CUT - 0.001) == acc.FORMING
    assert acc.live_convention("TREND", CUT) == acc.COMPLETED
    assert acc.live_convention("trend", CUT + 365 * 86400.0) == acc.COMPLETED
    assert acc.live_convention("TREND", 0.0) == acc.FORMING
    assert acc.live_convention("WILDCARD", CUT - 1) == acc.live_convention("WILDCARD", 2e9) == acc.FORMING
    assert acc.live_convention("TREND", -1.0) is None and acc.live_convention("SNIPER", CUT) is None
    assert all([a for a, _ in s] == sorted(a for a, _ in s) for s in acc.LIVE_CONVENTIONS.values())
    assert not acc.same_convention("TREND", CUT - 1, acc.COMPLETED) and acc.same_convention("TREND", CUT, acc.COMPLETED)
    assert acc.same_convention("TREND", CUT - 1, None)                 # nothing declared: compare everywhere
    assert acc.REPLAY_CONVENTIONS == {"WILDCARD": acc.FORMING, "TREND": acc.COMPLETED}


def test_a_trend_book_straddling_the_cutover_is_graded_on_post_cutover_fills_only():
    """Live TREND read the forming bar until 09-19 09:43Z: a completed-bar replay reproduces every later fill but takes
    a different population before it (here one bar late). Before D3 that FAILED by construction; now the pre-cutover
    fills are excluded and counted, and the rest is graded."""
    live = _trend_fills(CUT - 22 * 7200.0 + 60.0, 44)                    # 22 fills before the cutover, 22 after
    rp = [acc.Fill(**{**f.__dict__, "t_open": f.t_open + (960.0 if f.t_open < CUT else 0.0)}) for f in live]
    assert acc.score_entries(live, rp, "TREND").verdict == "FAIL"        # graded on every fill, as before D3
    e = acc.score_entries(live, rp, "TREND", replay_convention=acc.COMPLETED)
    assert (e.verdict, e.n, e.info["matched"]) == ("PASS", 22, 22)
    assert e.info["excluded_bar_convention"] == {"live": 22, "replay": 22}
    assert any(n.startswith("22 live / 22 replay fills excluded") and "completed from 2026-09-19 09:43Z" in n
               for n in e.notes)
    # fewer post-cutover fills than the entries minimum (the 09-01..09-22 evidence: 31 before, 8 after): NOT GRADED
    few = acc.score_entries(live[:30], rp[:30], "TREND", replay_convention=acc.COMPLETED)
    assert (few.verdict, few.n) == ("NOT GRADED", 8)
    assert few.notes[0] == "NOT GRADED: 8 live fills where live also read the completed bar, below the 20-fill minimum"


def test_grade_applies_the_schedule_by_default():
    """Through grade() with the default REPLAY_CONVENTIONS, on a sized book straddling the cutover."""
    t0 = CUT - 22 * 7200.0 - 1800.0 + 60.0                               # TREND fill i opens at CUT + (i - 22) x 2h + 60 s
    live = _live_book(n_wc=30, n_tr=44, t0=t0)
    rep = acc.grade(live, _as_replay(live), since=t0 - 60, until=t0 + 400000.0, n_boot=200)
    e = _layer(rep, "ENTRIES", "TREND")
    assert (e.verdict, e.n, e.info["excluded_bar_convention"]) == ("PASS", 22, {"live": 22, "replay": 22})
    assert _layer(rep, "ENTRIES", "WILDCARD").n == 30


def test_an_all_pre_cutover_trend_window_is_not_graded_with_the_reason_not_failed():
    live = _live_book()                                                  # 08-29: live TREND read the forming bar
    rp = [f if f.sleeve == "WILDCARD" else acc.Fill(**{**f.__dict__, "t_open": f.t_open + 960.0})
          for f in _as_replay(live)]
    rep = _grade(live, rp)
    e = _layer(rep, "ENTRIES", "TREND")
    assert (e.verdict, e.n) == ("NOT GRADED", 0)
    assert e.notes[0].startswith("NOT GRADED: 0 live fills") and "24 live / 24 replay fills excluded" in e.notes[1]
    assert "ENTRIES TREND: NOT GRADED" in acc.format_report(rep)
    # declared as reading the forming bar, the same replay is graded on every fill - and fails, as before D3
    assert _layer(_grade(live, rp, replay_conventions={"TREND": acc.FORMING}), "ENTRIES", "TREND").verdict == "FAIL"


def test_wildcard_entry_grades_are_unchanged_by_the_schedule():
    """Live WILDCARD read the forming bar throughout and so does the repaired replay: every fill stays graded, so the
    marginal PASS that rests on live's recorded refusals does not move. A replay declared to read completed bars (a
    WILDCARD live never ran) keeps its FAIL by construction, with a note, instead of turning NOT GRADED."""
    live = _live_book()
    extra = [acc.Fill(sym=f"X{i}_USDT", side="LONG", sleeve="WILDCARD", t_open=T0 + 600.0 + i * 3600.0,
                      t_close=T0 + 1800.0 + i * 3600.0, r=0.5, stop_frac=0.05, leverage=3.0) for i in range(40)]
    for rp, want in ((_as_replay(live)[:-3], "PASS"), (_as_replay(live) + extra, "FAIL")):
        base = acc.score_entries(live, rp, "WILDCARD")
        for conv in (acc.FORMING, acc.COMPLETED):
            now = acc.score_entries(live, rp, "WILDCARD", replay_convention=conv)
            assert (now.verdict, now.n, now.info, now.checks) == (want, base.n, base.info, base.checks)
            assert bool(now.notes) == (conv == acc.COMPLETED)
    assert _layer(_grade(live, _as_replay(live)), "ENTRIES", "WILDCARD").verdict == "PASS"


def test_end_to_end_exit_pairs_follow_the_schedule_but_an_exits_file_does_not():
    """End-to-end exit pairs are built on the replay's own entries, so a pre-cutover TREND pair joins two different
    entries; an exits file runs the replay's exit engine on live's own entries and needs no filter."""
    live = _live_book()
    rp = [acc.Fill(**{**f.__dict__, "r": f.r - (0.5 if f.sleeve == "TREND" else 0.0)}) for f in _as_replay(live)]
    x = _layer(_grade(live, rp), "EXITS")
    assert x.verdict == "PASS" and x.info["pairs_by_sleeve"] == {"WILDCARD": 30}
    assert any(n.startswith("24 live / 24 replay fills excluded") for n in x.notes)
    xf = _layer(_grade(live, _as_replay(live), exits=rp), "EXITS")
    assert xf.verdict == "FAIL" and xf.info["pairs_by_sleeve"] == {"WILDCARD": 30, "TREND": 24} and not xf.notes


def test_tool_takes_the_replay_conventions(tmp_path, capsys):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import replay_acceptance as tool

    live = _live_book()
    fs = tmp_path / "futures_feature_store.jsonl"
    fs.write_text("\n".join(json.dumps({
        "ts": f.t_close, "hold_min": (f.t_close - f.t_open) / 60.0, "symbol": f.sym, "side": f.side, "kind": f.sleeve,
        "leverage": f.leverage, "pnl_usdt": f.usd, "risk_usdt": f.risk_usdt, "sl_margin_pct": f.stop_frac * f.leverage * 100,
        "regime_size_mult": 1.0, "equity_at_entry": f.available_at_entry, "entry_price": f.entry_price}) for f in live),
        encoding="utf-8")
    rp = tmp_path / "replay.json"
    rp.write_text(json.dumps([{"sym": f.sym, "side": f.side, "sleeve": f.sleeve, "ts": f.t_open, "exit_ts": f.t_close,
                               "net": f.r, "sl_frac": f.stop_frac, "lev": f.leverage} for f in live]), encoding="utf-8")
    args = ["--feature-store", str(fs), "--replay", str(rp), "--since", str(T0 - 60), "--until", str(T0 + 400000),
            "--n-boot", "50"]
    assert tool.main(args) == 0
    assert "ENTRIES TREND: NOT GRADED" in capsys.readouterr().out     # default: TREND replay on completed bars
    assert tool.main(args + ["--replay-conventions", "trend=forming"]) == 0
    assert "ENTRIES TREND: PASS" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        tool.main(args + ["--replay-conventions", "TREND=closed"])
    with pytest.raises(SystemExit):                                    # an unknown sleeve key
        tool.main(args + ["--replay-conventions", "TRND=forming"])
