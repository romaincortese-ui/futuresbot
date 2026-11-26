# WS2: Reusable assets and extraction plan (Dev 1 + QA 1, 2026-11-26)

**In short:** about 5,900 lines of the bot are worth keeping. About 3,500 of them have no link to the live bot and need only the Python standard library or pandas. About 210 existing tests cover them: today, offline, 213 related tests passed in 6 s. The other ~33k lines stay behind. A standalone "research kit" with no Railway or private-key code takes about **4.5 developer-days** (range 3.5-6). Some data is being lost **every day**. The team can save the public part itself. Saving the rest needs the owner (section 6).

## 1. Keep (port into the kit)

| Asset | Where | Why it is worth keeping | State today |
|---|---|---|---|
| Bar cache (no forming bars, no gaps) | `futuresbot/replay/bars.py` (491 lines, stdlib) | Durable bar store | 15 tests. Min1/Min15 only; **Min5 missing** |
| One exit engine on FAIR price | `futuresbot/replay/exits.py` (750) | Matched live exits: corr 0.999, 93.5% within 0.1R (`docs/DECISION_RULE.md` ~17845) | 25 tests. **Imports `FuturesRuntime`** (lines 68-70, 593-744) |
| Sizing like live | `futuresbot/replay/sizing.py` (495, stdlib) | 93% of fills sized within 5% | 19 tests |
| Replay-vs-live grader | `futuresbot/replay/acceptance.py` (748, stdlib) | Answers "does the replay track reality?" | 25 tests |
| Gap-refusing fetch | `tools/pit_fetch.py` (240) | Fixed a bug that flipped study verdicts | **0 tests** |
| Point-in-time universe | `tools/pit_pool.py` (110, stdlib) | Removes hindsight in the coin list | **0 tests** |
| Luck controls | `tools/pit_placebo.py` (181), `tools/mc_ledger.py` (70), `a1/analyze.py` | Permutation and time-shift placebos | 7 tests / **0** / 0 |
| Feature builder | scratchpad `a1/build_features.py` | ~30 entry inputs per trade, no look-ahead | 0 tests. 3 known defects (`04_dev1.md` §2) |
| Walk-forward, costs, venue rules | `walk_forward.py`, `realistic_costs.py`, `exchange_spec.py` | Generic helpers | 5 / 11 tests |
| Shadow ledger | `futuresbot/shadow_ledger.py` (625, stdlib) | Records what was NOT traded (live trades are a biased sample) | 10 tests |
| Evidence-archive pattern | `tools/archive_evidence.py` (566) | Dated, idempotent, hash-verified, secret-safe | 16 tests. Uses `railway ssh`: **keep the pattern, drop that part** |
| Strategy plug-in (frozen, Approach 2 only) | `wildcard.py`, `random_mode.py` | Rebuilds the bot's candidates | 21 / 56 tests |
| Fixtures | `tests/fixtures/replay_exits_live_fills.json.gz`, `replay_live_book_0813_0923.json` | Real-fill truth sets | in git |

**Keep as reference docs, not code:** the order-client lessons in `futuresbot/marketdata.py` (single-send orders, key-expiry detection). The kit holds **no private-key or order code**, so it cannot trade by accident.

## 2. Leave behind

`runtime.py` (15,361 lines), `strategy.py`, `pmt_strategy.py`, sniper/squeeze, Telegram, Redis publishers, prediction/news overlays, calibration jobs, `main.py`, `railway*.toml`, the ~866 env flags, and ~120 of 130 `tools/` scripts (88 mention `railway`). `docs/DECISION_RULE.md`, `daily_audit.md`, `LIVE_CONFIG.md` and the team memos stay here as the historical record; freeze it with a git tag at `89fe090` (whoever holds push rights).

## 3. Target shape

A new private repo with one package. We use the working name `edgekit`; the owner decides the name and where it lives.

```
edgekit/
  data/      bars.py (+Min5, +daily), fetch.py (pit_fetch), venues/mexc_public.py  # public endpoints only
  universe/  pit_pool.py
  replay/    exits.py (rules frozen, no runtime import), sizing.py, acceptance.py
  features/  build.py (from a1, defects fixed), holdout.py (cutoff guard)
  stats/     placebo.py, mc_ledger.py, walk_forward.py, family-wise correction, day-block bootstrap
  strategies/ mexc_wildcard/ (frozen detector, Approach 2 only)
  archive/   archive.py (manifest + sha256, any storage target)
tests/  fixtures/  docs/LESSONS.md  pyproject.toml (Python 3.12, pinned)  .github/workflows/ci.yml
```

Data sits **outside git**, described by `MANIFEST.json` files (path, sha256, source, retrieved-at). Option B can add an ETF/daily-bar adapter under `data/venues/`: +2-4 days each; non-crypto effort unknown until a source is chosen (`04_dev1.md` §4).

## 4. Effort (developer-days)

| Step | Days | Basis |
|---|---|---|
| Skeleton, CI, copy the stdlib-only modules and their tests | 1.0 | ~3,500 lines already free of runtime imports; their tests pass offline today |
| Cut `exits.py` free of `FuturesRuntime`: first record the live-code reference outputs on the 70 live fills plus ~300 random paths as golden fixtures, then delete the import | 1.0-1.5 | The equivalence test already exists (`tests/test_replay_exits.py`); we convert it, we do not invent it |
| Min5 in `bars.py`; feature builder hardened (no silent `{}`, exact lookbacks, uses `fetch.py`) | 1.0 | Same work as Approach 2 step 1, counted once |
| Public-only MEXC adapter split out of `marketdata.py`; archive job without `railway ssh` | 0.5-1.0 | Small, already-tested surfaces |
| Tests for pit_fetch/pit_pool/mc_ledger, holdout guard, README/LESSONS | 0.5-1.0 | See section 5 |
| **Total** | **4-5.5 (call it 4.5)** | Excludes new venue adapters |

This is the same task as the minutes' "Research kit off FuturesRuntime; P1 feature tests; CI on Python 3.12" (Dev 1 + QA 1, due 12-04). Approach 2 (P2, 12-06) should run on the kit, not on the bot repo.

## 5. Tests the kit must ship with (QA 1)

1. The ~210 ported tests, green on **Python 3.12**, in **random order** (an order-dependent test exists; `07_qa1.md` §2), with **network blocked**.
2. **Golden exit tests:** frozen fixtures reproduce today's live-code results exactly; without them the decoupling could silently lose the 0.999 match.
3. **No look-ahead:** a feature at time t uses only bars closed by t; token and BTC lookbacks share offsets.
4. **Fetch honesty:** a short or rate-limited series raises, is never cached, never returns `{}`.
5. **Point-in-time universe:** today's major that was small then stays in the historical pool.
6. **Holdout guard:** loaders refuse rows at or after the sealed cutoff unless given the CEO/QA 2-signed P0 hash.
7. **Archive integrity:** idempotent re-runs; a hash mismatch fails loudly; no secret is written.
8. **Independence:** no import of `futuresbot.runtime`; no `railway`, secrets or private endpoints in the code.
9. **Placebo sanity:** shuffled outcomes must not "pass" (Approach 1's best cells hit ~85% on random labels).

## 6. Data at risk, and how to save it

| Data | Where now | Clock | Who can act | How |
|---|---|---|---|---|
| MEXC position history 08-29 → 11-26 (276 closed) + transfers | Only in this session's **scratchpad** (`hist_all.json`, `transfers.json`); a reboot can wipe it | Now | **Team** | Copy to durable private storage within 24 h; verify against `plan/ws2_scratchpad_sha256.txt` (written today). Holds holdout-period trades: QA 2 keeps it sealed |
| MEXC history after today | Exchange only (keys only on Railway) | Oldest day drops off daily (~90 days kept) | **Owner only** | Export every ≤60 days while the bot runs (`tools/export_position_history.py` via Railway, or a MEXC website export if one exists: unknown), or accept the loss |
| 1m bars (public) | MEXC, from ~10-28 | ~30 days, one day lost per day | **Team** (Dev 2, due 11-30) | Cache all USDT perps, then a daily off-laptop job. Very rough size ~0.6 GB (scaled from 519 MB per year of 15m bars, 622 symbols) |
| 5m and 15m bars (public) | MEXC: 5m back to at least 05-10 (retention unknown); 15m ~361 days | Sliding | **Team** | Archive 5m from 05-10 and 15m as far back as served, now |
| Laptop evidence archive | Owner's laptop only (`FUTURESBOT_EVIDENCE_DIR`): 15m bars 2025-09-28 onward for 622 symbols (519 MB); daily 1m bars and container snapshots ~09-23 → 10-21; `wc/` study folders cited 167 times | Disk was full on 10-22. 15m bars from before ~2025-11-30 are **no longer on MEXC**, so this is the only copy | **Owner only** | Copy the folder (and any `wc/` left in %TEMP%) to cloud or external disk with checksums; ~30-60 min; size unknown (≥0.5 GB) |
| Railway `/data`: feature store, ~900-row shadow ledger, R paths, scan and tick journals, state | Railway only (repo: 09-07 snapshot; laptop: to 10-21) | Lost if the service, volume or billing stops; some journals overwrite themselves (`archive_evidence.py` header) | **Owner only** | One read-only `tools/archive_evidence.py` run after `railway login`, or a supervised read-only session as on 11-26. The bot is not changed. Post-10-20 rows go to QA 2, sealed |

## 7. Decisions for the owner

1. Where the kit lives: a new private repo (recommended) or a folder in this repo.
2. Durable storage for a few GB of data. Provider and cost are unknown; we expect it to be small.
3. Copy the laptop archive (about 30-60 min of his time).
4. A one-off read-only export of `/data` and the MEXC history, and whether to repeat it every ≤60 days while the bot keeps running. If he does nothing, both are lost over time.

**Risk we can only flag:** the bot keeps trading about $34.62 with nobody watching. The $140 floor is not enforced (`07_qa1.md` §3), and the venue excludes UK residents (`02_architect.md`). The kit does not depend on the bot staying up.
