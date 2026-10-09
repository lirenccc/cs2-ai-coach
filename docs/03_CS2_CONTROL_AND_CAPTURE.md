# 03 — CS2 Control and Capture

## 1. 总原则

只使用：
- 启动参数
- TCP console / NetCon
- Demo playback console commands
- Windows 屏幕/窗口捕捉

不使用：
- DLL injection
- process memory read/write
- game binary patch
- online-match overlay

Valve 的 Trusted Mode 明确限制第三方程序向 CS2 进程注入，因此这条边界是架构硬约束。

## 2. CS2 启动

推荐由 `Cs2ProcessManager`：

1. 检测 Steam
2. 检测 CS2 是否已运行
3. 检查 NetCon 是否可连接
4. 如需要用户重启，明确提示
5. 启动 CS2 时添加随机高位 `-netconport`

示意：

```text
steam.exe -applaunch 730 -netconport <ephemeral-port>
```

注意：
- Valve 文档说明 `-netconport <number>` 创建可远程访问的 server console。
- 因此应把它视为本机攻击面。
- 端口随机化。
- 只在分析会话期间开启。
- Windows 防火墙策略建议阻断外部网络访问。
- 不把端口/token上传日志。

## 3. NetCon Client

Rust 模块：

```text
Cs2NetConClient
- connect(address)
- send(command)
- read_until_idle()
- command(command, timeout)
- close()
```

必须处理：
- connection refused
- CS2 正在启动
- console 回包噪声
- 命令成功但没有结构化 ACK
- socket 断开
- CS2 重启

## 4. Demo Playback Adapter

支持能力探测，而不是假定永远存在。

目标 command family：
- `playdemo`
- `demo_pause`
- `demo_resume`
- `demo_togglepause`
- `demo_goto`
- `demo_gototick`
- `demo_timescale`
- `demo_info`

实际发布前要在当前 CS2 build 上跑 smoke test。

### Load demo

优先尝试绝对路径或已验证的 managed path。

如果 CS2 对任意路径行为不稳定：
- 将 Demo 复制到一个受控的 CS2 demo staging 目录
- 文件名使用 hash + 安全 ASCII
- 记录 original path -> staged path
- 分析结束可清理

## 5. Seek 设计

不要业务层直接：

```text
demo_gototick 12345
```

而是：

```text
seek_to_incident(incident_id)
```

内部：
1. 获取事件 tick
2. 减去 pre-roll
3. clamp 到 round start
4. pause
5. seek
6. 等待 seek settle
7. 设置 POV
8. set timescale
9. capture / resume

### Seek settle
Demo seek 不是“发命令后立刻画面已稳定”。

要建立状态：
- `SEEK_SENT`
- `SEEKING`
- `SETTLED`
- `POV_READY`

MVP 可先使用：
- 固定短 debounce
- screenshot hash/scene stability 检查

后续可通过 console/demo info 做更精确确认。

## 6. POV / spectator

封装：

```text
focus_player(PlayerReplayRef)
```

`PlayerReplayRef` 同时保存：
- steam/account id
- demo user id
- nickname
- round-local slot if resolved

原因：CS2 不同版本/不同 demo 的 spectator 定位方式可能变化。

第一阶段：
- 能跳到正确事件就算成功
- POV 自动切换是增强项
- POV 失败不应阻塞整个 Incident 分析，可要求用户手动切换后继续 capture

## 7. Windows Capture

### 首选：Windows.Graphics.Capture
微软官方 API 可捕捉 display 或 application window。

优点：
- 面向窗口
- Direct3D frame
- 可抓 snapshot / stream

### fallback：DXGI Desktop Duplication
适合：
- 全屏/桌面级 frame duplication
- 以 GPU surface 获取帧
- 可在程序级裁切 CS2 窗口区域

## 8. CaptureAdapter

```text
CaptureTarget
- kind: window | monitor
- hwnd?
- process_id?
- title?
- rect
- dpi_scale

CapturePlan
- target
- ticks[]
- player
- resolution_policy
- crop_policy
- settle_policy
```

### Burst capture
每个 Incident 不要无脑录视频。

例：
- t=-2.0s
- t=-0.8s
- t=-0.2s
- t=0.2s
- t=1.0s

实际选择应根据事件类型生成，而不是固定。

## 9. Capture quality checks

每张 frame 做本地质量检查：

- width/height > minimum
- 非全黑
- 非全白
- variance 足够
- 与上一张不是完全相同
- CS2 window still active
- 可选：HUD/画面 ROI 存在性检测

失败：
- 重试 capture
- 如果窗口最小化，提示恢复
- fallback capture adapter

## 10. Frame storage

路径示例：

```text
runtime/
  matches/<match_id>/
    captures/<incident_id>/
      000_tick_123456.webp
      001_tick_123490.webp
      manifest.json
```

manifest：
- tick
- capture_time
- window rect
- adapter
- resolution
- image sha256
- selected player
- seek command version

## 11. 不建议 MVP 上 HLAE

HLAE 对视频制作很强，但产品第一版不应该依赖注入/修改链路。

如果未来专门做“离线 cinematic export”：
- 独立可选模块
- 明确需要 insecure/offline 场景
- 与正常 CS2 竞技启动路径完全分离
- 不作为 AI Coach 核心依赖
