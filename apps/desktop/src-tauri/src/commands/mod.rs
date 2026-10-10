//! Narrow typed Tauri command surface.
//! The renderer cannot build raw CS2 console lines or call the analyzer directly.
//! Capture commands expose high-level ops only — no arbitrary HWND / raw D3D.

use crate::bootstrap::app_phase;
use crate::capture::adapter::{discover_running_cs2_window, CaptureAdapter, NativeCaptureAdapter};
use crate::capture::error::CaptureError;
use crate::capture::types::{
    CaptureBurstRequest, CaptureFrameRequest, CaptureHealth, ReplayCaptureContext,
};
use crate::cs2::replay::ReplayCommand;
use crate::sidecar::{self, BridgeError, SidecarManager, SidecarStatus};
use serde::Serialize;
use std::path::PathBuf;
use std::time::Duration;
use tauri::State;

#[derive(Serialize)]
pub struct DesktopHealth {
    app: &'static str,
    version: &'static str,
    platform: &'static str,
}

#[derive(Serialize)]
pub struct CaptureSnapshotResult {
    pub frame_id: String,
    pub width: u32,
    pub height: u32,
    pub content_sha256: String,
    pub valid: bool,
    pub storage_path_relative: Option<String>,
    pub warnings: Vec<String>,
}

fn default_capture_runtime() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join("runtime")
}

fn map_capture_err(err: CaptureError) -> String {
    format!("{}: {}", err.code, err.message)
}

#[tauri::command]
pub fn get_app_phase() -> String {
    app_phase().to_string()
}

#[tauri::command]
pub fn desktop_health() -> DesktopHealth {
    DesktopHealth {
        app: "CS2 AI Coach",
        version: env!("CARGO_PKG_VERSION"),
        platform: std::env::consts::OS,
    }
}

#[tauri::command]
pub async fn analyzer_health(
    state: State<'_, SidecarManager>,
) -> Result<sidecar::AnalyzerHealth, BridgeError> {
    state.health().await
}

#[tauri::command]
pub fn sidecar_status(state: State<'_, SidecarManager>) -> SidecarStatus {
    state.status()
}

/// Import a local demo via the analyzer sidecar. Renderer never sees the session token.
#[tauri::command]
pub async fn import_demo(
    state: State<'_, SidecarManager>,
    path: String,
) -> Result<serde_json::Value, BridgeError> {
    state.import_demo(path).await
}

/// Load the offline Match Review projection for a parsed match.
#[tauri::command]
pub async fn get_match_review(
    state: State<'_, SidecarManager>,
    match_id: String,
) -> Result<serde_json::Value, BridgeError> {
    state.get_match_review(match_id).await
}

#[tauri::command]
pub fn preview_replay_command(kind: String, value: Option<String>) -> Result<String, String> {
    let cmd = match kind.as_str() {
        "pause" => ReplayCommand::Pause,
        "resume" => ReplayCommand::Resume,
        "timescale" => {
            let raw = value.ok_or_else(|| "missing timescale".to_string())?;
            let scale: f32 = raw.parse().map_err(|_| "invalid timescale".to_string())?;
            ReplayCommand::timescale(scale)?
        }
        _ => return Err("unsupported preview command".into()),
    };
    Ok(cmd.to_console_line())
}

#[tauri::command]
pub fn capture_health() -> Result<CaptureHealth, String> {
    let adapter = NativeCaptureAdapter::new(default_capture_runtime());
    Ok(adapter.health())
}

/// Capture a single CS2 offline-replay frame. Renderer receives metadata + managed path only.
#[tauri::command]
pub fn capture_cs2_snapshot(demo_tick: Option<u64>) -> Result<CaptureSnapshotResult, String> {
    let mut adapter = NativeCaptureAdapter::new(default_capture_runtime());
    if let Some(tick) = demo_tick {
        let ctx = ReplayCaptureContext::from_demo_tick(tick)
            .map_err(|e| format!("CAPTURE_REPLAY_CONTEXT_INVALID: {e}"))?;
        adapter.set_replay_context(ctx).map_err(map_capture_err)?;
    }
    let target = discover_running_cs2_window().map_err(map_capture_err)?;
    adapter.open(&target).map_err(map_capture_err)?;
    let frame = adapter
        .capture_frame(&CaptureFrameRequest {
            timeout: Duration::from_secs(5),
            persist: true,
            previous_content_sha256: None,
            replay_paused: true,
        })
        .map_err(map_capture_err)?;
    adapter.close();
    Ok(CaptureSnapshotResult {
        frame_id: frame.frame_id,
        width: frame.width,
        height: frame.height,
        content_sha256: frame.content_sha256,
        valid: frame.quality.valid,
        storage_path_relative: frame
            .storage_path
            .as_ref()
            .map(|p| p.file_name().unwrap_or_default().to_string_lossy().into()),
        warnings: frame.quality.warnings,
    })
}

#[tauri::command]
pub fn capture_cs2_burst(count: u32) -> Result<Vec<CaptureSnapshotResult>, String> {
    let mut adapter = NativeCaptureAdapter::new(default_capture_runtime());
    let target = discover_running_cs2_window().map_err(map_capture_err)?;
    adapter.open(&target).map_err(map_capture_err)?;
    let frames = adapter
        .capture_burst(
            &CaptureBurstRequest {
                count,
                interval: Duration::from_millis(100),
                timeout: Duration::from_secs(20),
                persist: true,
                replay_paused: true,
            },
            None,
        )
        .map_err(map_capture_err)?;
    adapter.close();
    Ok(frames
        .into_iter()
        .map(|frame| CaptureSnapshotResult {
            frame_id: frame.frame_id,
            width: frame.width,
            height: frame.height,
            content_sha256: frame.content_sha256,
            valid: frame.quality.valid,
            storage_path_relative: frame
                .storage_path
                .as_ref()
                .map(|p| p.file_name().unwrap_or_default().to_string_lossy().into()),
            warnings: frame.quality.warnings,
        })
        .collect())
}
