# CS2 AI Coach

Windows-first 离线 CS2 Demo 复盘教练。基线日期：2026-10-09。

导入 `.dem` → 结构化解析与规则引擎 → 外部控制 CS2 回放 → 可选关键帧捕获 → evidence 绑定的 AI 建议。

## 产品边界

只做离线 Demo 复盘。不做：

- DLL 注入 / 读写 CS2 进程内存 / 二进制补丁
- wallhack 式叠加或实时竞技信息优势
- Trusted Mode / VAC 绕过
- 在 renderer 中保存 API Key
- 把整场录像逐帧上传模型

## 仓库结构

```text
cs2-ai-coach/
├─ AGENTS.md                 # Cursor / 代理硬约束
├─ TASKS.md                  # 实现 backlog
├─ SOURCE_BASELINE.md        # 外部依赖核实基线
├─ apps/desktop/             # Tauri v2 + React + TypeScript
├─ services/analyzer/        # Python 3.12 FastAPI sidecar
├─ packages/contracts/       # 共享类型与 JSON Schema
├─ fixtures/real-demo/       # 脱敏 golden（无 .dem）
├─ docs/                     # 设计与 spike 文档（见 docs/README.md）
├─ scripts/                  # bootstrap / check / dev / probe
└─ runtime/                  # 本地数据（gitignore）
```

文档入口：[`docs/README.md`](docs/README.md)。

## 当前已落地

- FastAPI `/v1/health`、`/v1/demos/import`（loopback + session token）
- `.dem` 校验、SHA-256 去重、SQLite migration / repository
- `DemoParserPort` + 可选 `demoparser2` adapter
- 独立 PBDEMS2 `structural_probe`
- Opening death / untraded death 规则原语；timing 不写死 tickrate
- `AiProvider`、structured output、evidence / frame ID 校验
- Rust `NetConClient` + 类型化 `ReplayCommand`
- 桌面端经 Tauri command 查健康状态（renderer 不持有 token）
- Tauri 托管 analyzer sidecar（随机 loopback 端口、会话 token、优雅关闭、bridge 错误码）

尚未完成：真实 CS2 `-netconport` 冒烟、窗口捕获、打包版 analyzer binary。见 [`TASKS.md`](TASKS.md)。

## 快速开始

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
.\scripts\check.ps1
.\scripts\dev.ps1
```

真实 demo 结构预检（不依赖 demoparser2；支持 `.dem` 或下载得到的 `.zip`）：

```powershell
.\scripts\probe_demo.ps1 "C:\path\to\match.dem"
.\scripts\probe_demo.ps1 "C:\Users\12159\AppData\Roaming\Wmpvp\demo\9208210907649202700_0.zip"
```

## 测试

```powershell
pnpm test
cargo test
python -m pytest services\analyzer\tests -q
```

或：`.\scripts\run_all_tests.ps1` / `.\scripts\check.ps1`。

## 先读顺序

1. [`AGENTS.md`](AGENTS.md)
2. [`docs/00_PRODUCT_SCOPE.md`](docs/00_PRODUCT_SCOPE.md) … [`docs/07_TEST_SECURITY_RELEASE.md`](docs/07_TEST_SECURITY_RELEASE.md)
3. [`TASKS.md`](TASKS.md)
4. Real-demo spike：[`docs/spikes/real-demo/`](docs/spikes/real-demo/)
