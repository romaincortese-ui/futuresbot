"""Phases 1 + 5 — Account identity, policy, explicit paths, collision refusal."""
import os

import pytest

from futuresbot.accounts import (
    DEFAULT_ACCOUNT_ID,
    Account,
    ChannelBinding,
    Credentials,
    HardLimits,
    Paths,
    Policy,
    assert_no_collisions,
)


def _paths(root, name="a"):
    return Paths(
        runtime_state_file=os.path.join(root, name, "rt.json"),
        status_file=os.path.join(root, name, "st.json"),
        feature_store_file=os.path.join(root, name, "fs.jsonl"),
        shadow_ledger_file=os.path.join(root, name, "sl.jsonl"),
    )


# --------------------------------------------------------------------------
# credentials never leak through repr — the cheapest breach to prevent
# --------------------------------------------------------------------------

def test_credentials_are_hidden_in_repr_and_fingerprint():
    creds = Credentials(api_key="mx0vABCDEFGH", api_secret="supersecret")
    assert "mx0vABCDEFGH" not in repr(creds)
    assert "supersecret" not in repr(creds)
    assert creds.fingerprint == "mx0v…"
    assert creds.configured


def test_unset_credentials_report_cleanly():
    creds = Credentials()
    assert not creds.configured
    assert creds.fingerprint == "unset"


# --------------------------------------------------------------------------
# the default account must be indistinguishable from today
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("FUTURES_ACCOUNT_ID", "FUTURES_ACCOUNT_LABEL", "FUTURES_ACCOUNT_ENABLED",
                "FUTURES_FEATURE_STORE_FILE", "FUTURES_SHADOW_LEDGER_FILE",
                "MEXC_API_KEY_EXPIRES_AT", "MEXC_API_KEY_CREATED_AT",
                "FUTURES_MAX_LOSS_PER_TRADE_USDT", "FUTURES_MAX_LOSS_PER_DAY_USDT",
                "FUTURES_MAX_LOSS_PER_WEEK_USDT"):
        monkeypatch.delenv(key, raising=False)


def test_default_account_id_is_main_and_flagged_as_default():
    account = Account.from_env()
    assert account.id == DEFAULT_ACCOUNT_ID
    assert account.is_default


def test_named_account_is_not_default(monkeypatch):
    monkeypatch.setenv("FUTURES_ACCOUNT_ID", "test2")
    account = Account.from_env()
    assert account.id == "test2"
    assert not account.is_default
    assert account.label == "Test2"


def test_from_env_prefers_a_supplied_config_over_raw_env(monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "from-env")

    class Cfg:
        api_key = "from-config"
        api_secret = "s"
        runtime_state_file = "/data/rt.json"
        status_file = "/data/st.json"
        telegram_token = "tok"
        telegram_chat_id = "chat"
        margin_budget_usdt = 50.0
        leverage_min = 3
        leverage_max = 7
        paper_trade = False

    account = Account.from_env(config=Cfg())
    assert account.credentials.api_key == "from-config"
    assert account.paths.runtime_state_file == "/data/rt.json"
    assert account.policy.margin_budget_usdt == 50.0
    assert account.paper is False


def test_feature_store_and_ledger_default_beside_the_state_file():
    class Cfg:
        api_key = "k"; api_secret = "s"
        runtime_state_file = os.path.join("/data", "rt.json")
        status_file = "/data/st.json"
        telegram_token = ""; telegram_chat_id = ""
        margin_budget_usdt = 75.0; leverage_min = 15; leverage_max = 25
        paper_trade = True

    paths = Account.from_env(config=Cfg()).paths
    assert paths.feature_store_file.endswith("futures_feature_store.jsonl")
    assert paths.shadow_ledger_file.endswith("futures_shadow_ledger.jsonl")
    assert os.path.dirname(paths.feature_store_file) == os.path.dirname(paths.runtime_state_file)


# --------------------------------------------------------------------------
# policy
# --------------------------------------------------------------------------

def test_policy_slots_and_sleeve_gating():
    policy = Policy(max_concurrent={"WILDCARD": 2, "SQUEEZE": 1},
                    sleeves_enabled=frozenset({"WILDCARD"}))
    assert policy.slots_for("wildcard") == 2
    assert policy.slots_for("squeeze") == 1
    assert policy.slots_for("unknown") == 0
    assert policy.allows("WILDCARD")
    assert not policy.allows("SQUEEZE")


def test_hard_limits_default_to_no_cap():
    assert HardLimits().any_set is False
    assert HardLimits(max_loss_per_day_usdt=25.0).any_set is True


def test_hard_limits_read_from_env(monkeypatch):
    monkeypatch.setenv("FUTURES_MAX_LOSS_PER_DAY_USDT", "40")
    monkeypatch.setenv("FUTURES_MAX_LOSS_PER_TRADE_USDT", "not-a-number")
    limits = Account.from_env().policy.hard_limits
    assert limits.max_loss_per_day_usdt == 40.0
    assert limits.max_loss_per_trade_usdt is None   # junk must not become a cap


# --------------------------------------------------------------------------
# apply_to — the seam a future registry plugs into
# --------------------------------------------------------------------------

def test_apply_to_projects_only_fields_the_config_has(tmp_path):
    from dataclasses import dataclass

    @dataclass
    class Cfg:
        api_key: str = ""
        api_secret: str = ""
        paper_trade: bool = True
        margin_budget_usdt: float = 0.0
        runtime_state_file: str = ""
        status_file: str = ""
        telegram_token: str = ""
        telegram_chat_id: str = ""

    account = Account(
        id="b", label="B",
        credentials=Credentials(api_key="K", api_secret="S"),
        policy=Policy(margin_budget_usdt=12.0),
        paths=_paths(str(tmp_path), "b"),
        channels=(ChannelBinding(token="t", address="c"),),
        paper=False,
    )
    out = account.apply_to(Cfg())
    assert out.api_key == "K"
    assert out.margin_budget_usdt == 12.0
    assert out.paper_trade is False
    assert out.telegram_chat_id == "c"
    assert out.runtime_state_file.endswith("rt.json")


# --------------------------------------------------------------------------
# collision refusal — the silent failure this whole module exists to prevent
# --------------------------------------------------------------------------

def _account(root, name, *, key=None, token=None):
    return Account(
        id=name, label=name,
        credentials=Credentials(api_key=key or f"key-{name}", api_secret="s"),
        paths=_paths(root, name),
        channels=(ChannelBinding(token=token or f"tok-{name}", address="chat"),),
    )


def test_distinct_accounts_pass(tmp_path):
    assert_no_collisions([_account(str(tmp_path), "a"), _account(str(tmp_path), "b")])


def test_shared_state_path_is_refused(tmp_path):
    a = _account(str(tmp_path), "a")
    b = Account(id="b", label="b", credentials=Credentials(api_key="k2", api_secret="s"),
                paths=a.paths, channels=(ChannelBinding(token="t2", address="c"),))
    with pytest.raises(ValueError, match="share path"):
        assert_no_collisions([a, b])


def test_shared_api_key_is_refused(tmp_path):
    with pytest.raises(ValueError, match="share an API key"):
        assert_no_collisions([_account(str(tmp_path), "a", key="same"),
                              _account(str(tmp_path), "b", key="same")])


def test_shared_telegram_token_is_refused(tmp_path):
    # getUpdates is single-consumer per token: two pollers means /close all
    # lands on a nondeterministic account.
    with pytest.raises(ValueError, match="single-consumer"):
        assert_no_collisions([_account(str(tmp_path), "a", token="same"),
                              _account(str(tmp_path), "b", token="same")])


def test_duplicate_account_id_is_refused(tmp_path):
    with pytest.raises(ValueError, match="duplicate account id"):
        assert_no_collisions([_account(str(tmp_path), "a"), _account(str(tmp_path), "a")])


def test_path_comparison_is_normalised(tmp_path):
    a = _account(str(tmp_path), "a")
    messy = Paths(
        runtime_state_file=a.paths.runtime_state_file.replace(os.sep, "/").replace("/a/", "/./a/"),
        status_file=os.path.join(str(tmp_path), "b", "st.json"),
        feature_store_file=os.path.join(str(tmp_path), "b", "fs.jsonl"),
        shadow_ledger_file=os.path.join(str(tmp_path), "b", "sl.jsonl"),
    )
    b = Account(id="b", label="b", credentials=Credentials(api_key="k2", api_secret="s"),
                paths=messy, channels=())
    with pytest.raises(ValueError, match="share path"):
        assert_no_collisions([a, b])
