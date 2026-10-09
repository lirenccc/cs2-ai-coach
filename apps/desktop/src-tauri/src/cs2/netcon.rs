use crate::cs2::error::Cs2Error;
use crate::cs2::replay::ReplayCommand;
use std::io::{self, Read, Write};
use std::net::{Shutdown, SocketAddr, TcpStream};
use std::time::{Duration, Instant};

const DEFAULT_IDLE_SLICE: Duration = Duration::from_millis(50);
const MAX_RESPONSE_BYTES: usize = 256 * 1024;

/// Loopback-only NetCon TCP client. Host is never taken from the renderer.
pub struct NetConClient {
    stream: TcpStream,
    port: u16,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetConResponse {
    /// Raw bytes decoded lossily as UTF-8 for logging/fixtures (never log passwords).
    pub raw_text: String,
    pub timed_out_idle: bool,
}

impl NetConClient {
    pub fn connect_loopback(port: u16, timeout: Duration) -> Result<Self, Cs2Error> {
        Self::connect_loopback_with_password(port, timeout, None)
    }

    pub fn connect_loopback_with_password(
        port: u16,
        timeout: Duration,
        password: Option<&str>,
    ) -> Result<Self, Cs2Error> {
        let address = loopback_addr(port);
        let stream = TcpStream::connect_timeout(&address, timeout).map_err(|e| {
            Cs2Error::new(
                "NETCON_CONNECT_FAILED",
                format!("failed to connect to loopback NetCon: {e}"),
                Some("Ensure CS2 was launched with -netconport (and -tools on Windows)"),
            )
        })?;
        stream.set_write_timeout(Some(timeout)).map_err(io_to_err)?;
        stream.set_read_timeout(Some(timeout)).map_err(io_to_err)?;
        stream.set_nodelay(true).ok();
        let mut client = Self { stream, port };
        if let Some(password) = password {
            // Engine banner: "Must send PASS command". Do not log the password.
            let mut line = String::from("PASS ");
            line.push_str(password);
            line.push('\n');
            client
                .stream
                .write_all(line.as_bytes())
                .map_err(|e| map_io_lost(e, "failed to write NetCon PASS"))?;
            client
                .stream
                .flush()
                .map_err(|e| map_io_lost(e, "failed to flush NetCon PASS"))?;
            let _ = client.read_until_idle(Duration::from_millis(150), timeout);
        }
        Ok(client)
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    pub fn send(&mut self, command: &ReplayCommand) -> Result<(), Cs2Error> {
        let mut line = command.to_console_line();
        line.push('\n');
        self.stream
            .write_all(line.as_bytes())
            .map_err(|e| map_io_lost(e, "failed to write NetCon command"))?;
        self.stream
            .flush()
            .map_err(|e| map_io_lost(e, "failed to flush NetCon command"))
    }

    /// Read console output until the idle gap elapses or `overall` timeout hits.
    pub fn read_until_idle(
        &mut self,
        idle: Duration,
        overall: Duration,
    ) -> Result<NetConResponse, Cs2Error> {
        let deadline = Instant::now() + overall;
        let mut buf = Vec::new();
        let mut chunk = [0u8; 4096];
        let mut last_data = Instant::now();
        let mut saw_data = false;

        loop {
            if Instant::now() >= deadline {
                return Ok(NetConResponse {
                    raw_text: String::from_utf8_lossy(&buf).into_owned(),
                    timed_out_idle: true,
                });
            }
            if saw_data && last_data.elapsed() >= idle {
                return Ok(NetConResponse {
                    raw_text: String::from_utf8_lossy(&buf).into_owned(),
                    timed_out_idle: false,
                });
            }

            let remaining = deadline.saturating_duration_since(Instant::now());
            let slice = remaining.min(DEFAULT_IDLE_SLICE).max(Duration::from_millis(1));
            self.stream
                .set_read_timeout(Some(slice))
                .map_err(io_to_err)?;

            match self.stream.read(&mut chunk) {
                Ok(0) => {
                    if saw_data || !buf.is_empty() {
                        return Ok(NetConResponse {
                            raw_text: String::from_utf8_lossy(&buf).into_owned(),
                            timed_out_idle: false,
                        });
                    }
                    return Err(Cs2Error::connection_lost(
                        "NetCon peer closed the TCP connection",
                    ));
                }
                Ok(n) => {
                    if buf.len() + n > MAX_RESPONSE_BYTES {
                        buf.extend_from_slice(&chunk[..n.min(MAX_RESPONSE_BYTES - buf.len())]);
                        return Ok(NetConResponse {
                            raw_text: String::from_utf8_lossy(&buf).into_owned(),
                            timed_out_idle: false,
                        });
                    }
                    buf.extend_from_slice(&chunk[..n]);
                    saw_data = true;
                    last_data = Instant::now();
                }
                Err(e) if is_timeout(&e) => {
                    if !saw_data && Instant::now() >= deadline {
                        return Ok(NetConResponse {
                            raw_text: String::new(),
                            timed_out_idle: true,
                        });
                    }
                    if saw_data && last_data.elapsed() >= idle {
                        return Ok(NetConResponse {
                            raw_text: String::from_utf8_lossy(&buf).into_owned(),
                            timed_out_idle: false,
                        });
                    }
                }
                Err(e) => return Err(map_io_lost(e, "failed to read NetCon output")),
            }
        }
    }

    pub fn command(
        &mut self,
        command: &ReplayCommand,
        timeout: Duration,
    ) -> Result<NetConResponse, Cs2Error> {
        self.send(command)?;
        self.read_until_idle(Duration::from_millis(200), timeout)
    }

    /// Calibration helper: send, wait for engine work, then drain with a longer idle.
    /// Used to capture intermittent `Demo Skipping:` lines after `demo_gototick`.
    pub fn command_then_drain(
        &mut self,
        command: &ReplayCommand,
        work: Duration,
        idle: Duration,
        overall: Duration,
    ) -> Result<NetConResponse, Cs2Error> {
        self.send(command)?;
        std::thread::sleep(work);
        self.read_until_idle(idle, overall)
    }

    pub fn disconnect(&mut self) {
        // Prefer a write-side shutdown first so the engine can finish draining.
        let _ = self.stream.shutdown(Shutdown::Write);
        let _ = self.stream.shutdown(Shutdown::Both);
    }

    pub fn reconnect(port: u16, timeout: Duration) -> Result<Self, Cs2Error> {
        Self::connect_loopback(port, timeout)
    }
}

impl Drop for NetConClient {
    fn drop(&mut self) {
        self.disconnect();
    }
}

pub fn loopback_addr(port: u16) -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], port))
}

pub fn assert_loopback_only(host: &str) -> Result<(), Cs2Error> {
    if matches!(host, "127.0.0.1" | "localhost" | "::1") {
        Ok(())
    } else {
        Err(Cs2Error::new(
            "NETCON_HOST_FORBIDDEN",
            format!("NetCon host must be loopback; refusing {host}"),
            Some("Use the desktop-managed NetCon session only"),
        ))
    }
}

fn io_to_err(e: io::Error) -> Cs2Error {
    Cs2Error::new("NETCON_IO", e.to_string(), None)
}

fn map_io_lost(e: io::Error, context: &str) -> Cs2Error {
    if matches!(
        e.kind(),
        io::ErrorKind::ConnectionReset
            | io::ErrorKind::ConnectionAborted
            | io::ErrorKind::BrokenPipe
            | io::ErrorKind::UnexpectedEof
            | io::ErrorKind::NotConnected
    ) {
        Cs2Error::connection_lost(format!("{context}: {e}"))
    } else {
        Cs2Error::new("NETCON_IO", format!("{context}: {e}"), None)
    }
}

fn is_timeout(e: &io::Error) -> bool {
    e.kind() == io::ErrorKind::WouldBlock
        || e.kind() == io::ErrorKind::TimedOut
        || e.raw_os_error() == Some(10060) // WSAETIMEDOUT
        || e.raw_os_error() == Some(10035) // WSAEWOULDBLOCK
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn loopback_guard_rejects_lan() {
        assert!(assert_loopback_only("127.0.0.1").is_ok());
        assert!(assert_loopback_only("10.0.0.5").is_err());
        assert!(assert_loopback_only("example.com").is_err());
    }

    #[test]
    fn connect_send_and_read_roundtrip() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut sock, _) = listener.accept().unwrap();
            let mut buf = [0u8; 64];
            let n = sock.read(&mut buf).unwrap();
            assert_eq!(&buf[..n], b"demo_pause\n");
            sock.write_all(b"ok pause\n").unwrap();
        });

        let mut client =
            NetConClient::connect_loopback(port, Duration::from_secs(2)).expect("connect");
        let resp = client
            .command(&ReplayCommand::Pause, Duration::from_secs(2))
            .expect("command");
        assert!(resp.raw_text.contains("ok pause"));
        client.disconnect();
        server.join().unwrap();
    }

    #[test]
    fn connection_lost_on_peer_close() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        thread::spawn(move || {
            let (sock, _) = listener.accept().unwrap();
            drop(sock);
        });
        let mut client =
            NetConClient::connect_loopback(port, Duration::from_secs(2)).expect("connect");
        let err = client
            .read_until_idle(Duration::from_millis(50), Duration::from_secs(1))
            .expect_err("peer close");
        assert_eq!(err.code, "NETCON_CONNECTION_LOST");
    }
}
