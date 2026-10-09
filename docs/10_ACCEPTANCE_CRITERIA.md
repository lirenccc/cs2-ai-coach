# 10 — MVP Acceptance Criteria

## A. Demo import
- [ ] 可导入合法 `.dem`
- [ ] 相同文件 SHA-256 去重
- [ ] 非法文件有明确错误
- [ ] 不因 Unicode path 崩溃

## B. Parser
- [ ] 输出 map/players/rounds
- [ ] 输出 kills/damages
- [ ] 至少一种 utility/event
- [ ] parser version 可追踪
- [ ] 不兼容 demo 不静默成功

## C. Structured review
- [ ] 可选择 focus player
- [ ] 可查看每回合 timeline
- [ ] 至少 3 类 deterministic Incident
- [ ] Incident 可显示 evidence

## D. CS2
- [ ] 检测 CS2 状态
- [ ] 可建立 NetCon
- [ ] 可播放 demo
- [ ] 可 pause/resume
- [ ] 可 seek 至 3 个已知 anchor
- [ ] 失败时可重试

## E. Capture
- [ ] 抓到 CS2 非黑画面
- [ ] burst capture
- [ ] 记录 frame manifest
- [ ] resize 后不崩
- [ ] window invalid 后提示恢复

## F. AI
- [ ] 输入 fact packet + frames
- [ ] 输出 JSON schema
- [ ] facts 引用 evidence
- [ ] observations 引用 frame
- [ ] 缺失证据可输出 uncertainty
- [ ] schema invalid 不进入正式报告

## G. UX
- [ ] 从 match -> round -> incident 不超过几个核心操作
- [ ] 点击 Incident 可“在 CS2 中查看”
- [ ] AI 分析可单独触发
- [ ] Parse/Capture/AI 都有 progress/error/retry

## H. Security
- [ ] 无 DLL injection
- [ ] 无 process memory read/write
- [ ] API key 不在 renderer storage
- [ ] NetCon command allowlist
- [ ] analyzer 只 bind loopback
- [ ] logs secrets scan 通过

## I. Reliability
- [ ] sidecar crash 不导致主程序永久卡死
- [ ] 应用重启可看到已解析比赛
- [ ] job interruption 可恢复或重跑
- [ ] migration failure 不破坏原 DB
