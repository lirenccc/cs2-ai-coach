# Rule Engine v1 — Deterministic Core

Date: 2026-10-10  
Contract: `rule-engine-v1-2026-10-10`  
Thresholds: `rule-thresholds-v1-2026-10-10`

## Scope

First deterministic coaching batch:

```text
R001 Opening Death
R002 Untraded Death
R003 Advantage Loss Candidate  (ADVANTAGE_LOSS_CANDIDATE)
```

Out of scope for the rule-engine milestone: Isolated Contact, Repeat Peek,
click-to-CS2, production AI orchestration, AI-based rule decisions.

Timeline/Incident UI is delivered separately as Match Review v1
(`docs/spikes/review/MATCH_REVIEW_V1.md`) and consumes these rule outputs
read-only.

## VERIFIED

1. Rules consume only normalized structured inputs (`RuleContext`).
2. Same DemoTick life-ending events are applied as one alive-state batch; input
   permutation tests pass for R003.
3. Candidate IDs are stable hashes of
   `(rule_id, rule_version, match_id, round_id, subject, anchor_demo_tick)`.
4. R002 returns `UNRESOLVED` (not a boolean false) when trade attribution crosses
   unresolved takeover.
5. R003 uses authoritative round `winner` / `win_reason` (bomb/defuse/time included).
6. Private fixture SHA-256
   `d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec`
   evaluates offline without CS2 / WGC / NetCon / OpenAI.
7. Redacted private summary:
   `docs/spikes/rules/fixtures/p0_2_rule_engine_summary.redacted.json`

## DERIVED

1. Alive counts = freeze_end alive identities + batched deaths.
2. R003 severity from peak advantage (2→3, 3→4, ≥4→5); confidence stays `1.0`
   only for fully resolved evaluations.
3. `rule_context_from_parsed` maps `ParsedDemo.selected_ticks` @ `round_freeze_end`
   into round-side / initial alive.

## UNRESOLVED / fixture observations

1. On the private fixture, demoparser2 freeze_end ticks may expose fewer than 10
   players with `team in {CT,T}` (observed 7: 4 CT + 3 T). Deaths for identities
   absent from that alive set are ignored for counts — not invented.
2. Structural-probe `botid == userid` takeover ambiguity remains as in P0.6A;
   rules honor explicit unresolved flags rather than guessing.
3. R002 nearest-teammate distance / LOS metrics are not yet attached.

Do not promote unresolved items to product invariants.

## Private regression (opt-in)

```powershell
$env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.dem"
python -m pytest services\analyzer\tests\test_rule_engine_real_demo.py -q
python -m pytest services\analyzer\tests\test_structural_probe_real_demo.py -q
```
