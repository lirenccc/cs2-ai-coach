# 09 — Recommended Cursor Workflow

## 1. 不要让 Agent 一次生成整个仓库

推荐循环：

```text
读 1~2 个设计文档
→ 实现一个小 task
→ 跑测试
→ review diff
→ commit
→ 下一个 task
```

## 2. 每个 Prompt 都写 Acceptance Criteria

坏：
> 帮我实现 demo 分析。

好：
> 实现 DemoParserAdapter，只输出 header/players/rounds/kills/damages，不做 UI；添加 5 个单测；parser-specific dataframe 不得越过 adapter。

## 3. 要求 Agent 明确 assumptions

CS2 这种外部依赖最怕“它以为某命令存在”。

每次 integration change 要求输出：

```text
Verified:
Assumed:
Needs manual verification:
```

## 4. 把当前 CS2 build smoke test 作为人工 gate

Cursor 可以写代码，但不能替代真实游戏环境确认：

- NetCon
- demo command
- POV
- capture
- focus/minimize behavior

## 5. 建议 commit 粒度

- `chore: bootstrap desktop and analyzer`
- `feat(parser): add normalized match parser`
- `feat(storage): add sqlite metadata repository`
- `feat(cs2): add netcon replay adapter`
- `feat(capture): add windows frame capture`
- `feat(rules): add opening and trade incidents`
- `feat(ai): add structured incident analysis`
- `feat(ui): add incident review workflow`

避免：
`feat: build entire app`

## 6. Agent review prompt

每完成一个模块：

> 根据 AGENTS.md 和本模块 docs，审查当前 diff。不要修改代码。列出：
> 1. 架构违规
> 2. 安全风险
> 3. 未覆盖边界情况
> 4. 缺失测试
> 5. 可能受 CS2 更新影响的假设
> 按严重度排序。

## 7. 第一阶段不要追求

- 动画
- 复杂设计系统
- 云端
- 账户体系
- 自动下载平台 Demo
- 视频剪辑

先证明：
**parse -> incident -> seek -> capture -> AI -> report**
