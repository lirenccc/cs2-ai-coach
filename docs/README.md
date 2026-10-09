# Documentation Index

## Canonical design (start here)

| Doc | Purpose |
| --- | --- |
| [00_PRODUCT_SCOPE.md](00_PRODUCT_SCOPE.md) | Product boundary and non-goals |
| [01_SYSTEM_ARCHITECTURE.md](01_SYSTEM_ARCHITECTURE.md) | Process model and adapters |
| [02_DEMO_PIPELINE.md](02_DEMO_PIPELINE.md) | Import, parse, normalize |
| [03_CS2_CONTROL_AND_CAPTURE.md](03_CS2_CONTROL_AND_CAPTURE.md) | NetCon and window capture |
| [04_ANALYSIS_ENGINE.md](04_ANALYSIS_ENGINE.md) | Deterministic rules / incidents |
| [05_AI_PIPELINE.md](05_AI_PIPELINE.md) | Evidence-linked coaching AI |
| [06_DATA_AND_API.md](06_DATA_AND_API.md) | Storage and API shapes |
| [07_TEST_SECURITY_RELEASE.md](07_TEST_SECURITY_RELEASE.md) | Test and release gates |
| [08_RISK_REGISTER.md](08_RISK_REGISTER.md) | Known risks |
| [09_CURSOR_WORKFLOW.md](09_CURSOR_WORKFLOW.md) | How to drive Cursor on this repo |
| [10_ACCEPTANCE_CRITERIA.md](10_ACCEPTANCE_CRITERIA.md) | Done means |

Also:

- [FULL_TECHNICAL_DESIGN.md](FULL_TECHNICAL_DESIGN.md) — concatenated design pack (reference dump; prefer numbered docs above)
- Root [`SOURCE_BASELINE.md`](../SOURCE_BASELINE.md) — verified external dependency links

## Spikes / verified research

| Path | Purpose |
| --- | --- |
| [spikes/real-demo/P0_2_REPORT.md](spikes/real-demo/P0_2_REPORT.md) | Independent PBDEMS2 probe of the private fixture |
| [spikes/real-demo/SCHEMA_DECISIONS.md](spikes/real-demo/SCHEMA_DECISIONS.md) | Identity / tick / round schema decisions from that fixture |
| [spikes/real-demo/VALIDATION.md](spikes/real-demo/VALIDATION.md) | v0.2 scaffold validation notes |

Private `.dem` files are never committed. Golden redacted summary lives under `fixtures/real-demo/expected/`.

## Ops

| Path | Purpose |
| --- | --- |
| [ops/SIDECAR_PACKAGING.md](ops/SIDECAR_PACKAGING.md) | Tauri-managed analyzer packaging plan (P0.3) |

## Cursor prompts

| Path | Purpose |
| --- | --- |
| [prompts/P0_2_FULL_PARSER.md](prompts/P0_2_FULL_PARSER.md) | Next prompt: full demoparser2 normalization vs structural probe |
