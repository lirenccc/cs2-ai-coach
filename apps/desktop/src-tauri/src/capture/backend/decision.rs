//! Primary vs fallback backend selection. Do not hide WGC bugs behind DXGI in development.

use crate::capture::types::CaptureBackend;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FallbackReason {
    WgcUnsupported,
    WgcInitFailed,
    WgcRepeatedInvalidFrames,
    OsRuntimeUnsupported,
    ForcedForTest,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BackendDecision {
    pub backend: CaptureBackend,
    pub reason: String,
    pub fallback: Option<FallbackReason>,
}

/// Prefer WGC. DXGI is selected only when WGC is unavailable or explicitly failing.
pub fn select_backend(
    wgc_supported: bool,
    wgc_init_ok: bool,
    wgc_invalid_streak: u32,
    allow_dxgi_fallback: bool,
) -> BackendDecision {
    if wgc_supported && wgc_init_ok && wgc_invalid_streak < 3 {
        return BackendDecision {
            backend: CaptureBackend::WindowsGraphicsCapture,
            reason: "WGC supported and healthy".into(),
            fallback: None,
        };
    }

    let fallback = if !wgc_supported {
        FallbackReason::WgcUnsupported
    } else if !wgc_init_ok {
        FallbackReason::WgcInitFailed
    } else {
        FallbackReason::WgcRepeatedInvalidFrames
    };

    if allow_dxgi_fallback {
        BackendDecision {
            backend: CaptureBackend::DesktopDuplication,
            reason: format!("falling back to DXGI: {fallback:?}"),
            fallback: Some(fallback),
        }
    } else {
        BackendDecision {
            backend: CaptureBackend::WindowsGraphicsCapture,
            reason: format!(
                "WGC preferred; DXGI fallback disabled during development ({fallback:?})"
            ),
            fallback: Some(fallback),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prefers_wgc_when_healthy() {
        let d = select_backend(true, true, 0, true);
        assert_eq!(d.backend, CaptureBackend::WindowsGraphicsCapture);
        assert!(d.fallback.is_none());
    }

    #[test]
    fn fallback_decision_when_wgc_unavailable() {
        let d = select_backend(false, false, 0, true);
        assert_eq!(d.backend, CaptureBackend::DesktopDuplication);
        assert_eq!(d.fallback, Some(FallbackReason::WgcUnsupported));
    }

    #[test]
    fn does_not_auto_hide_wgc_bugs_without_allow() {
        let d = select_backend(true, true, 5, false);
        assert_eq!(d.backend, CaptureBackend::WindowsGraphicsCapture);
        assert!(d.reason.contains("disabled"));
    }
}
