//! DXGI Desktop Duplication fallback strategy (P0.6 documents path; WGC proof is required first).
//!
//! When exercised:
//! - capture the monitor containing CS2
//! - crop using validated CS2 window/client coordinates
//! - account for DPI/scaling
//! - do not assume top-left at (0, 0)

use crate::capture::types::RectPx;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DesktopDuplicationPlan {
    pub monitor_id: String,
    pub crop_in_monitor: RectPx,
    pub dpi_scale: f64,
    pub notes: Vec<String>,
}

pub fn plan_monitor_crop(
    monitor_origin: (i32, i32),
    monitor_size: (u32, u32),
    window_frame: RectPx,
    dpi_scale: f64,
) -> Option<DesktopDuplicationPlan> {
    let x = window_frame.x.saturating_sub(monitor_origin.0);
    let y = window_frame.y.saturating_sub(monitor_origin.1);
    if x < 0 || y < 0 {
        return None;
    }
    let x = x as u32;
    let y = y as u32;
    if x >= monitor_size.0 || y >= monitor_size.1 {
        return None;
    }
    let width = window_frame.width.min(monitor_size.0 - x);
    let height = window_frame.height.min(monitor_size.1 - y);
    if width == 0 || height == 0 {
        return None;
    }
    Some(DesktopDuplicationPlan {
        monitor_id: format!("monitor@{},{}", monitor_origin.0, monitor_origin.1),
        crop_in_monitor: RectPx { x: x as i32, y: y as i32, width, height },
        dpi_scale,
        notes: vec![
            "crop uses validated window frame relative to monitor origin".into(),
            "top-left (0,0) is never assumed for the CS2 window".into(),
            "DPI scale recorded for higher-layer coordinate transforms".into(),
        ],
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crop_accounts_for_monitor_origin() {
        let plan = plan_monitor_crop(
            (100, 200),
            (1920, 1080),
            RectPx {
                x: 300,
                y: 400,
                width: 800,
                height: 600,
            },
            1.25,
        )
        .unwrap();
        assert_eq!(plan.crop_in_monitor.x, 200);
        assert_eq!(plan.crop_in_monitor.y, 200);
        assert_eq!(plan.dpi_scale, 1.25);
    }
}
