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

Storage schema v2（migration `003_storage_v2.sql`）将身份拆成三层，并把规范化事件做成索引表。  
**不要**把 dense player-tick 写入 SQLite；高密度 tick 走 `TickStore`（Parquet/DuckDB 预留）。

### demos
- id
- sha256 UNIQUE
- original_path
- size_bytes
- imported_at

### matches
- id
- demo_id
- map_name
- parser_name
- parser_version
- normalization_schema_version
- structural_probe_version
- storage_schema_version
- patch_version / build_num（源 build/patch，可空）
- server_start_tick（可空；match 级 server 时钟参考）
- parse_status / counts / parsed_json（兼容载荷）
- created_at

### player_identities
- id
- steamid64 UNIQUE（可空；bot 可不建 identity）
- display_name_latest

### controller_sessions
- id
- match_id
- userid（demo-local controller）
- player_identity_id?（FK，可空）
- connected_demo_tick? / disconnected_demo_tick?
- is_bot / is_hltv

同一 Steam 玩家可有多个 `controller_sessions`；同一 userid 区间不假设整场唯一。

### pawn_lives
- id
- match_id
- controller_session_id?
- pawn_handle
- spawn_demo_tick? / death_demo_tick?

不假设每回合每个 controller 只有一条 pawn life。

### rounds
- id
- match_id
- round_no
- freeze_end_demo_tick
- end_demo_tick
- end_marker_type（`round_officially_ended` | `cs_win_panel_match` | null）
- winner / win_reason

### round_markers
原始 round 标记证据（可出现 freeze_end 多于 officially_ended）：
- marker_type / demo_tick / server_tick? / sequence_index

### kill_events / damage_events / grenade_events
- `event_id` 为主键（稳定内部事件身份）
- `demo_tick` + 可空 `server_tick`
- `source_event_id` / `source_parser` 保留规范化来源身份
- **禁止** `UNIQUE(match_id, round_id, player_id, event_type)` 一类约束（bot takeover 后同 controller 同回合可多次死亡）

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

SQLite 使用显式 migration（`services/analyzer/migrations/`）：
- `001_init.sql`
- `002_match_parsed.sql`
- `003_storage_v2.sql`

规则：
- 已发布 migration 不修改
- 新变更只能增加 migration
- 通过 `schema_migrations` 表保证幂等
- app 启动时自动备份旧 DB（后续加固）
- migration fail 时不继续启动写入

### TickStore port

`TickStore`（`write_ticks` / `query` / `delete_match`）是 dense tick 的唯一写入边界。  
初始实现可为 filesystem JSON；生产路径应落到 Parquet，并由 DuckDB 查询。Repository 只接受规范化 domain models，不接受 parser DataFrame。

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
