//! Manual Windows / real-CS2 integration probes.
//!
//! Ignored by default so CI never requires Steam or CS2.
//!
//! Run (PowerShell):
//! ```text
//! $env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.zip"
//! cargo test -p cs2-ai-coach --lib cs2::integration -- --ignored --nocapture
//! ```

use super::calibration::{
    decide_domain, default_anchors_fixture_path, default_results_fixture_path,
    engine_report_matches_anchor, load_anchor_set, operator_instruction, parse_demo_info_tick,
    parse_demo_skip_report, pre_roll_tick, redact_console_preview, CalibrationAnchorResult,
    CalibrationDecision, CalibrationResultDocument, CalibrationSeekTest, CommandDeliveryEvidence,
    PauseAtServerTickFinding, PreRollTrial, ReplayPositionEvidence, VerificationPrecision,
    VisualVerification, REPLAY_SEMANTICS_VERSION,
};
use super::process::Cs2ProcessManager;
use super::replay::ReplayCommand;
use super::session::{ReplaySession, ReplaySessionState};
use super::staging::DemoStagingService;
use super::tick::{ReplayTick, ReplayTickDomain};
use std::collections::HashMap;
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

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

    // Seek smoke: production path accepts calibrated DemoTick (see P0.5A).
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
    redact_console_preview(raw, 240)
}

fn read_cs2_build_fields() -> (Option<String>, Option<String>, Option<String>) {
    let mut mgr = Cs2ProcessManager::new();
    let Ok(cs2) = mgr.detect_cs2() else {
        return (None, None, None);
    };
    let steam_inf = cs2
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .map(|root| root.join("csgo").join("steam.inf"));
    let Some(inf) = steam_inf else {
        return (None, None, None);
    };
    let Ok(text) = std::fs::read_to_string(&inf) else {
        return (None, None, None);
    };
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
    // Steam buildid lives in appmanifest; best-effort only.
    let buildid = cs2
        .parent() // win64
        .and_then(|p| p.parent()) // bin
        .and_then(|p| p.parent()) // game
        .and_then(|p| p.parent()) // CSGO root
        .and_then(|p| p.parent()) // common
        .and_then(|p| p.parent()) // steamapps
        .map(|steamapps| steamapps.join("appmanifest_730.acf"))
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|acf| {
            for line in acf.lines() {
                let t = line.trim();
                if t.starts_with("\"buildid\"") {
                    // "buildid"		"25815307"
                    let parts: Vec<_> = t.split('"').collect();
                    if let Some(v) = parts.iter().rev().find(|s| {
                        !s.is_empty() && s.chars().all(|c| c.is_ascii_digit())
                    }) {
                        return Some((*v).to_string());
                    }
                }
            }
            None
        });
    (patch, client, buildid)
}

fn load_operator_verifications() -> HashMap<String, VisualVerification> {
    let Ok(path) = std::env::var("CS2_COACH_CALIBRATION_VERIFICATIONS") else {
        return HashMap::new();
    };
    let Ok(text) = std::fs::read_to_string(&path) else {
        eprintln!("calibration_verifications_unreadable path={path}");
        return HashMap::new();
    };
    let Ok(raw) = serde_json::from_str::<HashMap<String, String>>(&text) else {
        eprintln!("calibration_verifications_invalid_json");
        return HashMap::new();
    };
    raw.into_iter()
        .filter_map(|(k, v)| parse_verification(&v).map(|vv| (k, vv)))
        .collect()
}

fn parse_verification(s: &str) -> Option<VisualVerification> {
    match s.trim().to_ascii_lowercase().as_str() {
        "correct_event" => Some(VisualVerification::CorrectEvent),
        "early" => Some(VisualVerification::Early),
        "late" => Some(VisualVerification::Late),
        "wrong_round" => Some(VisualVerification::WrongRound),
        "not_observable" => Some(VisualVerification::NotObservable),
        _ => None,
    }
}

fn verification_key(anchor_id: &str, domain: ReplayTickDomain, repeat: u32) -> String {
    let domain = match domain {
        ReplayTickDomain::DemoTick => "demo_tick",
        ReplayTickDomain::ServerTick => "server_tick",
    };
    format!("{anchor_id}:{domain}:{repeat}")
}

fn utc_timestamp() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("{secs}")
}

#[test]
#[ignore = "P0.5A real-CS2 tick calibration; not for CI"]
fn probe_replay_tick_calibration() {
    let demo = real_demo_path().expect("set CS2_COACH_REAL_DEMO");
    assert!(demo.is_file(), "demo missing: {}", demo.display());

    let anchors = load_anchor_set(default_anchors_fixture_path()).expect("anchors");
    assert_eq!(
        anchors.fixture_sha256,
        "d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec"
    );
    let operator = load_operator_verifications();
    let settle = Duration::from_secs(
        std::env::var("CS2_COACH_CALIBRATION_SETTLE_SECS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(3),
    );
    let repeats: u32 = std::env::var("CS2_COACH_CALIBRATION_REPEATS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(2);

    let (patch, client, buildid) = read_cs2_build_fields();
    eprintln!(
        "cs2_patch={:?} client={:?} buildid={:?} settle_ms={} repeats={}",
        patch,
        client,
        buildid,
        settle.as_millis(),
        repeats
    );

    let mut session = ReplaySession::new(staging_root());
    let port = match session.start_launch() {
        Ok(p) => p,
        Err(err) if err.code == "CS2_TOOLS_UNAVAILABLE" => {
            panic!("environment blocker CS2_TOOLS_UNAVAILABLE: {}", err.message);
        }
        Err(err) => panic!("launch failed {}: {}", err.code, err.message),
    };
    eprintln!("netcon_port_allocated={port}");
    session.connect().expect("connect");

    let (staged, _) = session.stage_and_play_demo(&demo).expect("playdemo");
    assert_eq!(staged.sha256, anchors.fixture_sha256);
    // Long settle: premature seeks under -tools have correlated with
    // FATAL CopyNewEntity during map/entity rebuild.
    std::thread::sleep(Duration::from_secs(15));
    let _ = session.pause();
    std::thread::sleep(Duration::from_secs(2));

    let mut anchor_results: Vec<CalibrationAnchorResult> = Vec::new();
    let mut demo_info_any_tick = false;
    let mut aborted = false;
    let mut abort_note: Option<String> = None;

    'anchors: for anchor in &anchors.anchors {
        let mut tests = Vec::new();
        for domain in [ReplayTickDomain::DemoTick, ReplayTickDomain::ServerTick] {
            let value = match domain {
                ReplayTickDomain::DemoTick => anchor.demo_tick,
                ReplayTickDomain::ServerTick => anchor.server_tick,
            };
            let candidate = match domain {
                ReplayTickDomain::DemoTick => ReplayTick::demo(value),
                ReplayTickDomain::ServerTick => ReplayTick::server(value),
            };
            for repeat in 1..=repeats {
                eprintln!(
                    "----\n{}",
                    operator_instruction(anchor, candidate)
                );
                let _ = session.pause();
                // Do NOT seek to demo tick 0: observed to trigger HostStateRequest /
                // map reload under -tools and FATAL CopyNewEntity crashes.
                // Alternating demo_tick vs server_tick candidates (~3778 apart)
                // already forces a real skip between tests.
                let seek = match session.go_to_tick_calibration_candidate_drained(candidate) {
                    Ok(resp) => resp,
                    Err(err) => {
                        eprintln!(
                            "calibration_seek_failed code={} msg={}",
                            err.code, err.message
                        );
                        aborted = true;
                        abort_note = Some(format!("{}: {}", err.code, err.message));
                        break 'anchors;
                    }
                };
                std::thread::sleep(settle);
                let _ = session.pause();
                let info = session.demo_info().unwrap_or_else(|_| {
                    super::netcon::NetConResponse {
                        raw_text: String::new(),
                        timed_out_idle: true,
                    }
                });
                let position_raw = format!("{}\n{}", seek.raw_text, info.raw_text);
                let skip = parse_demo_skip_report(&seek.raw_text)
                    .or_else(|| parse_demo_skip_report(&info.raw_text));
                let reported = skip
                    .map(|s| s.demo_tick)
                    .or_else(|| parse_demo_info_tick(&info.raw_text));
                if skip.is_some() || reported.is_some() {
                    demo_info_any_tick = true;
                }
                let key = verification_key(&anchor.anchor_id, domain, repeat);
                let verification = operator.get(&key).copied();
                if let Some(v) = verification {
                    eprintln!("operator_verification[{key}]={v:?}");
                } else {
                    eprintln!(
                        "operator_verification[{key}]=<unset> (set CS2_COACH_CALIBRATION_VERIFICATIONS)"
                    );
                }
                if let Some(report) = skip {
                    eprintln!(
                        "engine_skip demo_tick={} game_tick={:?} matches_anchor={}",
                        report.demo_tick,
                        report.game_tick,
                        engine_report_matches_anchor(
                            &report,
                            anchor.demo_tick,
                            anchor.server_tick,
                            64
                        )
                    );
                }
                let offset = skip.map(|s| s.demo_tick as i64 - anchor.demo_tick as i64);
                let precision = if skip.is_some() {
                    VerificationPrecision::EngineReported
                } else if verification.is_some() {
                    VerificationPrecision::Visual
                } else {
                    VerificationPrecision::None
                };
                tests.push(CalibrationSeekTest {
                    candidate_domain: domain,
                    candidate_value: value,
                    repeat,
                    command_delivery: CommandDeliveryEvidence {
                        write_ok: true,
                        raw_response_preview: redact_preview(&seek.raw_text),
                    },
                    replay_position: ReplayPositionEvidence {
                        engine_reported_tick: reported,
                        engine_reported_raw: if position_raw.trim().is_empty() {
                            None
                        } else {
                            Some(redact_console_preview(&position_raw, 500))
                        },
                        verification,
                        verification_precision: precision,
                        offset_ticks: offset,
                        settle_duration_ms: settle.as_millis() as u64,
                    },
                });
            }
        }
        if !tests.is_empty() {
            anchor_results.push(CalibrationAnchorResult {
                anchor_id: anchor.anchor_id.clone(),
                demo_tick: anchor.demo_tick,
                server_tick: anchor.server_tick,
                tests,
            });
        }
        if aborted {
            break;
        }
    }

    // Winning-domain repeatability is evaluated after decision; still always
    // exercised both domains above with `repeats`.
    let decision = decide_domain(&anchor_results, 64);
    eprintln!("decision={decision:?} code={:?}", decision.as_error_code());

    // Optional pause-at-server-tick calibration (defuse anchor).
    let defuse = anchors
        .anchors
        .iter()
        .find(|a| a.event_type == "bomb_defused")
        .expect("defuse anchor");
    let pause_at = session
        .pause_at_server_tick_calibration(defuse.server_tick)
        .expect("pause_at_server_tick write");
    std::thread::sleep(settle);
    let pause_info = session.demo_info().ok();
    let pause_finding = PauseAtServerTickFinding {
        command_accepted_write: true,
        reliable_pause_at_event: None,
        raw_response_preview: Some(redact_preview(&pause_at.raw_text)),
        notes: format!(
            "calibration-only; demo_info_after={}",
            pause_info
                .as_ref()
                .map(|r| redact_preview(&r.raw_text))
                .unwrap_or_default()
        ),
    };

    // Pre-roll contract trials (math + optional seeks on winning domain only when calibrated).
    let mut pre_roll_trials = Vec::new();
    let sample = anchors
        .anchors
        .iter()
        .find(|a| a.anchor_id == "A02_mid_defuse")
        .unwrap_or(&anchors.anchors[0]);
    let domain_for_preroll = decision.authoritative_domain();
    for seconds in [0.0_f64, 2.0, 5.0] {
        let pre = pre_roll_tick(
            sample.demo_tick,
            sample.round_start_demo_tick,
            seconds,
            anchors.verified_tick_rate,
        )
        .expect("pre_roll");
        let unclamped = sample.demo_tick.saturating_sub(
            (seconds * anchors.verified_tick_rate).round() as u64,
        );
        let clamped = unclamped < sample.round_start_demo_tick;
        pre_roll_trials.push(PreRollTrial {
            anchor_id: sample.anchor_id.clone(),
            requested_pre_roll_seconds: seconds,
            ticks_per_second: anchors.verified_tick_rate,
            round_start_demo_tick: sample.round_start_demo_tick,
            anchor_replay_tick: sample.demo_tick,
            pre_roll_replay_tick: pre,
            clamped_to_round_start: clamped,
        });
        if let Some(domain) = domain_for_preroll {
            // Pre-roll position uses the same domain as production seek once known.
            let tick = match domain {
                ReplayTickDomain::DemoTick => ReplayTick::demo(pre),
                ReplayTickDomain::ServerTick => {
                    // Without a validated conversion, only DemoTick pre-roll seeks
                    // are issued against demo_gototick when DemoTick wins.
                    // ServerTick authoritative: use server clock analog via rate.
                    let server_pre = pre_roll_tick(
                        sample.server_tick,
                        sample
                            .server_tick
                            .saturating_sub(sample.demo_tick.saturating_sub(sample.round_start_demo_tick)),
                        seconds,
                        anchors.verified_tick_rate,
                    )
                    .unwrap_or(sample.server_tick);
                    ReplayTick::server(server_pre)
                }
            };
            let _ = session.go_to_tick_calibration_candidate(tick);
            std::thread::sleep(Duration::from_millis(500));
        }
    }

    let doc = CalibrationResultDocument {
        replay_semantics_version: REPLAY_SEMANTICS_VERSION.into(),
        cs2_patch_version: patch,
        cs2_client_version: client,
        steam_buildid: buildid,
        fixture_sha256: anchors.fixture_sha256.clone(),
        app_commit: std::env::var("CS2_COACH_APP_COMMIT").ok(),
        calibration_timestamp_utc: utc_timestamp(),
        decision,
        decision_error_code: decision.as_error_code().map(|s| s.to_string()),
        anchors: anchor_results,
        pre_roll_trials,
        demo_info_reliable: demo_info_any_tick,
        pause_at_server_tick: pause_finding,
        notes: {
            let mut n = vec![
                "command_delivery.write_ok is not replay_position proof".into(),
                "replay_position from engine Demo Skipping lines (demo tick / game tick)".into(),
                "do not demo_gototick 0 under -tools (HostStateRequest / CopyNewEntity risk)".into(),
                "visual verification via CS2_COACH_CALIBRATION_VERIFICATIONS JSON map".into(),
                format!("staged_demo={}", staged.staged_name),
            ];
            if let Some(msg) = abort_note {
                n.push(format!("aborted_early={msg}"));
            } else if aborted {
                n.push("aborted_early=true".into());
            }
            n
        },
    };

    let out_path = std::env::var_os("CS2_COACH_CALIBRATION_OUT")
        .map(PathBuf::from)
        .unwrap_or_else(default_results_fixture_path);
    if let Some(parent) = out_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let json = serde_json::to_string_pretty(&doc).expect("serialize");
    std::fs::write(&out_path, json.as_bytes()).expect("write results");
    eprintln!("wrote_calibration_results={}", out_path.display());
    eprintln!("decision_summary={decision:?}");

    // Environment / harness health assertions (not domain claims).
    assert_eq!(session.state(), ReplaySessionState::DemoReady);
    assert!(
        !matches!(decision, CalibrationDecision::Inconsistent)
            || decision.as_error_code() == Some("REPLAY_TICK_DOMAIN_INCONSISTENT")
    );
    session.close();
}

/// P1.4 Click-to-CS2: stage + DemoTick seek from a redacted plan fixture.
/// Full desktop GUI smoke remains manual; this validates the native seek path.
#[test]
#[ignore = "P1.4 real-CS2 Click-to-CS2; launches CS2; not for CI"]
fn probe_click_to_cs2_incident_seek() {
    use super::incident_replay::{
        enforce_calibration_guard, read_observed_build_identity, resolve_demo_source,
        validate_plan_for_production, IncidentReplayPlan, DEFAULT_SETTLE_MS,
    };
    use std::sync::Mutex;

    let demo = real_demo_path().expect("set CS2_COACH_REAL_DEMO");
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join("docs/spikes/replay/fixtures/p1_4_replay_plans.redacted.json");
    let raw = std::fs::read_to_string(&fixture).expect("plan fixture");
    let doc: serde_json::Value = serde_json::from_str(&raw).expect("json");
    let plans = doc["plans"].as_array().expect("plans");
    assert!(plans.len() >= 3);

    let mut session = ReplaySession::new(staging_root());
    session.start_launch().expect("launch");
    session.connect().expect("connect");
    enforce_calibration_guard(read_observed_build_identity()).expect("calibration");

    for plan_val in plans {
        let mut plan: IncidentReplayPlan =
            serde_json::from_value(plan_val.clone()).expect("plan decode");
        // Fixture is renderer-safe; inject private source for this probe only.
        plan.demo_source_path = Some(demo.to_string_lossy().into_owned());
        validate_plan_for_production(&plan).expect("plan ok");
        let source = resolve_demo_source(&plan, &staging_root()).expect("source");
        let (staged, _) = session.stage_and_play_demo(&source).expect("stage/play");
        assert_eq!(staged.sha256, plan.demo_sha256);
        std::thread::sleep(Duration::from_millis(1500));
        let _ = session.pause().expect("pause");
        let seek = ReplayTick::demo(plan.seek_demo_tick);
        let resp = session.go_to_tick(seek).expect("seek");
        std::thread::sleep(Duration::from_millis(
            if plan.settle_debounce_ms == 0 {
                DEFAULT_SETTLE_MS
            } else {
                plan.settle_debounce_ms
            },
        ));
        let skip = parse_demo_skip_report(&resp.raw_text);
        eprintln!(
            "rule={} seek={} delivery_chars={} engine_skip={:?}",
            plan.rule_id,
            plan.seek_demo_tick,
            resp.raw_text.len(),
            skip.as_ref().map(|s| s.demo_tick)
        );
        let _ = session.timescale(0.5).expect("timescale");
        let _ = session.resume().expect("resume");
        // Idempotent reseek same plan.
        let _ = session.pause().expect("pause2");
        let _ = session.go_to_tick(ReplayTick::demo(plan.seek_demo_tick)).expect("reseek");
    }
    // Mutex unused — documents coordinator ownership model for future wiring.
    let _mgr = Mutex::new(());
    session.close();
}
