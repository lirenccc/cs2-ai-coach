# P0.6A — Event / Identity / Capture Validation

Date: 2026-10-10  
Private fixture: `9208210907649202700_0` (not committed)  
Fixture SHA-256: `d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec`  
CS2 build (calibrated family): Patch `1.41.9.0` / Client `2000930` / buildid `25815307`

## Goal

Close semantic gaps before deterministic coaching rules depend on them:

```text
normalized parser event
 → stable identity / controller / pawn-life
 → authoritative DemoTick
 → P0.5A calibrated seek
 → P0.6 capture
 → traceable frame evidence
```

This milestone is **validation and contract-hardening only**. Parser, Storage v2, P0.5A, and P0.6 capture backends were not redesigned.

## Versioned contracts

| Contract | Version |
| --- | --- |
| `evidence_lineage_version` | `p0.6a-2026-10-10` |
| `identity_semantics_version` | `p0.6a-2026-10-10` |
| `round_side_contract_version` | `p0.6a-2026-10-10` |
| `geometry_policy_version` | `p0.6a-2026-10-10` |
| `capture_manifest_version` | `p0.6-2026-10-10` (unchanged from P0.6) |
| `replay_calibration_version` | `p0.5a-2026-10-10` (unchanged) |

## Redacted fixtures

| File | Purpose |
| --- | --- |
| `fixtures/pawn_lifecycle.redacted.json` | Multi-life controller + pawn-handle reuse |
| `fixtures/bot_takeover_timeline.redacted.json` | A03 takeover before/after attribution |
| `fixtures/round_side_states.redacted.json` | Side across r1 / r12 / r13 / r18 |
| `fixtures/capture_at_event.redacted.json` | Lineage + semantic results for capture-at-event |
| `fixtures/capture_manifest.redacted.json` | P0.6 manifest sample (still valid) |

No Steam IDs, player names, screenshots, or Demo bytes are committed.

---

## VERIFIED

1. **Controller → multiple pawn lives**  
   Controller `C3` has deaths on pawn handles `-1370816145` and `432572463` (including both in round 6 around takeover). `(round, player)` is **not** a unique life key.

2. **Pawn handle is not match-global**  
   Handle `432572463` appears on controllers `C3`, `C4`, and `C8` after takeovers. Storage must keep `controller_session_id` + `pawn_handle`.

3. **BOT takeover death attribution**  
   Sequence at DemoTick `33717`: pre-death (`C3`, pawn `-1370816145` @ `33462`) → takeover → post-death (`C3`, pawn `432572463` @ `34176`). Post-takeover death credits the taking-over controller.

4. **Halftime side switch**  
   Awpy tick `side`/`team_num` at freeze_end: all sampled identities switch between round 12 and 13. Round 1 ≡ round 12; round 13 ≡ round 18. Initial roster team must **not** be reused permanently.

5. **Capture-at-event lineage**  
   Calibrated `ReplaySeekPosition::DemoTick` + settle + WGC yields manifests with `requested_demo_tick` and `replay_semantics_version`. ServerTick cannot enter the production seek path. DemoTick 0 nudge remains forbidden.

6. **Paused duplicate hashes**  
   Same hash + replay paused ⇒ allowed stable frame (`AllowedStableWhilePaused`). Not treated as capture failure.

7. **Calibration build guard**  
   Observed build ≠ calibrated fixture build ⇒ `REPLAY_CALIBRATION_BUILD_MISMATCH` (no silent “calibrated” claim).

8. **Geometry mismatch acknowledged**  
   Client `1280×720` vs WGC content `1282×752` is expected. Policy records window/client/WGC/stored sizes + crop status; does not assume equality.

---

## DERIVED

1. Kill/damage credit around takeover uses attacker/victim `userid` / pawn fields at the event tick (same controller model as deaths).
2. Canonical client-area crop may be planned from screen-origin inset or small even chrome deltas; otherwise raw frame is preserved with `RawPreservedCropUnreliable`.
3. Round winners from parser rounds are available but are **not** a substitute for per-player side at a tick.

---

## UNRESOLVED

1. Structural-probe `bot_takeover` emits `botid == userid` for all 12 takeovers in this fixture — cannot authoritatively separate bot controller id without richer entity state.
2. Automatic POV / visual event recognition from captured frames (several anchors marked `not_visually_observable`).
3. Trade-opportunity attribution across takeover + side (needs side-aware teammate policy).
4. Whether Awpy tick equals DemoTick in all maps/builds (freeze samples matched DemoTick freeze_end on this fixture — treat as fixture-verified, not universal).

Do **not** promote unresolved items to product invariants.

---

## Contracts for rule consumers

### Evidence lineage

Optional fields stay empty when unknown. Never invent `player_identity_id` from display names.

### `RoundPlayerState`

```text
round_id, player_identity_id, side, team_identity?, source
```

**Authoritative source (this fixture):** tick/entity `side` / `team_num` at a round-relevant DemoTick (e.g. freeze_end).  
**Forbidden:** permanent use of initial roster side across the side transition; inferring halftime from round number alone when tick evidence exists.

### Takeover attribution (summary)

| Category | Credit | Certainty |
| --- | --- | --- |
| Death | Taking-over controller / identity | VERIFIED |
| Kill / damage | Controller at event tick | DERIVED |
| Survival | Open `PawnLife` for session | VERIFIED |
| Trade | Needs side-aware policy | UNRESOLVED |

### Geometry policy

```text
raw capture + geometry metadata
 → deterministic canonical client crop when reliable
 → else preserve raw and mark crop_status
```

### Hash policy

```text
same hash + paused → allowed
same hash + expected advancing → possible stale (time/state policy)
```

---

## Tests

### CI-safe

- Python: `tests/test_p0_6a_evidence_contracts.py`
- Rust: `capture::lineage`, `capture::geometry`, `capture::hash_policy`, `ReplayCaptureContext::require_calibrated_build`

### Ignored / manual (require CS2)

- `probe_capture_at_event_semantics`
- existing P0.6 probes (`probe_capture_after_calibrated_seek`, resize, minimized, WGC burst, …)

CI must not require CS2.

---

## Confirmation

- P0.2 parser behavior: unchanged  
- Storage v2 identity hierarchy: compatible (validated, not rewritten)  
- P0.5A DemoTick calibration: unchanged; build guard added at capture evidence boundary  
- P0.6 WGC primary path: unchanged; geometry/hash/lineage contracts layered on top  
