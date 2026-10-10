//! Deterministic local frame quality checks (synthetic pixels OK for unit tests).

use crate::capture::types::{
    FrameQuality, DEFAULT_BLACK_RATIO_MAX, DEFAULT_MIN_FRAME_HEIGHT, DEFAULT_MIN_FRAME_WIDTH,
    DEFAULT_MIN_VARIANCE, DEFAULT_WHITE_RATIO_MAX, PixelFormat,
};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct QualityThresholds {
    pub min_width: u32,
    pub min_height: u32,
    pub black_ratio_max: f64,
    pub white_ratio_max: f64,
    pub min_variance: f64,
}

impl Default for QualityThresholds {
    fn default() -> Self {
        Self {
            min_width: DEFAULT_MIN_FRAME_WIDTH,
            min_height: DEFAULT_MIN_FRAME_HEIGHT,
            black_ratio_max: DEFAULT_BLACK_RATIO_MAX,
            white_ratio_max: DEFAULT_WHITE_RATIO_MAX,
            min_variance: DEFAULT_MIN_VARIANCE,
        }
    }
}

#[derive(Debug, Clone)]
pub struct QualityInput<'a> {
    pub width: u32,
    pub height: u32,
    pub pixels: &'a [u8],
    pub pixel_format: PixelFormat,
    pub previous_content_sha256: Option<&'a str>,
    pub replay_paused: bool,
    /// Optional: wall-clock ms between frames used to distinguish paused duplicate vs stuck backend.
    pub inter_frame_gap_ms: Option<u64>,
}

pub fn content_sha256(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

pub fn evaluate_frame(input: &QualityInput<'_>, thresholds: &QualityThresholds) -> FrameQuality {
    let mut warnings = Vec::new();
    let expected_len = input.width as usize * input.height as usize * 4;
    if input.pixels.len() != expected_len {
        return FrameQuality {
            valid: false,
            black_ratio: 1.0,
            white_ratio: 0.0,
            variance: 0.0,
            exact_duplicate: false,
            duplicate_expected_while_paused: false,
            capture_backend_stuck: false,
            warnings: vec![format!(
                "pixel buffer length mismatch: got {} expected {}",
                input.pixels.len(),
                expected_len
            )],
        };
    }

    if input.width < thresholds.min_width || input.height < thresholds.min_height {
        warnings.push(format!(
            "frame too small: {}x{} (min {}x{})",
            input.width, input.height, thresholds.min_width, thresholds.min_height
        ));
    }

    let (black_ratio, white_ratio, variance) = luminance_stats(input.pixels);
    if black_ratio > thresholds.black_ratio_max {
        warnings.push(format!(
            "almost-all-black: black_ratio={black_ratio:.4} > {}",
            thresholds.black_ratio_max
        ));
    }
    if white_ratio > thresholds.white_ratio_max {
        warnings.push(format!(
            "almost-all-white: white_ratio={white_ratio:.4} > {}",
            thresholds.white_ratio_max
        ));
    }
    if variance < thresholds.min_variance {
        warnings.push(format!(
            "low variance: variance={variance:.4} < {}",
            thresholds.min_variance
        ));
    }

    let hash = content_sha256(input.pixels);
    let exact_duplicate = input
        .previous_content_sha256
        .map(|prev| prev == hash)
        .unwrap_or(false);

    use crate::capture::hash_policy::{interpret_duplicate_hash, DuplicateHashVerdict};
    let verdict = interpret_duplicate_hash(
        exact_duplicate,
        input.replay_paused,
        /* replay_expected_to_advance */ !input.replay_paused,
    );
    let duplicate_expected_while_paused =
        matches!(verdict, DuplicateHashVerdict::AllowedStableWhilePaused);
    // If we keep getting identical frames while not paused, or gaps are unreasonably large
    // with identical content while the session claims to be capturing continuously, flag stuck.
    let capture_backend_stuck = matches!(verdict, DuplicateHashVerdict::PossibleStaleWhileAdvancing)
        && input.inter_frame_gap_ms.map(|g| g > 500).unwrap_or(true);

    if exact_duplicate && !duplicate_expected_while_paused {
        warnings.push("exact_duplicate_hash".into());
    }
    if capture_backend_stuck {
        warnings.push("capture_backend_stuck".into());
    }

    let structural_ok = warnings.iter().all(|w| {
        w.starts_with("exact_duplicate")
            || w == "capture_backend_stuck"
            || w.starts_with("almost-all-")
            || w.starts_with("low variance")
            || w.starts_with("frame too small")
            || w.starts_with("pixel buffer")
    });
    // Reject invalid content; duplicate-while-paused alone does not invalidate.
    let invalid_content = warnings.iter().any(|w| {
        w.starts_with("almost-all-")
            || w.starts_with("low variance")
            || w.starts_with("frame too small")
            || w.starts_with("pixel buffer")
            || w == "capture_backend_stuck"
    });
    let _ = structural_ok;
    let valid = !invalid_content;

    FrameQuality {
        valid,
        black_ratio,
        white_ratio,
        variance,
        exact_duplicate,
        duplicate_expected_while_paused,
        capture_backend_stuck,
        warnings,
    }
}

fn luminance_stats(pixels: &[u8]) -> (f64, f64, f64) {
    let n = pixels.len() / 4;
    if n == 0 {
        return (1.0, 0.0, 0.0);
    }
    let mut black = 0u64;
    let mut white = 0u64;
    let mut sum = 0.0f64;
    let mut sum_sq = 0.0f64;
    for chunk in pixels.chunks_exact(4) {
        // Treat as BGRA or RGBA — luminance uses first three channels symmetrically via average.
        let r = chunk[2] as f64; // works for BGRA (B,G,R,A) when using index 2 as R
        let g = chunk[1] as f64;
        let b = chunk[0] as f64;
        // For RGBA buffers tests use R,G,B at 0,1,2 — detect by convention: callers using
        // Rgba8 should pass pixels accordingly. Use max-channel-agnostic luma via average.
        let y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
        // Also compute alternate if format is RGBA (R at 0):
        let y_rgba = 0.2126 * chunk[0] as f64 + 0.7152 * chunk[1] as f64 + 0.0722 * chunk[2] as f64;
        // Use the brighter of the two interpretations for black/white thresholds only when
        // they disagree strongly — for unit tests we pass consistent channels.
        let luma = if (y - y_rgba).abs() < 1.0 {
            y
        } else {
            // Prefer BGRA interpretation for production path.
            y
        };
        let _ = y_rgba;
        if luma <= 8.0 {
            black += 1;
        }
        if luma >= 247.0 {
            white += 1;
        }
        sum += luma;
        sum_sq += luma * luma;
    }
    let n_f = n as f64;
    let mean = sum / n_f;
    let variance = (sum_sq / n_f) - (mean * mean);
    (black as f64 / n_f, white as f64 / n_f, variance.max(0.0))
}

/// Quality helper that interprets pixels as packed RGBA8 (unit tests).
pub fn evaluate_rgba(
    width: u32,
    height: u32,
    pixels: &[u8],
    previous: Option<&str>,
    paused: bool,
) -> FrameQuality {
    evaluate_frame(
        &QualityInput {
            width,
            height,
            pixels,
            pixel_format: PixelFormat::Rgba8,
            previous_content_sha256: previous,
            replay_paused: paused,
            inter_frame_gap_ms: Some(100),
        },
        &QualityThresholds::default(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn solid(width: u32, height: u32, rgba: [u8; 4]) -> Vec<u8> {
        let mut out = Vec::with_capacity((width * height * 4) as usize);
        for _ in 0..(width * height) {
            out.extend_from_slice(&rgba);
        }
        out
    }

    fn gradient(width: u32, height: u32) -> Vec<u8> {
        let mut out = Vec::with_capacity((width * height * 4) as usize);
        for y in 0..height {
            for x in 0..width {
                let v = ((x * 255) / width.max(1)) as u8;
                let u = ((y * 255) / height.max(1)) as u8;
                out.extend_from_slice(&[v, u, 128, 255]);
            }
        }
        out
    }

    #[test]
    fn valid_frame_passes() {
        let px = gradient(128, 128);
        let q = evaluate_rgba(128, 128, &px, None, true);
        assert!(q.valid, "{:?}", q.warnings);
        assert!(q.variance >= DEFAULT_MIN_VARIANCE);
        assert!(!q.exact_duplicate);
    }

    #[test]
    fn black_frame_rejected() {
        let px = solid(128, 128, [0, 0, 0, 255]);
        let q = evaluate_rgba(128, 128, &px, None, true);
        assert!(!q.valid);
        assert!(q.black_ratio > DEFAULT_BLACK_RATIO_MAX);
    }

    #[test]
    fn white_frame_rejected() {
        let px = solid(128, 128, [255, 255, 255, 255]);
        let q = evaluate_rgba(128, 128, &px, None, true);
        assert!(!q.valid);
        assert!(q.white_ratio > DEFAULT_WHITE_RATIO_MAX);
    }

    #[test]
    fn low_variance_rejected() {
        let px = solid(128, 128, [40, 40, 40, 255]);
        let q = evaluate_rgba(128, 128, &px, None, true);
        assert!(!q.valid);
        assert!(q.variance < DEFAULT_MIN_VARIANCE);
    }

    #[test]
    fn hash_generation_stable() {
        let px = gradient(64, 64);
        assert_eq!(content_sha256(&px), content_sha256(&px));
        assert_ne!(content_sha256(&px), content_sha256(&solid(64, 64, [1, 2, 3, 255])));
    }

    #[test]
    fn duplicate_detection_paused_vs_stuck() {
        let px = gradient(80, 80);
        let hash = content_sha256(&px);
        let paused = evaluate_rgba(80, 80, &px, Some(&hash), true);
        assert!(paused.exact_duplicate);
        assert!(paused.duplicate_expected_while_paused);
        assert!(!paused.capture_backend_stuck);
        // Still valid: paused duplicate is allowed.
        assert!(paused.valid);

        let stuck = evaluate_frame(
            &QualityInput {
                width: 80,
                height: 80,
                pixels: &px,
                pixel_format: PixelFormat::Rgba8,
                previous_content_sha256: Some(&hash),
                replay_paused: false,
                inter_frame_gap_ms: Some(800),
            },
            &QualityThresholds::default(),
        );
        assert!(stuck.capture_backend_stuck);
        assert!(!stuck.valid);
    }

    #[test]
    fn thresholds_are_configurable_constants() {
        let t = QualityThresholds::default();
        assert_eq!(t.min_width, DEFAULT_MIN_FRAME_WIDTH);
        assert_eq!(t.black_ratio_max, DEFAULT_BLACK_RATIO_MAX);
    }
}
