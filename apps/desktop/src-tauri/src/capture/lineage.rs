//! Evidence lineage + calibration/build compatibility (P0.6A).

use crate::cs2::calibration::REPLAY_SEMANTICS_VERSION;
use serde::{Deserialize, Serialize};

pub const EVIDENCE_LINEAGE_VERSION: &str = "p0.6a-2026-10-10";
pub const IDENTITY_SEMANTICS_VERSION: &str = "p0.6a-2026-10-10";

/// Build identity string embedded in calibrated capture evidence.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Cs2BuildIdentity {
    pub patch_version: String,
    pub client_version: String,
    pub steam_buildid: String,
}

impl Cs2BuildIdentity {
    pub fn as_compact(&self) -> String {
        format!(
            "patch={};client={};buildid={}",
            self.patch_version, self.client_version, self.steam_buildid
        )
    }
}

/// Calibrated build frozen with P0.5A / P0.6 evidence.
pub fn calibrated_build_identity() -> Cs2BuildIdentity {
    Cs2BuildIdentity {
        patch_version: "1.41.9.0".into(),
        client_version: "2000930".into(),
        steam_buildid: "25815307".into(),
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CaptureCalibrationContext {
    pub replay_calibration_version: String,
    pub expected_build: Cs2BuildIdentity,
    pub observed_build: Option<Cs2BuildIdentity>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CalibrationCompatibility {
    Compatible,
    /// Typed mismatch — must not silently claim calibrated semantic capture.
    BuildMismatch { code: &'static str },
    Uncalibrated { reason: String },
}

pub fn check_calibration_compatibility(
    ctx: &CaptureCalibrationContext,
) -> CalibrationCompatibility {
    if ctx.replay_calibration_version != REPLAY_SEMANTICS_VERSION {
        return CalibrationCompatibility::Uncalibrated {
            reason: format!(
                "replay_calibration_version {} != {}",
                ctx.replay_calibration_version, REPLAY_SEMANTICS_VERSION
            ),
        };
    }
    let Some(observed) = &ctx.observed_build else {
        return CalibrationCompatibility::Uncalibrated {
            reason: "observed CS2 build identity missing".into(),
        };
    };
    if observed != &ctx.expected_build {
        return CalibrationCompatibility::BuildMismatch {
            code: "REPLAY_CALIBRATION_BUILD_MISMATCH",
        };
    }
    CalibrationCompatibility::Compatible
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EvidenceLineage {
    pub evidence_lineage_version: String,
    pub match_id: String,
    pub frame_id: String,
    pub frame_sha256: String,
    pub requested_demo_tick: u64,
    pub replay_calibration_version: String,
    pub cs2_build_identity: String,
    pub capture_manifest_id: Option<String>,
    pub parser_event_id: Option<String>,
    pub round_id: Option<u32>,
    pub player_identity_id: Option<String>,
    pub controller_session_id: Option<String>,
    pub pawn_life_id: Option<String>,
    /// False when build/calibration guard fails.
    pub calibrated: bool,
}

impl EvidenceLineage {
    pub fn from_capture(
        match_id: impl Into<String>,
        frame_id: impl Into<String>,
        frame_sha256: impl Into<String>,
        requested_demo_tick: u64,
        compat: &CalibrationCompatibility,
        build: &Cs2BuildIdentity,
        capture_manifest_id: Option<String>,
    ) -> Result<Self, String> {
        if requested_demo_tick == 0 {
            return Err("DemoTick 0 nudge is forbidden".into());
        }
        let calibrated = matches!(compat, CalibrationCompatibility::Compatible);
        if let CalibrationCompatibility::BuildMismatch { code } = compat {
            return Err(code.to_string());
        }
        Ok(Self {
            evidence_lineage_version: EVIDENCE_LINEAGE_VERSION.to_string(),
            match_id: match_id.into(),
            frame_id: frame_id.into(),
            frame_sha256: frame_sha256.into(),
            requested_demo_tick,
            replay_calibration_version: REPLAY_SEMANTICS_VERSION.to_string(),
            cs2_build_identity: build.as_compact(),
            capture_manifest_id,
            parser_event_id: None,
            round_id: None,
            player_identity_id: None,
            controller_session_id: None,
            pawn_life_id: None,
            calibrated,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CaptureSemanticResult {
    CorrectEventWindow,
    Early,
    Late,
    WrongRound,
    NotVisuallyObservable,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matching_build_is_compatible() {
        let ctx = CaptureCalibrationContext {
            replay_calibration_version: REPLAY_SEMANTICS_VERSION.to_string(),
            expected_build: calibrated_build_identity(),
            observed_build: Some(calibrated_build_identity()),
        };
        assert_eq!(
            check_calibration_compatibility(&ctx),
            CalibrationCompatibility::Compatible
        );
    }

    #[test]
    fn mismatched_build_returns_typed_error_code() {
        let mut observed = calibrated_build_identity();
        observed.client_version = "9999999".into();
        let ctx = CaptureCalibrationContext {
            replay_calibration_version: REPLAY_SEMANTICS_VERSION.to_string(),
            expected_build: calibrated_build_identity(),
            observed_build: Some(observed),
        };
        match check_calibration_compatibility(&ctx) {
            CalibrationCompatibility::BuildMismatch { code } => {
                assert_eq!(code, "REPLAY_CALIBRATION_BUILD_MISMATCH");
            }
            other => panic!("unexpected {other:?}"),
        }
        let err = EvidenceLineage::from_capture(
            "m",
            "f",
            "h",
            4354,
            &check_calibration_compatibility(&ctx),
            &calibrated_build_identity(),
            None,
        )
        .unwrap_err();
        assert_eq!(err, "REPLAY_CALIBRATION_BUILD_MISMATCH");
    }

    #[test]
    fn lineage_rejects_tick_zero() {
        let compat = CalibrationCompatibility::Compatible;
        assert!(EvidenceLineage::from_capture(
            "m",
            "f",
            "h",
            0,
            &compat,
            &calibrated_build_identity(),
            None,
        )
        .is_err());
    }

    #[test]
    fn versions_are_stable() {
        assert_eq!(EVIDENCE_LINEAGE_VERSION, "p0.6a-2026-10-10");
        assert_eq!(IDENTITY_SEMANTICS_VERSION, "p0.6a-2026-10-10");
    }
}
