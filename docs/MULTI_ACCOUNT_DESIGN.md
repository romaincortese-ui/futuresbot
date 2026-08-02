# Multi-Account Architecture — Design Draft 1

**Status:** draft, for discussion. Nothing here is implemented.
**Date:** 2026-08-01
**Author:** Romain Cortese (with Claude)

---

## 0. Purpose

Today the bot is one program serving one MEXC account, controlled by one person over
Telegram, deployed as one Railway service. That is not a bad design — it is an *unstated*
one. Every layer assumes "the account" and "the operator" are singular and identical.

This document proposes making those assumptions explicit so the same strategy engine can:

- trade **N accounts** (mine, a second test account, later possibly other people's);
- be driven by **channels other than Telegram** — a website, a mobile app, an HTTP API —
  without the strategy layer knowing anything about them.

It is deliberately a *first draft*: the shape is argued, the details are open, and §9 lists
what I do not yet know.

---

## 1. Goals and non-goals

### Goals

| G1 | One strategy engine, N accounts, no copy-paste and no forked repo. |
| G2 | Telegram is **one** delivery channel, not the interface. A website must be addable without touching strategy code. |
| G3 | Adding an account is a config change, not a code change. |
| G4 | Accounts are isolated: one account's state, history, positions or failure cannot affect another's. |
| G5 | Every phase ships independently. The live account is never a migration test subject. |

### Non-goals (for this draft)

- Custody of third parties' funds, and the legal shape that requires. Real, but a separate
  document — the architecture below is agnostic to who owns the account.
- Multi-exchange. The design should not *prevent* it, but MEXC is the only adapter here.
- Changing any strategy behaviour. This is a structural refactor; entry and exit logic
  must be byte-for-byte identical afterwards.

---

## 2. Where we are today

Honest current state, verified by reading the code rather than assumed.

**The good news is substantial:**

- No module-level singletons, no `lru_cache`, no `global` statements anywhere in the
  package. All runtime state is instance-scoped on `FuturesRuntime`.
- `MexcFuturesClient` signs from `self.config.api_key` — the client is already per-config.
- `TelegramClient(token, chat_id)` is already fully parameterised.
- Both signal detectors (`detect_wildcard_signal`, `detect_squeeze_signal`) are **pure
  functions** of a DataFrame — zero account state reaches them.
- `_open_wildcard_position(sig, available_balance, kind=...)` is already shaped as a
  `(signal, balance) → bool` fan-out function.
- Every state path and Redis key is already env-overridable.

**The coupling is concentrated in four places:**

| # | Coupling | Where |
|---|---|---|
| C1 | `FuturesConfig.from_env()` reads process-global env with no injection point. Two calls return identical credentials. | `config.py:443-612` |
| C2 | ~660 of 785 env names never reach `FuturesConfig`; they are read at call time deep in `strategy.py`, `runtime.py`, `pmt_strategy.py`. `main.py` pins 143 of them process-globally at import. | package-wide |
| C3 | Outbound notification is a **pre-formatted HTML string**. `_notify(text)` is the only interface. A website cannot consume it. | `runtime.py:753, 759` |
| C4 | Inbound commands are Telegram-shaped: `getUpdates` long-polling, and `getUpdates` is **single-consumer per bot token**. | `runtime.py:~2100-2200` |

C1 and C2 look fatal and are not — see D1. **C3 is the real blocker for the website**, and
it is the most interesting problem in this document.

---

## 3. The core idea: three layers

Today `FuturesRuntime` is one class that is simultaneously a market scanner, an account
manager, and a Telegram bot. The proposal is to name those three things and give them a
boundary — starting as modules in one process, not as microservices.

```
┌─────────────────────────────────────────────────────────────┐
│  MARKET LAYER          — knows the venue, knows no accounts   │
│  public klines/tickers, indicators, detectors                 │
│  output: Signal (policy-free)                                 │
└───────────────────────────┬───────────────────────────────────┘
                            │  Signal
┌───────────────────────────▼───────────────────────────────────┐
│  ACCOUNT LAYER         — knows one account, knows no channels  │
│  credentials · policy · sizing · slots · positions · state     │
│  risk limits · learning rows                                   │
│  output: Event (typed, structured)                             │
└───────────────────────────┬───────────────────────────────────┘
                            │  Event
┌───────────────────────────▼───────────────────────────────────┐
│  CHANNEL LAYER         — knows humans, knows no strategy        │
│  TelegramChannel · WebChannel · (future: email, push)          │
│  renders Events; produces Commands                             │
└─────────────────────────────────────────────────────────────────┘
```

The layering rule, and the whole point of the document:

> **Signals flow down. Events flow up. Nothing skips a layer, and no layer knows the one
> above it.**

The market layer must never see an API key. The account layer must never format HTML.

---

## 4. Domain model

Five concepts, none of which exist as types today.

### 4.1 `Account`

Identity plus credentials plus policy. Replaces "the process environment."

```python
@dataclass(frozen=True, slots=True)
class Account:
    id: str                     # "main", "test2" — stable, appears in every path/log/event
    label: str                  # human name for display
    credentials: Credentials    # api_key, api_secret, expiry metadata
    policy: Policy              # see 4.2
    channels: tuple[ChannelBinding, ...]
    paper: bool
    enabled: bool
```

`id` is an **identity token, not a path fragment.** Paths and keys are declared explicitly
per account, never derived by string-concatenating `id`. Deriving them means a typo in one
variable silently relocates the live position ledger — and `_load_state` cannot distinguish
"empty file" from "wrong file": either way you boot with zero positions against real open
positions.

### 4.2 `Policy`

Everything that makes account B behave differently from account A. Explicitly a **small,
closed set** — not "all 785 env vars."

```python
@dataclass(frozen=True, slots=True)
class Policy:
    margin_budget_usdt: float
    max_concurrent: dict[str, int]      # {"WILDCARD": 2, "SQUEEZE": 1}
    leverage_cap: int
    max_stop_margin_pct: float          # the -20% cap
    risk_pct_per_trade: float
    hard_limits: HardLimits             # absolute USDT loss caps: per trade / day / week
    sleeves_enabled: frozenset[str]
```

Everything *not* in `Policy` is a global strategy constant shared by every account. That is
a feature: it means a strategy change is one deploy, not N. The line between "policy" and
"strategy constant" is the main thing to get right, and §9 flags it as open.

### 4.3 `Signal` — policy-free

**This is the load-bearing change.** Today `WildcardSignal` already carries `leverage`,
`sl_price`, `tp_price` and `balance_fraction`, computed *inside* the detector from process
env (`wildcard.py:163-186`). The −20% margin cap trims leverage and can then move the stop.

So today's "signal" secretly embeds one account's risk policy. Sharing it across accounts
would silently apply my risk settings to someone else's money.

The split:

```python
@dataclass(frozen=True, slots=True)
class Signal:            # market layer — identical for every account
    symbol: str; side: str
    entry_price: float; atr_pct: float
    raw_stop_frac: float          # geometry only, before any margin cap
    sleeve: str; lateness: float
    features: Mapping[str, float] # roc, rsi, coil width...
    detected_at: float
```

```python
@dataclass(frozen=True, slots=True)
class OrderIntent:       # account layer — Signal x Policy x balance
    account_id: str; signal: Signal
    leverage: int; contracts: int
    stop_price: float; take_profit_price: float
    client_order_id: str          # deterministic, for idempotency + audit
```

`Signal → OrderIntent` is the one function that must be pure and heavily tested. It is
where sizing, the margin cap, the leverage trim, and the hard limits all live.

### 4.4 `Event` — typed, not formatted

The fix for C3. Today `_notify` takes rendered HTML; a website would have to scrape it.

```python
@dataclass(frozen=True, slots=True)
class Event:
    account_id: str
    kind: EventKind          # ENTRY, EXIT, AUTH_FAILURE, KEY_EXPIRY, HEARTBEAT,
                             # DRAWDOWN, DIGEST, COMMAND_REPLY, BOOT
    severity: Severity       # INFO, WARN, CRITICAL
    at: float
    data: Mapping[str, Any]  # structured — symbol, r_multiple, pnl_usdt, reason...
    dedupe_key: str | None   # replaces the _notify_once cooldown-key convention
```

Rendering moves to the channel. `TelegramChannel` owns the emoji and the `<b>` tags;
`WebChannel` serialises `data` as JSON. **Same event, two presentations, one source of
truth.** Adding a website stops being a strategy-layer change.

This also makes events *persistable*, which is what a web UI actually needs: a page load is
"give me the last 50 events for account X," not "replay Telegram history."

### 4.5 `Command` — channel-agnostic

The fix for C4. Today commands arrive only as Telegram text and are dispatched inline in a
long `if/elif` chain.

```python
@dataclass(frozen=True, slots=True)
class Command:
    account_id: str
    verb: str                # status | pause | resume | close | flat | pnl | why
    args: Mapping[str, Any]
    actor: Actor             # who asked, and over which channel
    received_at: float
```

A `CommandSource` produces `Command`s; a `CommandHandler` consumes them and returns
`Event`s. Telegram polling and an HTTP `POST /accounts/{id}/commands` become two sources of
the same type. Authorisation is checked once, on `Actor`, in one place.

This also dissolves the single-consumer-per-bot-token constraint: with a web front end,
commands do not have to arrive over Telegram at all.

---

## 5. Design decisions

### D1 — One process per account (for now), one codebase

**Decision:** each account runs as its own OS process (today: its own Railway service),
from the same image and the same commit.

**Why:** C1 and C2 look like blockers to N accounts and are dissolved entirely by process
isolation. `main.py` uses `os.environ.setdefault`, so per-service Railway variables win
over all 143 defaults; the ~660 call-time env reads are only a problem when two runtimes
share one `os.environ`. In separate processes every env name becomes per-account tunable
**at zero code cost.**

**Rejected:** threads or an in-process account loop. It requires threading a settings
object through ~660 call sites in live money-moving code, where a wrong coercion does not
raise — it silently shifts an entry gate, and you find out days later in the P&L. Enormous
risk, zero delivered benefit over a second process.

**Consequence to accept:** market data is fetched N times. Fine to ~5 accounts; §9 flags
the rate-limit ceiling. The three-layer split is what makes a shared scanner *possible
later* without rewriting anything — but we should not build it until the duplication
actually hurts.

### D2 — Config becomes layered, and `Account` is the only new global

```
strategy constants (code + main.py defaults)   ← shared by all accounts
        ↓ overridden by
account Policy (declared per account)          ← the small closed set
        ↓ resolved into
FuturesConfig                                  ← unchanged shape, built per account
```

`FuturesConfig` keeps its 97 fields and its `from_env()`. We add one constructor:
`FuturesConfig.for_account(account)`. The existing `for_symbol()` already establishes the
`dataclasses.replace` scoping idiom — this is a direct lift of a pattern already in the
repo.

### D3 — Every artefact is namespaced by account, explicitly

State file, status file, feature store, shadow ledger, digest marker, and every Redis key
get an explicit per-account value. **Declared, not derived** (see 4.1).

Two deliberate exceptions that stay shared, because they are *venue* data, not account
data: funding observations and the prediction/event overlays. Namespacing those would
duplicate work and break the spot bot that consumes them.

Learning rows gain an `account` column **before** the second account exists — commingled
rows are not separable retroactively. Whether the expectancy engine should then pool or
segregate is an open question (§9), but the column must exist first either way.

### D4 — The Telegram seam is already narrow; exploit it

Every outbound byte goes through exactly two functions (`_notify`, `_notify_once`), and
`TelegramClient` is already parameterised. So D-4 is smaller than it sounds:

1. Change `_notify(text)` → `emit(event)` internally.
2. `TelegramChannel` subscribes and renders. Behaviour is identical.
3. `WebChannel` subscribes later and does not touch strategy code.

The conversion can be incremental — an `Event` carrying a `text` field renders identically
on day one, and call sites migrate to structured `data` one at a time.

### D5 — Identity is visible everywhere, from day one

Account id appears in: the log formatter, every `Event`, every learning row, the boot
manifest, and every message header. Two chats side by side must never be ambiguous.

Cheap, and it is the difference between an operator surface and a guessing game.

---

## 6. What the website case actually changes

If the bot becomes the backend of a web platform, the layering above is necessary but not
sufficient. Four additions:

**6.1 A read model.** A web UI needs to *query* — positions, history, equity curve, events,
per-account P&L. Today the only readable artefacts are a status JSON blob and JSONL files
on a container volume. This wants a real store (Postgres is the obvious Railway-native
choice). Note this is a **read** model: the trading loop stays authoritative and file-based;
the store is projected from `Event`s. That keeps the money path free of a new dependency.

**6.2 A command API.** `POST /accounts/{id}/commands` returning a command id, with the
result delivered as an `Event`. Commands must be **idempotent** (a double-tapped "close"
must not double-close) — hence `client_order_id` in `OrderIntent`.

**6.3 An identity/authorisation model.** Telegram's chat id is doing double duty as
authentication *and* routing today. A website needs real users, and a user↔account
mapping that is many-to-many (an owner, maybe a read-only viewer). `Actor` in §4.5 is the
placeholder for this; it is under-specified in this draft.

**6.4 Credential intake.** The moment a browser can submit an API key, key handling becomes
a first-class security problem rather than a Railway variable. Out of scope here, and
flagged as the largest unknown in §9.

**Explicitly: none of 6.1–6.4 requires the strategy layer to change.** That is the test of
whether this design is right.

---

## 7. Migration path

Ordered, each phase independently shippable and revertible. Phases 1–4 are worth doing
**even if multi-account is abandoned** — they are improvements to the current single account.

| # | Phase | Touches live? | Status |
|---|---|---|---|
| 0 | Prerequisites — the four defects in §8. Independently valuable. | Yes | **outstanding** |
| 1 | Introduce `Account` + `Policy` types. Live account constructed via a default `Account("main", ...)`. Provably zero behaviour change. | Yes | ✅ `accounts.py` |
| 2 | Identity everywhere: account id in message headers and learning rows. No-op while the id is `main`. | Yes | ✅ |
| 3 | `Event` type + `emit()`; `TelegramChannel` renders. Start with a `text` passthrough, migrate call sites incrementally. | Yes | ✅ `events.py` |
| 4 | `Command` type + `CommandSource`; Telegram poller becomes one implementation. | Yes | ✅ `commands.py` |
| 5 | Namespace every artefact explicitly. Set each var to what it resolves to today — nothing moves on disk. | Restart only | ✅ via `Account.paths` |
| 6 | Account #2 as a second service, paper, no keys. Soak. | No | not started |
| 7 | Account #2 live, small. | No | not started |
| 8 | *(only if the platform case is real)* Event store + read API + web channel. | No | not started |

**Phase 1–5 delivery notes (2026-08-01).** Shipped as three new modules plus additive
wiring; no existing message, path or behaviour changed. Verified: for the default account
the feature-store and shadow-ledger paths resolve byte-identically to the previous
derivation, and `_mode_label()` is unchanged. `Credentials.__repr__` is redacted so keys
cannot reach a traceback. `assert_no_collisions()` refuses two accounts sharing a state
path, an API key, or a Telegram bot token.

Two call sites are migrated onto `emit()` (auth-failure and key-expiry alerts) as proof of
the path; every other message still goes through `_notify` unchanged and can migrate one at
a time. Phase 4's `TelegramCommandSource` is built and tested but **not yet swapped into
the runtime loop** — the existing inline handler still runs. That swap is deliberately a
separate change, because it is the one with real behavioural risk.

Phases 1–5 are roughly a week of careful work and leave the system strictly better even at
N=1. Phase 8 is a different project and should be scoped separately.

---

## 8. Prerequisites — defects that block multi-account

Found while reading the code for this design. All four are live bugs at N=1; all become
serious at N>1. Details and evidence in the session notes.

1. **`_save_state` is non-atomic** (`runtime.py:2546`, bare `write_text`). This is the
   authoritative open-positions ledger, rewritten every cycle. A container kill mid-write
   truncates it and the bot reboots with zero positions against real open positions.
   `shadow_ledger.py:93` already does tmp+`os.replace` — the pattern is in-repo.
2. **`/close all` aborts at the first failure.** `close_position` is unguarded inside
   `_force_close_position`; one MEXC error and every position after it in the loop never
   gets a close attempt. This is the get-me-out path.
3. **The convex sleeves have no equity-drawdown brake.** `_drawdown_size_multiplier`
   (`:5102`) is only called from `_enter_trade` (`:7014`) — the decommissioned PMT path.
   The code says so at `:2857`. *(The streak throttle at `:3951` is wired and works — these
   are different protections.)*
4. **Slippage has never been measured on the live sleeves.** `_record_fill` (`:5747`) is
   also PMT-only. Any capacity or cost claim about the live strategy is currently
   unanchored.

---

## 9. Open questions

Genuinely unresolved. Listed so they get answered rather than assumed.

1. **Where is the policy/strategy line?** §4.2 proposes a small closed `Policy`. Is
   `FUTURES_WILDCARD_MIN_TURNOVER_USDT` policy or strategy? Getting this wrong in either
   direction is costly: too small and accounts cannot differ usefully; too large and every
   account is a separate strategy and the learning corpus never pools.
2. **Should the expectancy engine pool across accounts?** Pooling gives more rows (it needs
   n≥6 per condition), but mixes balances, fee tiers and policies. Pooled-but-attributed is
   probably right; unproven.
3. **Rate limits.** MEXC's private-endpoint limits — per key or per IP? The reconcile
   poller runs at a 2-second cadence while a position is open. If limits are per-IP, that
   binds account count far sooner than anything in this document.
4. **Static egress.** Does Railway give a stable outbound IP on this plan? It determines
   whether IP-whitelisting keys is viable, which in turn removes MEXC's 90-day expiry.
5. **Credential storage once a browser is involved** (6.4). The largest unknown here, and
   the point at which this stops being a refactor and becomes a security design.
6. **Does anything outside this repo consume `futures_runtime_status`?** If so, namespacing
   it needs a one-release dual-write.
7. **Capacity.** The wildcard sleeve trades small caps at a ~$3M/24h turnover floor — about
   $35 of flow per second. N accounts entering the same signal compete for the same book,
   and all rest byte-identical stops derived from the same bar close. The binding
   constraint is *aggregate dollars*, not account count. Unquantifiable until (8.4) is
   fixed. This is a constraint on the *strategy*, not on this architecture — but it caps
   how much the architecture is worth.

---

## 10. What this document is not

It does not argue that multi-account should happen now. It argues that *if* it happens, the
seams above are where to cut — and that four of the phases are worth doing regardless.

The strategy's own edge is unresolved (trial 4, n=21, one trade carrying the result). No
architecture changes that, and a clean multi-account backend around an unproven strategy is
still an unproven strategy — just better organised.
