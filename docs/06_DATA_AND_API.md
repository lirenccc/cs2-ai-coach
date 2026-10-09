# 06 — Storage, Data Model and Local API

## 1. Storage 分工

### SQLite
放：
- settings
- demo index
- match metadata
- player identity
- rounds summary
- incidents
- jobs
- captures metadata
- AI analysis
- prompt/model versions

### Parquet
放：
- high-volume player ticks
- optional dense shot/trajectory tables
- derived spatial samples

### DuckDB
做：
- Parquet 查询
- cross-match aggregates
- longitudinal profile

## 2. Runtime layout

```text
%LOCALAPPDATA%/CS2AICoach/
  app.db
  logs/
  cache/
  matches/
    <match_id>/
      source.json
      rounds.parquet
      kills.parquet
      damages.parquet
      ticks/
        round_01.parquet
        round_02.parquet
      captures/
      analysis/
```

## 3. SQLite 核心表

### demos
- id
- sha256 UNIQUE
- original_path
- managed_path
- file_size
- imported_at

### matches
- id
- demo_id
- map_name
- parser_name
- parser_version
- schema_version
- parse_status
- created_at

### match_players
- id
- match_id
- steam_id
- account_id
- nickname
- team
- is_focus_player

### rounds
- id
- match_id
- round_no
- start_tick
- end_tick
- winner
- win_reason

### incidents
- id
- match_id
- round_id
- player_id
- type
- anchor_tick
- start_tick
- end_tick
- severity
- rule_confidence
- ruleset_version
- evidence_json
- status

### captures
- id
- incident_id
- tick
- role
- path
- sha256
- width
- height
- adapter
- created_at

### ai_analyses
- id
- incident_id
- provider
- model
- prompt_version
- schema_version
- request_fingerprint
- result_json
- confidence
- created_at

### jobs
- id
- type
- entity_id
- status
- progress
- attempt
- error_code
- error_message
- started_at
- finished_at

## 4. Migration

SQLite 使用显式 migration：
- `001_init.sql`
- `002_add_capture_manifest.sql`

规则：
- 已发布 migration 不修改
- 新变更只能增加 migration
- app 启动时自动备份旧 DB
- migration fail 时不继续启动写入

## 5. Analyzer Local API

Tauri -> sidecar。

### Health

`GET /v1/health`

Response：
```json
{
  "status": "ok",
  "version": "0.1.0",
  "parser": {
    "name": "awpy",
    "available": true
  }
}
```

### Import

`POST /v1/demos/import`

```json
{
  "path": "C:\\demos\\match.dem"
}
```

Response：
```json
{
  "demo_id": "uuid",
  "match_id": "uuid",
  "job_id": "uuid"
}
```

### Match

`GET /v1/matches/{match_id}`

### Rounds

`GET /v1/matches/{match_id}/rounds`

### Incidents

`GET /v1/matches/{match_id}/incidents?player_id=...`

### Run rules

`POST /v1/matches/{match_id}/analyze/rules`

```json
{
  "player_id": "uuid",
  "ruleset": "default"
}
```

### Register captured frame

`POST /v1/incidents/{incident_id}/frames`

Tauri 捕图后把 manifest/path 登记给 analyzer。

### AI analyze

`POST /v1/incidents/{incident_id}/analyze/ai`

```json
{
  "frame_ids": ["uuid", "uuid"],
  "force": false
}
```

### Jobs

`GET /v1/jobs/{job_id}`

### Cancel
`POST /v1/jobs/{job_id}/cancel`

## 6. Error envelope

统一：

```json
{
  "error": {
    "code": "DEMO_UNSUPPORTED_VERSION",
    "message": "This demo cannot be parsed by the installed parser.",
    "retryable": false,
    "details": {}
  },
  "request_id": "uuid"
}
```

Renderer 不解析 Python exception 字符串。

## 7. Tauri command boundary

React 只调用 typed commands，例如：

```text
import_demo(path)
get_match(match_id)
get_rounds(match_id)
get_incidents(match_id, player_id)
seek_incident(incident_id)
capture_incident(incident_id)
analyze_incident(incident_id)
```

不要让 React 拼：
- localhost URL
- netcon command
- OS path manipulation
- SQL
