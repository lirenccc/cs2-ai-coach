# P1.4 — Click-to-CS2 Incident Replay

Date: 2026-10-11  
Phase label: `P1.4`  
Depends on: Match Review v1, Rule Engine R001–R003, P0.5 NetCon, P0.5A DemoTick calibration  
Redacted plan fixture: `docs/spikes/replay/fixtures/p1_4_replay_plans.redacted.json`

## Scope

First desktop-to-CS2 product interaction:

```text
Match Review → select Incident → ▶ View in CS2
→ native resolves IncidentReplayPlan
→ stage exact Demo
→ seek calibrated DemoTick (with pre-roll)
→ resume at ~0.5x
```

Out of scope: automatic POV, keyframe capture orchestration, AI coaching, R004+,
video export, dense tick UI, live-match assistance.

## Verdict classes

| Class | Meaning |
| --- | --- |
| **VERIFIED** | Exercised by CI unit tests and/or private real-Demo / GUI smoke |
| **DERIVED** | Follows from prior P0.5 / P0.5A / P1.3 contracts |
| **UNRESOLVED** | Explicit remaining limitation |

## Architecture boundary

```text
React (match_id, incident_id only)
  → Tauri invoke view_incident_in_cs2
    → authenticated sidecar GET .../replay-plan
    → IncidentReplayCoordinator (Rust)
      → Demo staging + NetCon session
      → DemoTick seek + settle + timescale + resume
```

Renderer must **not** receive / supply:

- sidecar session token / random analyzer port
- NetCon host/port
- absolute Demo path
- raw console strings
- renderer-chosen seek ticks

## IncidentReplayPlan contract

Version `1.0.0`. Authoritative fields (snake_case wire):

| Field | Notes |
| --- | --- |
| `match_id` / `incident_id` / `rule_id` | Stable domain IDs |
| `round_id` / `round_number` | From deterministic review |
| `start_demo_tick` / `anchor_demo_tick` / `end_demo_tick` | Preserved even when seek differs |
| `seek_demo_tick` | Pre-roll result (DemoTick) |
| `replay_tick_domain` | Always `DemoTick` for production |
| `replay_semantics_version` | `p0.5a-2026-10-10` |
| `timing_source` | `match.tick_rate` or `structural_probe.derived_tick_rate` or degraded |
| `verified_tick_rate` | Null when degraded |
| `pre_roll_seconds` | Default `5.0` |
| `settle_policy` / `settle_debounce_ms` | Fixed debounce (default 2000 ms) |
| `timescale` / `auto_resume` | Default `0.5` / `true` |
| `pov_auto_selected` | Always `false` in P1.4 |
| `demo_sha256` | Exact imported Demo identity |
| `demo_source_path` | **Native-only** (stripped from renderer-safe view) |

API:

```text
GET /v1/matches/{match_id}/incidents/{incident_id}/replay-plan
```

Missing incident → `INCIDENT_NOT_FOUND` (no fallback tick).

## Pre-roll policy (VERIFIED)

```text
candidate = anchor_demo_tick - round(pre_roll_seconds * ticks_per_second)
seek_demo_tick = max(round_start_demo_tick, candidate)
```

- Never `5 * 64` as a global constant.
- `ticks_per_second` from `match.tick_rate`, else structural-probe `derived_tick_rate` for the exact Demo file.
- If neither is available → land at authoritative `start_demo_tick` (`timing_degraded=true`).
- Do not cross into the previous round.

## DemoTick invariant (VERIFIED / DERIVED)

Production seek uses `ReplayTickDomain::DemoTick` only (`demo_gototick`).  
`server_tick` cannot enter the production replay plan or seek command.  
P0.5A calibration semantics version must match (`p0.5a-2026-10-10`).

## Build / calibration guard (VERIFIED)

Before semantic seek:

```text
observed CS2 build (steam.inf + buildid)
  vs
calibrated build (P0.5A / P0.6A frozen identity)
```

Mismatch → `REPLAY_CALIBRATION_BUILD_MISMATCH` (fail closed; do not claim positioned).

## Demo staging (VERIFIED)

- Resolve `match → demo_sha256 → original_path` inside analyzer/native only.
- Prefer existing import source; else reuse managed `{sha}.dem` under `runtime/demo-staging`.
- Missing both → `REPLAY_SOURCE_MISSING` (never load a similarly named Demo).
- Staging remains SHA-named and idempotent; original Demo is not modified.

## Session reuse / concurrency (VERIFIED)

- Single native coordinator owns playdemo / seek / timescale / resume.
- Concurrent policy: **newer request supersedes** prior in-flight generation (`REPLAY_ACTION_SUPERSEDED` for late results).
- Same Incident re-click: safe; reuses process/NetCon/staged Demo when SHA matches and reseeks.
- Does not launch unlimited CS2 processes or create unlimited staged copies.

## UI state model (VERIFIED)

```text
Idle → Preparing → (LaunchingCS2 / Connecting / LoadingDemo / Seeking) → Playing | Failed
```

Optional controls after Playing: Pause / Resume / 0.5x / 1.0x (typed actions only).

Match Review filters/selection remain usable when replay fails.  
POV is displayed as **not automatically selected**.

## Position evidence (DERIVED)

Result separates:

- `command_delivery_ok`
- `requested_demo_tick`
- `engine_position_evidence?` (parsed `Demo Skipping: skipping to demo tick N (game tick M)` when present)

Write success alone is not position proof.

## Real GUI / host smoke

Private fixture: `9208210907649202700_0` (not committed).  
SHA-256: `d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec`.

### Tauri desktop (VERIFIED 2026-10-11)

1. `pnpm tauri dev` → Vite `:1420` ready, `cs2-ai-coach.exe` running
2. Sidecar spawn path unchanged (random loopback + session token)
3. Match already imported in local `runtime/app.db` → Match Review loads 106 incidents (R001/R002/R003)
4. UI exposes ▶ View in CS2 on the selected incident (IDs only)

### Native Click-to-CS2 probe (VERIFIED, ignored CI)

```powershell
$env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.dem"
cargo test -p cs2-ai-coach --lib cs2::integration::probe_click_to_cs2_incident_seek -- --ignored --nocapture
```

Host result (2026-10-11):

| Rule | Seek DemoTick | Engine skip evidence |
| --- | ---: | --- |
| R001 | 56689 | delivery ok; skip line not observed this run |
| R002 | 51625 | delivery ok; skip line not observed this run |
| R003 | 48358 | `engine_skip=Some(48358)` matches requested seek |

Idempotent reseek of each plan succeeded in the same session.  
POV not auto-selected (by design).

Redacted mid-match plan examples (from fixture):

| Rule | Round | Anchor DemoTick | Seek DemoTick | Timing source |
| --- | ---: | ---: | ---: | --- |
| R001 | 10 | 57009 | 56689 | structural_probe.derived_tick_rate (~64 Hz measured) |
| R002 | 9 | 51945 | 51625 | structural_probe.derived_tick_rate |
| R003 | 8 | 48678 | 48358 | structural_probe.derived_tick_rate |

## Failure cases (typed remediation)

| Case | Code |
| --- | --- |
| Invalid / missing incident | `INCIDENT_NOT_FOUND` |
| Demo source gone | `REPLAY_SOURCE_MISSING` |
| CS2 build ≠ calibrated | `REPLAY_CALIBRATION_BUILD_MISMATCH` |
| CS2 running without NetCon | `CS2_ALREADY_RUNNING_WITHOUT_NETCON` |
| Workshop Tools missing | `CS2_TOOLS_UNAVAILABLE` |
| NetCon lost mid-action | `NETCON_CONNECTION_LOST` |
| Sidecar down | `SIDECAR_*` |
| Superseded click | `REPLAY_ACTION_SUPERSEDED` |

No infinite retry. No hangs by design (bounded connect/command timeouts).

## Remaining POV limitation (UNRESOLVED)

Automatic observer/player switching is **not** implemented.  
Correct match + round/time is sufficient for P1.4 success.  
Wrong POV is not classified as a seek failure.

## Security / privacy

Preserved: no DLL injection, no process memory, no `-insecure`, no arbitrary console,
no arbitrary TCP target, no renderer-visible NetCon credentials, offline Demo only.  
Private Demo / screenshots / Steam IDs are not committed.

## CI

- Analyzer: `tests/test_incident_replay.py`
- Contracts: `IncidentReplayPlan` / `ViewIncidentInCs2Result` shape
- Rust: `cs2::incident_replay` unit tests
- React: `review/replayAction.test.ts` concurrency
- Real CS2 / full GUI: manual (not required in CI)
