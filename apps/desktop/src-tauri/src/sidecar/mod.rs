//! Loopback client for the analyzer sidecar.
//! The renderer never sees the session token; Tauri attaches it here.

use reqwest::header::{HeaderMap, HeaderValue};
use serde::{Deserialize, Serialize};
use std::env;
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParserHealth {
    pub name: String,
    pub available: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalyzerHealth {
    pub status: String,
    pub version: String,
    pub database: String,
    pub parser: ParserHealth,
}

#[derive(thiserror::Error, Debug)]
pub enum AnalyzerError {
    #[error("invalid analyzer configuration: {0}")]
    Config(String),
    #[error("analyzer request failed: {0}")]
    Request(String),
}

pub async fn health() -> Result<AnalyzerHealth, AnalyzerError> {
    let host = env::var("CS2_COACH_ANALYZER_HOST").unwrap_or_else(|_| "127.0.0.1".into());
    if host != "127.0.0.1" && host != "localhost" {
        return Err(AnalyzerError::Config(
            "analyzer host must be loopback".into(),
        ));
    }

    let port = env::var("CS2_COACH_ANALYZER_PORT").unwrap_or_else(|_| "8765".into());
    let token = env::var("CS2_COACH_SESSION_TOKEN")
        .map_err(|_| AnalyzerError::Config("CS2_COACH_SESSION_TOKEN is missing".into()))?;

    let mut headers = HeaderMap::new();
    headers.insert(
        "x-cs2-coach-token",
        HeaderValue::from_str(&token)
            .map_err(|_| AnalyzerError::Config("invalid session token".into()))?,
    );

    let client = reqwest::Client::builder()
        .default_headers(headers)
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| AnalyzerError::Request(e.to_string()))?;

    let url = format!("http://{host}:{port}/v1/health");
    let response = client
        .get(url)
        .send()
        .await
        .map_err(|e| AnalyzerError::Request(e.to_string()))?
        .error_for_status()
        .map_err(|e| AnalyzerError::Request(e.to_string()))?;

    response
        .json::<AnalyzerHealth>()
        .await
        .map_err(|e| AnalyzerError::Request(e.to_string()))
}
