# 08 — Risk Register

| Risk | Impact | Likelihood | Mitigation |
|---|---|---:|---|
| CS2 update breaks parser | High | High | Parser adapter, golden demos, versioned parser, compatibility UI |
| Demo seek command changes | High | Medium | Replay adapter, capability probe, smoke tests |
| POV switching unreliable | Medium | Medium | Best-effort adapter, manual fallback, do not block analysis |
| Capture black frame | High | Medium | WGC primary, DXGI fallback, frame quality check |
| Window minimized/covered | Medium | Medium | Detect and prompt, bring-to-front policy |
| NetCon exposed on LAN | High | Medium | Random port, firewall guidance, short lifetime, allowlist |
| AI hallucinates facts | High | High | Structured packet, evidence references, schema/post validation |
| AI cost too high | High | Medium | Rule-first filtering, 3~6 frames/incident, cache |
| AI latency feels slow | Medium | Medium | Jobs/progress, cache, analyze on demand |
| SQLite becomes huge | Medium | High if ticks stored there | Keep dense tick data in Parquet |
| Map geometry/nav format changes | Medium | Medium | Optional capability, Awpy adapter, graceful degradation |
| User expects live coach | Product/Safety | Medium | Product copy and architecture enforce offline Demo scope |
| Windows capture API edge cases | Medium | Medium | Feasibility spike before UI investment |
| Packaging Python sidecar difficult | Medium | Medium | P0 packaging spike before beta |
| Model/provider behavior changes | Medium | High | Provider adapter, schema eval, prompt/model versioning |

## Stop-ship conditions

以下任一情况不可发布：

- 需要关闭/绕过反作弊才能使用核心功能
- 核心路径依赖 CS2 进程注入
- AI facts 可无 evidence 写入报告
- API key 出现在 renderer/log
- Demo seek 经常落错回合且没有告警
- parser 对不兼容 demo 静默产生错误数据
