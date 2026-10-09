//! Replay session state machine + thin adapter over process/NetCon/staging.

use crate::cs2::error::Cs2Error;
use crate::cs2::netcon::{NetConClient, NetConResponse};
use crate::cs2::process::{Cs2ProcessManager, LaunchPlan};
use crate::cs2::replay::ReplayCommand;
use crate::cs2::staging::{DemoStagingService, StagedDemo};
use crate::cs2::tick::ReplayTick;
use serde::Serialize;
use std::path::{Path, PathBuf};
use std::time::Duration;

pub const MAX_RECONNECT_ATTEMPTS: u32 = 3;
const CONNECT_TIMEOUT: Duration = Duration::from_secs(3);
const COMMAND_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ReplaySessionState {
    NotRunning,
    Launching,
    ProcessReady,
    Connecting,
    Connected,
    DemoLoading,
    DemoReady,
    ConnectionLost,
    Failed,
}

impl ReplaySessionState {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::NotRunning => "NotRunning",
            Self::Launching => "Launching",
            Self::ProcessReady => "ProcessReady",
            Self::Connecting => "Connecting",
            Self::Connected => "Connected",
            Self::DemoLoading => "DemoLoading",
            Self::DemoReady => "DemoReady",
            Self::ConnectionLost => "ConnectionLost",
            Self::Failed => "Failed",
        }
    }

    fn can_transition(self, next: Self) -> bool {
        use ReplaySessionState::*;
        matches!(
            (self, next),
            (NotRunning, Launching)
                | (Launching, ProcessReady)
                | (Launching, Failed)
                | (ProcessReady, Connecting)
                | (ProcessReady, Failed)
                | (Connecting, Connected)
                | (Connecting, ConnectionLost)
                | (Connecting, Failed)
                | (Connected, DemoLoading)
                | (Connected, ConnectionLost)
                | (Connected, Failed)
                | (DemoLoading, DemoReady)
                | (DemoLoading, ConnectionLost)
                | (DemoLoading, Failed)
                | (DemoReady, DemoLoading)
                | (DemoReady, ConnectionLost)
                | (DemoReady, Failed)
                | (ConnectionLost, Connecting)
                | (ConnectionLost, Failed)
                | (ConnectionLost, NotRunning)
                | (Failed, NotRunning)
                | (DemoReady, NotRunning)
                | (Connected, NotRunning)
                | (ProcessReady, NotRunning)
                | (Launching, NotRunning)
                | (NotRunning, NotRunning)
        )
    }
}

pub struct ReplaySession {
    state: ReplaySessionState,
    process: Cs2ProcessManager,
    staging: DemoStagingService,
    client: Option<NetConClient>,
    launch_plan: Option<LaunchPlan>,
    reconnect_attempts: u32,
    last_error: Option<Cs2Error>,
    staged: Option<StagedDemo>,
}

impl ReplaySession {
    pub fn new(staging_root: impl Into<PathBuf>) -> Self {
        Self {
            state: ReplaySessionState::NotRunning,
            process: Cs2ProcessManager::new(),
            staging: DemoStagingService::new(staging_root),
            client: None,
            launch_plan: None,
            reconnect_attempts: 0,
            last_error: None,
            staged: None,
        }
    }

    pub fn state(&self) -> ReplaySessionState {
        self.state
    }

    pub fn last_error(&self) -> Option<&Cs2Error> {
        self.last_error.as_ref()
    }

    pub fn netcon_port(&self) -> Option<u16> {
        self.launch_plan.as_ref().map(|p| p.netcon_port)
    }

    fn transition(&mut self, next: ReplaySessionState) -> Result<(), Cs2Error> {
        if !self.state.can_transition(next) {
            let err = Cs2Error::invalid_transition(self.state.as_str(), next.as_str());
            self.last_error = Some(err.clone());
            return Err(err);
        }
        self.state = next;
        Ok(())
    }

    pub fn start_launch(&mut self) -> Result<u16, Cs2Error> {
        self.transition(ReplaySessionState::Launching)?;

        // Reuse an already-open coach NetCon if CS2 is running with a live port.
        if let Some(port) = self.process.detect_running_netcon_port() {
            let password = random_hex_password();
            let plan = self
                .process
                .build_launch_plan(port, Some(password))
                .map_err(|e| {
                    self.fail(e.clone());
                    e
                })?;
            self.launch_plan = Some(plan);
            self.transition(ReplaySessionState::ProcessReady)?;
            return Ok(port);
        }

        let port = Cs2ProcessManager::allocate_netcon_port().map_err(|e| {
            self.fail(e.clone());
            e
        })?;
        // Generate a password for documentation/probe only; not passed unless env opt-in.
        let password = random_hex_password();
        let plan = self
            .process
            .build_launch_plan(port, Some(password))
            .map_err(|e| {
                self.fail(e.clone());
                e
            })?;
        self.process.launch_cs2(&plan).map_err(|e| {
            self.fail(e.clone());
            e
        })?;
        self.launch_plan = Some(plan);
        self.process
            .wait_for_cs2_ready(port, None)
            .map_err(|e| {
                self.fail(e.clone());
                e
            })?;
        self.transition(ReplaySessionState::ProcessReady)?;
        Ok(port)
    }

    pub fn connect(&mut self) -> Result<(), Cs2Error> {
        let port = self
            .launch_plan
            .as_ref()
            .map(|p| p.netcon_port)
            .ok_or_else(|| {
                let e = Cs2Error::new(
                    "NETCON_NO_SESSION",
                    "no NetCon launch plan; start_launch first",
                    Some("Launch CS2 with a coach-managed NetCon session"),
                );
                self.last_error = Some(e.clone());
                e
            })?;
        if self.state == ReplaySessionState::ProcessReady
            || self.state == ReplaySessionState::ConnectionLost
        {
            self.transition(ReplaySessionState::Connecting)?;
        } else if self.state != ReplaySessionState::Connecting {
            let e = Cs2Error::invalid_transition(self.state.as_str(), "Connecting");
            self.last_error = Some(e.clone());
            return Err(e);
        }

        let password = self
            .launch_plan
            .as_ref()
            .and_then(|plan| plan.netcon_password.as_deref())
            .filter(|_| {
                std::env::var("CS2_COACH_ATTEMPT_NETCON_PASSWORD")
                    .ok()
                    .as_deref()
                    == Some("1")
            });
        match NetConClient::connect_loopback_with_password(port, CONNECT_TIMEOUT, password) {
            Ok(client) => {
                self.client = Some(client);
                self.reconnect_attempts = 0;
                self.transition(ReplaySessionState::Connected)
            }
            Err(e) => {
                self.client = None;
                let _ = self.transition(ReplaySessionState::ConnectionLost);
                self.last_error = Some(e.clone());
                Err(e)
            }
        }
    }

    pub fn reconnect(&mut self) -> Result<(), Cs2Error> {
        if self.reconnect_attempts >= MAX_RECONNECT_ATTEMPTS {
            let e = Cs2Error::reconnect_exhausted();
            self.fail(e.clone());
            return Err(e);
        }
        self.reconnect_attempts += 1;
        if self.state != ReplaySessionState::ConnectionLost {
            self.transition(ReplaySessionState::ConnectionLost)?;
        }
        // Drop existing client before reconnect.
        if let Some(mut client) = self.client.take() {
            client.disconnect();
        }
        // Engine may leave CLOSE_WAIT briefly; bounded backoff, no infinite loop.
        let mut last_err = None;
        for delay_ms in [0u64, 200, 500] {
            if delay_ms > 0 {
                std::thread::sleep(Duration::from_millis(delay_ms));
            }
            match self.connect() {
                Ok(()) => return Ok(()),
                Err(e) => {
                    last_err = Some(e);
                    // connect() already moved state to ConnectionLost on failure.
                }
            }
        }
        Err(last_err.unwrap_or_else(Cs2Error::reconnect_exhausted))
    }

    pub fn send_command(&mut self, command: &ReplayCommand) -> Result<NetConResponse, Cs2Error> {
        self.ensure_connected()?;
        let client = self.client.as_mut().expect("connected");
        match client.command(command, COMMAND_TIMEOUT) {
            Ok(resp) => Ok(resp),
            Err(e) => {
                self.mark_connection_lost(e.clone());
                Err(e)
            }
        }
    }

    pub fn stage_and_play_demo(
        &mut self,
        source: impl AsRef<Path>,
    ) -> Result<(StagedDemo, NetConResponse), Cs2Error> {
        let staged = self.staging.stage(source.as_ref())?;
        if let Ok(paths) = self.process.resolve_install_paths() {
            let _ = self.staging.publish_to_csgo(&staged, &paths.csgo_dir);
        }
        self.transition(ReplaySessionState::DemoLoading)?;
        let cmd = ReplayCommand::play_staged_demo(&staged.staged_name).map_err(|msg| {
            let e = Cs2Error::new("REPLAY_COMMAND_INVALID", msg, None);
            self.fail(e.clone());
            e
        })?;
        let resp = self.send_command(&cmd)?;
        self.staged = Some(staged.clone());
        self.transition(ReplaySessionState::DemoReady)?;
        Ok((staged, resp))
    }

    pub fn pause(&mut self) -> Result<NetConResponse, Cs2Error> {
        self.send_command(&ReplayCommand::Pause)
    }

    pub fn resume(&mut self) -> Result<NetConResponse, Cs2Error> {
        self.send_command(&ReplayCommand::Resume)
    }

    pub fn timescale(&mut self, value: f32) -> Result<NetConResponse, Cs2Error> {
        let cmd = ReplayCommand::timescale(value).map_err(|msg| {
            Cs2Error::new("REPLAY_COMMAND_INVALID", msg, None)
        })?;
        self.send_command(&cmd)
    }

    pub fn demo_info(&mut self) -> Result<NetConResponse, Cs2Error> {
        self.send_command(&ReplayCommand::DemoInfo)
    }

    pub fn go_to_tick(&mut self, tick: ReplayTick) -> Result<NetConResponse, Cs2Error> {
        let cmd = ReplayCommand::go_to_tick(tick).map_err(|msg| {
            Cs2Error::new("REPLAY_COMMAND_INVALID", msg, None)
        })?;
        self.send_command(&cmd)
    }

    /// Calibration-only seek: either raw clock candidate, no production domain gate.
    pub fn go_to_tick_calibration_candidate(
        &mut self,
        tick: ReplayTick,
    ) -> Result<NetConResponse, Cs2Error> {
        let cmd = ReplayCommand::go_to_tick_calibration_candidate(tick);
        self.send_command(&cmd)
    }

    /// Calibration seek with extended drain so intermittent engine skip lines are kept.
    pub fn go_to_tick_calibration_candidate_drained(
        &mut self,
        tick: ReplayTick,
    ) -> Result<NetConResponse, Cs2Error> {
        self.ensure_connected()?;
        let cmd = ReplayCommand::go_to_tick_calibration_candidate(tick);
        let client = self.client.as_mut().expect("connected");
        match client.command_then_drain(
            &cmd,
            Duration::from_millis(800),
            Duration::from_millis(400),
            Duration::from_secs(8),
        ) {
            Ok(resp) => Ok(resp),
            Err(e) => {
                self.mark_connection_lost(e.clone());
                Err(e)
            }
        }
    }

    /// Calibration-only `demo_pauseatservertick` experiment.
    pub fn pause_at_server_tick_calibration(
        &mut self,
        server_tick: u64,
    ) -> Result<NetConResponse, Cs2Error> {
        let cmd = ReplayCommand::pause_at_server_tick_calibration(server_tick);
        self.send_command(&cmd)
    }

    pub fn poll_health(&mut self) -> Result<(), Cs2Error> {
        if matches!(
            self.state,
            ReplaySessionState::Connected
                | ReplaySessionState::DemoLoading
                | ReplaySessionState::DemoReady
        ) {
            if !self.process.is_cs2_process_alive() {
                let e = Cs2Error::connection_lost("CS2 process exited");
                self.mark_connection_lost(e.clone());
                return Err(e);
            }
        }
        Ok(())
    }

    pub fn disconnect(&mut self) {
        if let Some(mut client) = self.client.take() {
            client.disconnect();
        }
        if self.state.can_transition(ReplaySessionState::ConnectionLost) {
            self.state = ReplaySessionState::ConnectionLost;
        }
    }

    pub fn close(&mut self) {
        self.disconnect();
        self.launch_plan = None;
        self.reconnect_attempts = 0;
        self.staged = None;
        self.state = ReplaySessionState::NotRunning;
    }

    fn ensure_connected(&mut self) -> Result<(), Cs2Error> {
        if matches!(
            self.state,
            ReplaySessionState::Connected
                | ReplaySessionState::DemoLoading
                | ReplaySessionState::DemoReady
        ) && self.client.is_some()
        {
            return Ok(());
        }
        let e = Cs2Error::new(
            "NETCON_NOT_CONNECTED",
            "NetCon session is not connected",
            Some("Connect before issuing replay commands"),
        );
        self.last_error = Some(e.clone());
        Err(e)
    }

    fn mark_connection_lost(&mut self, err: Cs2Error) {
        self.client = None;
        self.last_error = Some(err);
        if self.state.can_transition(ReplaySessionState::ConnectionLost) {
            self.state = ReplaySessionState::ConnectionLost;
        }
    }

    fn fail(&mut self, err: Cs2Error) {
        self.last_error = Some(err);
        if self.state.can_transition(ReplaySessionState::Failed) {
            self.state = ReplaySessionState::Failed;
        } else {
            self.state = ReplaySessionState::Failed;
        }
    }
}

/// Desktop-owned session holder. Renderer never receives raw console access.
pub struct ReplaySessionManager {
    inner: Option<ReplaySession>,
    staging_root: PathBuf,
}

impl ReplaySessionManager {
    pub fn new(staging_root: impl Into<PathBuf>) -> Self {
        Self {
            inner: None,
            staging_root: staging_root.into(),
        }
    }

    pub fn session_mut(&mut self) -> &mut ReplaySession {
        if self.inner.is_none() {
            self.inner = Some(ReplaySession::new(&self.staging_root));
        }
        self.inner.as_mut().expect("session")
    }

    pub fn close(&mut self) {
        if let Some(session) = self.inner.as_mut() {
            session.close();
        }
        self.inner = None;
    }
}

fn random_hex_password() -> String {
    use rand::RngCore;
    let mut bytes = [0u8; 16];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_illegal_transitions() {
        let mut session = ReplaySession::new(std::env::temp_dir().join("cs2coach-session-test"));
        assert_eq!(session.state(), ReplaySessionState::NotRunning);
        let err = session
            .transition(ReplaySessionState::Connected)
            .unwrap_err();
        assert_eq!(err.code, "REPLAY_INVALID_TRANSITION");
    }

    #[test]
    fn reconnect_is_bounded() {
        let mut session = ReplaySession::new(std::env::temp_dir().join("cs2coach-session-re"));
        session.state = ReplaySessionState::ConnectionLost;
        session.launch_plan = Some(LaunchPlan {
            program: PathBuf::from("steam.exe"),
            args: vec![
                "-applaunch".into(),
                "730".into(),
                "-netconport".into(),
                "1".into(),
            ],
            netcon_port: 1,
            netcon_password: None,
            uses_tools: false,
        });
        session.reconnect_attempts = MAX_RECONNECT_ATTEMPTS;
        let err = session.reconnect().unwrap_err();
        assert_eq!(err.code, "NETCON_RECONNECT_EXHAUSTED");
    }

    #[test]
    fn close_resets_to_not_running() {
        let mut session = ReplaySession::new(std::env::temp_dir().join("cs2coach-session-close"));
        session.state = ReplaySessionState::DemoReady;
        session.close();
        assert_eq!(session.state(), ReplaySessionState::NotRunning);
        assert!(session.client.is_none());
    }
}
