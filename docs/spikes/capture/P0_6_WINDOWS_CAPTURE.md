# P0.6 Windows Capture Spike

Date: 2026-10-10  
Host OS: Windows 10/11 (`win32` 10.0.26300)  
Private fixture: `9208210907649202700_0` (zip/dem **not** committed)  
Replay semantics: `p0.5a-2026-10-10` (unchanged; DemoTick authoritative)  
Redacted manifest sample: `docs/spikes/capture/fixtures/capture_manifest.redacted.json`

## Verdict

**Windows.Graphics.Capture can capture valid, non-black CS2 offline-replay frames from a process-owned HWND**, after calibrated `ReplaySeekPosition::DemoTick` seeks, with versioned manifests and local quality checks.

Parser / Storage v2 / P0.5A seek semantics were **not** modified.

## Environment

| Field | Value |
| --- | --- |
| OS | Microsoft Windows NT 10.0.26300.0 |
| GPU (CS2 render device log) | NVIDIA GeForce RTX 4070 Ti SUPER (`0x10DE` / `0x2705`), driver `32.0.16.1088` |
| Other adapters present | AMD Radeon(TM) Graphics; Todesk Virtual Display |
| CS2 `PatchVersion` | `1.41.9.0` |
| CS2 `ClientVersion` | `2000930` |
| Steam `buildid` | `25815307` |
| Calibration match | **yes** — same build family as P0.5A; no silent reuse across mismatched builds |

## Capture backend

| Item | Result |
| --- | --- |
| Primary | `CaptureBackend::WindowsGraphicsCapture` |
| WGC supported | `GraphicsCaptureSession::IsSupported() == true` |
| API path | `HWND` → `IGraphicsCaptureItemInterop::CreateForWindow` → `GraphicsCaptureItem` → `Direct3D11CaptureFramePool::CreateFreeThreaded` (`B8G8R8A8UIntNormalized`, 2 buffers) → `GraphicsCaptureSession::StartCapture` → `TryGetNextFrame` → DXGI staging `CopyResource` / `Map` → CPU BGRA buffer |
| DXGI fallback | **Documented strategy only** (`DesktopDuplicationPlan` crop-from-monitor). Not auto-exercised while WGC is healthy (development does not hide WGC bugs behind fallback). |
| Pixel format recorded | `B8G8R8A8_UNORM` |
| HDR | Not required on this setup; SDR path used. If HD Color/HDR ever yields wrong colors, report format/environment rather than claiming validity. |

## Window discovery

Process ownership first (`cs2.exe` PID), title/class metadata only.

| Observation | Value |
| --- | --- |
| Main window class | `SDL_app` |
| Title (locale-dependent) | e.g. localized CS2 title — **not** used as identity |
| Client area | `1280×720` windowed |
| Captured content size | `1282×752` (WGC content size; may include thin chrome vs client rect) |
| Ambiguity handling | typed `CAPTURE_TARGET_AMBIGUOUS` when multiple large non-tool windows |
| Missing window | `CAPTURE_CS2_WINDOW_NOT_FOUND` |

## Single-frame / burst

| Probe | Result |
| --- | --- |
| Single frame | `1282×752`, `valid=true`, `black_ratio≈0.26`, `variance≈4363` |
| Burst ×5 | all `valid=true`; paused replay may reuse identical hashes (expected) |
| Static-frame note | WGC often stops delivering frames while the scene is paused; session/pool recreate forces a fresh sample |

Example content hash (encoded PNG SHA-256):

```text
e0370b197addc71af40527b54cb2670748c9659971f3bed295e30723299824fa
```

## Capture after calibrated seek

Policy: `SettlePolicy::FixedDuration { ms: 2000 }` (spike value; not final production), plus a short resume/pause compositor nudge (**never** `demo_gototick 0`).

| Anchor | DemoTick | ServerTick (reference only) | Capture |
| --- | ---: | ---: | --- |
| A01_early_plant | 4354 | 8133 | valid, distinct hash |
| A02_mid_defuse | 42294 | 46073 | valid + 5-frame burst |
| A04_post_halftime_explode | 79639 | 83418 | valid |

- Seek path: `ReplayCommand::go_to_seek_position(ReplaySeekPosition::DemoTick(..))` only.
- `ReplaySeekPosition::ServerTick` / `ReplayTick::server` rejected at production boundary.
- Manifest records `requested_demo_tick` + `replay_semantics_version` + optional `server_tick_reference` (never passed to `demo_gototick`).

## Occlusion / minimized / restore / resize

| Scenario | Observed |
| --- | --- |
| Occlusion | Manual probe exists (`probe_occlusion_behavior`). WGC typically continues capturing composited window contents while occluded — do not assume BitBlt-like blackout. |
| Minimized | Verified: `CAPTURE_TARGET_MINIMIZED` on discover after `ShowWindow(SW_MINIMIZE)`. Restore rediscovers a non-minimized target. Must **not** return a silent valid black success. |
| Resize | `SetWindowPos` exercise: HWND survived; `frame_pool_recreated=true` on subsequent capture. CS2 may keep the same internal render size in this windowed mode — recreate path still runs. If HWND itself changes, rediscover rather than reuse the stale handle. |
| Device recreate | Not required on the happy path for this spike. |

## Manifest + storage

- Version: `p0.6-2026-10-10`
- Runtime tree: `runtime/captures/<match-id>/<capture-id>/frame-NNNN.png` + `manifest.json`
- Image blobs **not** in SQLite
- Committed fixture is redacted (no HWND, no private absolute paths, no NetCon secrets)
- PNG content hash computed on final encoded bytes

## Tauri boundary

Exposed commands only:

- `capture_health`
- `capture_cs2_snapshot`
- `capture_cs2_burst`

Not exposed: arbitrary HWND capture, desktop region capture, raw D3D surfaces, large RGBA IPC payloads (renderer gets metadata + managed file reference).

## Security / product invariants (unchanged)

- Offline Demo replay capture only; no live competitive automation
- No injection, process-memory access, binary patch, overlay advantage
- Higher layers must explicitly start an offline replay capture operation
- No tick-0 seek nudges on this build family

## Fallback strategy (when WGC is not usable)

Select DXGI Desktop Duplication only if:

- WGC unsupported / init failed / repeated invalid frames **and** fallback explicitly allowed

Then: capture the monitor containing CS2, crop with validated window/client coordinates + DPI, never assume origin `(0,0)`.

P0.6 success criterion is WGC proof first — DXGI remains a strategy stub.

## Known limitations / assumptions

1. Captured resolution on this run was windowed `~1280×720`, not forced 1920×1080.
2. Automatic POV is out of scope; wrong camera is a later milestone.
3. Paused bursts may share content hashes; distinguish `duplicate_expected_while_paused` vs `capture_backend_stuck`.
4. Late-match anchors can share hashes if visuals converge or settle is insufficient — operator visual check remains useful.
5. Future CS2 builds may change HWND class/layout or WGC behavior; re-run ignored probes.
6. Virtual display adapters (remote desktop) can coexist; prefer the GPU CS2 actually uses.

## How to re-run

```powershell
$env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.zip"
cargo test -p cs2-ai-coach --lib probe_capture_after_calibrated_seek -- --ignored --nocapture --test-threads=1
cargo test -p cs2-ai-coach --lib probe_wgc_single_frame -- --ignored --nocapture --test-threads=1
cargo test -p cs2-ai-coach --lib probe_wgc_burst_5 -- --ignored --nocapture --test-threads=1
cargo test -p cs2-ai-coach --lib probe_resize_recovery -- --ignored --nocapture --test-threads=1
```

Do **not** commit private screenshots or the private Demo.
