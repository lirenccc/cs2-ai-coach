//! Capture domain types. Win32/COM/D3D objects never leave the native adapter.

use crate::cs2::calibration::REPLAY_SEMANTICS_VERSION;
use crate::cs2::tick::{ReplaySeekPosition, ReplayTickDomain};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::time::Duration;

pub const CAPTURE_MANIFEST_VERSION: &str = "p0.6-2026-10-10";
pub const DEFAULT_MAX_BURST_FRAMES: u32 = 16;
pub const DEFAULT_MIN_FRAME_WIDTH: u32 = 64;
pub const DEFAULT_MIN_FRAME_HEIGHT: u32 = 64;
pub const DEFAULT_BLACK_RATIO_MAX: f64 = 0.985;
pub const DEFAULT_WHITE_RATIO_MAX: f64 = 0.985;
pub const DEFAULT_MIN_VARIANCE: f64 = 8.0;
pub const DEFAULT_SETTLE_MS: u64 = 2000;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CaptureTargetKind {
    Window,
    Monitor,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CaptureBackend {
    WindowsGraphicsCapture,
    DesktopDuplication,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PixelFormat {
    Bgra8,
    Rgba8,
}

impl PixelFormat {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Bgra8 => "B8G8R8A8_UNORM",
            Self::Rgba8 => "R8G8B8A8_UNORM",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct RectPx {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CaptureTarget {
    pub target_id: String,
    pub kind: CaptureTargetKind,
    /// Runtime-only handle; never a durable identity in committed fixtures.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hwnd: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub process_id: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub process_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub class_name: Option<String>,
    pub client_rect: RectPx,
    pub frame_rect: RectPx,
    pub dpi_scale: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub monitor_id: Option<String>,
    pub is_minimized: bool,
    pub is_visible: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FrameQuality {
    pub valid: bool,
    pub black_ratio: f64,
    pub white_ratio: f64,
    pub variance: f64,
    pub exact_duplicate: bool,
    /// True when a near-identical frame is expected because replay is paused.
    pub duplicate_expected_while_paused: bool,
    /// True when timestamps suggest the capture backend stopped delivering new frames.
    pub capture_backend_stuck: bool,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CaptureFrame {
    pub frame_id: String,
    pub width: u32,
    pub height: u32,
    pub pixel_format: PixelFormat,
    pub captured_at_unix_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_timestamp_qpc: Option<u64>,
    pub content_sha256: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub storage_path: Option<PathBuf>,
    pub quality: FrameQuality,
    /// CPU-owned BGRA/RGBA buffer for in-process use; never sent to renderer by default.
    #[serde(skip)]
    pub pixels: Vec<u8>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SettlePolicy {
    FixedDuration { ms: u64 },
}

impl SettlePolicy {
    pub fn fixed_ms(ms: u64) -> Self {
        Self::FixedDuration { ms }
    }

    pub fn duration(self) -> Duration {
        match self {
            Self::FixedDuration { ms } => Duration::from_millis(ms),
        }
    }

    pub fn ms(self) -> u64 {
        match self {
            Self::FixedDuration { ms } => ms,
        }
    }
}

impl Default for SettlePolicy {
    fn default() -> Self {
        Self::FixedDuration {
            ms: DEFAULT_SETTLE_MS,
        }
    }
}

/// Capture receives already-resolved calibrated replay context — never raw ServerTick seeks.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReplayCaptureContext {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub match_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub incident_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub event_id: Option<String>,
    pub requested_demo_tick: u64,
    /// Optional reference only; never used as `demo_gototick` argument.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub server_tick_reference: Option<u64>,
    pub calibrated_replay_semantics_version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub seek_evidence: Option<String>,
    pub settle_policy: SettlePolicy,
}

impl ReplayCaptureContext {
    pub fn from_demo_tick(demo_tick: u64) -> Result<Self, String> {
        if demo_tick == 0 {
            return Err(
                "DemoTick 0 nudge is forbidden for the calibrated build family".into(),
            );
        }
        Ok(Self {
            match_id: None,
            incident_id: None,
            event_id: None,
            requested_demo_tick: demo_tick,
            server_tick_reference: None,
            calibrated_replay_semantics_version: REPLAY_SEMANTICS_VERSION.to_string(),
            seek_evidence: None,
            settle_policy: SettlePolicy::default(),
        })
    }

    /// Production capture seek position — DemoTick only.
    pub fn seek_position(&self) -> Result<ReplaySeekPosition, String> {
        if self.requested_demo_tick == 0 {
            return Err("DemoTick 0 nudge is forbidden".into());
        }
        if self.calibrated_replay_semantics_version != REPLAY_SEMANTICS_VERSION {
            return Err(format!(
                "replay semantics version mismatch: got {}, expected {}",
                self.calibrated_replay_semantics_version, REPLAY_SEMANTICS_VERSION
            ));
        }
        Ok(ReplaySeekPosition::DemoTick(self.requested_demo_tick))
    }

    pub fn reject_server_tick_seek(domain: ReplayTickDomain) -> Result<(), String> {
        if domain == ReplayTickDomain::ServerTick {
            return Err(
                "ServerTick must not enter the production capture seek path for demo_gototick"
                    .into(),
            );
        }
        Ok(())
    }

    pub fn with_ids(mut self, match_id: impl Into<String>, event_id: impl Into<String>) -> Self {
        self.match_id = Some(match_id.into());
        self.event_id = Some(event_id.into());
        self
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct CaptureFrameRequest {
    pub timeout: Duration,
    pub persist: bool,
    pub previous_content_sha256: Option<String>,
    pub replay_paused: bool,
}

impl Default for CaptureFrameRequest {
    fn default() -> Self {
        Self {
            timeout: Duration::from_secs(3),
            persist: true,
            previous_content_sha256: None,
            replay_paused: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct CaptureBurstRequest {
    pub count: u32,
    pub interval: Duration,
    pub timeout: Duration,
    pub persist: bool,
    pub replay_paused: bool,
}

impl Default for CaptureBurstRequest {
    fn default() -> Self {
        Self {
            count: 3,
            interval: Duration::from_millis(100),
            timeout: Duration::from_secs(15),
            persist: true,
            replay_paused: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CaptureHealth {
    pub wgc_supported: bool,
    pub selected_backend: CaptureBackend,
    pub backend_reason: String,
    pub open_session: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_frame_size: Option<(u32, u32)>,
    pub frame_pool_recreated: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ResizeRecoveryInfo {
    pub frame_pool_recreated: bool,
    pub old_size: (u32, u32),
    pub new_size: (u32, u32),
    pub hwnd_changed: bool,
    pub target_rediscovered: bool,
    pub device_recreated: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CaptureSessionStats {
    pub frame_pool_recreated: bool,
    pub last_content_size: Option<(u32, u32)>,
    pub frames_captured: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cs2::tick::ReplayTickDomain;

    #[test]
    fn replay_context_accepts_calibrated_demo_tick() {
        let ctx = ReplayCaptureContext::from_demo_tick(4354).unwrap();
        assert_eq!(
            ctx.seek_position().unwrap(),
            ReplaySeekPosition::DemoTick(4354)
        );
        assert_eq!(
            ctx.calibrated_replay_semantics_version,
            REPLAY_SEMANTICS_VERSION
        );
    }

    #[test]
    fn raw_server_tick_cannot_enter_capture_seek_path() {
        assert!(ReplayCaptureContext::reject_server_tick_seek(ReplayTickDomain::ServerTick).is_err());
        assert!(ReplayCaptureContext::reject_server_tick_seek(ReplayTickDomain::DemoTick).is_ok());
    }

    #[test]
    fn demo_tick_zero_nudge_forbidden() {
        assert!(ReplayCaptureContext::from_demo_tick(0).is_err());
        let mut ctx = ReplayCaptureContext::from_demo_tick(100).unwrap();
        ctx.requested_demo_tick = 0;
        assert!(ctx.seek_position().is_err());
    }
}
