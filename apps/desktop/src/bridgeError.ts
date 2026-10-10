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
    case "MATCH_NOT_FOUND":
      return "Import the demo first, then open review with the returned match_id.";
    case "MATCH_NOT_PARSED":
      return "Re-import the demo; review requires a completed parse.";
    case "INCIDENT_NOT_FOUND":
      return "Refresh Match Review; the incident may no longer exist in the deterministic result.";
    case "REPLAY_SOURCE_MISSING":
      return "Re-import the original Demo file, then retry View in CS2.";
    case "REPLAY_CALIBRATION_BUILD_MISMATCH":
      return "CS2 build does not match calibrated DemoTick semantics; recalibrate or use the verified build.";
    case "CS2_ALREADY_RUNNING_WITHOUT_NETCON":
      return "Close CS2, then relaunch from the coach so -netconport can be applied.";
    case "CS2_TOOLS_UNAVAILABLE":
      return "Restore Workshop Tools (assetsystem.dll) or launch CS2 from Steam without -tools for normal play.";
    case "CS2_NOT_INSTALLED":
    case "STEAM_NOT_FOUND":
      return "Install Steam/CS2 (appid 730), then retry.";
    case "NETCON_CONNECTION_LOST":
    case "NETCON_NOT_CONNECTED":
      return "Reconnect or relaunch CS2 with a coach-managed NetCon session.";
    case "REPLAY_ACTION_SUPERSEDED":
      return "Only the latest View in CS2 request is applied.";
    case "SIDECAR_MALFORMED_RESPONSE":
      return "Restart the app; if it persists, file a bug with the analyzer version.";
    default:
      return undefined;
  }
}
