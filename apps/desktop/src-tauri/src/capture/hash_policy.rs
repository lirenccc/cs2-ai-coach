//! Paused-frame hash semantics (P0.6A).
//!
//! Identical hashes while replay is paused are allowed stable frames.
//! Identical hashes while replay is expected to advance may indicate staleness.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DuplicateHashVerdict {
    /// Not a duplicate.
    Unique,
    /// Same hash + paused → allowed.
    AllowedStableWhilePaused,
    /// Same hash + advancing expected → possible stale capture.
    PossibleStaleWhileAdvancing,
}

/// Interpret an exact content-hash duplicate under replay state.
///
/// This does **not** reject paused duplicates. Quality validity for black/white
/// frames remains separate in [`crate::capture::quality`].
pub fn interpret_duplicate_hash(
    exact_duplicate: bool,
    replay_paused: bool,
    replay_expected_to_advance: bool,
) -> DuplicateHashVerdict {
    if !exact_duplicate {
        return DuplicateHashVerdict::Unique;
    }
    if replay_paused && !replay_expected_to_advance {
        return DuplicateHashVerdict::AllowedStableWhilePaused;
    }
    if replay_expected_to_advance {
        return DuplicateHashVerdict::PossibleStaleWhileAdvancing;
    }
    // Paused flag false but not explicitly advancing — treat as possible stale.
    DuplicateHashVerdict::PossibleStaleWhileAdvancing
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn paused_identical_hashes_are_allowed() {
        assert_eq!(
            interpret_duplicate_hash(true, true, false),
            DuplicateHashVerdict::AllowedStableWhilePaused
        );
    }

    #[test]
    fn advancing_identical_hashes_are_stale_candidates() {
        assert_eq!(
            interpret_duplicate_hash(true, false, true),
            DuplicateHashVerdict::PossibleStaleWhileAdvancing
        );
    }

    #[test]
    fn unique_hash_is_unique() {
        assert_eq!(
            interpret_duplicate_hash(false, true, false),
            DuplicateHashVerdict::Unique
        );
    }
}
