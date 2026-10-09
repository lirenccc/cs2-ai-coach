use crate::cs2::replay::ReplayCommand;
use std::io::{self, Write};
use std::net::{SocketAddr, TcpStream};
use std::time::Duration;

pub struct NetConClient {
    stream: TcpStream,
}

impl NetConClient {
    pub fn connect_loopback(port: u16, timeout: Duration) -> io::Result<Self> {
        let address = SocketAddr::from(([127, 0, 0, 1], port));
        let stream = TcpStream::connect_timeout(&address, timeout)?;
        stream.set_write_timeout(Some(timeout))?;
        stream.set_read_timeout(Some(timeout))?;
        Ok(Self { stream })
    }

    pub fn send(&mut self, command: &ReplayCommand) -> io::Result<()> {
        let mut line = command.to_console_line();
        line.push('\n');
        self.stream.write_all(line.as_bytes())?;
        self.stream.flush()
    }
}
