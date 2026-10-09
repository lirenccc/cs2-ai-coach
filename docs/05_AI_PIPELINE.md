# 05 — AI Pipeline

## 1. AI 的职责

AI 负责：
- 解释
- 结合视觉上下文
- 判断多种可能原因
- 生成训练建议
- 把事实翻译成教练语言

AI 不负责：
- 猜 tick
- 猜击杀事件
- 猜血量
- 猜经济
- 猜谁是谁
- 从整场视频重新恢复 Demo facts

## 2. 推荐 API 形态

使用支持：
- text input
- image input
- JSON Schema structured output

的 Responses-style API。

OpenAI 当前 Responses API 支持 text/image input；Structured Outputs 可让输出遵循 JSON Schema。

模型名称不要硬编码进业务代码：

```text
AI_PROVIDER=openai
AI_MODEL_INCIDENT=<config>
AI_MODEL_SUMMARY=<config>
```

## 3. Incident Packet

发给模型的输入分 5 部分。

### A. Immutable facts
例如：
- map
- side
- round
- score
- target player
- anchor tick
- alive before/after
- hp
- weapon
- utility
- killer
- teammate distance

### B. Rule hypothesis
例如：
- candidate type: repeat_peek_after_damage
- rule confidence: 0.84

必须明确告诉模型：
“这只是规则候选，不是最终结论。”

### C. Evidence table
每个事实都有 evidence id。

### D. Keyframes
3~6 张优先，而非几十张。

### E. Coaching rubric
要求模型：
- 不重新发明事实
- 证据不足时输出 uncertainty
- 给 1~3 个具体建议
- 避免绝对化
- 区分个人错误、团队结构问题和合理风险

## 4. 输出模型

见：
`packages/contracts/schemas/coach_incident_analysis.schema.json`

逻辑：

```text
summary
severity
confidence
facts[]
observations[]
inferences[]
recommendations[]
uncertainties[]
```

### facts
只能重述输入事实，并带 evidence ids。

### observations
只描述图像可直接观察的内容。

### inferences
解释“可能为什么”。

### recommendations
可执行建议。

### uncertainties
缺失视角/信息不足/无法判断。

## 5. Prompt 版本

Prompt 不是写死在 Python string。

目录：

```text
services/analyzer/app/ai/prompts/
  incident_v001.md
  match_summary_v001.md
```

每次分析保存：
- prompt_version
- prompt_hash
- schema_version
- model

## 6. Hallucination 防线

### Rule 1
如果输出事实引用不存在 evidence id：
- validation fail
- 不展示
- 可重试一次

### Rule 2
如果模型说：
“你还有一颗烟”
但 packet 中没有 utility 证据：
- 标记 unsupported claim

### Rule 3
视觉 observation 不应伪装成 Demo fact。

### Rule 4
recommendation 可有观点，但 inference 要有 confidence。

### Rule 5
模型无法看到的信息必须允许 `"unknown"`。

## 7. AI 请求策略

### Incident 级
高质量视觉分析。

### Round 级
基于 Incident 输出，不重新传所有图片。

### Match 级
只传：
- round summaries
- incident summaries
- aggregate metrics

这样成本和噪声都低。

## 8. Keyframe Planner

Input：
- incident type
- anchor tick
- rule evidence
- local events

Output：

```text
KeyframePlan
- frame roles:
  - context_before
  - first_contact
  - damage_received
  - re_peek
  - death_or_resolution
- desired tick
- acceptable tick window
- preferred POV
```

如果一个 frame role 已被另一张图片覆盖，不重复。

## 9. 图片预处理

建议：
- 保留原始 frame
- AI 版本 resize 到合理上限
- WebP/JPEG
- 不做会隐藏战术信息的强 crop
- 可以另生成 ROI：
  - center view
  - radar
  - killfeed
  - utility/HUD

但 MVP 先发完整帧更简单。

## 10. API Key

### 开发版
用户输入个人 API key：
- Rust/OS credential store 保存
- Renderer 只显示 masked 状态
- Python sidecar 通过 Tauri 请求或启动时安全注入

### 商业版
不要让用户拿到平台主 key。
推荐：
- 自有 backend 作为 API broker
- 用户认证
- quota
- rate limit
- billing
- abuse control

## 11. Retry

只重试：
- network timeout
- 429 / transient
- provider 5xx
- structured output parsing临时失败

不无限重试。

AI job 需要：
- max_attempts
- exponential backoff
- cancel
- request fingerprint
- idempotency cache

## 12. Privacy

默认：
- Demo 本地保存
- 结构化解析本地
- 只有用户主动启用 AI 时才上传必要事实/图片
- UI 明确“将上传哪些内容”
- 支持删除本地 AI artifacts
- 日志不保存完整 API payload（debug opt-in 除外）
