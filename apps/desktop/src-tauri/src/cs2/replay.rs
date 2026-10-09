use crate::cs2::tick::{ReplayTick, GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED};

#[cfg(test)]
use crate::cs2::tick::ReplayTickDomain;

#[derive(Debug, Clone, PartialEq)]
pub enum ReplayCommand {
    Pause,
    Resume,
    TogglePause,
    /// UNVERIFIED: serializes to `demo_gototick <value>` using
    /// [`GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED`]. Do not treat as calibrated.
    GoToTick(ReplayTick),
    Timescale(f32),
    DemoInfo,
    PlayStagedDemo(String),
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

    /// Build a seek command. Rejects naked-domain mismatch with the UNVERIFIED belief.
    /// Never translates between demo/server ticks.
    pub fn go_to_tick(tick: ReplayTick) -> Result<Self, String> {
        if tick.domain != GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED {
            return Err(format!(
                "GoToTick currently accepts only {:?} (UNVERIFIED engine domain; see P0.5A); got {:?}",
                GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED, tick.domain
            ));
        }
        Ok(Self::GoToTick(tick))
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
    fn go_to_tick_requires_unverified_demo_domain() {
        let cmd = ReplayCommand::go_to_tick(ReplayTick::demo(3779)).unwrap();
        assert_eq!(cmd.to_console_line(), "demo_gototick 3779");
        assert!(ReplayCommand::go_to_tick(ReplayTick::server(3779)).is_err());
        assert_eq!(
            GOTO_TICK_DOMAIN_BELIEF_UNVERIFIED,
            ReplayTickDomain::DemoTick
        );
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
}
