//! Windows capture adapters (P0.6).
//!
//! Offline Demo replay capture only. No live-match automation, injection,
//! process-memory access, or renderer-facing raw HWND/D3D privileges.

#![allow(dead_code)] // Adapter surface exercised by unit/integration tests and Tauri commands.

pub mod adapter;
pub mod backend;
pub mod discover;
pub mod error;
pub mod manifest;
pub mod quality;
pub mod storage;
pub mod types;

#[cfg(test)]
mod integration;

#[allow(unused_imports)]
pub use adapter::{discover_running_cs2_window, CaptureAdapter, NativeCaptureAdapter};
#[allow(unused_imports)]
pub use error::CaptureError;
#[allow(unused_imports)]
pub use types::{
    CaptureBackend, CaptureBurstRequest, CaptureFrame, CaptureFrameRequest, CaptureHealth,
    CaptureTarget, ReplayCaptureContext, SettlePolicy,
};
