#[derive(Debug, Clone, PartialEq)]
pub enum ReplayCommand {
    Pause,
    Resume,
    SeekTick(u64),
    Timescale(f32),
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

    pub fn to_console_line(&self) -> String {
        match self {
            Self::Pause => "demo_pause".to_string(),
            Self::Resume => "demo_resume".to_string(),
            Self::SeekTick(tick) => format!("demo_gototick {tick}"),
            Self::Timescale(value) => format!("demo_timescale {value:.3}"),
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
    if name.contains("..") {
        return Err("parent path components are forbidden".into());
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
        ] {
            assert!(ReplayCommand::play_staged_demo(name).is_err(), "{name}");
        }
    }

    #[test]
    fn seek_preserves_raw_tick() {
        assert_eq!(
            ReplayCommand::SeekTick(3779).to_console_line(),
            "demo_gototick 3779"
        );
    }

    #[test]
    fn timescale_is_bounded() {
        assert!(ReplayCommand::timescale(0.09).is_err());
        assert!(ReplayCommand::timescale(4.01).is_err());
        assert!(ReplayCommand::timescale(f32::NAN).is_err());
        assert!(ReplayCommand::timescale(1.0).is_ok());
    }
}
