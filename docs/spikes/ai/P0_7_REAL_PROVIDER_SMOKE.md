# P0.7 — Real Provider Smoke

Date: 2026-10-10  
Private capture source: local P0.6 WGC frame for anchor `A04_post_halftime_explode` (PNG **not** committed)  
Known frame SHA-256: `e0370b197addc71af40527b54cb2670748c9659971f3bed295e30723299824fa`  
Redacted result: `docs/spikes/ai/fixtures/provider_smoke_result.redacted.json`

## Goal

Prove the real external provider path:

```text
known structured evidence
+ one or more real P0.6 capture frames
        ↓
existing AiProvider
        ↓
OpenAI Responses API
        ↓
strict structured output
        ↓
existing schema validation
        ↓
evidence_id / frame_id post-validation
        ↓
accepted or explicitly rejected result
```

Out of scope: Rule Engine, production incidents, UI, automatic POV, E2E orchestration.

## Audit vs baseline (before edits)

### Already present

| Piece | Status |
| --- | --- |
| `AiProvider` protocol | Present |
| `OpenAiProvider` + `client.responses.parse(...)` | Present |
| `CoachIncidentAnalysis` Pydantic schema | Present |
| Local evidence/frame ID validator | Present |
| Optional `[ai]` extra (`openai`) | Present |
| API key boundary (analyzer-side only) | Present by architecture |

### Missing for P0.7 (implemented)

| Gap | Fix |
| --- | --- |
| Real opt-in provider smoke with private P0.6 frame | `tests/test_ai_real_provider_smoke.py` |
| `store=false` | request + `OpenAiProvider` |
| Versioned prompt | `prompts/provider_smoke_v001.md` |
| Request fingerprint | `fingerprint.py` |
| Typed failure mapping | `errors.py` |
| Smoke evidence pack + lineage metadata | `smoke_pack.py` |
| Full post-validator | `validate_analysis_result` |
| Explicit image `detail` | request + fingerprint |
| OpenAI-compatible `base_url` (relay) | `OpenAiProvider(base_url=...)` |
| Redacted fixture | `fixtures/provider_smoke_result.redacted.json` |

Earlier milestones (P0.2–P0.6A) were not reopened.

---

## Environment / configuration

| Variable | Role |
| --- | --- |
| `CS2_COACH_OPENAI_API_KEY` | Preferred analyzer-side key |
| `OPENAI_API_KEY` | Fallback if coach-prefixed key unset |
| `CS2_COACH_OPENAI_BASE_URL` / `OPENAI_BASE_URL` | OpenAI-compatible relay base (e.g. `https://…/v1`) |
| `CS2_COACH_AI_MODEL` | Model config |
| `CS2_COACH_AI_IMAGE_DETAIL` | `auto` \| `low` \| `high` |
| `CS2_COACH_AI_REAL_SMOKE=1` | Opt-in gate |
| `CS2_COACH_AI_SMOKE_FRAME` | Private local PNG path |
| `CS2_COACH_AI_SMOKE_WRITE_FIXTURE=1` | Write redacted fixture after success |

Normal CI leaves `CS2_COACH_AI_REAL_SMOKE` unset/false.

---

## VERIFIED

1. **Architecture preserved** — rules/storage/renderer do not consume OpenAI response objects; model stays configuration.
2. **Responses Structured Outputs** — `client.responses.parse(..., text_format=CoachIncidentAnalysis)` with openai SDK `2.54.0`.
3. **`store=false`** — smoke request and provider path set `store=False`.
4. **Real image input** — local P0.6 WGC `frame-0008.png` (SHA-256 matches A04 fixture hash) accepted as `input_image` with `detail=auto`.
5. **Real provider call succeeded** — relay `https://nikoapi.xyz/v1`, model `gpt-6.1-sol`, ~210s wall time for one smoke request.
6. **Schema validation** — structured output parsed as `CoachIncidentAnalysis` (severity/confidence/facts/observations/…).
7. **Evidence/frame post-validation** — `validation_ok=true`; fact cited `ev-smoke-a04-bomb-exploded`; observation cited `frame-smoke-a04-0008`; 4 uncertainties (visual insufficiency allowed).
8. **Request fingerprint** — deterministic SHA-256 `9d73134b78a5563c30d34722de45de887180a89b1ac4d9afaf177ecc8f46b793` for this logical request; unit tests cover mutation/exclusion.
9. **Privacy** — no API key / base64 / absolute private path / Steam ID / player name in committed fixture or git tree; `runtime/**` remains ignored.
10. **CI suites** — `pnpm test`, `cargo test` (89 passed / 17 ignored real-CS2), analyzer `pytest` 112 passed + opt-in smoke skipped in normal runs; private P0.2 with `CS2_COACH_REAL_DEMO` still passes.
11. **Typed failures** — unit-tested mapping for auth / timeout / rate-limit / network / 5xx / refusal / incomplete (no real API spend).

## DERIVED

1. Smoke anchor `A04_post_halftime_explode` is sufficient for contract proof even when visual POV is weak (`uncertainties_count=4`).
2. Official `api.openai.com` rejects this relay key; OpenAI-compatible `base_url` is required for GPT 中转.
3. Image detail `auto` is adequate for ~1282×752 smoke cost/quality; geometry remains capture-contract owned.
4. Pydantic `CoachIncidentAnalysis` is the machine schema gate aligned with `coach_incident_analysis.schema.json`.

## UNRESOLVED

1. Product retention policy beyond smoke `store=false` (user-controlled retention not implemented).
2. Whether `gpt-6.1-sol` remains a supported default after productization (must stay configuration).
3. Multi-frame smoke (acceptance allows ≥1; this run used one A04 frame).
4. Relay-specific SLA / Responses API feature parity over time (treat as capability-probed).

Do **not** promote unresolved items to product invariants.

---

## Contract notes

### Request fingerprint

Includes: provider, model, prompt/schema/AI contract versions, normalized facts, evidence/frame IDs, frame SHA-256, image detail.  
Excludes: API key, auth material, absolute paths, random request IDs, timestamps, raw image bytes.

### Post-validation

Structured Outputs prove shape. Provenance still requires `validate_analysis_result`.

### Failure taxonomy

| Condition | Code |
| --- | --- |
| Auth failure | `AI_AUTH_FAILED` |
| Rate limit | `AI_RATE_LIMITED` (retryable) |
| Timeout | `AI_TIMEOUT` (retryable) |
| Network | `AI_NETWORK_FAILED` (retryable) |
| Provider 5xx | `AI_PROVIDER_5XX` (retryable) |
| Refusal | `AI_REFUSED` |
| Incomplete | `AI_INCOMPLETE_RESPONSE` |
| Bad structured output | `AI_STRUCTURED_OUTPUT_INVALID` |
| Evidence/frame contract fail | `AI_EVIDENCE_VALIDATION_FAILED` |
