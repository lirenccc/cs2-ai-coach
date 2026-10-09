//! Explicit replay tick domains.
//!
//! P0.2 proved `demo_tick` and `server_tick` differ on the private fixture.
//! Public replay APIs must never accept a naked integer whose clock is unknown.
//!
//! P0.5A calibrates which domain `demo_gototick` consumes for a specific CS2
//! build + fixture. See `docs/spikes/replay/P0_5A_TICK_CALIBRATION.md` and
//! [`crate::cs2::calibration::REPLAY_SEMANTICS_VERSION`].

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReplayTickDomain {
    DemoTick,
    ServerTick,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReplayTick {
    pub value: u64,
    pub domain: ReplayTickDomain,
}

impl ReplayTick {
    pub fn demo(value: u64) -> Self {
        Self {
            value,
            domain: ReplayTickDomain::DemoTick,
        }
    }

    pub fn server(value: u64) -> Self {
        Self {
            value,
            domain: ReplayTickDomain::ServerTick,
        }
    }
}

/// Production seek position for `demo_gototick` after P0.5A calibration.
///
/// Variants encode the domain explicitly — there is no `seek(u64)`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "domain", content = "value", rename_all = "snake_case")]
pub enum ReplaySeekPosition {
    DemoTick(u64),
    ServerTick(u64),
}

impl ReplaySeekPosition {
    pub fn to_replay_tick(self) -> ReplayTick {
        match self {
            Self::DemoTick(v) => ReplayTick::demo(v),
            Self::ServerTick(v) => ReplayTick::server(v),
        }
    }
}

/// Calibrated engine domain for `demo_gototick`.
///
/// Evidence: `docs/spikes/replay/P0_5A_TICK_CALIBRATION.md` and
/// `docs/spikes/replay/fixtures/tick_calibration.redacted.json`
/// (CS2 PatchVersion 1.41.9.0 / ClientVersion 2000930 / buildid 25815307,
/// fixture SHA-256 d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec).
/// Engine lines: `Demo Skipping: skipping to demo tick <N> (game tick <M>)`.
/// Invalidate / re-run when CS2 build or fixture semantics change
/// ([`crate::cs2::calibration::REPLAY_SEMANTICS_VERSION`]).
pub const GOTO_TICK_DOMAIN_CALIBRATED: Option<ReplayTickDomain> =
    Some(ReplayTickDomain::DemoTick);

/// Historical UNVERIFIED belief (pre-P0.5A). Prefer [`GOTO_TICK_DOMAIN_CALIBRATED`].
pub const GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED: ReplayTickDomain = ReplayTickDomain::DemoTick;

/// Domain accepted by the production `ReplayCommand::go_to_tick` builder.
pub fn production_goto_tick_domain() -> ReplayTickDomain {
    GOTO_TICK_DOMAIN_CALIBRATED.unwrap_or(GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED)
}

pub fn production_goto_tick_is_calibrated() -> bool {
    GOTO_TICK_DOMAIN_CALIBRATED.is_some()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn domains_are_distinct() {
        assert_ne!(ReplayTick::demo(1), ReplayTick::server(1));
        assert_ne!(
            ReplaySeekPosition::DemoTick(1),
            ReplaySeekPosition::ServerTick(1)
        );
    }

    #[test]
    fn seek_position_preserves_domain() {
        let demo = ReplaySeekPosition::DemoTick(42).to_replay_tick();
        assert_eq!(demo.domain, ReplayTickDomain::DemoTick);
        assert_eq!(demo.value, 42);
        let server = ReplaySeekPosition::ServerTick(99).to_replay_tick();
        assert_eq!(server.domain, ReplayTickDomain::ServerTick);
    }

    #[test]
    fn calibrated_constant_is_demo_tick() {
        assert_eq!(
            GOTO_TICK_DOMAIN_CALIBRATED,
            Some(ReplayTickDomain::DemoTick)
        );
        assert!(production_goto_tick_is_calibrated());
        assert_eq!(production_goto_tick_domain(), ReplayTickDomain::DemoTick);
    }
}
