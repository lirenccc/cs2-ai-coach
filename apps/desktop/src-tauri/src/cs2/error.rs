//! Typed CS2 / NetCon / staging errors with stable codes.

use serde::Serialize;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Cs2Error {
    pub code: &'static str,
    pub message: String,
    pub remediation: Option<&'static str>,
}

impl Cs2Error {
    pub fn new(
        code: &'static str,
        message: impl Into<String>,
        remediation: Option<&'static str>,
    ) -> Self {
        Self {
            code,
            message: message.into(),
            remediation,
        }
    }

    pub fn cs2_not_installed() -> Self {
        Self::new(
            "CS2_NOT_INSTALLED",
            "Counter-Strike 2 executable was not found",
            Some("Install CS2 via Steam (appid 730) and retry"),
        )
    }

    pub fn steam_not_found() -> Self {
        Self::new(
            "STEAM_NOT_FOUND",
            "Steam executable was not found",
            Some("Install Steam or set CS2_COACH_STEAM_EXE to steam.exe"),
        )
    }

    pub fn already_running_without_netcon() -> Self {
        Self::new(
            "CS2_ALREADY_RUNNING_WITHOUT_NETCON",
            "CS2 is already running without the required NetCon configuration",
            Some("Close CS2, then relaunch from the coach so -netconport can be applied"),
        )
    }

    pub fn tools_unavailable(detail: impl Into<String>) -> Self {
        Self::new(
            "CS2_TOOLS_UNAVAILABLE",
            detail,
            Some(
                "Launch CS2 from Steam without -tools to play normally. For NetCon on Windows, restore Workshop Tools modules (assetsystem.dll next to cs2.exe) or reinstall CS2 / Workshop Tools, then retry",
            ),
        )
    }

    pub fn launch_failed(detail: impl Into<String>) -> Self {
        Self::new(
            "CS2_LAUNCH_FAILED",
            detail,
            Some("Verify Steam/CS2 install paths and try again"),
        )
    }

    pub fn start_timeout() -> Self {
        Self::new(
            "CS2_START_TIMEOUT",
            "CS2 did not accept a NetCon connection in time",
            Some("Confirm CS2 reached the main menu, then retry"),
        )
    }

    pub fn connection_lost(detail: impl Into<String>) -> Self {
        Self::new(
            "NETCON_CONNECTION_LOST",
            detail,
            Some("Reconnect or relaunch CS2 with NetCon enabled"),
        )
    }

    pub fn invalid_transition(from: &str, to: &str) -> Self {
        Self::new(
            "REPLAY_INVALID_TRANSITION",
            format!("illegal replay session transition {from} -> {to}"),
            Some("Reset the replay session and start again"),
        )
    }

    pub fn reconnect_exhausted() -> Self {
        Self::new(
            "NETCON_RECONNECT_EXHAUSTED",
            "NetCon reconnect attempts were exhausted",
            Some("Relaunch CS2 with a fresh NetCon session"),
        )
    }
}

impl fmt::Display for Cs2Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for Cs2Error {}
