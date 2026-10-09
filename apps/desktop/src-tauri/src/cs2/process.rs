//! Windows-first CS2 / Steam process discovery and launch.
//!
//! Uses OS process APIs and typed argv only. No DLL injection, no game-memory
//! read/write, no binary patching, no `-insecure`.

use crate::cs2::error::Cs2Error;
use rand::Rng;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};
use sysinfo::{ProcessesToUpdate, System};

pub const CS2_APP_ID: &str = "730";
const DEFAULT_READY_TIMEOUT: Duration = Duration::from_secs(180);
const READY_POLL: Duration = Duration::from_millis(500);

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Cs2ProcessState {
    NotInstalled,
    SteamMissing,
    NotRunning,
    Running {
        pid: u32,
        image_path: Option<PathBuf>,
    },
    RunningWithoutNetCon {
        pid: u32,
    },
    NetConReady {
        pid: Option<u32>,
        port: u16,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LaunchPlan {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub netcon_port: u16,
    /// Password launch arg is intentionally omitted until `-netconpassword`
    /// is verified on a real build (see P0_5_NETCON_STATUS.md).
    pub netcon_password: Option<String>,
    /// Windows NetCon workaround flag; only set when tools modules are present.
    pub uses_tools: bool,
}

#[derive(Debug, Clone)]
pub struct Cs2InstallPaths {
    pub steam_exe: PathBuf,
    pub cs2_exe: PathBuf,
    pub game_dir: PathBuf,
    pub csgo_dir: PathBuf,
}

pub struct Cs2ProcessManager {
    sys: System,
}

impl Default for Cs2ProcessManager {
    fn default() -> Self {
        Self::new()
    }
}

impl Cs2ProcessManager {
    pub fn new() -> Self {
        Self {
            sys: System::new(),
        }
    }

    pub fn detect_steam(&mut self) -> Result<PathBuf, Cs2Error> {
        if let Ok(custom) = std::env::var("CS2_COACH_STEAM_EXE") {
            let path = PathBuf::from(&custom);
            if path.is_file() {
                return Ok(path);
            }
            return Err(Cs2Error::steam_not_found());
        }

        self.refresh_processes();
        for (_pid, process) in self.sys.processes() {
            let name = process.name().to_string_lossy().to_ascii_lowercase();
            if name == "steam.exe" || name == "steam" {
                if let Some(path) = process.exe() {
                    return Ok(path.to_path_buf());
                }
            }
        }

        for candidate in common_steam_candidates() {
            if candidate.is_file() {
                return Ok(candidate);
            }
        }
        Err(Cs2Error::steam_not_found())
    }

    pub fn detect_cs2(&mut self) -> Result<PathBuf, Cs2Error> {
        if let Ok(custom) = std::env::var("CS2_COACH_CS2_EXE") {
            let path = PathBuf::from(&custom);
            if path.is_file() {
                return Ok(path);
            }
            return Err(Cs2Error::cs2_not_installed());
        }

        self.refresh_processes();
        for (_pid, process) in self.sys.processes() {
            let name = process.name().to_string_lossy().to_ascii_lowercase();
            if name == "cs2.exe" || name == "cs2" {
                if let Some(path) = process.exe() {
                    return Ok(path.to_path_buf());
                }
            }
        }

        let steam = self.detect_steam().ok();
        for candidate in common_cs2_candidates(steam.as_deref()) {
            if candidate.is_file() {
                return Ok(candidate);
            }
        }
        Err(Cs2Error::cs2_not_installed())
    }

    pub fn resolve_install_paths(&mut self) -> Result<Cs2InstallPaths, Cs2Error> {
        let steam_exe = self.detect_steam()?;
        let cs2_exe = self.detect_cs2()?;
        let game_dir = cs2_exe
            .parent()
            .and_then(|p| p.parent()) // win64 -> bin
            .and_then(|p| p.parent()) // bin -> game
            .map(|p| p.to_path_buf())
            .ok_or_else(Cs2Error::cs2_not_installed)?;
        let csgo_dir = game_dir.join("csgo");
        if !csgo_dir.is_dir() {
            return Err(Cs2Error::cs2_not_installed());
        }
        Ok(Cs2InstallPaths {
            steam_exe,
            cs2_exe,
            game_dir,
            csgo_dir,
        })
    }

    pub fn get_process_state(&mut self, expected_netcon_port: Option<u16>) -> Cs2ProcessState {
        if self.detect_cs2().is_err() {
            return Cs2ProcessState::NotInstalled;
        }
        if self.detect_steam().is_err() {
            return Cs2ProcessState::SteamMissing;
        }

        self.refresh_processes();
        let mut running: Option<(u32, Option<PathBuf>, Option<u16>)> = None;
        for (pid, process) in self.sys.processes() {
            let name = process.name().to_string_lossy().to_ascii_lowercase();
            if name == "cs2.exe" || name == "cs2" {
                let mut cmdline_port = parse_netcon_port_from_cmd(process.cmd());
                // On Windows, sysinfo often omits argv without elevation; fall back to WMI.
                if cmdline_port.is_none() {
                    cmdline_port = windows_cs2_netcon_port_via_wmi();
                }
                running = Some((
                    pid.as_u32(),
                    process.exe().map(|p| p.to_path_buf()),
                    cmdline_port,
                ));
                break;
            }
        }

        let Some((pid, image_path, cmdline_port)) = running else {
            return Cs2ProcessState::NotRunning;
        };

        if let Some(port) = expected_netcon_port {
            if netcon_port_open(port) {
                return Cs2ProcessState::NetConReady {
                    pid: Some(pid),
                    port,
                };
            }
            // Different port than this session expects → treat as unmanaged instance.
            return Cs2ProcessState::RunningWithoutNetCon { pid };
        }

        if let Some(port) = cmdline_port {
            if netcon_port_open(port) {
                return Cs2ProcessState::NetConReady {
                    pid: Some(pid),
                    port,
                };
            }
        }

        if cmdline_port.is_some() {
            // Flag present but socket not accepting yet / failed to bind.
            return Cs2ProcessState::RunningWithoutNetCon { pid };
        }

        Cs2ProcessState::Running { pid, image_path }
    }

    /// OS command-line inspection only (not game-memory). Returns NetCon port if present.
    pub fn detect_running_netcon_port(&mut self) -> Option<u16> {
        match self.get_process_state(None) {
            Cs2ProcessState::NetConReady { port, .. } => Some(port),
            _ => None,
        }
    }

    /// Build typed launch argv. Never concatenates an untrusted shell string.
    pub fn build_launch_plan(
        &mut self,
        netcon_port: u16,
        netcon_password: Option<String>,
    ) -> Result<LaunchPlan, Cs2Error> {
        let paths = self.resolve_install_paths()?;
        // Prefer Steam applaunch so the normal Steam client session is preserved.
        //
        // Windows note: Valve issue csgo-osx-linux#3603 — without `-tools`, early
        // `-netconport` socket creation can fail with WSANOTINITIALISED because
        // WSAStartup has not run yet. `-tools` is a documented Workshop Tools path,
        // not injection / `-insecure` / VAC bypass.
        //
        // `-tools` requires ToolFramework modules such as `assetsystem.dll`. If they
        // are missing, CS2 shows error 126 / “game files missing” — do not force it.
        let mut args = vec![
            "-applaunch".to_string(),
            CS2_APP_ID.to_string(),
            "-netconport".to_string(),
            netcon_port.to_string(),
        ];
        let mut uses_tools = false;
        if cfg!(windows) {
            let tools_ok = tools_modules_present(&paths.cs2_exe);
            let force_tools =
                std::env::var("CS2_COACH_FORCE_TOOLS").ok().as_deref() == Some("1");
            let allow_without = std::env::var("CS2_COACH_ALLOW_NETCON_WITHOUT_TOOLS")
                .ok()
                .as_deref()
                == Some("1");
            if tools_ok || force_tools {
                args.push("-tools".to_string());
                uses_tools = true;
            } else if !allow_without {
                return Err(Cs2Error::tools_unavailable(
                    "Windows NetCon currently requires -tools, but assetsystem.dll is missing next to cs2.exe (ToolFramework2 dependency; Win32 error 126)",
                ));
            }
        }
        // Password: engine strings mention PASS auth; launch option is community-
        // documented. Pass only when CS2_COACH_ATTEMPT_NETCON_PASSWORD=1 until
        // verified on this machine's build (see P0_5_NETCON_STATUS.md).
        if let Some(password) = netcon_password.clone() {
            if std::env::var("CS2_COACH_ATTEMPT_NETCON_PASSWORD").ok().as_deref() == Some("1") {
                args.push("-netconpassword".to_string());
                args.push(password);
            }
        }
        Ok(LaunchPlan {
            program: paths.steam_exe,
            args,
            netcon_port,
            netcon_password,
            uses_tools,
        })
    }

    pub fn allocate_netcon_port() -> Result<u16, Cs2Error> {
        // Prefer high ephemeral ports.
        let mut rng = rand::thread_rng();
        for _ in 0..32 {
            let port = rng.gen_range(49152..=65535);
            if TcpListener::bind(("127.0.0.1", port)).is_ok() {
                return Ok(port);
            }
        }
        let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| {
            Cs2Error::launch_failed(format!("failed to allocate NetCon port: {e}"))
        })?;
        Ok(listener
            .local_addr()
            .map_err(|e| Cs2Error::launch_failed(e.to_string()))?
            .port())
    }

    pub fn launch_cs2(&mut self, plan: &LaunchPlan) -> Result<(), Cs2Error> {
        match self.get_process_state(Some(plan.netcon_port)) {
            Cs2ProcessState::NetConReady { .. } => return Ok(()),
            Cs2ProcessState::RunningWithoutNetCon { .. }
            | Cs2ProcessState::Running { .. } => {
                return Err(Cs2Error::already_running_without_netcon());
            }
            Cs2ProcessState::NotInstalled => return Err(Cs2Error::cs2_not_installed()),
            Cs2ProcessState::SteamMissing => return Err(Cs2Error::steam_not_found()),
            Cs2ProcessState::NotRunning => {}
        }

        Command::new(&plan.program)
            .args(&plan.args)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| {
                Cs2Error::launch_failed(format!(
                    "failed to spawn {}: {e}",
                    plan.program.display()
                ))
            })?;
        Ok(())
    }

    pub fn wait_for_cs2_ready(
        &mut self,
        port: u16,
        timeout: Option<Duration>,
    ) -> Result<Cs2ProcessState, Cs2Error> {
        let timeout = timeout.unwrap_or(DEFAULT_READY_TIMEOUT);
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            let state = self.get_process_state(Some(port));
            if matches!(state, Cs2ProcessState::NetConReady { .. }) {
                return Ok(state);
            }
            // Also accept open NetCon before process enumeration settles.
            if netcon_port_open(port) {
                return Ok(Cs2ProcessState::NetConReady { pid: None, port });
            }
            thread::sleep(READY_POLL);
        }
        Err(Cs2Error::start_timeout())
    }

    pub fn is_cs2_process_alive(&mut self) -> bool {
        self.refresh_processes();
        self.sys.processes().values().any(|process| {
            let name = process.name().to_string_lossy().to_ascii_lowercase();
            name == "cs2.exe" || name == "cs2"
        })
    }

    fn refresh_processes(&mut self) {
        self.sys.refresh_processes(ProcessesToUpdate::All, true);
    }
}

fn netcon_port_open(port: u16) -> bool {
    std::net::TcpStream::connect_timeout(
        &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
        Duration::from_millis(200),
    )
    .is_ok()
}

/// Workshop/tools prerequisite for Windows `-tools` NetCon workaround.
fn tools_modules_present(cs2_exe: &Path) -> bool {
    let Some(dir) = cs2_exe.parent() else {
        return false;
    };
    // Observed failure: ToolFramework2_002 → assetsystem, Win32 error 126 (MOD_NOT_FOUND).
    dir.join("assetsystem.dll").is_file() && dir.join("toolframework2.dll").is_file()
}

fn parse_netcon_port_from_cmd(cmd: &[impl AsRef<std::ffi::OsStr>]) -> Option<u16> {
    let mut args = cmd.iter().map(|a| a.as_ref().to_string_lossy());
    while let Some(arg) = args.next() {
        if arg == "-netconport" {
            return args.next().and_then(|v| v.parse().ok());
        }
        if let Some(rest) = arg.strip_prefix("-netconport=") {
            return rest.parse().ok();
        }
    }
    None
}

fn parse_netcon_port_from_command_line(line: &str) -> Option<u16> {
    let parts: Vec<&str> = line.split_whitespace().collect();
    parse_netcon_port_from_cmd(&parts)
}

/// Fixed WMI query (no user-controlled shell concatenation). OS process metadata only.
#[cfg(windows)]
fn windows_cs2_netcon_port_via_wmi() -> Option<u16> {
    let output = Command::new("powershell.exe")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-CimInstance Win32_Process -Filter \"name = 'cs2.exe'\" | Select-Object -First 1 -ExpandProperty CommandLine)",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let line = String::from_utf8_lossy(&output.stdout);
    parse_netcon_port_from_command_line(line.trim())
}

#[cfg(not(windows))]
fn windows_cs2_netcon_port_via_wmi() -> Option<u16> {
    None
}

fn common_steam_candidates() -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(pf86) = std::env::var("ProgramFiles(x86)") {
        out.push(PathBuf::from(pf86).join("Steam").join("steam.exe"));
    }
    if let Ok(pf) = std::env::var("ProgramFiles") {
        out.push(PathBuf::from(pf).join("Steam").join("steam.exe"));
    }
    out.push(PathBuf::from(
        r"C:\Program Files (x86)\Steam\steam.exe",
    ));
    out
}

fn common_cs2_candidates(steam_exe: Option<&Path>) -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Some(steam) = steam_exe {
        if let Some(steam_dir) = steam.parent() {
            roots.push(
                steam_dir
                    .join("steamapps")
                    .join("common")
                    .join("Counter-Strike Global Offensive"),
            );
        }
    }
    if let Ok(pf86) = std::env::var("ProgramFiles(x86)") {
        roots.push(
            PathBuf::from(pf86)
                .join("Steam")
                .join("steamapps")
                .join("common")
                .join("Counter-Strike Global Offensive"),
        );
    }
    roots.push(PathBuf::from(
        r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive",
    ));

    roots
        .into_iter()
        .map(|root| root.join("game").join("bin").join("win64").join("cs2.exe"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn launch_plan_uses_typed_argv_not_shell_string() {
        let mut mgr = Cs2ProcessManager::new();
        // May fail on machines without Steam; still validate constructor helpers.
        let port = 51234u16;
        let plan = LaunchPlan {
            program: PathBuf::from(r"C:\Steam\steam.exe"),
            args: vec![
                "-applaunch".into(),
                CS2_APP_ID.into(),
                "-netconport".into(),
                port.to_string(),
            ],
            netcon_port: port,
            netcon_password: None,
            uses_tools: false,
        };
        assert_eq!(plan.args.len(), 4);
        assert_eq!(plan.args[0], "-applaunch");
        assert_eq!(plan.args[2], "-netconport");
        assert!(!plan.args.iter().any(|a| a.contains('&') || a.contains('|')));
        // Ensure build_launch_plan shape when Steam is present.
        match mgr.build_launch_plan(port, None) {
            Ok(built) => {
                assert_eq!(built.args[0], "-applaunch");
                assert_eq!(built.args[1], "730");
                assert_eq!(built.args[2], "-netconport");
                assert_eq!(built.args[3], port.to_string());
                assert!(!built.args.iter().any(|a| a == "-insecure"));
                assert!(!built.args.iter().any(|a| a == "-netconpassword"));
                if cfg!(windows) && built.uses_tools {
                    assert!(built.args.iter().any(|a| a == "-tools"));
                }
            }
            Err(err) => {
                // Missing Workshop Tools modules on this machine is an expected gate.
                assert_eq!(err.code, "CS2_TOOLS_UNAVAILABLE");
            }
        }
    }

    #[test]
    fn tools_modules_gate_checks_dlls() {
        let dir = std::env::temp_dir().join(format!("cs2coach-tools-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let exe = dir.join("cs2.exe");
        std::fs::write(&exe, b"x").unwrap();
        assert!(!tools_modules_present(&exe));
        std::fs::write(dir.join("toolframework2.dll"), b"x").unwrap();
        assert!(!tools_modules_present(&exe));
        std::fs::write(dir.join("assetsystem.dll"), b"x").unwrap();
        assert!(tools_modules_present(&exe));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn allocate_port_is_nonzero() {
        let port = Cs2ProcessManager::allocate_netcon_port().unwrap();
        assert!(port > 0);
    }

    #[test]
    fn parses_netcon_port_from_argv() {
        assert_eq!(
            parse_netcon_port_from_cmd(&["cs2.exe", "-netconport", "54624"]),
            Some(54624)
        );
        assert_eq!(
            parse_netcon_port_from_cmd(&["cs2.exe", "-netconport=12345", "-tools"]),
            Some(12345)
        );
        assert_eq!(parse_netcon_port_from_cmd(&["cs2.exe", "-tools"]), None);
        assert_eq!(
            parse_netcon_port_from_command_line(
                r#""C:\game\cs2.exe" -steam -netconport 54624 -tools"#
            ),
            Some(54624)
        );
    }

    #[test]
    #[ignore = "requires Steam/CS2 install; not for CI"]
    fn detect_steam_and_cs2_on_windows() {
        let mut mgr = Cs2ProcessManager::new();
        let steam = mgr.detect_steam().expect("steam");
        let cs2 = mgr.detect_cs2().expect("cs2");
        assert!(steam.ends_with("steam.exe") || steam.ends_with("steam"));
        assert!(cs2.ends_with("cs2.exe") || cs2.ends_with("cs2"));
    }
}
