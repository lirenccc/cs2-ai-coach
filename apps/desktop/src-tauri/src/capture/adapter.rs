//! CaptureAdapter — high-level native capture boundary.

use crate::capture::backend::{select_backend, BackendDecision};
use crate::capture::discover::{discover_cs2_target, enumerate_cs2_windows, select_cs2_main_window};
use crate::capture::error::CaptureError;
use crate::capture::manifest::{build_manifest, write_manifest_atomic, ManifestBuildInput};
use crate::capture::quality::{content_sha256, evaluate_frame, QualityInput, QualityThresholds};
use crate::capture::storage::CaptureStorage;
use crate::capture::types::{
    CaptureBackend, CaptureBurstRequest, CaptureFrame, CaptureFrameRequest, CaptureHealth,
    CaptureSessionStats, CaptureTarget, CaptureTargetKind, PixelFormat, ReplayCaptureContext,
    ResizeRecoveryInfo, DEFAULT_MAX_BURST_FRAMES,
};
use crate::cs2::process::Cs2ProcessManager;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub trait CaptureAdapter {
    fn discover_targets(&mut self) -> Result<Vec<CaptureTarget>, CaptureError>;
    fn open(&mut self, target: &CaptureTarget) -> Result<(), CaptureError>;
    fn capture_frame(&mut self, request: &CaptureFrameRequest) -> Result<CaptureFrame, CaptureError>;
    fn capture_burst(
        &mut self,
        request: &CaptureBurstRequest,
        cancel: Option<&AtomicBool>,
    ) -> Result<Vec<CaptureFrame>, CaptureError>;
    fn close(&mut self);
    fn health(&self) -> CaptureHealth;
}

pub struct NativeCaptureAdapter {
    storage: CaptureStorage,
    process: Cs2ProcessManager,
    target: Option<CaptureTarget>,
    #[cfg(windows)]
    session: Option<crate::capture::backend::WgcCaptureSession>,
    decision: BackendDecision,
    allow_dxgi_fallback: bool,
    wgc_invalid_streak: u32,
    stats: CaptureSessionStats,
    last_content_hash: Option<String>,
    capture_id: Option<String>,
    match_id: String,
    replay: Option<ReplayCaptureContext>,
    cs2_patch_version: Option<String>,
    cs2_client_version: Option<String>,
    steam_buildid: Option<String>,
    manifests: Vec<crate::capture::manifest::CaptureManifest>,
}

impl NativeCaptureAdapter {
    pub fn new(runtime_root: impl Into<PathBuf>) -> Self {
        let wgc_supported = cfg!(windows) && {
            #[cfg(windows)]
            {
                crate::capture::backend::wgc::wgc_is_supported()
            }
            #[cfg(not(windows))]
            {
                false
            }
        };
        let decision = select_backend(wgc_supported, wgc_supported, 0, false);
        Self {
            storage: CaptureStorage::new(runtime_root),
            process: Cs2ProcessManager::new(),
            target: None,
            #[cfg(windows)]
            session: None,
            decision,
            allow_dxgi_fallback: false,
            wgc_invalid_streak: 0,
            stats: CaptureSessionStats {
                frame_pool_recreated: false,
                last_content_size: None,
                frames_captured: 0,
            },
            last_content_hash: None,
            capture_id: None,
            match_id: "unscoped".into(),
            replay: None,
            cs2_patch_version: None,
            cs2_client_version: None,
            steam_buildid: None,
            manifests: Vec::new(),
        }
    }

    pub fn set_replay_context(&mut self, ctx: ReplayCaptureContext) -> Result<(), CaptureError> {
        let _ = ctx
            .seek_position()
            .map_err(CaptureError::replay_context)?;
        if let Some(mid) = &ctx.match_id {
            self.match_id = mid.clone();
        }
        self.replay = Some(ctx);
        Ok(())
    }

    pub fn set_cs2_build_meta(
        &mut self,
        patch: Option<String>,
        client: Option<String>,
        buildid: Option<String>,
    ) {
        self.cs2_patch_version = patch;
        self.cs2_client_version = client;
        self.steam_buildid = buildid;
    }

    pub fn set_allow_dxgi_fallback(&mut self, allow: bool) {
        self.allow_dxgi_fallback = allow;
        self.refresh_decision();
    }

    pub fn capture_id(&self) -> Option<&str> {
        self.capture_id.as_deref()
    }

    pub fn manifests(&self) -> &[crate::capture::manifest::CaptureManifest] {
        &self.manifests
    }

    pub fn last_resize(&self) -> Option<&ResizeRecoveryInfo> {
        #[cfg(windows)]
        {
            self.session.as_ref().and_then(|s| s.last_resize_info())
        }
        #[cfg(not(windows))]
        {
            None
        }
    }

    pub fn delete_current_capture(&self) -> Result<(), CaptureError> {
        if let Some(id) = &self.capture_id {
            self.storage.delete_capture(&self.match_id, id)?;
        }
        Ok(())
    }

    fn refresh_decision(&mut self) {
        let wgc_supported = cfg!(windows) && {
            #[cfg(windows)]
            {
                crate::capture::backend::wgc::wgc_is_supported()
            }
            #[cfg(not(windows))]
            {
                false
            }
        };
        self.decision = select_backend(
            wgc_supported,
            self.session_open() || wgc_supported,
            self.wgc_invalid_streak,
            self.allow_dxgi_fallback,
        );
    }

    fn session_open(&self) -> bool {
        #[cfg(windows)]
        {
            self.session.is_some()
        }
        #[cfg(not(windows))]
        {
            false
        }
    }

    fn ensure_capture_id(&mut self) {
        if self.capture_id.is_none() {
            self.capture_id = Some(CaptureStorage::new_capture_id());
        }
    }

    fn cs2_pid(&mut self) -> Result<u32, CaptureError> {
        use crate::cs2::process::Cs2ProcessState;
        match self.process.get_process_state(None) {
            Cs2ProcessState::Running { pid, .. }
            | Cs2ProcessState::RunningWithoutNetCon { pid }
            | Cs2ProcessState::NetConReady {
                pid: Some(pid), ..
            } => Ok(pid),
            Cs2ProcessState::NetConReady { pid: None, .. } => Err(CaptureError::window_not_found()),
            _ => Err(CaptureError::window_not_found()),
        }
    }

    fn unix_ms() -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0)
    }

    fn persist_and_wrap(
        &mut self,
        width: u32,
        height: u32,
        pixels: Vec<u8>,
        pixel_format: PixelFormat,
        source_timestamp_qpc: Option<u64>,
        request: &CaptureFrameRequest,
        frame_pool_recreated: bool,
        resize: Option<&ResizeRecoveryInfo>,
    ) -> Result<CaptureFrame, CaptureError> {
        let hash = content_sha256(&pixels);
        let quality = evaluate_frame(
            &QualityInput {
                width,
                height,
                pixels: &pixels,
                pixel_format,
                previous_content_sha256: request
                    .previous_content_sha256
                    .as_deref()
                    .or(self.last_content_hash.as_deref()),
                replay_paused: request.replay_paused,
                inter_frame_gap_ms: Some(100),
            },
            &QualityThresholds::default(),
        );

        if !quality.valid && quality.black_ratio > 0.98 {
            self.wgc_invalid_streak = self.wgc_invalid_streak.saturating_add(1);
            self.refresh_decision();
            return Err(CaptureError::frame_invalid(format!(
                "quality rejected: {:?}",
                quality.warnings
            )));
        }
        if !quality.valid && quality.capture_backend_stuck {
            return Err(CaptureError::frame_invalid("capture_backend_stuck"));
        }
        if !quality.valid {
            self.wgc_invalid_streak = self.wgc_invalid_streak.saturating_add(1);
            return Err(CaptureError::frame_invalid(format!(
                "quality rejected: {:?}",
                quality.warnings
            )));
        }
        self.wgc_invalid_streak = 0;

        self.ensure_capture_id();
        let capture_id = self.capture_id.clone().unwrap();
        let frame_index = (self.stats.frames_captured + 1) as u32;
        let frame_id = format!("frame-{frame_index:04}");
        let mut storage_path = None;
        let mut encoded_hash = hash.clone();
        let mut relative = format!("captures/{}/{capture_id}/{frame_id}.png", self.match_id);

        if request.persist {
            let path = self
                .storage
                .frame_path(&self.match_id, &capture_id, frame_index)?;
            encoded_hash = self.storage.write_png_atomic(
                &path,
                width,
                height,
                &pixels,
                pixel_format == PixelFormat::Bgra8,
            )?;
            relative = path
                .strip_prefix(self.storage.captures_root().parent().unwrap_or(path.as_path()))
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");
            storage_path = Some(path);
        }

        let captured_at = Self::unix_ms();
        let manifest = build_manifest(ManifestBuildInput {
            capture_id: capture_id.clone(),
            frame_id: frame_id.clone(),
            backend: self.decision.backend,
            target: self.target.clone(),
            replay: self.replay.clone(),
            frame_width: width,
            frame_height: height,
            pixel_format,
            captured_at_unix_ms: captured_at,
            source_timestamp_qpc,
            content_sha256: encoded_hash.clone(),
            quality: quality.clone(),
            storage_path_relative: relative.clone(),
            cs2_patch_version: self.cs2_patch_version.clone(),
            cs2_client_version: self.cs2_client_version.clone(),
            steam_buildid: self.steam_buildid.clone(),
            frame_pool_recreated: Some(frame_pool_recreated),
            resize_old_size: resize.map(|r| r.old_size),
            resize_new_size: resize.map(|r| r.new_size),
        });

        if request.persist {
            let mpath = self.storage.manifest_path(&self.match_id, &capture_id)?;
            // Append-style: write latest combined list as array under same path for spike simplicity
            // — store last frame manifest atomically; also keep in-memory list.
            write_manifest_atomic(&mpath, &manifest)
                .map_err(CaptureError::storage_failed)?;
        }
        self.manifests.push(manifest);
        self.last_content_hash = Some(hash);
        self.stats.frames_captured += 1;
        self.stats.last_content_size = Some((width, height));
        if frame_pool_recreated {
            self.stats.frame_pool_recreated = true;
        }

        Ok(CaptureFrame {
            frame_id,
            width,
            height,
            pixel_format,
            captured_at_unix_ms: captured_at,
            source_timestamp_qpc,
            content_sha256: encoded_hash,
            storage_path,
            quality,
            pixels,
        })
    }
}

impl CaptureAdapter for NativeCaptureAdapter {
    fn discover_targets(&mut self) -> Result<Vec<CaptureTarget>, CaptureError> {
        let pid = self.cs2_pid()?;
        let candidates = enumerate_cs2_windows(pid)?;
        match select_cs2_main_window(pid, &candidates)? {
            crate::capture::discover::DiscoveryOutcome::Found(t)
            | crate::capture::discover::DiscoveryOutcome::Minimized(t)
            | crate::capture::discover::DiscoveryOutcome::ZeroSize(t) => Ok(vec![t]),
            crate::capture::discover::DiscoveryOutcome::Ambiguous(list) => Ok(list),
            crate::capture::discover::DiscoveryOutcome::NotFound => {
                Err(CaptureError::window_not_found())
            }
        }
    }

    fn open(&mut self, target: &CaptureTarget) -> Result<(), CaptureError> {
        if target.kind != CaptureTargetKind::Window {
            return Err(CaptureError::unsupported(
                "P0.6 primary path opens CS2 window targets only",
            ));
        }
        if target.is_minimized {
            return Err(CaptureError::target_minimized());
        }
        if target.client_rect.width == 0 || target.client_rect.height == 0 {
            return Err(CaptureError::target_zero_size());
        }
        let hwnd = target.hwnd.ok_or_else(CaptureError::target_closed)?;

        #[cfg(windows)]
        {
            if self.decision.backend != CaptureBackend::WindowsGraphicsCapture
                && self.allow_dxgi_fallback
            {
                return Err(CaptureError::unsupported(
                    "DXGI Desktop Duplication fallback is documented but not auto-exercised in P0.6; WGC proof required first",
                ));
            }
            let session = crate::capture::backend::WgcCaptureSession::open(hwnd)?;
            self.session = Some(session);
            self.target = Some(target.clone());
            self.ensure_capture_id();
            self.refresh_decision();
            Ok(())
        }
        #[cfg(not(windows))]
        {
            let _ = hwnd;
            Err(CaptureError::unsupported(
                "Windows.Graphics.Capture requires Windows",
            ))
        }
    }

    fn capture_frame(&mut self, request: &CaptureFrameRequest) -> Result<CaptureFrame, CaptureError> {
        #[cfg(windows)]
        {
            if self.session.is_none() {
                return Err(CaptureError::target_closed());
            }
            // Refresh minimized/closed state from OS before borrowing the session.
            if let Some(hwnd) = self.target.as_ref().and_then(|t| t.hwnd) {
                let pid = self.target.as_ref().and_then(|t| t.process_id).unwrap_or(0);
                if pid != 0 {
                    if let Ok(cands) = enumerate_cs2_windows(pid) {
                        if let Some(c) = cands.iter().find(|c| c.hwnd == hwnd) {
                            if c.is_minimized {
                                return Err(CaptureError::target_minimized());
                            }
                            if c.client_width == 0 || c.client_height == 0 {
                                return Err(CaptureError::target_zero_size());
                            }
                        } else {
                            return Err(CaptureError::target_closed());
                        }
                    }
                }
            }
            let (raw, resize, recreated) = {
                let session = self.session.as_mut().ok_or_else(CaptureError::target_closed)?;
                let raw = session.capture_frame(request.timeout)?;
                let resize = session.last_resize_info().cloned();
                let recreated = raw.frame_pool_recreated || session.frame_pool_recreated();
                (raw, resize, recreated)
            };
            self.persist_and_wrap(
                raw.width,
                raw.height,
                raw.pixels_bgra,
                raw.pixel_format,
                raw.source_timestamp_qpc,
                request,
                recreated,
                resize.as_ref(),
            )
        }
        #[cfg(not(windows))]
        {
            let _ = request;
            Err(CaptureError::unsupported("capture requires Windows"))
        }
    }

    fn capture_burst(
        &mut self,
        request: &CaptureBurstRequest,
        cancel: Option<&AtomicBool>,
    ) -> Result<Vec<CaptureFrame>, CaptureError> {
        if request.count == 0 || request.count > DEFAULT_MAX_BURST_FRAMES {
            return Err(CaptureError::burst_limit(format!(
                "burst count must be 1..={DEFAULT_MAX_BURST_FRAMES}"
            )));
        }
        let deadline = std::time::Instant::now() + request.timeout;
        let per_frame_timeout = Duration::from_millis(
            (request.timeout.as_millis() as u64 / request.count as u64).max(200),
        );
        let mut frames = Vec::with_capacity(request.count as usize);
        for i in 0..request.count {
            if cancel.map(|c| c.load(Ordering::Relaxed)).unwrap_or(false) {
                return Err(CaptureError::cancelled());
            }
            if std::time::Instant::now() >= deadline {
                return Err(CaptureError::frame_timeout());
            }
            let remaining = deadline.saturating_duration_since(std::time::Instant::now());
            let req = CaptureFrameRequest {
                timeout: per_frame_timeout.min(remaining),
                persist: request.persist,
                previous_content_sha256: self.last_content_hash.clone(),
                replay_paused: request.replay_paused,
            };
            frames.push(self.capture_frame(&req)?);
            if i + 1 < request.count && !request.interval.is_zero() {
                std::thread::sleep(request.interval);
            }
        }
        Ok(frames)
    }

    fn close(&mut self) {
        #[cfg(windows)]
        {
            self.session = None;
        }
        self.target = None;
        self.last_content_hash = None;
    }

    fn health(&self) -> CaptureHealth {
        CaptureHealth {
            wgc_supported: {
                #[cfg(windows)]
                {
                    crate::capture::backend::wgc::wgc_is_supported()
                }
                #[cfg(not(windows))]
                {
                    false
                }
            },
            selected_backend: self.decision.backend,
            backend_reason: self.decision.reason.clone(),
            open_session: self.session_open(),
            target_id: self.target.as_ref().map(|t| t.target_id.clone()),
            last_frame_size: self.stats.last_content_size,
            frame_pool_recreated: self.stats.frame_pool_recreated,
        }
    }
}

/// Convenience: discover CS2 main window for the running process.
pub fn discover_running_cs2_window() -> Result<CaptureTarget, CaptureError> {
    let mut mgr = Cs2ProcessManager::new();
    use crate::cs2::process::Cs2ProcessState;
    let pid = match mgr.get_process_state(None) {
        Cs2ProcessState::Running { pid, .. }
        | Cs2ProcessState::RunningWithoutNetCon { pid }
        | Cs2ProcessState::NetConReady {
            pid: Some(pid), ..
        } => pid,
        _ => return Err(CaptureError::window_not_found()),
    };
    discover_cs2_target(pid)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn burst_limits_enforced() {
        let mut adapter = NativeCaptureAdapter::new(std::env::temp_dir().join("cap-burst-test"));
        let err = adapter
            .capture_burst(
                &CaptureBurstRequest {
                    count: DEFAULT_MAX_BURST_FRAMES + 1,
                    ..Default::default()
                },
                None,
            )
            .unwrap_err();
        assert_eq!(err.code, "CAPTURE_BURST_LIMIT");
    }

    #[test]
    fn timeout_configuration_defaults() {
        let req = CaptureFrameRequest::default();
        assert!(req.timeout >= Duration::from_secs(1));
        let burst = CaptureBurstRequest::default();
        assert!(burst.timeout >= Duration::from_secs(5));
    }

    #[test]
    fn resize_state_tracked_in_stats_default() {
        let adapter = NativeCaptureAdapter::new(std::env::temp_dir().join("cap-resize-test"));
        assert!(!adapter.stats.frame_pool_recreated);
        assert!(adapter.health().selected_backend == CaptureBackend::WindowsGraphicsCapture
            || !cfg!(windows));
    }
}
