"""Single-send orders (ASSESS2 M10, part A, owner decision 2026-10-01).

private_post used to re-send order/create up to 3 times on ANY error, timeouts
included, with no client order id: a POST that reached MEXC but timed out could open
a SECOND position. Now every order/create carries a unique externalOid and is POSTed
ONCE. When the POST gets no answer, the order is looked up by its externalOid:
found -> used as if the POST had answered; not found, found canceled/invalid with
nothing filled, or the lookup failing -> the ORIGINAL error is raised (the caller's
existing failure path runs) and the owner is alerted. Never a second POST.

MEXC's real "not found" reply, probed on the live account 2026-10-01
(wc/HARDEN/A/probe_lookup_out.json): HTTP 200, {"success": true, "code": 0}, no data.

These tests drive the REAL MexcFuturesClient over a fake transport, so the retry
loop, the payload, the signature and the lookup are the production code.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
import requests

import futuresbot.marketdata as md
from futuresbot import runtime as runtime_module
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import (ORDER_CREATE_PATH, MexcApiError, MexcFuturesClient,
                                   new_external_oid)
from futuresbot.runtime import CLOSE_FAILED_TS_KEY
from tests.test_assessment_fixes import _pos
from tests.test_assessment_fixes import _runtime as _exit_runtime

LOOKUP = "/api/v1/private/order/external/"
STOP_PLACE = "/api/v1/private/stoporder/place"


class _Resp:
    def __init__(self, payload=None, status: int = 200, bad_json: bool = False) -> None:
        self.payload, self.status_code, self.bad_json = payload, status, bad_json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")

    def json(self):
        if self.bad_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self.payload


class _Mexc:
    """A fake MEXC transport.

    create: what order/create does with the POST -
      "answer"            lands and answers {"orderId": ...}
      "reject"            refused: success false, code 2005
      "gone"              refused: the position is already closed (race)
      "<how>_landed"      lands, then the caller gets <how> instead of an answer
      "<how>_lost"        never lands, and the caller gets <how>
      "late"              read timeout; lands only after the FIRST lookup
      "busy_landed"       lands, then MEXC answers 501 "System busy"
    where <how> is timeout | conn | http502 | badjson.
    lookup: "ok" | "fail" (the lookup GET itself cannot be reached).
    ends: (state, dealVol) - a landed order instead ENDS in that state with that fill
      (MEXC: 4 canceled, 5 invalid); the position is left untouched.
    """

    def __init__(self, *, create: str = "answer", lookup: str = "ok",
                 stop_place_ok: bool = True, positions=None, ends=None) -> None:
        self.create, self.lookup, self.stop_place_ok = create, lookup, stop_place_ok
        self.ends = ends
        self.positions = [] if positions is None else positions
        self.calls: list[tuple] = []
        self.orders: dict[str, dict] = {}
        self.pending: tuple[str, dict] | None = None
        self.next_id = 9000

    # --- views ---
    def posts(self, path: str = ORDER_CREATE_PATH) -> list[dict]:
        return [c[2] for c in self.calls if c[0] == "POST" and c[1] == path]

    def lookups(self) -> list[str]:
        return [c[1] for c in self.calls if c[0] == "GET" and c[1].startswith(LOOKUP)]

    # --- transport ---
    def _land(self, body: dict) -> dict:
        self.next_id += 1
        if self.ends is not None:                      # accepted, then canceled/invalid
            state, dealt = self.ends
            row = {"orderId": str(self.next_id), "externalOid": body["externalOid"],
                   "symbol": body["symbol"], "side": body["side"], "vol": body["vol"],
                   "dealVol": dealt, "dealAvgPrice": 1.0 if dealt else 0, "state": state,
                   "errorCode": 0 if dealt else 4}
            self.orders[body["externalOid"]] = row
            return row
        row = {"orderId": str(self.next_id), "externalOid": body["externalOid"],
               "symbol": body["symbol"], "side": body["side"], "vol": body["vol"],
               "dealVol": body["vol"], "dealAvgPrice": 1.0, "state": 3}
        self.orders[body["externalOid"]] = row
        if body["side"] in (1, 3) and not body.get("reduceOnly"):
            self.positions.append({"symbol": body["symbol"], "positionId": "5550",
                                   "positionType": 1 if body["side"] == 1 else 2,
                                   "holdVol": body["vol"], "holdAvgPrice": 1.0,
                                   "leverage": body.get("leverage") or 5})
        else:
            self.positions.clear()
        return row

    def post(self, url, data=None, headers=None, timeout=None):
        path = urlparse(url).path
        body = json.loads(data) if data else None
        self.calls.append(("POST", path, body, data, headers, timeout))
        if path == ORDER_CREATE_PATH:
            return self._order_create(body)
        if path == STOP_PLACE and not self.stop_place_ok:
            return _Resp({"success": False, "code": 2009, "message": "position not exist"})
        return _Resp({"success": True, "code": 0})

    def _order_create(self, body: dict) -> _Resp:
        mode = self.create
        if mode == "answer":
            row = self._land(body)
            return _Resp({"success": True, "code": 0, "data": {"orderId": row["orderId"], "ts": 1}})
        if mode == "reject":
            return _Resp({"success": False, "code": 2005, "message": "Balance insufficient"})
        if mode == "gone":
            return _Resp({"success": False, "code": 2009, "message": "position not exist"})
        if mode == "busy_landed":                  # MEXC's own error, but the order was taken
            self._land(body)
            return _Resp({"success": False, "code": 501, "message": "System busy"})
        if mode == "late":
            self.pending = (body["externalOid"], body)
            raise requests.ReadTimeout("read timed out (15s)")
        how, outcome = mode.split("_")
        if outcome == "landed":
            self._land(body)
        if how == "timeout":
            raise requests.ReadTimeout("read timed out (15s)")
        if how == "conn":
            raise requests.ConnectionError("connection reset by peer")
        if how == "http502":
            return _Resp({}, status=502)
        if how == "badjson":
            return _Resp(bad_json=True)
        raise AssertionError(mode)

    def get(self, url, params=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append(("GET", path, params, None, headers, timeout))
        if path.startswith(LOOKUP):
            if self.lookup == "fail":
                raise requests.ConnectionError("lookup unreachable")
            if self.pending is not None and len(self.lookups()) > 1:
                self._land(self.pending[1])            # landed while we were looking
                self.pending = None
            row = self.orders.get(path.rsplit("/", 1)[1])
            return _Resp({"success": True, "code": 0, "data": row} if row
                         else {"success": True, "code": 0})        # MEXC's probed not-found
        if "/order/get/" in path:
            return _Resp({"success": True, "code": 0,
                          "data": {"orderId": path.rsplit("/", 1)[1], "dealAvgPrice": 95.0}})
        if path.endswith("/position/open_positions"):
            return _Resp({"success": True, "code": 0, "data": list(self.positions)})
        return _Resp({"success": True, "code": 0, "data": []})


@pytest.fixture()
def sleeps(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(md.time, "sleep", lambda s: slept.append(s))
    return slept


def _client(fake: _Mexc, alerts: list | None = None) -> MexcFuturesClient:
    client = MexcFuturesClient(FuturesConfig.from_env())
    client.session = fake
    if alerts is not None:
        client.order_alert_hook = lambda *a: alerts.append(a)
    return client


def _open(client: MexcFuturesClient, **kw) -> dict:
    args = dict(symbol="BTC_USDT", side=1, vol=3, leverage=5,
                take_profit_price=105.0, stop_loss_price=98.0)
    args.update(kw)
    return client.place_order(**args)


# --- the externalOid itself --------------------------------------------------------------

def test_external_oid_is_unique_and_within_mexc_rules():
    oids = {new_external_oid() for _ in range(5000)}
    assert len(oids) == 5000
    for oid in oids:
        assert len(oid) <= 32                   # MEXC 2030: "Max. 32"
        assert re.fullmatch(r"fb[0-9a-f]+", oid)


def test_every_attempt_sends_its_own_external_oid(sleeps):
    fake = _Mexc()
    client = _client(fake)
    _open(client)
    _open(client)
    client.close_position(symbol="BTC_USDT", side=4, vol=3, position_mode=2, position_id="5550")
    oids = [body["externalOid"] for body in fake.posts()]
    assert len(oids) == 3 and len(set(oids)) == 3


# --- the success path: today's request plus one field ------------------------------------

def test_open_success_is_todays_request_plus_external_oid(sleeps):
    fake = _Mexc()
    client = _client(fake)
    order = _open(client)
    (call,) = fake.calls                                     # one POST, no lookup
    _, path, body, data, headers, timeout = call
    oid = body["externalOid"]
    today = {"symbol": "BTC_USDT", "vol": 3, "leverage": 5, "side": 1, "type": 5,
             "openType": 1, "positionMode": 2, "takeProfitPrice": 105.0,
             "stopLossPrice": 98.0, "profitTrend": 1, "lossTrend": 2}
    assert path == ORDER_CREATE_PATH and timeout == 15
    assert data == json.dumps({**today, "externalOid": oid}, separators=(",", ":"))
    signed = f"{client.config.api_key}{headers['Request-Time']}{data}"
    assert headers["Signature"] == hmac.new(client.config.api_secret.encode(), signed.encode(),
                                            hashlib.sha256).hexdigest()
    assert order == {"orderId": "9001", "ts": 1}


def test_close_success_is_todays_request_plus_external_oid(sleeps):
    fake = _Mexc()
    client = _client(fake)
    client.close_position(symbol="BNB_USDT", side=4, vol=3, leverage=5, position_mode=2,
                          position_id="12345")
    (call,) = fake.calls
    body, data = call[2], call[3]
    today = {"symbol": "BNB_USDT", "vol": 3, "side": 4, "type": 5, "openType": 1,
             "positionId": 12345, "positionMode": 2, "reduceOnly": True}
    assert data == json.dumps({**today, "externalOid": body["externalOid"]}, separators=(",", ":"))


# --- no answer: look it up, never re-POST -------------------------------------------------

@pytest.mark.parametrize("how", ["timeout", "conn", "http502", "badjson"])
def test_an_order_that_landed_is_found_and_not_sent_again(sleeps, how):
    fake = _Mexc(create=f"{how}_landed")
    alerts: list = []
    client = _client(fake, alerts)
    order = _open(client)
    assert len(fake.posts()) == 1
    assert len(fake.lookups()) == 1
    assert fake.lookups()[0] == f"{LOOKUP}BTC_USDT/{fake.posts()[0]['externalOid']}"
    assert order["orderId"] == "9001"
    assert alerts == []


def test_an_order_still_landing_is_found_by_a_later_lookup(sleeps):
    fake = _Mexc(create="late")
    client = _client(fake)
    order = _open(client)
    assert len(fake.posts()) == 1 and len(fake.lookups()) == 2
    assert order["orderId"] == "9001"
    assert sleeps == [1.0]


def test_an_order_that_did_not_land_fails_cleanly_with_no_second_post(sleeps):
    fake = _Mexc(create="timeout_lost")
    alerts: list = []
    client = _client(fake, alerts)
    with pytest.raises(requests.ReadTimeout):                # the ORIGINAL error
        _open(client)
    assert len(fake.posts()) == 1
    assert len(fake.lookups()) == md._ORDER_LOOKUP_ATTEMPTS == 3
    assert sleeps == [1.0, 2.0]                              # bounded: ~3 s
    (alert,) = alerts
    assert alert[:3] == ("not_found", "BTC_USDT", "open")
    assert alert[3] == fake.posts()[0]["externalOid"]
    assert fake.positions == []


def test_a_failing_lookup_is_bounded_then_fails_and_alerts(sleeps):
    fake = _Mexc(create="timeout_landed", lookup="fail")
    alerts: list = []
    client = _client(fake, alerts)
    with pytest.raises(requests.ReadTimeout):
        _open(client)
    assert len(fake.posts()) == 1                            # never a blind re-POST
    assert len(fake.lookups()) == 3
    (alert,) = alerts
    assert alert[0] == "lookup_failed" and "lookup ConnectionError" in alert[4]


def test_an_exchange_refusal_is_neither_looked_up_nor_resent(sleeps):
    """MEXC answered "no": nothing landed. Raised at once (it used to be POSTed 3 times),
    with its payload intact for the balance guard."""
    fake = _Mexc(create="reject")
    alerts: list = []
    client = _client(fake, alerts)
    with pytest.raises(MexcApiError) as err:
        _open(client)
    assert err.value.payload["code"] == 2005
    assert len(fake.posts()) == 1 and fake.lookups() == [] and alerts == [] and sleeps == []


def test_a_mexc_server_error_is_looked_up_like_a_timeout(sleeps):
    """501 "system busy" (and 500, 9999) is an answer that does not say whether the order
    was taken: looked up, never re-sent."""
    fake = _Mexc(create="busy_landed")
    client = _client(fake)
    assert _open(client)["orderId"] == "9001"
    assert len(fake.posts()) == 1 and len(fake.lookups()) == 1


def test_order_create_is_single_send_even_when_a_caller_asks_for_retries(sleeps):
    fake = _Mexc(create="timeout_landed")
    client = _client(fake)
    with pytest.raises(requests.ReadTimeout):
        client.private_post(ORDER_CREATE_PATH, {"symbol": "BTC_USDT", "vol": 1, "side": 1,
                                                "externalOid": "fbx"}, attempts=3)
    assert len(fake.posts()) == 1


def test_other_private_posts_keep_their_retries(sleeps):
    fake = _Mexc(stop_place_ok=False)
    client = _client(fake)
    with pytest.raises(MexcApiError):
        client.place_position_tpsl(position_id="1", vol=1, take_profit_price=None,
                                   stop_loss_price=90.0, side="LONG")
    assert len(fake.posts(STOP_PLACE)) == 3                  # unchanged (see report)


def test_the_lookup_reads_mexc_reply_shapes(sleeps):
    fake = _Mexc()
    client = _client(fake)
    assert client.get_order_by_external_oid("BTC_USDT", "fbnone") is None   # probed shape
    fake.orders["fbmine"] = {"orderId": "1", "externalOid": "fbmine"}
    assert client.get_order_by_external_oid("BTC_USDT", "fbmine")["orderId"] == "1"
    fake.orders["fbother"] = {"orderId": "2", "externalOid": "someone-else"}
    assert client.get_order_by_external_oid("BTC_USDT", "fbother") is None

    def raise_code(code):
        def get(path, params=None, **kw):
            raise MexcApiError("x", path=path, payload={"success": False, "code": code})
        return get
    client.private_get = raise_code(2040)                    # documented "order not exist"
    assert client.get_order_by_external_oid("BTC_USDT", "fbx") is None
    client.private_get = raise_code(510)                     # rate limit: not an answer
    with pytest.raises(MexcApiError):
        client.get_order_by_external_oid("BTC_USDT", "fbx")


# --- the live entry path ------------------------------------------------------------------

def _live_entry_runtime(tmp_path, monkeypatch, fake):
    from tests.test_entry_envelope import MAJ, _clean_env
    from tests.test_entry_envelope import _runtime as _entry_runtime
    _clean_env(monkeypatch, "0", FUTURES_PAPER_TRADE="0")
    rt = _entry_runtime(tmp_path, MAJ)
    assert not rt.config.paper_trade
    real = MexcFuturesClient(rt.config)
    real.session = fake
    real.order_alert_hook = rt._on_order_unresolved
    rt.client.place_order = real.place_order
    rt.client.get_contract_detail.return_value = {"contractSize": 0.001, "minVol": 1}
    rt.client.get_order.return_value = {"dealAvgPrice": "1.0"}
    rt.client.get_open_positions.side_effect = lambda *a, **k: list(fake.positions)
    rt._entry_margin = lambda *a, **k: 20.0
    rt._convex_streak_multiplier = lambda: (1.0, 0)
    rt._entry_message = lambda position: ""
    rt._wildcard_attribution = {"A_USDT": {"range_24h": 0.5}}
    alerts: list = []
    rt._notify = lambda *a, **k: None
    rt._notify_once = lambda key, message, **kw: alerts.append((key, message))
    return rt, alerts


def test_entry_timeout_after_landing_records_the_position_once(tmp_path, monkeypatch, sleeps):
    from tests.test_entry_envelope import _sig
    fake = _Mexc(create="timeout_landed")
    rt, alerts = _live_entry_runtime(tmp_path, monkeypatch, fake)
    assert rt._open_wildcard_position(_sig(), 1000.0, veto_checked=True) is True
    assert len(fake.posts()) == 1 and len(fake.positions) == 1
    pos = rt.open_positions["A_USDT"]
    assert pos.position_id == "5550" and pos.order_id == "9001"
    assert pos.contracts == fake.posts()[0]["vol"]
    assert alerts == []


def test_entry_timeout_not_landed_skips_cleanly_and_alerts(tmp_path, monkeypatch, sleeps):
    from tests.test_entry_envelope import _sig
    fake = _Mexc(create="timeout_lost")
    rt, alerts = _live_entry_runtime(tmp_path, monkeypatch, fake)
    with pytest.raises(requests.ReadTimeout):    # the scan's own except logs and moves on
        rt._open_wildcard_position(_sig(), 1000.0, veto_checked=True)
    assert len(fake.posts()) == 1 and fake.positions == []
    assert "A_USDT" not in rt.open_positions
    (key, message), = alerts
    assert key == "futures_order_unresolved_not_found_A_USDT"
    assert "NOT re-sent" in message and "/reconcile" in message


# --- the live close path: C04 backoff and the race, unchanged ----------------------------

@pytest.fixture()
def clock(monkeypatch):
    class _Clock:
        t = 1_800_000_000.0

        def __call__(self):
            return self.t
    c = _Clock()
    monkeypatch.setattr(runtime_module.time, "time", c)
    return c


def _live_close_runtime(tmp_path, fake):
    rt = _exit_runtime(tmp_path, _client(fake))
    rt.client.order_alert_hook = rt._on_order_unresolved
    alerts: list = []
    rt._notify_once = lambda key, message, **kw: alerts.append((key, message))
    position = _pos()
    position.opened_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    rt.open_positions[position.symbol] = position
    fake.positions.append({"symbol": "ZEC_USDT", "positionId": "777", "positionType": 1,
                           "holdVol": 5})
    return rt, position, alerts


def test_close_timeout_after_landing_books_the_close_once(tmp_path, sleeps, clock):
    fake = _Mexc(create="timeout_landed")
    rt, position, alerts = _live_close_runtime(tmp_path, fake)
    assert rt._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS") is True
    assert len(fake.posts()) == 1
    assert fake.posts()[0]["reduceOnly"] is True                # one-way mode: a reduce-only sell
    assert position.symbol not in rt.open_positions
    assert rt.trade_history[-1]["exit_reason"] == "STOP_LOSS"
    assert fake.posts(STOP_PLACE) == [] and alerts == []


def test_close_not_landed_takes_the_c04_path_unchanged(tmp_path, sleeps, clock):
    fake = _Mexc(create="timeout_lost")
    rt, position, alerts = _live_close_runtime(tmp_path, fake)
    start = clock.t
    with pytest.raises(requests.ReadTimeout):
        rt._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS")
    assert len(fake.posts()) == 1
    assert len(fake.posts(STOP_PLACE)) == 1                  # the stop was put back
    assert position.metadata[CLOSE_FAILED_TS_KEY] == start   # C04 stamp
    keys = [k for k, _ in alerts]
    assert any(k.startswith("futures_close_failed_stop_restored_") for k in keys)
    unanswered = dict(alerts)["futures_order_unresolved_not_found_ZEC_USDT"]
    assert "The close order for <b>ZEC_USDT</b>" in unanswered   # one-way close: side 3 + reduceOnly
    n = len(fake.calls)
    clock.t = start + 59.0                                   # inside the backoff: untouched
    assert rt._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS") is False
    assert len(fake.calls) == n
    fake.create = "answer"
    clock.t = start + 60.0                                   # after it: one new order, closed
    assert rt._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS") is True
    assert len(fake.posts()) == 2
    assert fake.posts()[0]["externalOid"] != fake.posts()[1]["externalOid"]
    assert position.symbol not in rt.open_positions


def test_race_path_when_the_exchange_closed_it_first_is_unchanged(tmp_path, sleeps, clock):
    """The resting stop filled first: MEXC refuses the close, the restore fails, the
    position is gone -> [EXIT_RACE], no stamp, no alert. Only the number of close
    POSTs changed: 1 (it was 3, each refused)."""
    fake = _Mexc(create="gone", stop_place_ok=False)
    rt, position, alerts = _live_close_runtime(tmp_path, fake)
    fake.positions.clear()
    with pytest.raises(MexcApiError):
        rt._close_position_for_exit(position, current_price=95.0, reason="CONVEX_HARD_STOP")
    assert len(fake.posts()) == 1 and fake.lookups() == []
    assert CLOSE_FAILED_TS_KEY not in position.metadata
    assert "be_stop_bare" not in position.metadata
    assert alerts == []


# --- found, but MEXC canceled/invalidated it with nothing filled (fix round 1) ----------
# An accepted order can still end in state 4 (canceled) or 5 (invalid) - MEXC stores an
# errorCode for it. It opened or closed nothing, so it counts as NOT placed: the original
# error is raised, never a "recovered" success. A close then restores its stop and enters
# the C04 backoff; an entry is skipped. Before this fix the close was booked as done and
# the position was left on MEXC untracked, with its stop already cancelled.

_HOW = {"timeout": ("timeout_landed", requests.ReadTimeout),
        "busy": ("busy_landed", MexcApiError)}


@pytest.mark.parametrize("state", [4, 5])
@pytest.mark.parametrize("how", ["timeout", "busy"])
def test_a_found_order_that_ended_unfilled_counts_as_not_placed(sleeps, how, state):
    create, raised = _HOW[how]
    fake = _Mexc(create=create, ends=(state, 0))
    alerts: list = []
    client = _client(fake, alerts)
    with pytest.raises(raised):                              # the ORIGINAL error
        _open(client)
    assert len(fake.posts()) == 1 and len(fake.lookups()) == 1   # answered: no more lookups
    (alert,) = alerts
    assert alert[:3] == ("not_filled", "BTC_USDT", "open")
    assert f"state={state} dealVol=0 errorCode=4" in alert[4]


def test_a_found_order_with_a_partial_fill_is_still_used(sleeps):
    """Canceled after a partial fill: it DID trade, so it is used as a POST reply would be
    (partial fills on the success path are a separate follow-up)."""
    fake = _Mexc(create="timeout_landed", ends=(4, 1))
    alerts: list = []
    client = _client(fake, alerts)
    assert _open(client)["orderId"] == "9001"
    assert alerts == []


@pytest.mark.parametrize("state", [4, 5])
@pytest.mark.parametrize("how", ["timeout", "busy"])
def test_close_found_unfilled_restores_the_stop_and_backs_off(tmp_path, sleeps, clock, how, state):
    """The gate1/gate2 probe: the close's POST got no answer and MEXC holds it canceled or
    invalid with nothing filled. The position is still open on MEXC, so it stays tracked,
    its stop is put back, C04 backs off, and the owner is alerted."""
    create, raised = _HOW[how]
    fake = _Mexc(create=create, ends=(state, 0))
    rt, position, alerts = _live_close_runtime(tmp_path, fake)
    start = clock.t
    with pytest.raises(raised):
        rt._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS")
    assert len(fake.posts()) == 1 and len(fake.positions) == 1  # still open on MEXC
    assert position.symbol in rt.open_positions                  # still tracked
    assert rt.trade_history == []                                # nothing booked
    assert len(fake.posts(STOP_PLACE)) == 1                      # the stop was put back
    assert position.metadata[CLOSE_FAILED_TS_KEY] == start       # C04 stamp
    keys = [k for k, _ in alerts]
    assert "futures_order_unresolved_not_filled_ZEC_USDT" in keys
    assert any(k.startswith("futures_close_failed_stop_restored_") for k in keys)
    fake.create, fake.ends = "answer", None
    clock.t = start + 60.0                                       # after the backoff: closed
    assert rt._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS") is True
    assert len(fake.posts()) == 2 and fake.positions == []
    assert position.symbol not in rt.open_positions


def test_race_when_the_close_ended_invalid_because_the_stop_filled_first(tmp_path, sleeps, clock):
    """MEXC's own stop filled first, so our close (no answer) ended invalid. The restore
    finds no position -> [EXIT_RACE]: no stamp, no bare-stop flag, nothing booked here;
    the reconcile records the real fill, as on main after its refused re-send."""
    fake = _Mexc(create="timeout_landed", ends=(5, 0), stop_place_ok=False)
    rt, position, alerts = _live_close_runtime(tmp_path, fake)
    fake.positions.clear()
    with pytest.raises(requests.ReadTimeout):
        rt._close_position_for_exit(position, current_price=95.0, reason="CONVEX_HARD_STOP")
    assert len(fake.posts()) == 1
    assert CLOSE_FAILED_TS_KEY not in position.metadata
    assert "be_stop_bare" not in position.metadata
    assert rt.trade_history == []
    assert [k for k, _ in alerts] == ["futures_order_unresolved_not_filled_ZEC_USDT"]


def test_manual_close_found_unfilled_restores_the_stop(tmp_path, sleeps, clock):
    fake = _Mexc(create="timeout_landed", ends=(5, 0))
    rt, position, alerts = _live_close_runtime(tmp_path, fake)
    rt.client.get_fair_price = lambda symbol: 95.0
    with pytest.raises(requests.ReadTimeout):
        rt._force_close_position(symbol=position.symbol)
    assert len(fake.posts()) == 1 and len(fake.positions) == 1
    assert position.symbol in rt.open_positions and rt.trade_history == []
    assert len(fake.posts(STOP_PLACE)) == 1
    assert "futures_order_unresolved_not_filled_ZEC_USDT" in [k for k, _ in alerts]


@pytest.mark.parametrize("state", [4, 5])
def test_entry_found_unfilled_skips_cleanly_and_alerts(tmp_path, monkeypatch, sleeps, state):
    from tests.test_entry_envelope import _sig
    fake = _Mexc(create="timeout_landed", ends=(state, 0))
    rt, alerts = _live_entry_runtime(tmp_path, monkeypatch, fake)
    with pytest.raises(requests.ReadTimeout):
        rt._open_wildcard_position(_sig(), 1000.0, veto_checked=True)
    assert len(fake.posts()) == 1 and fake.positions == []
    assert "A_USDT" not in rt.open_positions
    (key, message), = alerts
    assert key == "futures_order_unresolved_not_filled_A_USDT"
    assert "canceled/invalid with nothing filled" in message
