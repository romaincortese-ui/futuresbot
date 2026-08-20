"""Account identity, policy and paths — phase 1 + 5 of docs/MULTI_ACCOUNT_DESIGN.md.

Today the bot has exactly one account and it is spelled "the process environment".
This module gives that account a name and a shape, without changing a single
thing about how it behaves.

Three rules carried over from the design doc:

* ``Account.id`` is an IDENTITY TOKEN, never a path fragment. Paths are declared
  explicitly per account. Deriving them by concatenating the id means one typo
  relocates the live position ledger — and ``_load_state`` cannot tell "empty
  file" from "wrong file": either way you boot with zero positions against real
  open positions.
* ``Policy`` is a SMALL CLOSED SET — the things that may legitimately differ
  between accounts. Everything else is a shared strategy constant, so a strategy
  change stays one deploy rather than N.
* ``from_env()`` reproduces today's live configuration exactly. The default
  account is ``main`` and nothing about it changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

DEFAULT_ACCOUNT_ID = "main"

# Sleeves that can be enabled per account. PMT is decommissioned but named here
# so an old config that mentions it resolves rather than raising.
KNOWN_SLEEVES = ("WILDCARD", "SQUEEZE", "TREND", "PMT")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_float(name, float(default)))


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class Credentials:
    """Exchange credentials plus the metadata the key-health countdown needs."""

    api_key: str = ""
    api_secret: str = ""
    expires_at: str = ""
    created_at: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @property
    def fingerprint(self) -> str:
        """Non-reversible label for logs and the boot manifest.

        Never log the key itself. Four characters is enough to tell two accounts
        apart in a log line and useless to anyone who intercepts it.
        """

        return f"{self.api_key[:4]}…" if len(self.api_key) >= 4 else "unset"

    def __repr__(self) -> str:  # keeps secrets out of tracebacks and reprs
        return f"Credentials(api_key={self.fingerprint!r}, api_secret=<hidden>)"


@dataclass(frozen=True, slots=True)
class HardLimits:
    """Absolute USDT loss caps. ``None`` means "no cap" — today's behaviour.

    Denominated in currency rather than percentages on purpose: a percentage cap
    scales with the balance it is supposed to be protecting, which is exactly
    backwards when the account is not the operator's own.
    """

    max_loss_per_trade_usdt: float | None = None
    max_loss_per_day_usdt: float | None = None
    max_loss_per_week_usdt: float | None = None

    @property
    def any_set(self) -> bool:
        return any(v is not None for v in
                   (self.max_loss_per_trade_usdt, self.max_loss_per_day_usdt, self.max_loss_per_week_usdt))


@dataclass(frozen=True, slots=True)
class Policy:
    """What may differ between accounts. Deliberately small.

    Anything NOT here is a shared strategy constant. That line is the main open
    question in the design doc (§9.1) — widening it later is easy, narrowing it
    after two accounts depend on it is not.
    """

    margin_budget_usdt: float = 75.0
    leverage_min: int = 15
    leverage_max: int = 25
    max_stop_margin_pct: float = 20.0
    risk_pct_per_trade: float = 0.0          # 0 = disabled, matching today
    max_concurrent: Mapping[str, int] = field(
        default_factory=lambda: {"WILDCARD": 2, "SQUEEZE": 1, "TREND": 1})
    sleeves_enabled: frozenset[str] = frozenset(("WILDCARD", "SQUEEZE"))
    hard_limits: HardLimits = field(default_factory=HardLimits)

    def slots_for(self, sleeve: str) -> int:
        return int(self.max_concurrent.get(sleeve.upper(), 0))

    def allows(self, sleeve: str) -> bool:
        return sleeve.upper() in self.sleeves_enabled


@dataclass(frozen=True, slots=True)
class Paths:
    """Per-account artefacts. Declared, never derived from the account id."""

    runtime_state_file: str
    status_file: str
    feature_store_file: str
    shadow_ledger_file: str

    def all(self) -> tuple[str, ...]:
        return (self.runtime_state_file, self.status_file,
                self.feature_store_file, self.shadow_ledger_file)


@dataclass(frozen=True, slots=True)
class ChannelBinding:
    """Where this account's events go, and which ones it wants.

    ``mute`` names event kinds to suppress. Two kinds can never be muted —
    see events.UNMUTABLE — because an account that has silenced its own auth
    failures is an account that goes dark without anyone noticing.
    """

    kind: str = "telegram"
    token: str = ""
    address: str = ""
    mute: frozenset[str] = frozenset()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.address)


@dataclass(frozen=True, slots=True)
class Account:
    id: str = DEFAULT_ACCOUNT_ID
    label: str = "Main"
    credentials: Credentials = field(default_factory=Credentials)
    policy: Policy = field(default_factory=Policy)
    paths: Paths | None = None
    channels: tuple[ChannelBinding, ...] = ()
    paper: bool = True
    enabled: bool = True

    @property
    def is_default(self) -> bool:
        """True for the pre-existing single-account deployment.

        Guarded behaviour keys off this: anything account-aware must be a no-op
        for the live account until it is explicitly opted in.
        """

        return self.id == DEFAULT_ACCOUNT_ID

    def channel(self, kind: str = "telegram") -> ChannelBinding | None:
        for binding in self.channels:
            if binding.kind == kind:
                return binding
        return None

    # -- construction --------------------------------------------------------

    @classmethod
    def from_env(cls, *, config: Any = None) -> "Account":
        """Build the account today's environment already describes.

        ``config`` is an optional FuturesConfig; when given, its resolved paths
        and credentials win, so this cannot drift from what the runtime actually
        uses. Without it the same env vars are read directly.
        """

        account_id = _env("FUTURES_ACCOUNT_ID", DEFAULT_ACCOUNT_ID) or DEFAULT_ACCOUNT_ID
        creds = Credentials(
            api_key=getattr(config, "api_key", None) or _env("MEXC_API_KEY"),
            api_secret=getattr(config, "api_secret", None) or _env("MEXC_API_SECRET"),
            expires_at=_env("MEXC_API_KEY_EXPIRES_AT"),
            created_at=_env("MEXC_API_KEY_CREATED_AT"),
        )
        state_file = getattr(config, "runtime_state_file", None) or _env(
            "FUTURES_RUNTIME_STATE_FILE", "futures_runtime_state.json")
        status_file = getattr(config, "status_file", None) or _env(
            "FUTURES_STATUS_FILE", "futures_runtime_status.json")
        state_dir = os.path.dirname(state_file) or "."
        paths = Paths(
            runtime_state_file=state_file,
            status_file=status_file,
            feature_store_file=_env("FUTURES_FEATURE_STORE_FILE")
            or os.path.join(state_dir, "futures_feature_store.jsonl"),
            shadow_ledger_file=_env("FUTURES_SHADOW_LEDGER_FILE")
            or os.path.join(state_dir, "futures_shadow_ledger.jsonl"),
        )
        token = getattr(config, "telegram_token", None) or _env(
            "FUTURES_TELEGRAM_TOKEN", _env("TELEGRAM_TOKEN"))
        chat_id = getattr(config, "telegram_chat_id", None) or _env(
            "FUTURES_TELEGRAM_CHAT_ID", _env("TELEGRAM_CHAT_ID"))
        sleeves = {s for s in KNOWN_SLEEVES
                   if _env_bool(f"FUTURES_{s}_ENABLED", s in ("WILDCARD", "SQUEEZE"))}
        policy = Policy(
            margin_budget_usdt=(getattr(config, "margin_budget_usdt", None)
                                or _env_float("FUTURES_MARGIN_BUDGET_USDT", 75.0)),
            leverage_min=getattr(config, "leverage_min", None) or _env_int("FUTURES_LEVERAGE_MIN", 15),
            leverage_max=getattr(config, "leverage_max", None) or _env_int("FUTURES_LEVERAGE_MAX", 25),
            max_stop_margin_pct=_env_float("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0),
            risk_pct_per_trade=_env_float("FUTURES_MAX_TRADE_RISK_PCT", 0.0),
            max_concurrent={
                "WILDCARD": _env_int("FUTURES_WILDCARD_MAX_POSITIONS", 2),
                "SQUEEZE": _env_int("FUTURES_SQUEEZE_MAX_POSITIONS", 1),
            },
            sleeves_enabled=frozenset(sleeves),
            hard_limits=HardLimits(
                max_loss_per_trade_usdt=_optional_float("FUTURES_MAX_LOSS_PER_TRADE_USDT"),
                max_loss_per_day_usdt=_optional_float("FUTURES_MAX_LOSS_PER_DAY_USDT"),
                max_loss_per_week_usdt=_optional_float("FUTURES_MAX_LOSS_PER_WEEK_USDT"),
            ),
        )
        return cls(
            id=account_id,
            label=_env("FUTURES_ACCOUNT_LABEL", account_id.title()) or account_id.title(),
            credentials=creds,
            policy=policy,
            paths=paths,
            channels=(ChannelBinding(kind="telegram", token=token, address=chat_id),),
            paper=bool(getattr(config, "paper_trade", None)
                       if config is not None else _env_bool("FUTURES_PAPER_TRADE", True)),
            enabled=_env_bool("FUTURES_ACCOUNT_ENABLED", True),
        )

    def apply_to(self, config: Any) -> Any:
        """Project this account onto a FuturesConfig.

        The inverse of ``from_env``. Used when a runtime is constructed FROM an
        Account rather than from the environment — the seam a future account
        registry plugs into. Only fields the account actually owns are touched.
        """

        overrides: dict[str, Any] = {
            "api_key": self.credentials.api_key,
            "api_secret": self.credentials.api_secret,
            "paper_trade": self.paper,
            "margin_budget_usdt": self.policy.margin_budget_usdt,
            "leverage_min": self.policy.leverage_min,
            "leverage_max": self.policy.leverage_max,
        }
        if self.paths is not None:
            overrides["runtime_state_file"] = self.paths.runtime_state_file
            overrides["status_file"] = self.paths.status_file
        binding = self.channel("telegram")
        if binding is not None:
            overrides["telegram_token"] = binding.token
            overrides["telegram_chat_id"] = binding.address
        valid = {k: v for k, v in overrides.items() if hasattr(config, k)}
        return replace(config, **valid)


def _optional_float(name: str) -> float | None:
    raw = _env(name)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def assert_no_collisions(accounts: "list[Account]") -> None:
    """Refuse to run two accounts that would write to the same place.

    The failure this prevents is silent: two runtimes sharing a state file both
    load and overwrite one open-positions map keyed by symbol, so account B's
    exit logic manages a position it does not hold. Loud at boot beats
    discovering it from the P&L.
    """

    seen_ids: set[str] = set()
    seen_paths: dict[str, str] = {}
    seen_keys: dict[str, str] = {}
    seen_channels: dict[tuple[str, str], str] = {}
    for account in accounts:
        if account.id in seen_ids:
            raise ValueError(f"duplicate account id: {account.id!r}")
        seen_ids.add(account.id)
        if account.paths is not None:
            for path in account.paths.all():
                normalised = os.path.normcase(os.path.normpath(path))
                if normalised in seen_paths:
                    raise ValueError(
                        f"accounts {seen_paths[normalised]!r} and {account.id!r} share path {path!r}")
                seen_paths[normalised] = account.id
        if account.credentials.api_key:
            if account.credentials.api_key in seen_keys:
                raise ValueError(
                    f"accounts {seen_keys[account.credentials.api_key]!r} and {account.id!r} "
                    "share an API key")
            seen_keys[account.credentials.api_key] = account.id
        for binding in account.channels:
            if not binding.configured:
                continue
            # One bot token cannot serve two accounts: Telegram getUpdates is a
            # single-consumer queue, so commands would misroute nondeterministically.
            token_key = (binding.kind, binding.token)
            if token_key in seen_channels:
                raise ValueError(
                    f"accounts {seen_channels[token_key]!r} and {account.id!r} share a "
                    f"{binding.kind} token; getUpdates is single-consumer per token")
            seen_channels[token_key] = account.id
