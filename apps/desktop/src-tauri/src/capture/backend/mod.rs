//! Capture backends. Primary: Windows.Graphics.Capture. Fallback strategy: DXGI.

mod decision;
#[cfg(windows)]
mod dxgi_strategy;
#[cfg(windows)]
pub mod wgc;

#[allow(unused_imports)]
pub use decision::{select_backend, BackendDecision, FallbackReason};

#[cfg(windows)]
#[allow(unused_imports)]
pub use dxgi_strategy::DesktopDuplicationPlan;
#[cfg(windows)]
pub use wgc::WgcCaptureSession;
