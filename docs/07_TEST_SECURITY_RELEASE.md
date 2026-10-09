# 07 — Testing, Security, Observability and Release

## 1. 测试金字塔

### Unit
Python：
- normalization
- tick window
- trade detection
- advantage state
- incident evidence
- AI validation

Rust：
- command escaping
- netcon framing
- path staging
- capture state machine

TS：
- view model
- timeline selectors
- job state reducer

### Contract
- JSON Schema
- Pydantic models
- TypeScript generated types
- API snapshots

### Golden Demo
维护一批“只用于测试”的 demo fixtures 或内部 fixture manifests。

每个 fixture 保存期望：
- map
- player count
- round count
- selected events
- known incident anchors

CS2 更新 / parser 更新时跑 regression。

### Integration
真实安装环境：
- launch/connect CS2
- play a test demo
- seek to anchor
- pause
- capture
- verify non-black frame

### AI Eval
人工标注一小批 incidents：
- fact fidelity
- tactical usefulness
- uncertainty honesty
- recommendation specificity

模型/prompt 更新必须跑 eval。

## 2. P0 四个 feasibility spikes

在写大 UI 前必须跑通：

### Spike A — Parser
给一场真实 Demo：
- roster
- rounds
- kills
- damages
- grenades
- ticks

### Spike B — NetCon
- 启动 CS2
- TCP connect
- `playdemo`
- pause/resume
- seek

### Spike C — Capture
- 找到 CS2 window
- 抓一张非黑 frame
- 连续抓 5 张
- resize/restart 后仍工作

### Spike D — AI
- 事实 packet
- 3 张图片
- JSON schema output
- 本地 validator 通过

任何一个 Spike 失败，先解决再进入完整产品。

## 3. Security

### API keys
- 不进入 renderer localStorage
- 不进入 `.env` 打包产物
- 不输出日志
- 开发机 `.env.local` gitignore
- 商业版由 backend broker

### NetCon
`-netconport` 被 Valve 描述为 remote console。

措施：
- 随机端口
- 生命周期尽量短
- 不监听额外自建公网接口
- 建议 Windows Firewall 限制
- 不接受任意 UI 自由输入 console command
- command allowlist

### File paths
Demo path 属于不可信输入：
- canonicalize
- extension/size check
- quote/escape
- 不把路径拼到 shell string
- 使用 argv / typed process API

### AI payload
- 默认只发关键事实和关键帧
- 用户可查看上传范围
- PII 最小化
- Steam ID 是否上传做设置项

## 4. Anti-cheat boundary

硬规则：
- 不注入 CS2
- 不 hook game process
- 不读内存
- 不做 live advantage
- 不自动向在线比赛提供 tactical signal

如果未来有实时 GSI 类功能，也必须独立安全评估，不与 Demo 产品默认混用。

## 5. Observability

本地结构化日志：

```text
timestamp
level
component
request_id
job_id
match_id?
incident_id?
error_code?
duration_ms?
```

禁止：
- API key
- Authorization header
- 完整 AI base64 图片
- 用户敏感路径（可 hash/脱敏）

## 6. Metrics

本地产品指标：
- parse_success_rate
- parse_duration
- rules_duration
- incidents_per_match
- seek_success_rate
- capture_success_rate
- ai_success_rate
- ai_schema_validation_rate
- user_opened_incident_rate

## 7. Crash recovery

启动时检查：
- RUNNING job 若进程已不存在 -> INTERRUPTED
- capture temp files -> 可恢复/清理
- sidecar pid stale -> cleanup
- DB integrity
- staged demo cleanup

## 8. Performance budget

基于一个 40 分钟比赛的容量思维：

- 30 FPS 全帧视频有 72,000 frames。
- 10 人、64 tick/s 的简单 player-tick 上界约 1,536,000 rows。
- 20 个 Incident × 5 个 frame = 100 张关键帧。
- 100 张相对 72,000 全帧，图像数量缩减约 720 倍。
- 若 AI 版图片平均约 300 KB，100 张临时数据约 30 MB。

这些是容量假设，不是产品承诺；真实 parser 输出和图片大小需 benchmark。

## 9. Packaging

### Desktop
Tauri Windows installer。

### Python sidecar
推荐打包为独立可执行文件：
- PyInstaller 或 Nuitka 做 feasibility test
- Tauri sidecar bundle
- 版本与主 app 固定

### 数据目录
不得写进 install directory。

### Auto update
第一版可手动。
稳定后再加签名 + updater。

## 10. Release gate

每次 release：

- [ ] parser golden demos pass
- [ ] current CS2 build smoke test
- [ ] netcon connect pass
- [ ] demo seek pass
- [ ] capture non-black pass
- [ ] AI schema eval pass
- [ ] migration test pass
- [ ] clean install test
- [ ] upgrade install test
- [ ] secrets scan
- [ ] no injection/process-memory code
