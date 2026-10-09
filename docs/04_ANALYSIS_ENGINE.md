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
Incident
- id
- match_id
- round_id
- player_id
- type
- start_tick
- anchor_tick
- end_tick
- severity
- confidence
- rule_version
- evidence[]
- metrics{}
- capture_hint{}
- status
```

## 5. 首批 Rule

### R001 Opening Death
条件：
- 该回合第一名死亡者是目标玩家

输出：
- tick
- killer
- damage context
- teammates alive

这是事实型，不直接说“错误”。

### R002 Untraded Death
思路：
- 目标死亡
- 在可配置 trade window 中
- 队友没有击杀 killer
- 同时记录最近队友距离/LOS

注意：
“没有被补枪”不一定是死者错误。
AI 需要结合距离、位置和画面再判断责任。

### R003 Isolated Contact
思路：
- 目标与敌方发生首次伤害/射击接触
- 最近可支援队友的 nav distance / LOS 超过阈值
- 目标仍主动接触

阈值必须地图/情境可配置，不要硬编码成全局真理。

### R004 Advantage Throw
思路：
- 本队处于人数优势
- 目标发生高风险死亡
- 死亡后优势显著下降

输出事实：
- before_alive: 4v3
- after_alive: 3v3
- objective state
- time remaining
- support distance

AI 再解释“是否不必要”。

### R005 Repeat Peek After Damage
候选：
- 玩家一次接触受到明显伤害
- 短时间再次暴露到相同/相邻 threat lane
- 随后死亡或继续受伤

需要：
- tick positions
- view angle if reliable
- LOS/nav geometry
- capture frames

这是最适合“规则 + 视觉”联合的 Incident。

### R006 Unsupported Entry
候选：
- 玩家进入 site/choke 前后
- 队友距离/LOS 不足
- 没有有效 flash/smoke 支援
- 玩家成为首批交火目标

### R007 Utility Timing
例：
- 死亡时仍携带关键 utility
- 烟/闪投出后未能影响即将发生的 duel
- teammate flash 与 entry 严重脱节

要避免简单地“死了还有雷 = 错”。

### R008 Clutch Decision
识别 1vX：
- 路线
- 时间
- bomb state
- sequential duel
- sound/visibility context

优先让 AI 做解释，不要用规则强判。

## 6. Rule API

```text
Rule.evaluate(context) -> list[IncidentCandidate]

RuleMetadata:
- id
- version
- required_tables
- required_fields
- severity_policy
- default_thresholds
```

每个 rule：
- deterministic
- unit-testable
- configurable
- versioned

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
