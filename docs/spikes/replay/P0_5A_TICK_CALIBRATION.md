# P0.5A Replay Tick Calibration

Date: 2026-10-10  
Host OS: Windows 10/11 (`win32`)  
Private fixture: `9208210907649202700_0` (zip/dem **not** committed)  
Replay semantics version: `p0.5a-2026-10-10`  
Machine-readable redacted result: `docs/spikes/replay/fixtures/tick_calibration.redacted.json`  
Anchor set: `docs/spikes/replay/fixtures/tick_calibration_anchors.redacted.json`

## Verdict

**Authoritative `demo_gototick` domain: `DemoTick`**

Symmetric rejection of `ServerTick` as the raw `demo_gototick` argument held across all required match regions on this build + fixture.

Production API freeze:

- `GOTO_TICK_DOMAIN_CALIBRATED = Some(DemoTick)`
- `ReplayCommand::go_to_tick` / `ReplaySeekPosition::DemoTick` accepted
- `ReplaySeekPosition::ServerTick` rejected at the production `demo_gototick` boundary
- No silent `demo_tick ↔ server_tick` translation
- Parser/storage dual-clock fields unchanged

This result is **build-specific**. Future CS2 updates must re-run `probe_replay_tick_calibration` (or invalidate `REPLAY_SEMANTICS_VERSION`).

## CS2 build tested

| Field | Value |
| --- | --- |
| Product | Counter-Strike 2 (`appID=730`) |
| `steam.inf` PatchVersion | `1.41.9.0` |
| `steam.inf` ClientVersion | `2000930` |
| Steam `buildid` | `25815307` |
| Launch path | `steam.exe -applaunch 730 -netconport <ephemeral> -tools` |
| Fixture SHA-256 | `d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec` |

## Selected redacted anchors

Deterministic algorithm `p0_5a_v1` over structural-probe events (no player names / Steam IDs).

| Anchor | Category | Round | Event | demo_tick | server_tick |
| --- | --- | ---: | --- | ---: | ---: |
| A01_early_plant | early_match | 1 | bomb_planted | 4354 | 8133 |
| A03_near_bot_death | near_bot_takeover | 6 | player_death | 34176 | 37954 |
| A02_mid_defuse | middle_match | 7 | bomb_defused | 42294 | 46073 |
| A06_mid_ak_hs | middle_match | 8 | player_death | 47548 | 51326 |
| A04_post_halftime_explode | after_halftime | 13 | bomb_exploded | 79639 | 83418 |
| A05_late_death | late_match | 15 | player_death | 88430 | 92208 |

Controller identities in the anchor fixture are redacted as `C<userid>` only.

## Experiment matrix

For every anchor:

| Candidate | Repeats | Command |
| --- | ---: | --- |
| raw `demo_tick` | 2 | `demo_gototick <demo_tick>` |
| raw `server_tick` | 2 | `demo_gototick <server_tick>` |

No pre-translation. Settle duration used: **2000 ms**.  
Evidence classes stored separately:

- `command_delivery` (`write_ok`, raw preview)
- `replay_position` (engine skip parse / optional visual)

NetCon ACK / `write_ok` alone is **not** position proof.

## Engine position evidence

On this build, successful seeks often emit:

```text
Demo Skipping: skipping to demo tick <N> (game tick <M>) ...
```

Interpretation (observed, not assumed a priori):

- `<N>` = engine **demo tick** ≡ parser `demo_tick`
- `<M>` = engine **game tick** ≡ parser `server_tick` (occasionally ±1)

### DemoTick candidates (winning)

| Anchor | Observed skip (repeat with data) | Matches anchor |
| --- | --- | --- |
| A01 | demo 4354 / game 8133 | yes (offset 0) |
| A03 | demo 34176 / game 37955 | yes (demo offset 0; game ±1) |
| A02 | demo 42294 / game 46073 | yes |
| A06 | demo 47548 / game 51327 | yes (game ±1) |
| A04 | demo 79639 / game 83418 | yes |
| A05 | demo 88430 / game 92209 | yes (game ±1) |

### ServerTick candidates (losing)

Supplying the parser `server_tick` value makes the engine treat it as a **demo tick**:

| Anchor | Observed skip | Matches anchor |
| --- | --- | --- |
| A01 | demo 8133 / game 11912 | no (~+3779 demo ticks) |
| A03 | demo 37954 / game 41733 | no |
| A06 | demo 51326 / game 55105 | no |
| A04 | demo 83418 / game 87197 | no |
| A05 | demo 92208 / game 95987 | no |

A02 server-tick repeats did not always return a parseable skip line; whenever a skip was observed for server candidates on other anchors, they consistently missed the event.

Decision helper output: `DemoTickAuthoritative`.

## Seek repeatability and error

- When the engine emits a skip line for a **DemoTick** candidate, landed demo tick equals the request (**offset 0**).
- Repeated seeks to the same value often produce **empty** console responses (no second skip line) but do not contradict the first observation; empty ≠ failure.
- Measurable seek error (engine-reported): **0 demo ticks**; game tick sometimes **±1**.
- Visual operator verification was optional (`CS2_COACH_CALIBRATION_VERIFICATIONS`); this run used engine skip reports as primary `replay_position` evidence.

## `demo_info` reliability

- `demo_info` after load can return header/contents text (map, patch, staged name).
- It is **not** a reliable continuous “current tick” source.
- Prefer parsing `Demo Skipping:` from the seek response itself (with extended drain).
- Field `demo_info_reliable` in the result JSON means “some parseable tick/skip evidence appeared in the run”, not that every `demo_info` call is trustworthy.

## `demo_pauseatservertick` (calibration-only)

Issued after the seek matrix against the defuse server tick `46073`:

```text
Desired pause tick 46073 is not in the future. The current tick is 95988. Pausing playback immediately.
```

Findings:

- Command write accepted.
- Engine speaks in **server/game tick** for this pause helper.
- It does **not** seek backward to the target; if the tick is already past, it pauses immediately.
- **Not** adopted as a production seek dependency.
- `reliable_pause_at_event`: unverified / not relied upon.

## Pre-roll (fixture timing metadata)

Using A02 (`demo_tick=42294`, round start `36503`, `verified_tick_rate=64.0` from structural probe — **not** a global constant):

| Pre-roll seconds | Result demo tick | Clamped to round start |
| ---: | ---: | --- |
| 0 | 42294 | no |
| 2 | 42166 | no |
| 5 | 41974 | no |

Clamp-to-round-start behavior is covered by unit tests (and would apply when `anchor - seconds*rate < round_start`). No cross-round pre-roll.

## Failure modes observed during calibration

| Failure | Notes |
| --- | --- |
| `FATAL ERROR: CopyNewEntity: invalid class index (221), out of range 0` | Seen during earlier runs that sought **`demo_gototick 0`** as a nudge and/or stressed reload under `-tools`. Harness now **forbids tick-0 nudges**. |
| Loading UI showing Deathmatch during crash | Correlated with the same fatal path; treat as engine/tools fragility, not a product feature. |
| Empty NetCon responses | Common on repeat seeks; do not treat as ACK success/failure. |

## Security assumptions (unchanged from P0.5)

1. Ephemeral `-netconport`, loopback client only, typed allowlist.
2. Engine still binds `0.0.0.0:<port>` — production firewall requirement remains.
3. No `-insecure`, no injection, no process memory, no renderer raw console.
4. `demo_pauseatservertick` is allowlisted for calibration/session typed API only; not a free-form console.

## Unresolved replay assumptions

1. Future CS2 builds may change `demo_gototick` domain labeling or skip-line format.
2. Game-tick ±1 vs parser `server_tick` is tolerated but not fully explained.
3. `demo_pauseatservertick` cannot rewind; production incident playback must not depend on it without a forward-only design.
4. POV / camera automation and capture remain out of scope (P0.6+).
5. Absolute-path `playdemo` stability still unproven (staging-to-csgo name used).

## Parser / storage confirmation

This spike did **not** change Python parser behavior, Storage v2 schema, or sidecar HTTP contracts. Dual-clock columns remain authoritative in storage; only the desktop replay seek contract was frozen to DemoTick for `demo_gototick`.

## How to re-run

```powershell
$env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.zip"
# optional: $env:CS2_COACH_CALIBRATION_REPEATS = "2"
# optional: $env:CS2_COACH_CALIBRATION_OUT = "...\tick_calibration.redacted.json"
cargo test -p cs2-ai-coach --lib probe_replay_tick_calibration -- --ignored --nocapture --test-threads=1
```

Do **not** seek to demo tick `0` as a settle/nudge under `-tools` on this build family.
