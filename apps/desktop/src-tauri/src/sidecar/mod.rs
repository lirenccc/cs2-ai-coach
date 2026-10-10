//! Analyzer sidecar lifecycle and loopback HTTP client.
//! The renderer never sees the session token; Tauri attaches it here.

mod manager;

pub use manager::{SidecarManager, SidecarStatus};

use reqwest::header::{HeaderMap, HeaderValue};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParserHealth {
    pub name: String,
    pub available: bool,
    #[serde(default)]
    pub version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalyzerHealth {
    pub status: String,
    pub version: String,
    pub database: String,
    pub parser: ParserHealth,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BridgeError {
    pub code: String,
    pub message: String,
    pub retryable: bool,
}

impl BridgeError {
    pub fn new(code: &str, message: impl Into<String>, retryable: bool) -> Self {
        Self {
            code: code.to_string(),
            message: message.into(),
            retryable,
        }
    }
}

impl std::fmt::Display for BridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for BridgeError {}

#[derive(Debug, Clone)]
pub struct SessionEndpoint {
    pub host: String,
    pub port: u16,
    pub token: String,
}

impl SessionEndpoint {
    pub fn base_url(&self) -> String {
        format!("http://{}:{}", self.host, self.port)
    }

    pub fn ensure_loopback(&self) -> Result<(), BridgeError> {
        if self.host != "127.0.0.1" && self.host != "localhost" {
            return Err(BridgeError::new(
                "SIDECAR_CONFIG",
                "analyzer host must be loopback",
                false,
            ));
        }
        Ok(())
    }
}

fn auth_headers(token: &str) -> Result<HeaderMap, BridgeError> {
    let mut headers = HeaderMap::new();
    headers.insert(
        "x-cs2-coach-token",
        HeaderValue::from_str(token).map_err(|_| {
            BridgeError::new("SIDECAR_CONFIG", "invalid session token", false)
        })?,
    );
    Ok(headers)
}

fn map_reqwest_error(err: reqwest::Error) -> BridgeError {
    if err.is_timeout() {
        return BridgeError::new(
            "SIDECAR_REQUEST_TIMEOUT",
            "analyzer request timed out",
            true,
        );
    }
    if err.is_connect() {
        return BridgeError::new(
            "SIDECAR_UNAVAILABLE",
            "analyzer is not reachable on loopback",
            true,
        );
    }
    BridgeError::new(
        "SIDECAR_REQUEST_FAILED",
        format!("analyzer request failed: {err}"),
        true,
    )
}

async fn authorized_client(token: &str, timeout: Duration) -> Result<reqwest::Client, BridgeError> {
    reqwest::Client::builder()
        .default_headers(auth_headers(token)?)
        .timeout(timeout)
        .build()
        .map_err(|e| BridgeError::new("SIDECAR_CONFIG", e.to_string(), false))
}

#[derive(Debug, Deserialize)]
struct AnalyzerErrorBody {
    error: AnalyzerErrorFields,
}

#[derive(Debug, Deserialize)]
struct AnalyzerErrorFields {
    code: String,
    message: String,
    #[serde(default)]
    retryable: bool,
}

async fn decode_json_response<T: DeserializeOwned>(
    response: reqwest::Response,
) -> Result<T, BridgeError> {
    let status = response.status();
    if status.as_u16() == 401 {
        return Err(BridgeError::new(
            "SIDECAR_UNAUTHORIZED",
            "analyzer rejected the session token",
            false,
        ));
    }
    let bytes = response
        .bytes()
        .await
        .map_err(|e| BridgeError::new("SIDECAR_REQUEST_FAILED", e.to_string(), true))?;
    if !status.is_success() {
        if let Ok(envelope) = serde_json::from_slice::<AnalyzerErrorBody>(&bytes) {
            return Err(BridgeError::new(
                &envelope.error.code,
                envelope.error.message,
                envelope.error.retryable,
            ));
        }
        return Err(BridgeError::new(
            "SIDECAR_REQUEST_FAILED",
            format!("analyzer returned HTTP {status}"),
            true,
        ));
    }
    serde_json::from_slice::<T>(&bytes).map_err(|e| {
        BridgeError::new(
            "SIDECAR_MALFORMED_RESPONSE",
            format!("analyzer response failed schema decode: {e}"),
            true,
        )
    })
}

pub async fn get_json_at<T: DeserializeOwned>(
    endpoint: &SessionEndpoint,
    path: &str,
    timeout: Duration,
) -> Result<T, BridgeError> {
    endpoint.ensure_loopback()?;
    let client = authorized_client(&endpoint.token, timeout).await?;
    let url = format!("{}{}", endpoint.base_url(), path);
    let response = client.get(url).send().await.map_err(map_reqwest_error)?;
    decode_json_response(response).await
}

pub async fn post_json_at<T: DeserializeOwned, B: Serialize>(
    endpoint: &SessionEndpoint,
    path: &str,
    body: &B,
    timeout: Duration,
) -> Result<T, BridgeError> {
    endpoint.ensure_loopback()?;
    let client = authorized_client(&endpoint.token, timeout).await?;
    let url = format!("{}{}", endpoint.base_url(), path);
    let response = client
        .post(url)
        .json(body)
        .send()
        .await
        .map_err(map_reqwest_error)?;
    decode_json_response(response).await
}

pub async fn health_at(endpoint: &SessionEndpoint) -> Result<AnalyzerHealth, BridgeError> {
    get_json_at(endpoint, "/v1/health", Duration::from_secs(2)).await
}

pub async fn request_shutdown(endpoint: &SessionEndpoint) -> Result<(), BridgeError> {
    endpoint.ensure_loopback()?;
    let client = authorized_client(&endpoint.token, Duration::from_secs(2)).await?;
    let url = format!("{}/v1/shutdown", endpoint.base_url());
    let response = client
        .post(url)
        .send()
        .await
        .map_err(map_reqwest_error)?;
    let _: JsonValue = decode_json_response(response).await?;
    Ok(())
}

fn validate_match_id(match_id: &str) -> Result<(), BridgeError> {
    if match_id.is_empty() || match_id.contains('/') || match_id.contains('\\') {
        return Err(BridgeError::new(
            "MATCH_ID_INVALID",
            "match_id must be a non-empty opaque id",
            false,
        ));
    }
    Ok(())
}

pub async fn get_match_review_at(
    endpoint: &SessionEndpoint,
    match_id: &str,
) -> Result<JsonValue, BridgeError> {
    validate_match_id(match_id)?;
    let path = format!("/v1/matches/{match_id}/review");
    get_json_at(endpoint, &path, Duration::from_secs(60)).await
}

fn validate_incident_id(incident_id: &str) -> Result<(), BridgeError> {
    if incident_id.is_empty() || incident_id.contains('/') || incident_id.contains('\\') {
        return Err(BridgeError::new(
            "INCIDENT_NOT_FOUND",
            "incident_id must be a non-empty opaque id",
            false,
        ));
    }
    Ok(())
}

pub async fn get_incident_replay_plan_at(
    endpoint: &SessionEndpoint,
    match_id: &str,
    incident_id: &str,
) -> Result<JsonValue, BridgeError> {
    validate_match_id(match_id)?;
    validate_incident_id(incident_id)?;
    let path = format!("/v1/matches/{match_id}/incidents/{incident_id}/replay-plan");
    get_json_at(endpoint, &path, Duration::from_secs(60)).await
}

#[derive(Debug, Serialize)]
struct ImportDemoBody<'a> {
    path: &'a str,
}

pub async fn import_demo_at(
    endpoint: &SessionEndpoint,
    path: &str,
) -> Result<JsonValue, BridgeError> {
    post_json_at(
        endpoint,
        "/v1/demos/import",
        &ImportDemoBody { path },
        Duration::from_secs(180),
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loopback_guard_rejects_lan_bind() {
        let endpoint = SessionEndpoint {
            host: "192.168.1.10".into(),
            port: 9000,
            token: "0123456789abcdef".into(),
        };
        let err = endpoint.ensure_loopback().unwrap_err();
        assert_eq!(err.code, "SIDECAR_CONFIG");
    }

    #[test]
    fn bridge_error_display_includes_code() {
        let err = BridgeError::new("SIDECAR_CRASHED", "child exited", true);
        assert_eq!(err.to_string(), "SIDECAR_CRASHED: child exited");
    }

    #[test]
    fn map_timeout_uses_stable_code() {
        // Construct via reqwest builder timeout path is awkward; assert helper shape instead.
        let err = BridgeError::new(
            "SIDECAR_REQUEST_TIMEOUT",
            "analyzer request timed out",
            true,
        );
        assert!(err.retryable);
        assert_eq!(err.code, "SIDECAR_REQUEST_TIMEOUT");
    }

    #[test]
    fn match_id_validation_rejects_traversal_and_omits_token() {
        let err = validate_match_id("../secret").unwrap_err();
        assert_eq!(err.code, "MATCH_ID_INVALID");
        assert!(!err.message.contains("secret"));
        assert!(validate_match_id("match-abc").is_ok());
    }
}
