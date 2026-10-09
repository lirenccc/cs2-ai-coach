mod bootstrap;
mod capture;
mod commands;
mod cs2;
mod security;
mod sidecar;

use cs2::session::ReplaySessionManager;
use std::sync::Mutex;
use tauri::Manager;

fn default_demo_staging_root() -> std::path::PathBuf {
    let manifest = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest
        .join("../../..")
        .join("runtime")
        .join("demo-staging")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let manager = tauri::async_runtime::block_on(sidecar::SidecarManager::start());
            app.manage(manager);
            app.manage(Mutex::new(ReplaySessionManager::new(
                default_demo_staging_root(),
            )));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_app_phase,
            commands::desktop_health,
            commands::analyzer_health,
            commands::sidecar_status,
            commands::preview_replay_command
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(manager) = app_handle.try_state::<sidecar::SidecarManager>() {
                    tauri::async_runtime::block_on(manager.stop());
                }
                if let Some(replay) = app_handle.try_state::<Mutex<ReplaySessionManager>>() {
                    if let Ok(mut guard) = replay.lock() {
                        guard.close();
                    }
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn app_phase_is_p0_5() {
        assert_eq!(commands::get_app_phase(), "P0.5");
    }
}
