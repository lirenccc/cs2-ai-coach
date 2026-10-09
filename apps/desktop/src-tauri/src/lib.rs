mod bootstrap;
mod capture;
mod commands;
mod cs2;
mod security;
mod sidecar;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            commands::get_app_phase,
            commands::desktop_health,
            commands::analyzer_health,
            commands::preview_replay_command
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn app_phase_is_p0_1() {
        assert_eq!(commands::get_app_phase(), "P0.1");
    }
}
