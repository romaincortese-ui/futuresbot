from futuresbot.conditional_expectancy import rank_conditions, summarize


def _rows():
    # interleaved by time so both OOS halves contain bad & good trades
    rows = []
    for i in range(24):
        bad = (i % 2 == 0)
        pnl = -2.0 if bad else 1.0
        rows.append({"ts": 1000 + i, "pnl_usdt": pnl, "r_multiple": pnl,
                     "bad": bad, "side": "SHORT" if bad else "LONG"})
    return rows


def test_summarize():
    s = summarize([{"pnl_usdt": 1}, {"pnl_usdt": -1}, {"pnl_usdt": 2}])
    assert s["n"] == 3
    assert abs(s["mean_usd"] - 0.667) < 0.01
    assert s["winrate"] == round(200 / 3, 1)


def test_flags_harmful_condition_avoid_and_helpful_favor():
    rows = _rows()
    conds = {"bad": lambda r: r.get("bad"), "side=LONG": lambda r: r.get("side") == "LONG"}
    by = {p["condition"]: p for p in rank_conditions(rows, conds, min_n=6)}
    assert by["bad"]["verdict"] == "AVOID"
    assert by["bad"]["gap_usd"] < 0
    assert by["bad"]["oos"]["consistent"] is True
    assert by["side=LONG"]["verdict"] == "FAVOR"


def test_insufficient_when_small_group():
    rows = [{"ts": i, "pnl_usdt": 1.0, "x": i == 0} for i in range(10)]
    ranked = rank_conditions(rows, {"x": lambda r: r.get("x")}, min_n=6)
    assert ranked[0]["verdict"] == "insufficient"


def test_weak_when_not_oos_consistent():
    # harmful only in the LATE half, flat in the early half -> not OOS-consistent -> weak
    rows = []
    for i in range(12):  # early half: condition is neutral
        rows.append({"ts": 100 + i, "pnl_usdt": 1.0, "c": (i % 2 == 0)})
    for i in range(12):  # late half: condition harmful
        rows.append({"ts": 200 + i, "pnl_usdt": -3.0 if (i % 2 == 0) else 1.0, "c": (i % 2 == 0)})
    p = rank_conditions(rows, {"c": lambda r: r.get("c")}, min_n=6)[0]
    assert p["verdict"] in ("weak", "insufficient")
    assert p["oos"]["consistent"] is False
