# Analyzer Sidecar

Python 3.12 FastAPI sidecar for offline demo analytics.

## Layout

```text
app/
├─ main.py / __main__.py   # FastAPI app factory and CLI entry
├─ config.py / security.py / errors.py
├─ api/                    # reserved for route modules
├─ demo/                   # DemoParserAdapter, awpy/demoparser2, structural_probe
├─ domain/                 # timing + API/domain models
├─ rules/                  # deterministic incident primitives
├─ services/               # import orchestration
├─ storage/                # SQLite db / migrations / repositories
├─ ai/                     # AiProvider + validation
├─ jobs/                   # reserved for persisted jobs
└─ keyframes/              # reserved for capture planning
migrations/
tests/
```

## Parser adapters

- Port: `DemoParserAdapter` (`app/demo/ports.py`)
- Normalized result: `ParsedDemo` (`app/demo/models.py`, schema v2) — header, roster, rounds, kills, damages, grenades, selected_ticks, event_counts
- `AwpyAdapter` — Awpy 2.x high-level tables (header/roster/rounds/kills/damages)
- `Demoparser2Adapter` — full P0.2 normalize; enriches `server_tick` / userid / pawn from `structural_probe` when demoparser2 omits them
- `create_demo_parser()` — Awpy first; demoparser2 fills gaps / denser kill tables

Parser-specific DataFrames are converted inside adapters and do not leave the demo package.

Import persists `ParsedDemo` onto `matches` (`parsed_json` + counts + parser metadata).

## Install

```powershell
python -m pip install -e ".\services\analyzer[dev,ai,demo]"
```

## Endpoints (current)

- `GET /v1/health` — version, database path, parser name/available/version
- `POST /v1/demos/import` — validate `.dem`, SHA-256 dedupe

Session token header: `x-cs2-coach-token`. Bind is loopback-only.

## Related docs

- `docs/02_DEMO_PIPELINE.md`
- `docs/spikes/real-demo/`
- `docs/ops/SIDECAR_PACKAGING.md`
