//! Narrow typed Tauri command surface.
//! The renderer cannot build raw CS2 console lines or call the analyzer directly.

use crate::bootstrap::app_phase;
use crate::cs2::replay::ReplayCommand;
use crate::sidecar;
use serde::Serialize;

#[derive(Serialize)]
pub struct DesktopHealth {
    app: &'static str,
    version: &'static str,
    platform: &'static str,
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
pub async fn analyzer_health() -> Result<sidecar::AnalyzerHealth, String> {
    sidecar::health().await.map_err(|e| e.to_string())
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
