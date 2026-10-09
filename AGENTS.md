# Project Instructions — CS2 AI Coach

## Product invariant

This is an offline CS2 demo coaching product. Never turn it into a live-match assistance or cheat product.

## Safety and game integration

- Never inject DLLs into CS2.
- Never read or write CS2 process memory.
- Never patch game binaries.
- Never implement wallhack-style overlays or real-time opponent information.
- Prefer demo files, external console control and OS-level capture.
- Keep all CS2 commands behind `Cs2ReplayAdapter`.
- Treat all undocumented/fragile CS2 behavior as capability-probed, not guaranteed.

## Architecture

- UI: React/TypeScript in `apps/desktop/src`.
- Native integration: Rust/Tauri in `apps/desktop/src-tauri`.
- Demo analytics and AI: Python sidecar in `services/analyzer`.
- Domain contracts live under `packages/contracts`.
- High-volume tick data is Parquet; application metadata is SQLite.
- DuckDB queries Parquet; do not mirror millions of tick rows into SQLite.

## AI rules

- Demo-derived structured facts are authoritative.
- AI is allowed to infer, explain and recommend, but must not rewrite facts.
- Every AI conclusion must distinguish facts, observations, inferences, recommendations and uncertainties.
- Use JSON-schema structured output for machine-consumed AI results.
- Store `model`, `prompt_version`, `schema_version` and evidence IDs with every AI result.
- Do not put model API keys in the web renderer or logs.
- Prefer sending selected keyframes plus a compact fact packet rather than full-match media.

## Engineering

- Write tests with each behavior change.
- Prefer small adapters with explicit interfaces over direct library calls spread through the codebase.
- No hidden global state for current demo, selected player or CS2 connection.
- All long-running operations use a job state with progress and cancellation.
- Every state transition must be idempotent or safely retryable.
- Never assume tick rate; read available timing metadata and preserve raw tick identifiers.
- Persist source/demo hash and parser version for reproducibility.
- Use UTC timestamps internally.
- User-facing timestamps may be localized by the UI.

## Error handling

- Errors shown to users must include a stable error code and remediation.
- Preserve a technical cause chain in local logs.
- Never log secrets, complete API keys or raw authorization headers.
- Parser incompatibility after a CS2 update must surface as a parser compatibility error, not a generic crash.

## Definition of done

A task is not done unless:
1. behavior has tests,
2. errors are handled,
3. the contract is typed,
4. docs are updated if architecture changed,
5. no safety invariant above is violated.
