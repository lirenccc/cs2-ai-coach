//! Versioned capture manifests with fixture redaction.

use crate::capture::types::{
    CaptureBackend, CaptureTarget, FrameQuality, PixelFormat, ReplayCaptureContext, SettlePolicy,
    CAPTURE_MANIFEST_VERSION, RectPx,
};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CaptureManifest {
    pub manifest_version: String,
    pub capture_id: String,
    pub frame_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub match_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub incident_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub event_id: Option<String>,
    pub requested_demo_tick: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub server_tick_reference: Option<u64>,
    pub replay_semantics_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cs2_patch_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cs2_client_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub steam_buildid: Option<String>,
    pub capture_backend: CaptureBackend,
    /// Never persist raw HWND as durable identity in committed fixtures.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_hwnd_runtime_only: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_process_id_runtime_only: Option<u32>,
    pub window_rect: RectPx,
    pub client_rect: RectPx,
    pub dpi_scale: f64,
    pub frame_width: u32,
    pub frame_height: u32,
    pub pixel_format: String,
    pub settle_policy: SettlePolicy,
    pub settle_ms: u64,
    pub captured_at_unix_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_timestamp_qpc: Option<u64>,
    pub content_sha256: String,
    pub quality: FrameQuality,
    pub storage_path_relative: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frame_pool_recreated: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resize_old_size: Option<(u32, u32)>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resize_new_size: Option<(u32, u32)>,
}

#[derive(Debug, Clone)]
pub struct ManifestBuildInput {
    pub capture_id: String,
    pub frame_id: String,
    pub backend: CaptureBackend,
    pub target: Option<CaptureTarget>,
    pub replay: Option<ReplayCaptureContext>,
    pub frame_width: u32,
    pub frame_height: u32,
    pub pixel_format: PixelFormat,
    pub captured_at_unix_ms: u64,
    pub source_timestamp_qpc: Option<u64>,
    pub content_sha256: String,
    pub quality: FrameQuality,
    pub storage_path_relative: String,
    pub cs2_patch_version: Option<String>,
    pub cs2_client_version: Option<String>,
    pub steam_buildid: Option<String>,
    pub frame_pool_recreated: Option<bool>,
    pub resize_old_size: Option<(u32, u32)>,
    pub resize_new_size: Option<(u32, u32)>,
}

pub fn build_manifest(input: ManifestBuildInput) -> CaptureManifest {
    let settle = input
        .replay
        .as_ref()
        .map(|r| r.settle_policy)
        .unwrap_or_default();
    let target = input.target.as_ref();
    CaptureManifest {
        manifest_version: CAPTURE_MANIFEST_VERSION.to_string(),
        capture_id: input.capture_id,
        frame_id: input.frame_id,
        match_id: input.replay.as_ref().and_then(|r| r.match_id.clone()),
        incident_id: input.replay.as_ref().and_then(|r| r.incident_id.clone()),
        event_id: input.replay.as_ref().and_then(|r| r.event_id.clone()),
        requested_demo_tick: input.replay.as_ref().map(|r| r.requested_demo_tick),
        server_tick_reference: input
            .replay
            .as_ref()
            .and_then(|r| r.server_tick_reference),
        replay_semantics_version: input
            .replay
            .as_ref()
            .map(|r| r.calibrated_replay_semantics_version.clone()),
        cs2_patch_version: input.cs2_patch_version,
        cs2_client_version: input.cs2_client_version,
        steam_buildid: input.steam_buildid,
        capture_backend: input.backend,
        target_hwnd_runtime_only: target.and_then(|t| t.hwnd),
        target_process_id_runtime_only: target.and_then(|t| t.process_id),
        window_rect: target.map(|t| t.frame_rect).unwrap_or(RectPx {
            x: 0,
            y: 0,
            width: 0,
            height: 0,
        }),
        client_rect: target.map(|t| t.client_rect).unwrap_or(RectPx {
            x: 0,
            y: 0,
            width: 0,
            height: 0,
        }),
        dpi_scale: target.map(|t| t.dpi_scale).unwrap_or(1.0),
        frame_width: input.frame_width,
        frame_height: input.frame_height,
        pixel_format: input.pixel_format.as_str().to_string(),
        settle_policy: settle,
        settle_ms: settle.ms(),
        captured_at_unix_ms: input.captured_at_unix_ms,
        source_timestamp_qpc: input.source_timestamp_qpc,
        content_sha256: input.content_sha256,
        quality: input.quality,
        storage_path_relative: input.storage_path_relative,
        frame_pool_recreated: input.frame_pool_recreated,
        resize_old_size: input.resize_old_size,
        resize_new_size: input.resize_new_size,
    }
}

/// Redact runtime-only / path / identity fields for committed fixtures.
pub fn redact_manifest(manifest: &CaptureManifest) -> CaptureManifest {
    let mut m = manifest.clone();
    m.target_hwnd_runtime_only = None;
    m.target_process_id_runtime_only = None;
    m.storage_path_relative = redact_storage_path(&m.storage_path_relative);
    if let Some(path_like) = m.seek_path_fields() {
        let _ = path_like;
    }
    m
}

trait SeekPathFields {
    fn seek_path_fields(&self) -> Option<()>;
}

impl SeekPathFields for CaptureManifest {
    fn seek_path_fields(&self) -> Option<()> {
        None
    }
}

fn redact_storage_path(path: &str) -> String {
    let p = Path::new(path);
    let file = p
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("frame.png");
    format!("runtime/captures/<match-id>/<capture-id>/{file}")
}

pub fn write_manifest_atomic(path: &Path, manifest: &CaptureManifest) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let tmp = path.with_extension("json.tmp");
    let json = serde_json::to_vec_pretty(manifest).map_err(|e| e.to_string())?;
    std::fs::write(&tmp, &json).map_err(|e| e.to_string())?;
    std::fs::rename(&tmp, path).map_err(|e| e.to_string())?;
    Ok(())
}

pub fn relative_under_runtime(abs: &Path, runtime_root: &Path) -> PathBuf {
    abs.strip_prefix(runtime_root)
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|_| PathBuf::from(abs.file_name().unwrap_or_default()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::capture::types::{CaptureTargetKind, FrameQuality};

    fn sample_quality() -> FrameQuality {
        FrameQuality {
            valid: true,
            black_ratio: 0.01,
            white_ratio: 0.0,
            variance: 120.0,
            exact_duplicate: false,
            duplicate_expected_while_paused: false,
            capture_backend_stuck: false,
            warnings: vec![],
        }
    }

    #[test]
    fn manifest_serialization_roundtrip() {
        let manifest = build_manifest(ManifestBuildInput {
            capture_id: "cap1".into(),
            frame_id: "frame-0001".into(),
            backend: CaptureBackend::WindowsGraphicsCapture,
            target: Some(CaptureTarget {
                target_id: "t1".into(),
                kind: CaptureTargetKind::Window,
                hwnd: Some(0x1234),
                process_id: Some(42),
                process_name: Some("cs2.exe".into()),
                title: Some("Counter-Strike 2".into()),
                class_name: Some("SDL_app".into()),
                client_rect: RectPx {
                    x: 0,
                    y: 0,
                    width: 1920,
                    height: 1080,
                },
                frame_rect: RectPx {
                    x: 10,
                    y: 20,
                    width: 1920,
                    height: 1080,
                },
                dpi_scale: 1.0,
                monitor_id: None,
                is_minimized: false,
                is_visible: true,
            }),
            replay: Some(
                ReplayCaptureContext::from_demo_tick(4354)
                    .unwrap()
                    .with_ids("match-a", "A01_early_plant"),
            ),
            frame_width: 1920,
            frame_height: 1080,
            pixel_format: PixelFormat::Bgra8,
            captured_at_unix_ms: 1_700_000_000_000,
            source_timestamp_qpc: Some(99),
            content_sha256: "abc".into(),
            quality: sample_quality(),
            storage_path_relative: "captures/match-a/cap1/frame-0001.png".into(),
            cs2_patch_version: Some("1.41.9.0".into()),
            cs2_client_version: Some("2000930".into()),
            steam_buildid: Some("25815307".into()),
            frame_pool_recreated: Some(false),
            resize_old_size: None,
            resize_new_size: None,
        });
        let json = serde_json::to_string(&manifest).unwrap();
        let back: CaptureManifest = serde_json::from_str(&json).unwrap();
        assert_eq!(back.requested_demo_tick, Some(4354));
        assert_eq!(back.manifest_version, CAPTURE_MANIFEST_VERSION);
        assert_eq!(back.pixel_format, "B8G8R8A8_UNORM");
    }

    #[test]
    fn manifest_redaction_strips_hwnd_and_paths() {
        let mut manifest = build_manifest(ManifestBuildInput {
            capture_id: "cap1".into(),
            frame_id: "frame-0001".into(),
            backend: CaptureBackend::WindowsGraphicsCapture,
            target: None,
            replay: None,
            frame_width: 100,
            frame_height: 100,
            pixel_format: PixelFormat::Bgra8,
            captured_at_unix_ms: 1,
            source_timestamp_qpc: None,
            content_sha256: "deadbeef".into(),
            quality: sample_quality(),
            storage_path_relative: r"C:\Users\private\runtime\captures\m\c\frame-0001.png".into(),
            cs2_patch_version: None,
            cs2_client_version: None,
            steam_buildid: None,
            frame_pool_recreated: None,
            resize_old_size: None,
            resize_new_size: None,
        });
        manifest.target_hwnd_runtime_only = Some(999);
        manifest.target_process_id_runtime_only = Some(1);
        let redacted = redact_manifest(&manifest);
        assert!(redacted.target_hwnd_runtime_only.is_none());
        assert!(redacted.target_process_id_runtime_only.is_none());
        assert!(!redacted.storage_path_relative.contains("Users"));
        assert!(redacted.storage_path_relative.contains("<match-id>"));
    }
}
