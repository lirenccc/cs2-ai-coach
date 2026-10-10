//! Capture geometry contract (P0.6A).
//!
//! Do not assume `capture_size == client_size`. Prefer a deterministic
//! canonical client-area crop when the client rect is embeddable in the
//! WGC content; otherwise keep the raw frame and mark crop status.

use crate::capture::types::RectPx;
use serde::{Deserialize, Serialize};

pub const GEOMETRY_POLICY_VERSION: &str = "p0.6a-2026-10-10";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CropStatus {
    /// Deterministic client-area crop applied.
    CanonicalClientApplied,
    /// Raw WGC frame retained; crop not reliable.
    RawPreservedCropUnreliable,
    /// Geometry incomplete — no crop attempted.
    InsufficientGeometry,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CaptureGeometry {
    pub geometry_policy_version: String,
    pub window_rect: RectPx,
    pub client_rect: RectPx,
    /// Client origin in screen coordinates when known.
    pub client_to_screen_origin: Option<(i32, i32)>,
    pub wgc_content_size: (u32, u32),
    pub stored_frame_size: (u32, u32),
    pub canonical_crop_rect: Option<RectPx>,
    pub dpi_scale: f64,
    pub crop_status: CropStatus,
}

/// Pure crop planner: map client area into WGC content coordinates.
///
/// Assumes WGC content is axis-aligned with the window frame and the client
/// area is inset from the frame. When sizes disagree without a reliable inset
/// model, returns `RawPreservedCropUnreliable`.
pub fn plan_canonical_client_crop(
    window_rect: RectPx,
    client_rect: RectPx,
    client_to_screen_origin: Option<(i32, i32)>,
    wgc_content_size: (u32, u32),
    dpi_scale: f64,
) -> CaptureGeometry {
    let stored = wgc_content_size;
    let client_w = client_rect.width;
    let client_h = client_rect.height;

    if client_w == 0 || client_h == 0 || wgc_content_size.0 == 0 || wgc_content_size.1 == 0 {
        return CaptureGeometry {
            geometry_policy_version: GEOMETRY_POLICY_VERSION.to_string(),
            window_rect,
            client_rect,
            client_to_screen_origin,
            wgc_content_size,
            stored_frame_size: stored,
            canonical_crop_rect: None,
            dpi_scale,
            crop_status: CropStatus::InsufficientGeometry,
        };
    }

    // Exact match: no crop needed.
    if wgc_content_size == (client_w, client_h) {
        return CaptureGeometry {
            geometry_policy_version: GEOMETRY_POLICY_VERSION.to_string(),
            window_rect,
            client_rect,
            client_to_screen_origin,
            wgc_content_size,
            stored_frame_size: stored,
            canonical_crop_rect: Some(RectPx {
                x: 0,
                y: 0,
                width: client_w,
                height: client_h,
            }),
            dpi_scale,
            crop_status: CropStatus::CanonicalClientApplied,
        };
    }

    // Infer top/left chrome inset from window vs client when screen origin known.
    if let Some((cx, cy)) = client_to_screen_origin {
        let inset_x = cx.saturating_sub(window_rect.x);
        let inset_y = cy.saturating_sub(window_rect.y);
        if inset_x >= 0
            && inset_y >= 0
            && (inset_x as u32) + client_w <= wgc_content_size.0
            && (inset_y as u32) + client_h <= wgc_content_size.1
        {
            return CaptureGeometry {
                geometry_policy_version: GEOMETRY_POLICY_VERSION.to_string(),
                window_rect,
                client_rect,
                client_to_screen_origin,
                wgc_content_size,
                stored_frame_size: stored,
                canonical_crop_rect: Some(RectPx {
                    x: inset_x,
                    y: inset_y,
                    width: client_w,
                    height: client_h,
                }),
                dpi_scale,
                crop_status: CropStatus::CanonicalClientApplied,
            };
        }
    }

    // Symmetric border heuristic used only when content is larger on both axes
    // by a small even delta (typical WGC chrome). Documented as DERIVED.
    if wgc_content_size.0 >= client_w && wgc_content_size.1 >= client_h {
        let dx = wgc_content_size.0 - client_w;
        let dy = wgc_content_size.1 - client_h;
        if dx <= 32 && dy <= 64 && dx % 2 == 0 {
            let x = (dx / 2) as i32;
            let y = (dy.saturating_sub(dx / 2)).min(dy) as i32;
            // Prefer top-heavy chrome (title bar): place leftover on top.
            let y = if dy >= dx { (dy - dx / 2) as i32 } else { y };
            if x >= 0
                && y >= 0
                && (x as u32) + client_w <= wgc_content_size.0
                && (y as u32) + client_h <= wgc_content_size.1
            {
                return CaptureGeometry {
                    geometry_policy_version: GEOMETRY_POLICY_VERSION.to_string(),
                    window_rect,
                    client_rect,
                    client_to_screen_origin,
                    wgc_content_size,
                    stored_frame_size: stored,
                    canonical_crop_rect: Some(RectPx {
                        x,
                        y,
                        width: client_w,
                        height: client_h,
                    }),
                    dpi_scale,
                    crop_status: CropStatus::CanonicalClientApplied,
                };
            }
        }
    }

    CaptureGeometry {
        geometry_policy_version: GEOMETRY_POLICY_VERSION.to_string(),
        window_rect,
        client_rect,
        client_to_screen_origin,
        wgc_content_size,
        stored_frame_size: stored,
        canonical_crop_rect: None,
        dpi_scale,
        crop_status: CropStatus::RawPreservedCropUnreliable,
    }
}

/// Apply a crop rect to a tightly packed BGRA/RGBA buffer.
pub fn crop_bgra(
    pixels: &[u8],
    src_w: u32,
    src_h: u32,
    crop: RectPx,
) -> Result<Vec<u8>, &'static str> {
    if crop.x < 0 || crop.y < 0 {
        return Err("negative crop origin");
    }
    let x = crop.x as u32;
    let y = crop.y as u32;
    if x + crop.width > src_w || y + crop.height > src_h {
        return Err("crop escapes source");
    }
    let mut out = vec![0u8; (crop.width * crop.height * 4) as usize];
    for row in 0..crop.height {
        let src_off = (((y + row) * src_w + x) * 4) as usize;
        let dst_off = (row * crop.width * 4) as usize;
        let len = (crop.width * 4) as usize;
        out[dst_off..dst_off + len].copy_from_slice(&pixels[src_off..src_off + len]);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exact_client_match_is_canonical() {
        let g = plan_canonical_client_crop(
            RectPx {
                x: 0,
                y: 0,
                width: 1280,
                height: 720,
            },
            RectPx {
                x: 0,
                y: 0,
                width: 1280,
                height: 720,
            },
            Some((0, 0)),
            (1280, 720),
            1.0,
        );
        assert_eq!(g.crop_status, CropStatus::CanonicalClientApplied);
        assert_eq!(g.geometry_policy_version, GEOMETRY_POLICY_VERSION);
    }

    #[test]
    fn p0_6_observed_size_mismatch_plans_or_preserves() {
        // Observed: client 1280x720, WGC 1282x752
        let g = plan_canonical_client_crop(
            RectPx {
                x: 632,
                y: 329,
                width: 1296,
                height: 759,
            },
            RectPx {
                x: 0,
                y: 0,
                width: 1280,
                height: 720,
            },
            Some((640, 361)),
            (1282, 752),
            1.0,
        );
        assert!(
            matches!(
                g.crop_status,
                CropStatus::CanonicalClientApplied | CropStatus::RawPreservedCropUnreliable
            ),
            "{:?}",
            g.crop_status
        );
        assert_ne!(g.wgc_content_size, (g.client_rect.width, g.client_rect.height));
    }

    #[test]
    fn unreliable_geometry_preserves_raw() {
        let g = plan_canonical_client_crop(
            RectPx {
                x: 0,
                y: 0,
                width: 100,
                height: 100,
            },
            RectPx {
                x: 0,
                y: 0,
                width: 50,
                height: 50,
            },
            None,
            (400, 300),
            1.0,
        );
        assert_eq!(g.crop_status, CropStatus::RawPreservedCropUnreliable);
        assert!(g.canonical_crop_rect.is_none());
    }

    #[test]
    fn crop_bgra_extracts_region() {
        // 4x2 image, crop 2x1 at (1,0)
        let mut px = vec![0u8; 4 * 2 * 4];
        px[4..8].copy_from_slice(&[1, 2, 3, 255]);
        let out = crop_bgra(
            &px,
            4,
            2,
            RectPx {
                x: 1,
                y: 0,
                width: 2,
                height: 1,
            },
        )
        .unwrap();
        assert_eq!(out.len(), 8);
        assert_eq!(&out[0..4], &[1, 2, 3, 255]);
    }
}
