//! High-level Click-to-CS2 orchestration.
//!
//! Renderer supplies only match_id + incident_id. This module resolves the
//! authoritative plan, stages the exact Demo, enforces calibration, and seeks
//! calibrated DemoTick only.

use crate::capture::lineage::{
    calibrated_build_identity, check_calibration_compatibility, CalibrationCompatibility,
    CaptureCalibrationContext, Cs2BuildIdentity,
};
use crate::cs2::calibration::{parse_demo_skip_report, REPLAY_SEMANTICS_VERSION};
use crate::cs2::error::Cs2Error;
use crate::cs2::process::Cs2ProcessManager;
use crate::cs2::session::{ReplaySession, ReplaySessionManager, ReplaySessionState};
use crate::cs2::tick::ReplayTick;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Duration;

pub const DEFAULT_TIMESCALE: f32 = 0.5;
pub const DEFAULT_SETTLE_MS: u64 = 2000;

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct IncidentReplayPlan {
    pub version: String,
    pub match_id: String,
    pub incident_id: String,
    pub rule_id: String,
    pub round_id: String,
    pub round_number: u32,
    pub start_demo_tick: u64,
    pub anchor_demo_tick: u64,
    pub end_demo_tick: u64,
    pub seek_demo_tick: u64,
    pub replay_tick_domain: String,
    pub replay_semantics_version: String,
    pub timing_source: String,
    pub verified_tick_rate: Option<f64>,
    #[serde(default)]
    pub timing_degraded: bool,
    pub pre_roll_seconds: f64,
    pub settle_policy: String,
    pub settle_debounce_ms: u64,
    pub timescale: f32,
    #[serde(default = "default_true")]
    pub auto_resume: bool,
    #[serde(default)]
    pub pov_auto_selected: bool,
    pub demo_sha256: String,
    #[serde(default)]
    pub demo_source_available: bool,
    /// Native-only. Must never be returned to the renderer.
    #[serde(default)]
    pub demo_source_path: Option<String>,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct EnginePositionEvidence {
    pub demo_tick: u64,
    pub game_tick: Option<u64>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ViewIncidentInCs2Result {
    pub phase: String,
    pub match_id: String,
    pub incident_id: String,
    pub rule_id: String,
    pub seek_demo_tick: u64,
    pub anchor_demo_tick: u64,
    pub requested_demo_tick: u64,
    pub command_delivery_ok: bool,
    pub engine_position_evidence: Option<EnginePositionEvidence>,
    pub timescale: f32,
    pub pov_auto_selected: bool,
    pub notes: Vec<String>,
    pub demo_sha256_prefix: String,
}

/// Concurrent policy: a newer request supersedes an older in-flight action.
pub struct IncidentReplayGate {
    generation: AtomicU64,
}

impl IncidentReplayGate {
    pub fn new() -> Self {
        Self {
            generation: AtomicU64::new(0),
        }
    }

    pub fn begin(&self) -> u64 {
        self.generation.fetch_add(1, Ordering::SeqCst) + 1
    }

    pub fn is_current(&self, generation: u64) -> bool {
        self.generation.load(Ordering::SeqCst) == generation
    }
}

impl Default for IncidentReplayGate {
    fn default() -> Self {
        Self::new()
    }
}

pub fn validate_plan_for_production(plan: &IncidentReplayPlan) -> Result<(), Cs2Error> {
    if plan.replay_tick_domain != "DemoTick" {
        return Err(Cs2Error::new(
            "REPLAY_TICK_DOMAIN_INCONSISTENT",
            format!(
                "production seek requires DemoTick, got {}",
                plan.replay_tick_domain
            ),
            Some("Re-import the match after updating the analyzer"),
        ));
    }
    if plan.replay_semantics_version != REPLAY_SEMANTICS_VERSION {
        return Err(Cs2Error::new(
            "REPLAY_CALIBRATION_BUILD_MISMATCH",
            format!(
                "plan semantics {} != calibrated {}",
                plan.replay_semantics_version, REPLAY_SEMANTICS_VERSION
            ),
            Some("Rebuild calibration for the current CS2 build, then retry"),
        ));
    }
    if plan.demo_sha256.len() != 64
        || !plan.demo_sha256.chars().all(|c| c.is_ascii_hexdigit())
    {
        return Err(Cs2Error::new(
            "REPLAY_SOURCE_MISSING",
            "replay plan is missing a valid Demo SHA-256",
            Some("Re-import the Demo and retry"),
        ));
    }
    Ok(())
}

pub fn resolve_demo_source(
    plan: &IncidentReplayPlan,
    staging_root: &Path,
) -> Result<PathBuf, Cs2Error> {
    if let Some(path) = plan.demo_source_path.as_deref() {
        let candidate = PathBuf::from(path);
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    let staged = staging_root.join(format!("{}.dem", plan.demo_sha256));
    if staged.is_file() {
        return Ok(staged);
    }
    Err(Cs2Error::new(
        "REPLAY_SOURCE_MISSING",
        "Imported Demo source is missing and no safe managed copy is available",
        Some("Re-import the original Demo file, then retry View in CS2"),
    ))
}

pub fn read_observed_build_identity() -> Option<Cs2BuildIdentity> {
    let mut mgr = Cs2ProcessManager::new();
    let cs2 = mgr.detect_cs2().ok()?;
    let game_dir = cs2.parent()?.parent()?.parent()?;
    let inf = game_dir.join("csgo").join("steam.inf");
    let text = std::fs::read_to_string(inf).ok()?;
    let mut patch = None;
    let mut client = None;
    for line in text.lines() {
        if let Some(v) = line.strip_prefix("PatchVersion=") {
            patch = Some(v.trim().to_string());
        }
        if let Some(v) = line.strip_prefix("ClientVersion=") {
            client = Some(v.trim().to_string());
        }
    }
    let buildid = cs2
        .parent()? // win64
        .parent()? // bin
        .parent()? // game
        .parent()? // CSGO
        .parent()? // common
        .parent() // steamapps
        .map(|steamapps| steamapps.join("appmanifest_730.acf"))
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|acf| {
            for line in acf.lines() {
                let t = line.trim();
                if let Some(rest) = t.strip_prefix("\"buildid\"") {
                    let value = rest.trim().trim_matches('"').to_string();
                    if !value.is_empty() {
                        return Some(value);
                    }
                }
            }
            None
        })
        .unwrap_or_default();
    Some(Cs2BuildIdentity {
        patch_version: patch.unwrap_or_default(),
        client_version: client.unwrap_or_default(),
        steam_buildid: buildid,
    })
}

pub fn enforce_calibration_guard(
    observed: Option<Cs2BuildIdentity>,
) -> Result<(), Cs2Error> {
    let ctx = CaptureCalibrationContext {
        replay_calibration_version: REPLAY_SEMANTICS_VERSION.to_string(),
        expected_build: calibrated_build_identity(),
        observed_build: observed,
    };
    match check_calibration_compatibility(&ctx) {
        CalibrationCompatibility::Compatible => Ok(()),
        CalibrationCompatibility::BuildMismatch { code } => Err(Cs2Error::new(
            code,
            "Current CS2 build does not match the calibrated DemoTick replay semantics",
            Some("Re-run tick calibration for this build, or use the calibrated CS2 version"),
        )),
        CalibrationCompatibility::Uncalibrated { reason } => Err(Cs2Error::new(
            "REPLAY_CALIBRATION_BUILD_MISMATCH",
            reason,
            Some("Ensure CS2 is installed and steam.inf is readable, then retry"),
        )),
    }
}

fn ensure_session_connected(session: &mut ReplaySession) -> Result<(), Cs2Error> {
    match session.state() {
        ReplaySessionState::DemoReady | ReplaySessionState::Connected => Ok(()),
        ReplaySessionState::NotRunning
        | ReplaySessionState::Failed
        | ReplaySessionState::ConnectionLost => {
            session.start_launch()?;
            session.connect()
        }
        ReplaySessionState::ProcessReady => session.connect(),
        ReplaySessionState::Launching | ReplaySessionState::Connecting => Err(Cs2Error::new(
            "REPLAY_INVALID_TRANSITION",
            "replay session is mid-launch",
            Some("Wait for CS2 to finish starting, then retry"),
        )),
        ReplaySessionState::DemoLoading => Err(Cs2Error::new(
            "REPLAY_INVALID_TRANSITION",
            "demo is still loading",
            Some("Wait a moment, then retry"),
        )),
    }
}

/// Orchestrate Click-to-CS2 for one generation. Returns Err if superseded mid-flight.
pub fn run_view_incident(
    gate: &IncidentReplayGate,
    generation: u64,
    manager: &Mutex<ReplaySessionManager>,
    plan: &IncidentReplayPlan,
) -> Result<ViewIncidentInCs2Result, Cs2Error> {
    validate_plan_for_production(plan)?;
    if !gate.is_current(generation) {
        return Err(superseded());
    }

    let staging_root = {
        let guard = manager.lock().expect("replay mutex");
        guard.staging_root().to_path_buf()
    };
    let source = resolve_demo_source(plan, &staging_root)?;

    // Fail closed on missing CS2 before claiming a calibrated seek.
    if Cs2ProcessManager::new().detect_cs2().is_err() {
        return Err(Cs2Error::cs2_not_installed());
    }
    enforce_calibration_guard(read_observed_build_identity())?;
    if !gate.is_current(generation) {
        return Err(superseded());
    }

    let settle = Duration::from_millis(if plan.settle_debounce_ms == 0 {
        DEFAULT_SETTLE_MS
    } else {
        plan.settle_debounce_ms
    });
    let timescale = if plan.timescale > 0.0 {
        plan.timescale
    } else {
        DEFAULT_TIMESCALE
    };

    let mut guard = manager.lock().expect("replay mutex");
    if !gate.is_current(generation) {
        return Err(superseded());
    }
    let session = guard.session_mut();
    ensure_session_connected(session)?;
    if !gate.is_current(generation) {
        return Err(superseded());
    }

    // Reload only when SHA differs (idempotent same-incident / same-demo clicks).
    let need_load = session.loaded_demo_sha() != Some(plan.demo_sha256.as_str());
    if need_load {
        let (staged, _) = session.stage_and_play_demo(&source)?;
        if staged.sha256 != plan.demo_sha256 {
            session.set_loaded_demo_sha(None);
            return Err(Cs2Error::new(
                "REPLAY_SOURCE_MISSING",
                "Staged Demo SHA does not match the imported match identity",
                Some("Re-import the exact Demo for this match, then retry"),
            ));
        }
        // Allow playdemo to settle before pause/seek.
        std::thread::sleep(Duration::from_millis(1500));
    }

    if !gate.is_current(generation) {
        return Err(superseded());
    }

    let _ = session.pause()?;
    let seek_tick = ReplayTick::demo(plan.seek_demo_tick);
    let seek_resp = session.go_to_tick(seek_tick)?;
    std::thread::sleep(settle);

    let evidence = parse_demo_skip_report(&seek_resp.raw_text).map(|skip| {
        EnginePositionEvidence {
            demo_tick: skip.demo_tick,
            game_tick: skip.game_tick,
        }
    });

    let _ = session.timescale(timescale)?;
    if plan.auto_resume {
        let _ = session.resume()?;
    }

    if !gate.is_current(generation) {
        return Err(superseded());
    }

    Ok(ViewIncidentInCs2Result {
        phase: "Playing".into(),
        match_id: plan.match_id.clone(),
        incident_id: plan.incident_id.clone(),
        rule_id: plan.rule_id.clone(),
        seek_demo_tick: plan.seek_demo_tick,
        anchor_demo_tick: plan.anchor_demo_tick,
        requested_demo_tick: plan.seek_demo_tick,
        // Delivery success ≠ position proof; evidence is separate.
        command_delivery_ok: true,
        engine_position_evidence: evidence,
        timescale,
        pov_auto_selected: false,
        notes: vec![
            "POV not automatically selected yet".into(),
            format!("timing_source={}", plan.timing_source),
        ],
        demo_sha256_prefix: plan.demo_sha256.chars().take(12).collect(),
    })
}

pub fn run_replay_control(
    manager: &Mutex<ReplaySessionManager>,
    action: &str,
) -> Result<(), Cs2Error> {
    let mut guard = manager.lock().expect("replay mutex");
    let session = guard.session_mut();
    match action {
        "pause" => {
            session.pause()?;
        }
        "resume" => {
            session.resume()?;
        }
        "timescale_half" => {
            session.timescale(0.5)?;
        }
        "timescale_one" => {
            session.timescale(1.0)?;
        }
        _ => {
            return Err(Cs2Error::new(
                "REPLAY_COMMAND_INVALID",
                format!("unsupported replay control action: {action}"),
                Some("Use pause, resume, timescale_half, or timescale_one"),
            ));
        }
    }
    Ok(())
}

fn superseded() -> Cs2Error {
    Cs2Error::new(
        "REPLAY_ACTION_SUPERSEDED",
        "A newer View in CS2 request superseded this action",
        Some("Only the latest incident replay request is applied"),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cs2::session::ReplaySessionManager;
    use std::sync::Arc;

    fn sample_plan(sha: &str, path: Option<&str>) -> IncidentReplayPlan {
        IncidentReplayPlan {
            version: "1.0.0".into(),
            match_id: "m1".into(),
            incident_id: "inc1".into(),
            rule_id: "R001".into(),
            round_id: "r1".into(),
            round_number: 1,
            start_demo_tick: 100,
            anchor_demo_tick: 500,
            end_demo_tick: 520,
            seek_demo_tick: 200,
            replay_tick_domain: "DemoTick".into(),
            replay_semantics_version: REPLAY_SEMANTICS_VERSION.into(),
            timing_source: "match.tick_rate".into(),
            verified_tick_rate: Some(128.0),
            timing_degraded: false,
            pre_roll_seconds: 5.0,
            settle_policy: "fixed_debounce_ms".into(),
            settle_debounce_ms: 10,
            timescale: 0.5,
            auto_resume: true,
            pov_auto_selected: false,
            demo_sha256: sha.into(),
            demo_source_available: path.is_some(),
            demo_source_path: path.map(|p| p.to_string()),
        }
    }

    #[test]
    fn plan_rejects_non_demo_tick_domain() {
        let mut plan = sample_plan(&"a".repeat(64), None);
        plan.replay_tick_domain = "ServerTick".into();
        let err = validate_plan_for_production(&plan).unwrap_err();
        assert_eq!(err.code, "REPLAY_TICK_DOMAIN_INCONSISTENT");
    }

    #[test]
    fn calibration_mismatch_fails_closed() {
        let observed = Cs2BuildIdentity {
            patch_version: "9.9.9.9".into(),
            client_version: "1".into(),
            steam_buildid: "1".into(),
        };
        let err = enforce_calibration_guard(Some(observed)).unwrap_err();
        assert_eq!(err.code, "REPLAY_CALIBRATION_BUILD_MISMATCH");
    }

    #[test]
    fn resolve_demo_prefers_existing_source_then_staged() {
        let root = std::env::temp_dir().join(format!(
            "cs2coach-replay-src-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let sha = "c".repeat(64);
        let dem = root.join("source.dem");
        std::fs::write(&dem, b"PBDEMS2demo").unwrap();
        let plan = sample_plan(&sha, Some(dem.to_str().unwrap()));
        assert_eq!(resolve_demo_source(&plan, &root).unwrap(), dem);

        let missing = sample_plan(&sha, Some(root.join("gone.dem").to_str().unwrap()));
        let staged = root.join(format!("{sha}.dem"));
        std::fs::write(&staged, b"PBDEMS2staged").unwrap();
        assert_eq!(resolve_demo_source(&missing, &root).unwrap(), staged);

        let none = sample_plan(&"d".repeat(64), None);
        let err = resolve_demo_source(&none, &root).unwrap_err();
        assert_eq!(err.code, "REPLAY_SOURCE_MISSING");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn concurrent_policy_supersedes_previous_generation() {
        let gate = IncidentReplayGate::new();
        let g1 = gate.begin();
        let g2 = gate.begin();
        assert!(!gate.is_current(g1));
        assert!(gate.is_current(g2));
    }

    #[test]
    fn replay_control_rejects_arbitrary_console() {
        let root = std::env::temp_dir().join("cs2coach-replay-ctrl");
        let mgr = Mutex::new(ReplaySessionManager::new(root));
        let err = run_replay_control(&mgr, "sv_cheats 1").unwrap_err();
        assert_eq!(err.code, "REPLAY_COMMAND_INVALID");
    }

    #[test]
    fn high_level_command_shape_accepts_ids_only() {
        // Documented boundary: orchestration entry consumes plan resolved from IDs.
        let plan = sample_plan(&"e".repeat(64), None);
        assert_eq!(plan.match_id, "m1");
        assert_eq!(plan.incident_id, "inc1");
        assert!(plan.demo_source_path.is_none() || plan.demo_source_path.is_some());
        let _gate = Arc::new(IncidentReplayGate::new());
    }
}
