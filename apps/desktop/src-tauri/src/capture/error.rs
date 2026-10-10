//! Typed capture errors with stable codes.

use serde::Serialize;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CaptureError {
    pub code: &'static str,
    pub message: String,
    pub remediation: Option<&'static str>,
}

impl CaptureError {
    pub fn new(
        code: &'static str,
        message: impl Into<String>,
        remediation: Option<&'static str>,
    ) -> Self {
        Self {
            code,
            message: message.into(),
            remediation,
        }
    }

    pub fn window_not_found() -> Self {
        Self::new(
            "CAPTURE_CS2_WINDOW_NOT_FOUND",
            "No capturable CS2 window was found for the detected process",
            Some("Ensure CS2 is running in offline Demo replay and the game window is open"),
        )
    }

    pub fn target_ambiguous(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_TARGET_AMBIGUOUS",
            detail,
            Some("Close helper/tool windows or leave only one CS2 main window visible"),
        )
    }

    pub fn target_closed() -> Self {
        Self::new(
            "CAPTURE_TARGET_CLOSED",
            "Capture target HWND is no longer valid",
            Some("Rediscover the CS2 window and retry the capture"),
        )
    }

    pub fn target_minimized() -> Self {
        Self::new(
            "CAPTURE_TARGET_MINIMIZED",
            "CS2 window is minimized and cannot produce a valid frame",
            Some("Restore the CS2 window, then retry capture"),
        )
    }

    pub fn target_zero_size() -> Self {
        Self::new(
            "CAPTURE_TARGET_ZERO_SIZE",
            "CS2 window client area has zero dimensions",
            Some("Restore or resize the CS2 window to a non-zero client area"),
        )
    }

    pub fn frame_timeout() -> Self {
        Self::new(
            "CAPTURE_FRAME_TIMEOUT",
            "No capture frame arrived before the timeout",
            Some("Ensure CS2 is compositing frames and increase the capture timeout"),
        )
    }

    pub fn device_lost(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_DEVICE_LOST",
            detail,
            Some("Retry capture; if it persists, restart the coach desktop process"),
        )
    }

    pub fn frame_invalid(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_FRAME_INVALID",
            detail,
            Some("Retry after settle; restore CS2 if minimized/occluded incorrectly"),
        )
    }

    pub fn copy_failed(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_COPY_FAILED",
            detail,
            Some("Retry capture; check GPU driver health if failures continue"),
        )
    }

    pub fn storage_failed(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_STORAGE_FAILED",
            detail,
            Some("Verify runtime capture directory permissions and free disk space"),
        )
    }

    pub fn unsupported(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_BACKEND_UNSUPPORTED",
            detail,
            Some("Use Windows 10 1903+ with Graphics Capture support, or enable DXGI fallback"),
        )
    }

    pub fn burst_limit(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_BURST_LIMIT",
            detail,
            Some("Reduce burst count or interval within the configured hard limits"),
        )
    }

    pub fn cancelled() -> Self {
        Self::new(
            "CAPTURE_CANCELLED",
            "Capture operation was cancelled",
            Some("Restart the offline replay capture operation if needed"),
        )
    }

    pub fn replay_context(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_REPLAY_CONTEXT_INVALID",
            detail,
            Some("Provide a calibrated DemoTick replay context; never pass ServerTick to demo_gototick"),
        )
    }

    pub fn wgc_unavailable(detail: impl Into<String>) -> Self {
        Self::new(
            "CAPTURE_WGC_UNAVAILABLE",
            detail,
            Some("Confirm OS support for Windows.Graphics.Capture or use documented DXGI fallback"),
        )
    }
}

impl fmt::Display for CaptureError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for CaptureError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_are_stable() {
        assert_eq!(CaptureError::window_not_found().code, "CAPTURE_CS2_WINDOW_NOT_FOUND");
        assert_eq!(CaptureError::target_ambiguous("x").code, "CAPTURE_TARGET_AMBIGUOUS");
        assert_eq!(CaptureError::frame_timeout().code, "CAPTURE_FRAME_TIMEOUT");
    }
}
