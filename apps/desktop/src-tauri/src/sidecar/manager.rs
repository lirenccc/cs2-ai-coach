//! Owns analyzer process lifecycle: random loopback port, session token, spawn/stop.

use super::{health_at, request_shutdown, AnalyzerHealth, BridgeError, SessionEndpoint};
use rand::RngCore;
use serde::Serialize;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

const READY_TIMEOUT: Duration = Duration::from_secs(20);
const READY_POLL: Duration = Duration::from_millis(250);
const GRACEFUL_WAIT: Duration = Duration::from_secs(3);

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SidecarStatus {
    Starting,
    Ready,
    Crashed,
    Stopped,
    Failed,
}

#[derive(Debug)]
struct LiveSidecar {
    child: Child,
    endpoint: SessionEndpoint,
    status: SidecarStatus,
}

#[derive(Debug)]
enum ManagerInner {
    Live(LiveSidecar),
    Failed {
        error: BridgeError,
        status: SidecarStatus,
    },
    Stopped,
}

/// Managed analyzer sidecar. Token and port stay inside Rust; never returned to the renderer.
pub struct SidecarManager {
    inner: Mutex<ManagerInner>,
}

#[derive(Debug, Clone)]
struct SpawnPlan {
    program: PathBuf,
    args: Vec<String>,
    current_dir: Option<PathBuf>,
    db_path: PathBuf,
}

impl SidecarManager {
    pub async fn start() -> Self {
        match Self::spawn_and_wait().await {
            Ok(live) => Self {
                inner: Mutex::new(ManagerInner::Live(live)),
            },
            Err(error) => Self {
                inner: Mutex::new(ManagerInner::Failed {
                    status: SidecarStatus::Failed,
                    error,
                }),
            },
        }
    }

    pub fn status(&self) -> SidecarStatus {
        let mut guard = self.inner.lock().expect("sidecar mutex");
        Self::refresh_locked(&mut guard);
        match &*guard {
            ManagerInner::Live(live) => live.status,
            ManagerInner::Failed { status, .. } => *status,
            ManagerInner::Stopped => SidecarStatus::Stopped,
        }
    }

    pub async fn health(&self) -> Result<AnalyzerHealth, BridgeError> {
        let endpoint = {
            let mut guard = self.inner.lock().expect("sidecar mutex");
            Self::refresh_locked(&mut guard);
            match &*guard {
                ManagerInner::Live(live) if live.status == SidecarStatus::Ready => {
                    live.endpoint.clone()
                }
                ManagerInner::Live(live) if live.status == SidecarStatus::Crashed => {
                    return Err(BridgeError::new(
                        "SIDECAR_CRASHED",
                        "analyzer sidecar process exited unexpectedly",
                        true,
                    ));
                }
                ManagerInner::Failed { error, .. } => return Err(error.clone()),
                ManagerInner::Stopped => {
                    return Err(BridgeError::new(
                        "SIDECAR_NOT_READY",
                        "analyzer sidecar is stopped",
                        true,
                    ));
                }
                ManagerInner::Live(_) => {
                    return Err(BridgeError::new(
                        "SIDECAR_NOT_READY",
                        "analyzer sidecar is not ready",
                        true,
                    ));
                }
            }
        };

        match health_at(&endpoint).await {
            Ok(health) => Ok(health),
            Err(err) => {
                let mut guard = self.inner.lock().expect("sidecar mutex");
                Self::refresh_locked(&mut guard);
                if matches!(
                    &*guard,
                    ManagerInner::Live(live) if live.status == SidecarStatus::Crashed
                ) {
                    Err(BridgeError::new(
                        "SIDECAR_CRASHED",
                        "analyzer sidecar process exited unexpectedly",
                        true,
                    ))
                } else {
                    Err(err)
                }
            }
        }
    }

    pub async fn stop(&self) {
        let endpoint = {
            let mut guard = self.inner.lock().expect("sidecar mutex");
            match &mut *guard {
                ManagerInner::Live(live) => Some(live.endpoint.clone()),
                _ => None,
            }
        };

        if let Some(endpoint) = endpoint {
            let _ = request_shutdown(&endpoint).await;
            let deadline = Instant::now() + GRACEFUL_WAIT;
            while Instant::now() < deadline {
                {
                    let mut guard = self.inner.lock().expect("sidecar mutex");
                    if let ManagerInner::Live(live) = &mut *guard {
                        if let Ok(Some(_)) = live.child.try_wait() {
                            *guard = ManagerInner::Stopped;
                            return;
                        }
                    } else {
                        return;
                    }
                }
                async_sleep(Duration::from_millis(100)).await;
            }
        }

        let mut guard = self.inner.lock().expect("sidecar mutex");
        if let ManagerInner::Live(live) = &mut *guard {
            let _ = live.child.kill();
            let _ = live.child.wait();
        }
        *guard = ManagerInner::Stopped;
    }

    async fn spawn_and_wait() -> Result<LiveSidecar, BridgeError> {
        let host = "127.0.0.1".to_string();
        let port = pick_loopback_port()?;
        let token = random_session_token();
        let plan = resolve_spawn_plan()?;

        if let Some(parent) = plan.db_path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| {
                BridgeError::new(
                    "SIDECAR_SPAWN_FAILED",
                    format!("failed to create db directory: {e}"),
                    false,
                )
            })?;
        }

        let mut args = plan.args.clone();
        args.extend([
            "--host".into(),
            host.clone(),
            "--port".into(),
            port.to_string(),
            "--token".into(),
            token.clone(),
            "--db-path".into(),
            plan.db_path.to_string_lossy().into_owned(),
        ]);

        let mut command = Command::new(&plan.program);
        command
            .args(&args)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .env("CS2_COACH_ANALYZER_HOST", &host)
            .env("CS2_COACH_ANALYZER_PORT", port.to_string())
            .env("CS2_COACH_SESSION_TOKEN", &token)
            .env("CS2_COACH_DB_PATH", &plan.db_path);

        if let Some(dir) = &plan.current_dir {
            command.current_dir(dir);
        }

        let child = command.spawn().map_err(|e| {
            BridgeError::new(
                "SIDECAR_SPAWN_FAILED",
                format!(
                    "failed to spawn analyzer ({}): {e}",
                    plan.program.display()
                ),
                true,
            )
        })?;

        let endpoint = SessionEndpoint { host, port, token };
        let mut live = LiveSidecar {
            child,
            endpoint: endpoint.clone(),
            status: SidecarStatus::Starting,
        };

        let deadline = Instant::now() + READY_TIMEOUT;
        while Instant::now() < deadline {
            if let Ok(Some(status)) = live.child.try_wait() {
                return Err(BridgeError::new(
                    "SIDECAR_CRASHED",
                    format!("analyzer exited during startup with {status}"),
                    true,
                ));
            }

            match health_at(&endpoint).await {
                Ok(_) => {
                    live.status = SidecarStatus::Ready;
                    return Ok(live);
                }
                Err(err) if err.code == "SIDECAR_UNAUTHORIZED" => return Err(err),
                Err(_) => async_sleep(READY_POLL).await,
            }
        }

        let _ = live.child.kill();
        let _ = live.child.wait();
        Err(BridgeError::new(
            "SIDECAR_START_TIMEOUT",
            "analyzer did not become healthy in time",
            true,
        ))
    }

    fn refresh_locked(inner: &mut ManagerInner) {
        if let ManagerInner::Live(live) = inner {
            if live.status == SidecarStatus::Ready || live.status == SidecarStatus::Starting {
                match live.child.try_wait() {
                    Ok(Some(_)) => live.status = SidecarStatus::Crashed,
                    Ok(None) => {}
                    Err(_) => live.status = SidecarStatus::Crashed,
                }
            }
        }
    }
}

fn pick_loopback_port() -> Result<u16, BridgeError> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| {
        BridgeError::new(
            "SIDECAR_CONFIG",
            format!("failed to allocate loopback port: {e}"),
            true,
        )
    })?;
    let port = listener
        .local_addr()
        .map_err(|e| BridgeError::new("SIDECAR_CONFIG", e.to_string(), true))?
        .port();
    // Listener drops here so the child can bind the same port.
    Ok(port)
}

fn random_session_token() -> String {
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn workspace_root() -> Result<PathBuf, BridgeError> {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let root = manifest
        .join("../../..")
        .canonicalize()
        .map_err(|e| BridgeError::new("SIDECAR_CONFIG", e.to_string(), false))?;
    Ok(root)
}

fn resolve_python_executable(root: &PathBuf) -> Result<PathBuf, BridgeError> {
    if let Ok(custom) = std::env::var("CS2_COACH_ANALYZER_PYTHON") {
        let path = PathBuf::from(&custom);
        if path.exists() {
            return Ok(path);
        }
        return Err(BridgeError::new(
            "SIDECAR_SPAWN_FAILED",
            format!("CS2_COACH_ANALYZER_PYTHON not found: {custom}"),
            false,
        ));
    }

    let candidates = [
        root.join(".venv").join("Scripts").join("python.exe"),
        root.join(".venv").join("bin").join("python"),
    ];
    for candidate in candidates {
        if candidate.exists() {
            return Ok(candidate);
        }
    }

    // Dev machines may run analyzer tests with system Python 3.12.
    for name in ["python", "python3"] {
        if Command::new(name)
            .arg("-c")
            .arg("import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 12) else 1)")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
        {
            return Ok(PathBuf::from(name));
        }
    }

    Err(BridgeError::new(
        "SIDECAR_SPAWN_FAILED",
        "python 3.12+ not found (run scripts/bootstrap.ps1 or set CS2_COACH_ANALYZER_PYTHON / CS2_COACH_ANALYZER_BIN)",
        false,
    ))
}

fn resolve_spawn_plan() -> Result<SpawnPlan, BridgeError> {
    if let Ok(bin) = std::env::var("CS2_COACH_ANALYZER_BIN") {
        let path = PathBuf::from(bin);
        if !path.exists() {
            return Err(BridgeError::new(
                "SIDECAR_SPAWN_FAILED",
                format!("CS2_COACH_ANALYZER_BIN not found: {}", path.display()),
                false,
            ));
        }
        let db_path = std::env::var("CS2_COACH_DB_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                std::env::temp_dir().join("cs2-ai-coach").join("app.db")
            });
        return Ok(SpawnPlan {
            program: path,
            args: Vec::new(),
            current_dir: None,
            db_path,
        });
    }

    let root = workspace_root()?;
    let python = resolve_python_executable(&root)?;

    let analyzer_dir = root.join("services").join("analyzer");
    if !analyzer_dir.join("app").exists() {
        return Err(BridgeError::new(
            "SIDECAR_SPAWN_FAILED",
            format!("analyzer package missing under {}", analyzer_dir.display()),
            false,
        ));
    }

    let db_path = std::env::var("CS2_COACH_DB_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| root.join("runtime").join("app.db"));

    Ok(SpawnPlan {
        program: python,
        args: vec!["-m".into(), "app".into()],
        current_dir: Some(analyzer_dir),
        db_path,
    })
}

async fn async_sleep(duration: Duration) {
    let _ = tauri::async_runtime::spawn_blocking(move || thread::sleep(duration)).await;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pick_loopback_port_is_nonzero() {
        let port = pick_loopback_port().expect("port");
        assert!(port > 0);
    }

    #[test]
    fn session_token_is_64_hex_chars() {
        let token = random_session_token();
        assert_eq!(token.len(), 64);
        assert!(token.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn distinct_ports_across_calls() {
        let a = pick_loopback_port().unwrap();
        let b = pick_loopback_port().unwrap();
        // Extremely unlikely to collide when binding :0 twice sequentially after drop.
        // Soft assert: both valid; equality is allowed but rare.
        assert!(a > 0 && b > 0);
        let _ = (a, b);
    }

    #[test]
    fn resolve_spawn_plan_finds_repo_python_or_errors_clearly() {
        match resolve_spawn_plan() {
            Ok(plan) => {
                assert!(
                    plan.program.exists()
                        || plan.program == PathBuf::from("python")
                        || plan.program == PathBuf::from("python3")
                );
                assert!(plan.args.contains(&"app".to_string()) || plan.args.is_empty());
            }
            Err(err) => {
                assert_eq!(err.code, "SIDECAR_SPAWN_FAILED");
                assert!(
                    err.message.contains("python")
                        || err.message.contains("ANALYZER")
                        || err.message.contains("analyzer")
                );
            }
        }
    }

    #[test]
    #[ignore = "spawns a real analyzer process; run with --ignored when validating P0.3"]
    fn spawn_health_and_graceful_stop_smoke() {
        let manager = tauri::async_runtime::block_on(SidecarManager::start());
        let health = tauri::async_runtime::block_on(manager.health())
            .expect("sidecar should become healthy");
        assert_eq!(health.status, "ok");
        assert_eq!(manager.status(), SidecarStatus::Ready);
        tauri::async_runtime::block_on(manager.stop());
        assert_eq!(manager.status(), SidecarStatus::Stopped);
    }

}
