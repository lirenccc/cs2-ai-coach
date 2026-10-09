mod bootstrap;
mod capture;
mod commands;
mod cs2;
mod security;
mod sidecar;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let manager = tauri::async_runtime::block_on(sidecar::SidecarManager::start());
            app.manage(manager);
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
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn app_phase_is_p0_3() {
        assert_eq!(commands::get_app_phase(), "P0.3");
    }
}
