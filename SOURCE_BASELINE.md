# Source Baseline — checked 2026-10-09

这些链接是架构关键外部依赖的核实基线。实现时仍需在当前版本再次验证。

## Demo parsing

- demoparser2 / LaihoE  
  https://github.com/LaihoE/demoparser  

  说明：CS2 replay parser，Rust 核心，提供 Python/Node binding。公开入口 `from demoparser2 import DemoParser`，查询方法包括 `parse_event(...)` 与 `parse_ticks(...)`。

- Awpy  
  https://github.com/pnxenopoulos/awpy  

  说明：CS2 Demo parsing / analytics / visualization；可访问 rounds, kills, damages, grenades, smokes, infernos, shots, footsteps, ticks，并提供 nav/visibility 等能力。

## CS2 external control

- Valve Developer Community — command line options  
  https://developer.valvesoftware.com/wiki/CHILLMODEA/Pages/Command_line_options  

  说明：`-netconport <number>` 创建可远程访问的 server console。

- CS2 current command-list community reference  
  https://github.com/ghostcap-gaming/Counter-Strike-2-Command-List  

  说明：当前列表中存在 `playdemo`, `demo_pause`, `demo_resume`, `demo_goto`, `demo_gototick`, `demo_timescale` 等。发布前必须在真实 CS2 build smoke test，不能只相信第三方列表。

## Anti-cheat / trusted mode

- Steam Support — CS2 Trusted Mode  
  https://help.steampowered.com/en/faqs/view/09A0-4879-4353-EF95  

  说明：Trusted Mode 阻止第三方文件注入/交互；定向进程篡改与 VAC 风险相关。因此产品架构明确不走 injection。

## Capture

- Microsoft — Windows.Graphics.Capture  
  https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture

- Microsoft — Desktop Duplication API  
  https://learn.microsoft.com/en-us/windows-hardware/drivers/display/desktop-duplication-api

## Desktop packaging

- Tauri v2 create project  
  https://v2.tauri.app/start/create-project/

- Tauri v2 sidecar  
  https://v2.tauri.app/develop/sidecar/

- Tauri shell plugin (JS)  
  https://v2.tauri.app/reference/javascript/shell/

- `tauri-plugin-shell` Rust docs  
  https://docs.rs/tauri-plugin-shell/latest/tauri_plugin_shell/

  说明：Tauri v2 支持 embedded external sidecar；Rust shell 插件暴露 `ShellExt::sidecar()` 与 `CommandChild`。打包计划见 `docs/ops/SIDECAR_PACKAGING.md`。

## AI

- OpenAI Responses API  
  https://developers.openai.com/api/reference/responses/overview

- OpenAI Responses resources  
  https://developers.openai.com/api/reference/resources/responses/

- OpenAI Structured Outputs  
  https://developers.openai.com/api/docs/guides/structured-outputs

  说明：Python SDK 在兼容模型上可用 `client.responses.parse(..., text_format=PydanticModel)`。

## Cursor

- Cursor Rules  
  https://cursor.com/docs/rules  

  说明：项目规则位于 `.cursor/rules/*.mdc`；`.cursorrules` 是 legacy 路径。
