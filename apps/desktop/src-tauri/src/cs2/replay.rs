use crate::cs2::tick::{
    production_goto_tick_domain, production_goto_tick_is_calibrated, ReplaySeekPosition, ReplayTick,
};

#[derive(Debug, Clone, PartialEq)]
pub enum ReplayCommand {
    Pause,
    Resume,
    TogglePause,
    /// Serializes to `demo_gototick <value>`.
    ///
    /// Production builder [`ReplayCommand::go_to_tick`] accepts only the
    /// calibrated domain ([`crate::cs2::tick::GOTO_TICK_DOMAIN_CALIBRATED`] =
    /// DemoTick for the P0.5A-tested build). Never translates clocks.
    GoToTick(ReplayTick),
    Timescale(f32),
    DemoInfo,
    PlayStagedDemo(String),
    /// Calibration-only experiment. Not a production seek dependency.
    PauseAtServerTick(u64),
}

impl ReplayCommand {
    pub fn timescale(value: f32) -> Result<Self, String> {
        if !value.is_finite() || !(0.1..=4.0).contains(&value) {
            return Err("timescale must be finite and between 0.1 and 4.0".into());
        }
        Ok(Self::Timescale(value))
    }

    pub fn play_staged_demo(name: impl Into<String>) -> Result<Self, String> {
        let name = name.into();
        validate_staged_demo_name(&name)?;
        Ok(Self::PlayStagedDemo(name))
    }

    /// Production seek builder. Rejects domain mismatch with the calibrated
    /// (or UNVERIFIED belief) engine domain. Never translates clocks.
    pub fn go_to_tick(tick: ReplayTick) -> Result<Self, String> {
        let accepted = production_goto_tick_domain();
        if tick.domain != accepted {
            let status = if production_goto_tick_is_calibrated() {
                "calibrated"
            } else {
                "UNVERIFIED belief; see P0.5A"
            };
            return Err(format!(
                "GoToTick accepts only {:?} ({status}); got {:?}",
                accepted, tick.domain
            ));
        }
        Ok(Self::GoToTick(tick))
    }

    pub fn go_to_seek_position(pos: ReplaySeekPosition) -> Result<Self, String> {
        Self::go_to_tick(pos.to_replay_tick())
    }

    /// Calibration-only: emit `demo_gototick` for either raw candidate domain.
    /// Production callers must use [`Self::go_to_tick`].
    pub fn go_to_tick_calibration_candidate(tick: ReplayTick) -> Self {
        Self::GoToTick(tick)
    }

    pub fn pause_at_server_tick_calibration(server_tick: u64) -> Self {
        Self::PauseAtServerTick(server_tick)
    }

    pub fn to_console_line(&self) -> String {
        match self {
            Self::Pause => "demo_pause".to_string(),
            Self::Resume => "demo_resume".to_string(),
            Self::TogglePause => "demo_togglepause".to_string(),
            Self::GoToTick(tick) => format!("demo_gototick {}", tick.value),
            Self::Timescale(value) => format!("demo_timescale {value:.3}"),
            Self::DemoInfo => "demo_info".to_string(),
            Self::PlayStagedDemo(name) => format!("playdemo {name}"),
            Self::PauseAtServerTick(tick) => format!("demo_pauseatservertick {tick}"),
        }
    }
}

fn validate_staged_demo_name(name: &str) -> Result<(), String> {
    if name.is_empty() || name.len() > 128 {
        return Err("invalid staged demo name length".into());
    }
    if !name.ends_with(".dem") {
        return Err("staged demo must end in .dem".into());
    }
    if name.contains("..") || name.contains('/') || name.contains('\\') {
        return Err("path separators and parent components are forbidden".into());
    }
    if !name
        .bytes()
        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
    {
        return Err("staged demo name contains unsafe characters".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_demo_name_builds_command() {
        let cmd = ReplayCommand::play_staged_demo("abc123_match.dem").unwrap();
        assert_eq!(cmd.to_console_line(), "playdemo abc123_match.dem");
    }

    #[test]
    fn console_metacharacters_are_rejected() {
        for name in [
            "x;quit.dem",
            "x\".dem",
            "../x.dem",
            "a b.dem",
            "回放.dem",
            "x\nquit.dem",
            "dir/x.dem",
            "dir\\x.dem",
        ] {
            assert!(ReplayCommand::play_staged_demo(name).is_err(), "{name}");
        }
    }

    #[test]
    fn go_to_tick_requires_calibrated_demo_domain() {
        use crate::cs2::tick::ReplayTickDomain;
        let accepted = production_goto_tick_domain();
        assert_eq!(accepted, ReplayTickDomain::DemoTick);
        assert!(production_goto_tick_is_calibrated());
        let cmd = ReplayCommand::go_to_tick(ReplayTick::demo(3779)).unwrap();
        assert_eq!(cmd.to_console_line(), "demo_gototick 3779");
        assert!(ReplayCommand::go_to_tick(ReplayTick::server(3779)).is_err());
        // Naked u64 is not part of the public builder surface — only ReplayTick /
        // ReplaySeekPosition. Calibration may still emit either candidate:
        let cand = ReplayCommand::go_to_tick_calibration_candidate(ReplayTick::server(999));
        assert_eq!(cand.to_console_line(), "demo_gototick 999");
    }

    #[test]
    fn seek_position_api_rejects_other_domain() {
        assert!(ReplayCommand::go_to_seek_position(ReplaySeekPosition::ServerTick(1)).is_err());
        assert!(ReplayCommand::go_to_seek_position(ReplaySeekPosition::DemoTick(1)).is_ok());
    }

    #[test]
    fn pause_at_server_tick_serializes() {
        let cmd = ReplayCommand::pause_at_server_tick_calibration(46073);
        assert_eq!(cmd.to_console_line(), "demo_pauseatservertick 46073");
    }

    #[test]
    fn timescale_is_bounded() {
        assert!(ReplayCommand::timescale(0.09).is_err());
        assert!(ReplayCommand::timescale(4.01).is_err());
        assert!(ReplayCommand::timescale(f32::NAN).is_err());
        assert!(ReplayCommand::timescale(1.0).is_ok());
    }

    #[test]
    fn demo_info_and_toggle_serialize() {
        assert_eq!(ReplayCommand::DemoInfo.to_console_line(), "demo_info");
        assert_eq!(
            ReplayCommand::TogglePause.to_console_line(),
            "demo_togglepause"
        );
    }

    #[test]
    fn domains_enum_still_distinct() {
        use crate::cs2::tick::ReplayTickDomain;
        assert_ne!(ReplayTickDomain::DemoTick, ReplayTickDomain::ServerTick);
    }
}
