//! CS2 process, NetCon, staging, and typed replay adapters.
//!
//! Safety: no DLL injection, no process-memory game APIs, no binary patching,
//! no renderer-facing raw console.

#![allow(dead_code)] // Adapter surface is exercised by unit/integration tests and upcoming UI.

pub mod error;
pub mod netcon;
pub mod process;
pub mod replay;
pub mod session;
pub mod staging;
pub mod tick;

#[cfg(test)]
mod integration;
