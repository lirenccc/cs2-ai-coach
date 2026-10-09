import type { BridgeError } from "./types";

export function asBridgeError(error: unknown): BridgeError {
  if (
    error &&
    typeof error === "object" &&
    "code" in error &&
    "message" in error &&
    typeof (error as BridgeError).code === "string" &&
    typeof (error as BridgeError).message === "string"
  ) {
    const value = error as BridgeError;
    return {
      code: value.code,
      message: value.message,
      retryable: Boolean(value.retryable),
    };
  }
  return {
    code: "SIDECAR_REQUEST_FAILED",
    message: String(error),
    retryable: true,
  };
}

export function formatBridgeError(error: BridgeError): string {
  const remediation = remediationFor(error.code);
  return remediation
    ? `${error.code}: ${error.message} — ${remediation}`
    : `${error.code}: ${error.message}`;
}

function remediationFor(code: string): string | undefined {
  switch (code) {
    case "SIDECAR_CRASHED":
      return "Restart the app; if it keeps failing, check analyzer logs.";
    case "SIDECAR_START_TIMEOUT":
      return "Confirm Python/.venv is installed, then restart.";
    case "SIDECAR_SPAWN_FAILED":
      return "Run scripts/bootstrap.ps1 or set CS2_COACH_ANALYZER_BIN.";
    case "SIDECAR_UNAVAILABLE":
    case "SIDECAR_NOT_READY":
      return "Wait for the sidecar to finish starting, then refresh.";
    case "SIDECAR_REQUEST_TIMEOUT":
      return "Retry; the analyzer may be busy.";
    default:
      return undefined;
  }
}
