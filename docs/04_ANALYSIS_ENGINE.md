# 04 — Analysis Engine

## 1. 分层

分析分 4 层：

```text
Facts
  ↓
Derived Metrics
  ↓
Rule Incidents
  ↓
AI Interpretation
```

AI 永远在最后一层。

## 2. Facts

直接来自 Demo：
- 谁
- 什么时候
- 在哪里
- HP/armor
- 击杀/死亡
- damage
- weapon
- grenade
- bomb
- teammate alive state
- player positions

这些可以在 UI 标记为 `FACT`。

## 3. Derived Metrics

代码计算：
- alive counts
- distance to nearest teammate
- path/navigation distance
- trade time
- first contact / first damage
- economy delta
- utility inventory estimate
- time since last damage
- time between peeks
- rotation time
- player spacing

这些属于 `DERIVED_FACT`，必须可复算。

## 4. Incident 统一结构

```text
Incident / IncidentCandidate
- id
- match_id
- round_id
- player_id / focus_side
- type
- start_tick / start_demo_tick
- anchor_tick / anchor_demo_tick
- end_tick / end_demo_tick
- severity
- confidence
- rule_version
- evidence[]
- metrics{}
- capture_hint{}
- status
```

实现见 `services/analyzer/app/rules/models.py`。

## 5. 首批 Rule（确定性核心）

编号说明：历史草稿曾把 Isolated Contact 标为 R003、Advantage Throw 标为 R004。
**当前首批确定性 coaching batch** 固定为：

```text
R001 Opening Death
R002 Untraded Death
R003 Advantage Loss Candidate   (incident_type = ADVANTAGE_LOSS_CANDIDATE)
```

Isolated Contact / Repeat Peek / Unsupported Entry 等仍属后续候选，尚未实现。

实现位置：`services/analyzer/app/rules/`。  
阈值版本：`rule-thresholds-v1-2026-10-10`（见 `RuleThresholds`）。  
补充说明：`docs/spikes/rules/RULE_ENGINE_V1.md`。

### 权威数据源（规则层）

| 状态 | 权威源 | 禁止 |
| --- | --- | --- |
| Side / team | `RoundPlayerState` / freeze_end `selected_ticks.team`（P0.6A） | 用初始 roster 跨半场永久缓存 |
| Alive counts | freeze_end 存活 identity 集合 + 同 DemoTick 批次 life-ending 事件 | 记分板截图 / AI 推断 |
| Round winner | 规范化回合 `winner` / `win_reason` | 仅凭最后一击或存活归零猜测 |
| Identity | `PlayerIdentity` → `ControllerSession` → `PawnLife` | 仅用 `(round, name)` / 裸 pawn handle |

证据确定性沿用 P0.6A：`VERIFIED` / `DERIVED` / `UNRESOLVED`。  
规则求值结果另有：`MATCHED` / `NOT_MATCHED` / `UNRESOLVED`。  
**不要把 UNRESOLVED 解释成条件为 false。**

### Same-tick 策略

同一 `DemoTick` 上的全部权威 life-ending 事件视为**一次状态转移批次**。  
批次内输入顺序不得改变 alive counts；证据序列化按 `event_id` 稳定排序。

### BOT takeover / 归因不足

- 关键事件标 `crosses_unresolved_takeover` 或 `certainty=unresolved` → 该主体 `UNRESOLVED`，不发射高置信 incident。
- 不在初始 alive 集合中的死亡：忽略（不编造 side / alive），不把缺口抬成产品不变量。
- 单回合 UNRESOLVED 不使整场作废。

### R001 Opening Death

条件（事实型，不直接说“错误”）：
- 受害者属于该回合最早 DemoTick 死亡批次（同 tick 多死均可）
- 受害者绑定 identity；side 取当前回合权威 side，而非初始 roster

输出：`IncidentCandidate`（tick、killer id、teammates_alive、pawn_life 引用等）

### R002 Untraded Death

思路：
- 目标死亡后，在可配置 `trade_window_demo_ticks`（默认 320 DemoTick）内
- 同 side 队友未击杀 killer → `UNTRADED_DEATH` candidate
- 队友集合必须来自权威 round-side

P0.6A：跨越未解析 takeover 的 trade 关系 → `UNRESOLVED`，**不得**当成“未补枪=true”或“已补枪=false”。

距离/LOS 仍未实现（后续增强）；当前不编造几何证据。

### R003 Advantage Loss Candidate

`incident_type = ADVANTAGE_LOSS_CANDIDATE`（候选信号，不断言责任/瞄准/道具）。

默认阈值：`minimum_player_advantage = 2`（如 5v3 / 4v2 / 3v1；5v4 不够格）。

保守语义（与旧草稿 “Advantage Throw = 高风险单死后优势塌缩” 不同，见下）：
1. 重建回合 alive 序列；
2. 某 side 曾达到 ≥ 阈值的人数优势，并记录 peak；
3. **且** 权威回合结果中该 side **输掉** 回合；
4. 每 side / round 至多一个 canonical candidate。

锚点约定：
- `start_demo_tick` = 确立 qualifying advantage 的 DemoTick
- `anchor_demo_tick` = 权威回合结束 tick
- `end_demo_tick` = 权威回合结束 tick

metrics 至少包含：`peak_advantage`、`peak_alive_friendly`、`peak_alive_enemy`、
`peak_demo_tick`、`final_round_winner`、可选 `collapse_demo_tick` / `minimum_later_advantage`。

与旧 Advantage Throw 草稿的差异（有意保留并文档化）：
- 旧草稿强调“目标高风险死亡后优势显著下降”；
- 当前实现用 **优势 + 回合战败** 的保守候选，避免把暂时回到均势一律标成 throw。

### 后续候选（未实现）

#### Isolated Contact（原草稿编号 R003）
- 首次伤害/射击接触 + 支援距离/LOS 阈值；地图可配置。

#### Repeat Peek After Damage
- 受伤后短时再暴露；常需几何/画面。

#### Unsupported Entry
- site/choke 进入缺少支援/utility。

#### Utility Timing / Clutch Decision
- 解释优先交给后续 AI；规则不强判。

## 6. Rule API

```text
Rule.evaluate(context) -> RuleEvaluationResult
  candidates: IncidentCandidate[]
  unresolved: UnresolvedEvaluation[]
  outcome: MATCHED | NOT_MATCHED | UNRESOLVED

RuleMetadata:
- id
- version
- incident_type
- required_inputs
- default_thresholds
```

每个 rule：
- deterministic
- unit-testable
- configurable
- versioned
- 永不调用 AiProvider / capture / NetCon / UI

## 7. Evidence

Evidence 设计为引用，不复制所有数据：

```json
{
  "kind": "demo_event",
  "ref": "kill:uuid",
  "tick": 123456,
  "label": "player death"
}
```

```json
{
  "kind": "metric",
  "name": "nearest_teammate_nav_distance",
  "value": 812.4,
  "unit": "game_units"
}
```

```json
{
  "kind": "frame",
  "ref": "capture:uuid",
  "tick": 123420
}
```

AI result 的每条核心结论必须引用 evidence IDs。  
规则层 evidence 实现见 `RuleEvidence`（`demo_event` / `metric` / `round_state` / `identity`）。

## 8. Severity

不要把 severity 与 confidence 混为一谈。

### severity
影响程度：
- 1 minor
- 2 low
- 3 medium
- 4 high
- 5 critical

### confidence
证据充分度：
- 0.0 ~ 1.0

例如：
- “4v2 时首个主动死亡” severity 4
- 但如果 POV 画面没抓到，AI 对“为什么 peek”的 confidence 可能只有 0.55
- 确定性规则在证据完整时可用 confidence `1.0`；`UNRESOLVED` 不得用高 confidence 伪装

## 9. Match Summary

聚合顺序：

```text
Incidents
 -> group by type
 -> normalize by opportunity
 -> map/side/phase breakdown
 -> repeated patterns
 -> top 3 training priorities
```

长期画像不能只按错误次数排序。

例如：
- 10 次 entry 中 4 次 unsupported
- 比 100 回合里 4 次 unsupported 更严重

因此应保存 denominator / opportunities。
