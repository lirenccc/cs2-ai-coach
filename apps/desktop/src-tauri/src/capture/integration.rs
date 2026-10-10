//! Ignored/manual Windows + real-CS2 capture probes (not for CI).
//!
//! ```powershell
//! $env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.zip"
//! cargo test -p cs2-ai-coach --lib probe_capture -- --ignored --nocapture --test-threads=1
//! ```

use super::adapter::{discover_running_cs2_window, CaptureAdapter, NativeCaptureAdapter};
use super::types::{
    CaptureBurstRequest, CaptureFrameRequest, ReplayCaptureContext, SettlePolicy,
};
use crate::cs2::calibration::REPLAY_SEMANTICS_VERSION;
use crate::cs2::process::Cs2ProcessManager;
use crate::cs2::replay::ReplayCommand;
use crate::cs2::session::ReplaySession;
use crate::cs2::tick::{ReplaySeekPosition, ReplayTick};
use std::path::{Path, PathBuf};
use std::time::Duration;

fn real_demo_path() -> Option<PathBuf> {
    std::env::var_os("CS2_COACH_REAL_DEMO").map(PathBuf::from)
}

fn runtime_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join("runtime")
}

fn staging_root() -> PathBuf {
    runtime_root().join("demo-staging")
}

fn read_steam_inf() -> (Option<String>, Option<String>, Option<String>) {
    let mut mgr = Cs2ProcessManager::new();
    let Ok(paths) = mgr.resolve_install_paths() else {
        return (None, None, None);
    };
    let inf = paths.game_dir.join("csgo").join("steam.inf");
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
    let buildid = std::fs::read_to_string(
        paths
            .steam_exe
            .parent()
            .unwrap_or(Path::new("."))
            .join("steamapps")
            .join("appmanifest_730.acf"),
    )
    .ok()
    .and_then(|s| {
        s.lines()
            .find_map(|l| {
                let t = l.trim();
                if t.starts_with("\"buildid\"") {
                    t.split('"').nth(3).map(|v| v.to_string())
                } else {
                    None
                }
            })
    });
    (patch, client, buildid)
}

#[test]
#[ignore = "requires running CS2 window; not for CI"]
fn probe_find_cs2_hwnd() {
    let target = discover_running_cs2_window().expect("CS2 window");
    println!(
        "hwnd_runtime={} pid={:?} client={}x{} title={:?} class={:?}",
        target.hwnd.unwrap_or(0),
        target.process_id,
        target.client_rect.width,
        target.client_rect.height,
        target.title,
        target.class_name
    );
    assert!(target.client_rect.width > 0);
    assert!(target.client_rect.height > 0);
}

#[test]
#[ignore = "requires running CS2; not for CI"]
fn probe_wgc_single_frame() {
    let target = discover_running_cs2_window().expect("CS2 window");
    let mut adapter = NativeCaptureAdapter::new(runtime_root());
    let (patch, client, buildid) = read_steam_inf();
    adapter.set_cs2_build_meta(patch, client, buildid);
    adapter.open(&target).expect("open WGC");
    let frame = adapter
        .capture_frame(&CaptureFrameRequest {
            timeout: Duration::from_secs(5),
            persist: true,
            previous_content_sha256: None,
            replay_paused: true,
        })
        .expect("frame");
    println!(
        "frame {}x{} hash={} valid={} black={:.4} var={:.2} path={:?}",
        frame.width,
        frame.height,
        frame.content_sha256,
        frame.quality.valid,
        frame.quality.black_ratio,
        frame.quality.variance,
        frame.storage_path
    );
    assert!(frame.quality.valid);
    assert!(frame.quality.black_ratio < 0.98);
    adapter.close();
}

#[test]
#[ignore = "requires running CS2; not for CI"]
fn probe_wgc_burst_5() {
    let target = discover_running_cs2_window().expect("CS2 window");
    let mut adapter = NativeCaptureAdapter::new(runtime_root());
    adapter.open(&target).expect("open");
    let frames = adapter
        .capture_burst(
            &CaptureBurstRequest {
                count: 5,
                interval: Duration::from_millis(80),
                timeout: Duration::from_secs(20),
                persist: true,
                replay_paused: true,
            },
            None,
        )
        .expect("burst");
    assert_eq!(frames.len(), 5);
    for (i, f) in frames.iter().enumerate() {
        println!(
            "burst[{i}] {}x{} valid={} hash={}",
            f.width, f.height, f.quality.valid, f.content_sha256
        );
        assert!(f.quality.valid);
    }
    adapter.close();
}

#[test]
#[ignore = "manual: cover CS2 with another window then run; not for CI"]
fn probe_occlusion_behavior() {
    let target = discover_running_cs2_window().expect("CS2 window");
    let mut adapter = NativeCaptureAdapter::new(runtime_root());
    adapter.open(&target).expect("open");
    match adapter.capture_frame(&CaptureFrameRequest::default()) {
        Ok(f) => println!(
            "occlusion: captured valid={} black={:.4} (WGC often continues while occluded)",
            f.quality.valid, f.quality.black_ratio
        ),
        Err(e) => println!("occlusion: typed error {} — {}", e.code, e.message),
    }
    adapter.close();
}

#[test]
#[ignore = "requires running CS2; minimizes via ShowWindow; not for CI"]
fn probe_minimized_behavior() {
    let target = discover_running_cs2_window().expect("CS2 window");
    let hwnd = target.hwnd.expect("hwnd");
    #[cfg(windows)]
    unsafe {
        use windows::Win32::Foundation::HWND;
        use windows::Win32::UI::WindowsAndMessaging::{ShowWindow, SW_MINIMIZE, SW_RESTORE};
        let h = HWND(hwnd as *mut core::ffi::c_void);
        let _ = ShowWindow(h, SW_MINIMIZE);
        std::thread::sleep(Duration::from_millis(600));
        let rediscovered = discover_running_cs2_window();
        match rediscovered {
            Err(e) => {
                println!("minimized discover typed: {} — {}", e.code, e.message);
                assert!(
                    e.code == "CAPTURE_TARGET_MINIMIZED"
                        || e.code == "CAPTURE_TARGET_ZERO_SIZE"
                        || e.code == "CAPTURE_CS2_WINDOW_NOT_FOUND"
                );
            }
            Ok(t) => {
                let mut adapter = NativeCaptureAdapter::new(runtime_root());
                match adapter.open(&t) {
                    Err(e) => {
                        println!("minimized open typed: {} — {}", e.code, e.message);
                        assert!(
                            e.code == "CAPTURE_TARGET_MINIMIZED"
                                || e.code == "CAPTURE_TARGET_ZERO_SIZE"
                        );
                    }
                    Ok(()) => match adapter.capture_frame(&CaptureFrameRequest::default()) {
                        Err(e) => {
                            println!("minimized capture typed: {} — {}", e.code, e.message);
                            assert!(
                                e.code == "CAPTURE_TARGET_MINIMIZED"
                                    || e.code == "CAPTURE_FRAME_INVALID"
                                    || e.code == "CAPTURE_FRAME_TIMEOUT"
                                    || e.code == "CAPTURE_TARGET_ZERO_SIZE"
                            );
                        }
                        Ok(f) => {
                            assert!(
                                !f.quality.valid || f.quality.black_ratio > 0.98,
                                "minimized must not return silent valid gameplay frame"
                            );
                            println!(
                                "minimized capture rejected via quality valid={} black={:.4}",
                                f.quality.valid, f.quality.black_ratio
                            );
                        }
                    },
                }
            }
        }
        let _ = ShowWindow(h, SW_RESTORE);
        std::thread::sleep(Duration::from_millis(600));
        let restored = discover_running_cs2_window().expect("restore rediscover");
        assert!(!restored.is_minimized);
        println!("restored client={}x{}", restored.client_rect.width, restored.client_rect.height);
    }
}

#[test]
#[ignore = "requires running CS2; resizes HWND via SetWindowPos; not for CI"]
fn probe_resize_recovery() {
    let target = discover_running_cs2_window().expect("CS2 window");
    let hwnd = target.hwnd.expect("hwnd");
    let mut adapter = NativeCaptureAdapter::new(runtime_root());
    adapter.open(&target).expect("open");
    let first = adapter
        .capture_frame(&CaptureFrameRequest {
            timeout: Duration::from_secs(5),
            persist: true,
            ..Default::default()
        })
        .expect("first");
    println!("resize: initial {}x{}", first.width, first.height);

    #[cfg(windows)]
    unsafe {
        use windows::Win32::Foundation::HWND;
        use windows::Win32::UI::WindowsAndMessaging::{
            SetWindowPos, SWP_NOMOVE, SWP_NOZORDER,
        };
        let h = HWND(hwnd as *mut core::ffi::c_void);
        let new_w = (first.width.saturating_sub(80)).max(640);
        let new_h = (first.height.saturating_sub(60)).max(360);
        let _ = SetWindowPos(
            h,
            None,
            0,
            0,
            new_w as i32,
            new_h as i32,
            SWP_NOMOVE | SWP_NOZORDER,
        );
        std::thread::sleep(Duration::from_millis(500));
    }

    let second = adapter
        .capture_frame(&CaptureFrameRequest {
            timeout: Duration::from_secs(5),
            persist: true,
            ..Default::default()
        })
        .expect("second");
    println!(
        "resize: after {}x{} pool_recreated={} last_resize={:?} hwnd_same=true",
        second.width,
        second.height,
        adapter.health().frame_pool_recreated,
        adapter.last_resize()
    );
    assert!(second.quality.valid);
    assert!(second.quality.black_ratio < 0.98);
    // Either dimensions changed or frame-pool recreate was recorded.
    assert!(
        second.width != first.width
            || second.height != first.height
            || adapter.health().frame_pool_recreated
            || adapter.last_resize().is_some()
    );
    adapter.close();
}

#[test]
#[ignore = "P0.6 capture-after-calibrated-seek; launches CS2; not for CI"]
fn probe_capture_after_calibrated_seek() {
    let demo = real_demo_path().expect("set CS2_COACH_REAL_DEMO");
    let mut session = ReplaySession::new(staging_root());
    let _port = session.start_launch().expect("launch/ready");
    session.connect().expect("connect");
    let (_staged, _play) = session.stage_and_play_demo(&demo).expect("playdemo");
    std::thread::sleep(Duration::from_secs(8));
    session.pause().expect("pause");

    // Anchors: early / middle / late (P0.5A). Never ServerTick. Never tick 0.
    let anchors = [
        ("A01_early_plant", 4354u64, 8133u64),
        ("A02_mid_defuse", 42294, 46073),
        ("A04_post_halftime_explode", 79639, 83418),
    ];

    let (patch, client, buildid) = read_steam_inf();
    // Confirm calibration build family before claiming capture-at-event correctness.
    if let Some(p) = &patch {
        assert_eq!(
            p, "1.41.9.0",
            "CS2 patch differs; re-run P0.5A before capture claims"
        );
    }
    if let Some(c) = &client {
        assert_eq!(c, "2000930", "CS2 client differs; re-run P0.5A");
    }

    let mut adapter = NativeCaptureAdapter::new(runtime_root());
    adapter.set_cs2_build_meta(patch, client, buildid);

    for (i, (event_id, demo_tick, server_ref)) in anchors.iter().enumerate() {
        // Production seek path only.
        assert!(ReplayCommand::go_to_tick(ReplayTick::server(*server_ref)).is_err());
        let pos = ReplaySeekPosition::DemoTick(*demo_tick);
        let cmd = ReplayCommand::go_to_seek_position(pos).expect("DemoTick seek");
        assert_ne!(*demo_tick, 0, "tick-0 nudge forbidden");
        session.send_command(&cmd).expect("seek");

        let settle = SettlePolicy::fixed_ms(2000);
        std::thread::sleep(settle.duration());
        // Nudge compositor while remaining paused-policy for capture (no tick-0).
        let _ = session.timescale(0.25);
        let _ = session.resume();
        std::thread::sleep(Duration::from_millis(250));
        let _ = session.pause();
        let _ = session.timescale(1.0);
        std::thread::sleep(Duration::from_millis(300));

        let mut ctx = ReplayCaptureContext::from_demo_tick(*demo_tick).unwrap();
        ctx = ctx.with_ids("9208210907649202700_0", *event_id);
        ctx.server_tick_reference = Some(*server_ref);
        ctx.settle_policy = settle;
        ctx.calibrated_replay_semantics_version = REPLAY_SEMANTICS_VERSION.to_string();
        adapter.set_replay_context(ctx).unwrap();

        let target = discover_running_cs2_window().expect("window");
        adapter.close();
        adapter.open(&target).expect("open capture");

        let frame = adapter
            .capture_frame(&CaptureFrameRequest {
                timeout: Duration::from_secs(5),
                persist: true,
                replay_paused: true,
                previous_content_sha256: None,
            })
            .expect("capture after seek");
        println!(
            "seek_capture[{event_id}] demo_tick={demo_tick} {}x{} valid={} hash={}",
            frame.width, frame.height, frame.quality.valid, frame.content_sha256
        );
        assert!(frame.quality.valid);
        assert_eq!(
            adapter.manifests().last().unwrap().requested_demo_tick,
            Some(*demo_tick)
        );
        assert_eq!(
            adapter
                .manifests()
                .last()
                .unwrap()
                .replay_semantics_version
                .as_deref(),
            Some(REPLAY_SEMANTICS_VERSION)
        );

        if i == 1 {
            let burst = adapter
                .capture_burst(
                    &CaptureBurstRequest {
                        count: 5,
                        interval: Duration::from_millis(100),
                        timeout: Duration::from_secs(20),
                        persist: true,
                        replay_paused: true,
                    },
                    None,
                )
                .expect("burst at mid anchor");
            assert_eq!(burst.len(), 5);
        }
    }

    if let Some(last) = adapter.manifests().last() {
        let redacted = crate::capture::manifest::redact_manifest(last);
        let out = runtime_root()
            .join("captures")
            .join("last_manifest.redacted.json");
        let _ = std::fs::create_dir_all(out.parent().unwrap());
        let _ = std::fs::write(&out, serde_json::to_vec_pretty(&redacted).unwrap());
        println!("wrote {}", out.display());
    }

    adapter.close();
    session.close();
}

#[test]
#[ignore = "P0.6A capture-at-event semantic validation; launches CS2; not for CI"]
fn probe_capture_at_event_semantics() {
    let demo = real_demo_path().expect("set CS2_COACH_REAL_DEMO");
    let mut session = ReplaySession::new(staging_root());
    let _port = session.start_launch().expect("launch");
    session.connect().expect("connect");
    let (_staged, _) = session.stage_and_play_demo(&demo).expect("playdemo");
    std::thread::sleep(Duration::from_secs(8));
    session.pause().expect("pause");

    let (patch, client, buildid) = read_steam_inf();
    let patch = patch.expect("patch");
    let client = client.expect("client");
    let buildid = buildid.unwrap_or_else(|| "unknown".into());

    let mut adapter = NativeCaptureAdapter::new(runtime_root());
    adapter.set_cs2_build_meta(
        Some(patch.clone()),
        Some(client.clone()),
        Some(buildid.clone()),
    );

    let anchors = [
        ("A01_early_plant", 4354u64, 1u32),
        ("A02_mid_defuse", 42294, 7),
        ("A04_post_halftime_explode", 79639, 13),
    ];
    for (event_id, demo_tick, round_id) in anchors {
        let mut ctx = ReplayCaptureContext::from_demo_tick(demo_tick).unwrap();
        ctx = ctx.with_ids("9208210907649202700_0", event_id);
        ctx.require_calibrated_build(&patch, &client, &buildid)
            .expect("calibration build match");
        assert_eq!(
            ctx.require_calibrated_build(&patch, "0", &buildid)
                .unwrap_err(),
            "REPLAY_CALIBRATION_BUILD_MISMATCH"
        );
        session
            .send_command(
                &ReplayCommand::go_to_seek_position(ReplaySeekPosition::DemoTick(demo_tick))
                    .unwrap(),
            )
            .expect("seek");
        std::thread::sleep(SettlePolicy::fixed_ms(2000).duration());
        adapter.set_replay_context(ctx).unwrap();
        let target = discover_running_cs2_window().expect("window");
        adapter.close();
        adapter.open(&target).expect("open");
        let frame = adapter
            .capture_frame(&CaptureFrameRequest {
                timeout: Duration::from_secs(5),
                persist: true,
                replay_paused: true,
                previous_content_sha256: None,
            })
            .expect("frame");
        let manifest = adapter.manifests().last().unwrap();
        println!(
            "semantic[{event_id}] round={round_id} tick={demo_tick} hash={} manifest_tick={:?} calib={}",
            frame.content_sha256,
            manifest.requested_demo_tick,
            manifest.replay_semantics_version.as_deref().unwrap_or("?")
        );
        assert_eq!(manifest.requested_demo_tick, Some(demo_tick));
        assert_eq!(
            manifest.replay_semantics_version.as_deref(),
            Some(REPLAY_SEMANTICS_VERSION)
        );
        assert!(frame.quality.valid);
        let again = adapter
            .capture_frame(&CaptureFrameRequest {
                timeout: Duration::from_secs(5),
                persist: false,
                replay_paused: true,
                previous_content_sha256: Some(frame.content_sha256.clone()),
            })
            .expect("paused duplicate allowed");
        assert!(again.quality.duplicate_expected_while_paused || again.quality.valid);
    }
    adapter.close();
    session.close();
}

#[test]
#[ignore = "requires running CS2; verifies cleanup releases session"]
fn probe_capture_cleanup_releases_resources() {
    let target = discover_running_cs2_window().expect("CS2 window");
    let mut adapter = NativeCaptureAdapter::new(runtime_root());
    adapter.open(&target).expect("open");
    assert!(adapter.health().open_session);
    adapter.close();
    assert!(!adapter.health().open_session);
    // Re-open proves prior session did not leak exclusivity.
    adapter.open(&target).expect("re-open after close");
    adapter.close();
}
