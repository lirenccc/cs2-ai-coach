//! Explicit replay tick domains.
//!
//! P0.2 proved `demo_tick` and `server_tick` differ on the private fixture.
//! Public replay APIs must never accept a naked integer whose clock is unknown.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
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

/// Engine `demo_gototick` domain belief for the current spike.
///
/// UNVERIFIED until P0.5A calibration against a real CS2 build + private fixture.
/// Callers must not treat this as proven seek semantics.
pub const GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED: ReplayTickDomain = ReplayTickDomain::DemoTick;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn domains_are_distinct() {
        assert_ne!(ReplayTick::demo(1), ReplayTick::server(1));
        assert_eq!(
            GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED,
            ReplayTickDomain::DemoTick
        );
    }
}
