# Implementation Backlog

原则：严格按顺序。P0 没跑通，不进入 P1 大规模 UI。

## P0 — Feasibility

### P0.1 Repo bootstrap
- [x] 初始化 Tauri v2 + React + TypeScript
- [x] 初始化 Python 3.12 sidecar
- [x] 建立 root `AGENTS.md`
- [x] 安装 `.cursor/rules`
- [x] 建立 CI：TS/Rust/Python lint + test
- [x] 建立 runtime gitignore

**Acceptance**
- `pnpm test`
- `cargo test`
- `pytest`
均有最小测试并通过。

### P0.2 Demo parser spike
- [x] 加 `demoparser2` adapter（可选 extra，未安装时返回不可用）
- [x] 加 `awpy` adapter（Awpy 2.x，可选 extra）
- [x] 做 `DemoParserAdapter`（`DemoParserPort` 别名保留）
- [x] 组合策略：Awpy 优先，缺失/更稀的 kills 由 demoparser2 补齐
- [x] 标准化输出 header / roster / rounds / kills / damages（无 DataFrame 泄漏）
- [x] 导入时将 `ParsedDemo` 持久化到 `matches`（`parsed_json` + counts）
- [x] 独立 PBDEMS2 structural probe（header / roster / legacy events）
- [x] 脱敏 golden summary：`fixtures/real-demo/expected/9208210907649202700_0.redacted-summary.json`
- [x] mocked fixture 单测（无网络、无真实 `.dem`）
- [x] 可选真实 demo 交叉验证（`CS2_COACH_REAL_DEMO`）

**Acceptance**
- 同一 demo 重跑结果稳定
- parser version 被记录
- 无 demo 时测试用 mocked fixture

### P0.3 Analyzer sidecar
- [x] FastAPI `/v1/health`
- [x] Tauri spawn sidecar
- [x] random localhost port
- [x] session token（Tauri 生成，仅注入 sidecar；renderer 不可见）
- [x] shutdown cleanup（`/v1/shutdown` + Exit 钩子；打包 binary 见 `docs/ops/SIDECAR_PACKAGING.md`）

**Acceptance**
- app 启动自动 sidecar ready
- sidecar 崩溃后 UI 有明确错误

### P0.4 Storage v2
- [x] SQLite migrations（storage schema v2）
- [x] demo SHA-256 dedupe
- [x] `player_identities` / `controller_sessions` / `pawn_lives` / rounds+markers / event indexes
- [x] `TickStore` port（dense ticks 不进 SQLite；Parquet/DuckDB 后续）
- [x] 双时钟列（`demo_tick` / `server_tick`）与 schema 决策对齐

**Acceptance**
- 私有 P0.2 fixture 导入后 identity / session / pawn / event 行可查询
- dense tick 不镜像进 SQLite

### P0.5 NetCon real-CS2 spike
- [x] CS2 process detect / Steam detect
- [x] launch with random high `-netconport` + Windows `-tools`（无 `-insecure`）
- [x] TCP client（仅 loopback）
- [x] command allowlist / `ReplayCommand`
- [x] Demo staging（SHA-256 安全名、zip-slip 拒绝）
- [x] typed tick domain（禁止裸 `seek(u64)`）
- [x] session state machine（进程退出 / TCP 丢失可检测）
- [x] load/pause/resume/timescale/`demo_info`/seek capability probe
- [x] 输出 `docs/spikes/replay/P0_5_NETCON_STATUS.md`

**Acceptance**
- 真实 CS2 上可连接 NetCon
- 私有 fixture 可 `playdemo` / pause / resume / timescale / seek 发令
- `demo_gototick` 时钟域保持 UNVERIFIED（交给 P0.5A）
- CI 不要求本机安装 CS2

### P0.5A Replay tick calibration
- [x] 对比 parser `demo_tick` / `server_tick` 与 `demo_gototick` 实际落点
- [x] 明确引擎命令消费的时钟域（本机验证：**DemoTick**）
- [x] 固化 seek API 域约束与校准夹具
- [x] 输出 `docs/spikes/replay/P0_5A_TICK_CALIBRATION.md` + redacted JSON

**Acceptance**
- 对私有 fixture ≥5 个分布式事件锚点双侧候选实验完成
- 权威时钟域已固化为 `ReplayTickDomain::DemoTick`（build-specific；见校准文档）
- CI 不要求本机 CS2；真机入口为 ignored `probe_replay_tick_calibration`

### P0.6 Windows capture spike
- [x] find CS2 window（进程归属优先；见 `capture::discover`）
- [x] Windows.Graphics.Capture proof（`CreateForWindow` + free-threaded frame pool）
- [x] fallback strategy（DXGI Desktop Duplication 决策/裁切计划；WGC 健康时不自动切换）
- [x] single snapshot + quality + versioned manifest
- [x] burst snapshot（有界 count/timeout/cancel）
- [x] resize / minimized typed recovery
- [x] capture-after-calibrated-seek（DemoTick + `p0.5a-2026-10-10`）
- [x] 输出 `docs/spikes/capture/P0_6_WINDOWS_CAPTURE.md` + redacted fixture

**Acceptance**
- windowed 非黑图（本机验证 ~1280×720 / 捕获 1282×752）
- resize 后 frame pool recreate 路径可恢复
- CI 不要求本机 CS2；真机入口为 ignored `probe_capture_*` / `probe_wgc_*`

### P0.6A Event / identity / capture validation
- [x] Evidence lineage 合约（可选字段；禁止 display name 作主键）
- [x] Pawn-life / 多命验证（redacted fixture）
- [x] BOT takeover 归因合约（A03 timeline；trade 标 UNRESOLVED）
- [x] Halftime / side：`RoundPlayerState` + tick `side` 权威源
- [x] Capture geometry 合约（client ≠ WGC content）
- [x] Paused duplicate hash 语义
- [x] Calibration/build mismatch → `REPLAY_CALIBRATION_BUILD_MISMATCH`
- [x] Capture-at-event 脱敏结果夹具 + ignored 真机 probe
- [x] 输出 `docs/spikes/capture/P0_6A_EVENT_IDENTITY_VALIDATION.md`

**Acceptance**
- 契约/夹具单测 CI 可跑；真机 probe 保持 ignored
- 不改写 P0.2 parser / Storage v2 / P0.5A / P0.6 行为语义

### P0.7 AI spike
- [x] AI provider interface
- [x] Responses API adapter（可选 `openai` extra；`store=false`；Structured Outputs；可选 `base_url` 中转）
- [x] image input helper（data URL + 显式 `detail`；不写日志/不落盘私图）
- [x] structured output schema + versioned prompt（`provider_smoke_v001`）
- [x] local evidence / frame ID post-validation
- [x] request fingerprint（确定性；排除 secrets/绝对路径）
- [x] typed provider failure mapping（auth/timeout/429/5xx/refusal/incomplete）
- [x] CI-safe unit tests + opt-in real smoke gate
- [x] 真实 P0.6 frame + structured evidence → OpenAI-compatible Responses smoke（`gpt-6.1-sol` / `store=false`）
- [x] redacted fixture + `docs/spikes/ai/P0_7_REAL_PROVIDER_SMOKE.md`

**Acceptance**
- 已知 structured evidence + ≥1 张真实 P0.6 frame → Responses Structured Output → schema + evidence/frame 校验通过
- unsupported evidence/frame id 被 validator 拒绝
- 真实调用保持 opt-in；正常 CI 不花费 API
- 详见 `docs/spikes/ai/P0_7_REAL_PROVIDER_SMOKE.md`

---

## P1 — Offline Demo Coach

### P1.1 Storage
- [x] SQLite migrations
- [x] demo SHA-256 dedupe
- [x] Storage schema v2：`player_identities` / `controller_sessions` / `pawn_lives` / rounds+markers / event indexes
- [x] `TickStore` port（dense ticks 不进 SQLite；Parquet/DuckDB 后续）
- [ ] Parquet match artifacts（大规模实现）
- [ ] DuckDB query layer

### P1.2 Normalize
- [x] Match/Player/Round/Event domain（schema 决策已写入 `docs/spikes/real-demo/SCHEMA_DECISIONS.md`；storage v2 已落地）
- [x] stable internal IDs（event_id / identity / session / pawn life）
- [x] timing abstraction（调用方传入 tickrate，不写死 64）
- [x] raw tick preserved（probe 同时保留 demo tick 与 server tick；storage 双时钟列）

### P1.3 Timeline
- [ ] match page
- [ ] round list
- [ ] kill/death timeline
- [ ] player selector
- [ ] event detail drawer

### P1.4 Rule Engine v1
- [x] opening death
- [x] untraded death
- [ ] advantage throw candidate
- [ ] isolated contact candidate
- [ ] repeat peek candidate

### P1.5 Incident UI
- [ ] evidence list
- [ ] severity/confidence separate
- [ ] filter/sort
- [ ] mark useful/not useful

**P1 Exit**
用户无需 AI，也能完成一场有价值的结构化复盘。

---

## P2 — CS2 Replay Integration

### P2.1 Session manager
- [ ] connect status
- [ ] launch/restart UX
- [ ] demo staging
- [ ] cleanup

### P2.2 Replay
- [ ] load demo
- [ ] seek with pre-roll
- [ ] pause/resume
- [ ] timescale
- [ ] POV focus best effort

### P2.3 Incident playback
- [ ] “在 CS2 查看”
- [ ] active incident state
- [ ] next/previous incident
- [ ] hotkeys

**P2 Exit**
从 Incident 点击到 CS2 正确时刻的成功率达到可用水平，并有失败恢复。

---

## P3 — Vision AI Coach

### P3.1 Keyframe planner
- [ ] per-incident frame roles
- [ ] settle policy
- [ ] frame quality check
- [ ] capture manifest

### P3.2 AI analysis
- [ ] packet builder
- [ ] prompt versioning
- [ ] schema validation
- [ ] retry/cancel
- [ ] result cache

### P3.3 Coach UI
- [ ] summary
- [ ] facts
- [ ] observations
- [ ] inferences
- [ ] recommendations
- [ ] uncertainties
- [ ] frame gallery

### P3.4 AI eval
- [ ] 30~50 个内部标注 Incident
- [ ] fact fidelity rubric
- [ ] coaching usefulness rubric
- [ ] regression report

**P3 Exit**
AI 不再是聊天框，而是可追溯 Incident 分析器。

---

## P4 — Longitudinal Coaching

- [ ] cross-match player identity
- [ ] opportunity-normalized metrics
- [ ] recurring mistake clusters
- [ ] map/side breakdown
- [ ] weekly training priorities
- [ ] improvement trend
- [ ] coach feedback loop

---

## Deferred

- [ ] cloud sync
- [ ] team workspace
- [ ] subscription/billing
- [ ] auto demo download integrations
- [ ] shareable web report
- [ ] video clip export
- [ ] voice coach
