//! Manual Windows / real-CS2 integration probes.
//!
//! Ignored by default so CI never requires Steam or CS2.
//!
//! Run (PowerShell):
//! ```text
//! $env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.zip"
//! cargo test -p cs2-ai-coach --lib cs2::integration -- --ignored --nocapture
//! ```

use super::process::Cs2ProcessManager;
use super::replay::ReplayCommand;
use super::session::{ReplaySession, ReplaySessionState};
use super::staging::DemoStagingService;
use super::tick::ReplayTick;
use std::path::PathBuf;
use std::time::Duration;

fn real_demo_path() -> Option<PathBuf> {
    std::env::var_os("CS2_COACH_REAL_DEMO").map(PathBuf::from)
}

fn staging_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join("runtime")
        .join("demo-staging")
}

#[test]
#[ignore = "requires Steam install; not for CI"]
fn probe_detect_steam() {
    let mut mgr = Cs2ProcessManager::new();
    let steam = mgr.detect_steam().expect("Steam");
    eprintln!("steam={}", steam.display());
    assert!(steam.is_file());
}

#[test]
#[ignore = "requires CS2 install; not for CI"]
fn probe_detect_cs2() {
    let mut mgr = Cs2ProcessManager::new();
    let cs2 = mgr.detect_cs2().expect("CS2");
    eprintln!("cs2={}", cs2.display());
    assert!(cs2.is_file());
}

#[test]
#[ignore = "launches real CS2; not for CI"]
fn probe_launch_connect_demo_controls() {
    let demo = real_demo_path().expect("set CS2_COACH_REAL_DEMO");
    assert!(demo.is_file(), "demo missing: {}", demo.display());

    let mut session = ReplaySession::new(staging_root());
    let port = session.start_launch().expect("launch/ready");
    eprintln!("netcon_port_allocated={}", port);

    session.connect().expect("connect");
    assert_eq!(session.state(), ReplaySessionState::Connected);

    let info = session.demo_info().expect("demo_info before load");
    eprintln!(
        "demo_info_before_load_len={} preview={}",
        info.raw_text.len(),
        redact_preview(&info.raw_text)
    );

    let (staged, play_resp) = session.stage_and_play_demo(&demo).expect("playdemo");
    eprintln!(
        "staged_name={} sha256_prefix={} play_resp={}",
        staged.staged_name,
        &staged.sha256[..12],
        redact_preview(&play_resp.raw_text)
    );

    // Allow demo load settle.
    std::thread::sleep(Duration::from_secs(8));

    let pause = session.pause().expect("pause");
    eprintln!("pause_resp={}", redact_preview(&pause.raw_text));
    let resume = session.resume().expect("resume");
    eprintln!("resume_resp={}", redact_preview(&resume.raw_text));
    let scale = session.timescale(0.5).expect("timescale");
    eprintln!("timescale_resp={}", redact_preview(&scale.raw_text));
    let _ = session.timescale(1.0);

    let info2 = session.demo_info().expect("demo_info after load");
    eprintln!(
        "demo_info_after_load_len={} preview={}",
        info2.raw_text.len(),
        redact_preview(&info2.raw_text)
    );

    // Seek is issued only to show playback moves; tick domain remains UNVERIFIED.
    let seek = session
        .go_to_tick(ReplayTick::demo(10_000))
        .expect("go_to_tick");
    eprintln!("seek_resp={}", redact_preview(&seek.raw_text));

    session.close();
    assert_eq!(session.state(), ReplaySessionState::NotRunning);
}

#[test]
#[ignore = "requires live NetCon from a coach-launched CS2; not for CI"]
fn probe_disconnect_reconnect_and_loss() {
    let mut session = ReplaySession::new(staging_root());
    let _port = session.start_launch().expect("launch");
    session.connect().expect("connect");
    let _ = session.send_command(&ReplayCommand::DemoInfo);

    session.disconnect();
    assert_eq!(session.state(), ReplaySessionState::ConnectionLost);

    match session.reconnect() {
        Ok(()) => {
            assert_eq!(session.state(), ReplaySessionState::Connected);
            let _ = session.send_command(&ReplayCommand::DemoInfo);
            eprintln!("reconnect_ok");
        }
        Err(err) => {
            // Observed on build 2000930: after client FIN, engine can leave
            // CLOSE_WAIT and refuse new accepts until CS2 restart.
            eprintln!(
                "reconnect_limited engine_close_wait_or_single_client err={}",
                err.code
            );
            assert!(
                matches!(
                    err.code,
                    "NETCON_CONNECT_FAILED" | "NETCON_RECONNECT_EXHAUSTED" | "NETCON_CONNECTION_LOST"
                ),
                "unexpected reconnect error {}",
                err.code
            );
        }
    }

    eprintln!("manual step: close CS2 window, then poll_health should surface loss");
    let _ = session.poll_health();
    session.close();
}

#[test]
#[ignore = "filesystem staging against private fixture; not for CI"]
fn probe_stage_private_fixture() {
    let demo = real_demo_path().expect("set CS2_COACH_REAL_DEMO");
    let svc = DemoStagingService::new(staging_root());
    let staged = svc.stage(&demo).expect("stage");
    assert!(staged.staged_name.ends_with(".dem"));
    assert_eq!(staged.sha256.len(), 64);
    eprintln!(
        "staged_name={} from_archive={}",
        staged.staged_name, staged.from_archive
    );
}

fn redact_preview(raw: &str) -> String {
    let flat: String = raw
        .chars()
        .map(|c| if c.is_control() { ' ' } else { c })
        .take(240)
        .collect();
    flat
}
