# Match Review v1 — Offline deterministic projection

Date: 2026-10-11  
Contract: `match-review-v1` / `schema_version=1.0.0`  
Depends on: Rule Engine v1 (`rule-engine-v1-2026-10-10`)

## Scope

First useful offline review surface:

```text
Match → Round → Timeline → Incident list → Incident evidence
```

Requires only local offline analysis. Does **not** require CS2, NetCon, Windows
capture, OpenAI, or AI-generated coaching.

Out of scope: R004+, Click-to-CS2, automatic seek, POV, keyframe planning,
AI explanation UI, video export, longitudinal coaching.

## Authoritative boundary

| Layer | Owns |
| --- | --- |
| Analyzer | round/player/side/alive identity, rule evaluation, incidents, metrics, evidence, UNRESOLVED |
| Renderer | request / filter / sort / select / format / render |

The React UI must **not** recompute opening death, trade status, advantage loss,
alive counts, round winner, takeover attribution, or current side.

## API

```text
GET /v1/matches/{match_id}/review
```

Authenticated via Tauri → sidecar session token. The renderer never receives the
token or random loopback port.

Tauri commands:

```text
import_demo(path)
get_match_review(match_id)
```

## Shared contract (`MatchReview`)

Wire format is snake_case JSON (shared in `packages/contracts`).

Top-level fields:

```text
schema_version
rule_engine_contract_version
thresholds_version
match
players[]
rounds[]
timeline_events[]
incidents[]          # emitted IncidentCandidates only
analysis_coverage[]  # per-rule matched / unresolved counts
unresolved_evaluations[]
```

Privacy: no absolute demo paths, no Steam IDs required in fixtures, no session
tokens.

## Ordering

| Collection | Canonical order |
| --- | --- |
| rounds | `round_number` ascending (never lexicographic opaque IDs) |
| timeline | `demo_tick`, then `event_id` |
| incidents | `round_number`, `anchor_demo_tick`, `rule_id`, `incident_id` |

## Same-tick presentation

Events sharing a DemoTick are grouped visually. Within a group, `event_id` order
is stable but **not** claimed as sub-tick chronology.

## UNRESOLVED presentation

Unresolved rule evaluations are listed under analysis coverage /
`unresolved_evaluations` with structured `reason_code` values such as:

```text
TAKEOVER_ATTRIBUTION_UNRESOLVED
MISSING_SIDE_PROVENANCE
MISSING_ALIVE_PROVENANCE
```

They must never appear in the main Incident list as coaching mistakes.

## Evidence drawer

Selecting an incident shows rule id/version, incident id, round, subject, tick
window, severity, confidence (separate), metrics, and evidence items with
inspectable evidence IDs. R003 exposes peak advantage / alive counts / peak tick /
round outcome / thresholds version when present in engine metrics/evidence.

## Timing

Human-readable times use `match.tick_rate` when present. No hard-coded 64 Hz.

## Future hooks (not implemented here)

| Hook | Preserved fields |
| --- | --- |
| View in CS2 | `incident_id`, `start_demo_tick`, `anchor_demo_tick`, `end_demo_tick` |
| AI panel | incident remains valid without AI; later attaches to selected incident |

## Private smoke

```powershell
$env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.dem"
python -m pytest services\analyzer\tests\test_match_review_real_demo.py -q
```

Redacted summary only:
`docs/spikes/review/fixtures/p0_2_match_review_summary.redacted.json`
