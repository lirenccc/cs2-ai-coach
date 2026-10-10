/** Click-to-CS2 UI state helpers (no tick arithmetic). */

import type { IncidentReplayUiPhase, ViewIncidentInCs2Result } from "@cs2-ai-coach/contracts";

export type ReplayUiState =
  | { phase: "Idle" }
  | { phase: "Preparing" | "LaunchingCS2" | "Connecting" | "LoadingDemo" | "Seeking"; requestId: number; incidentId: string }
  | { phase: "Playing"; requestId: number; incidentId: string; result: ViewIncidentInCs2Result }
  | { phase: "Failed"; requestId: number; incidentId: string; code: string; message: string };

export function beginReplayRequest(
  previousRequestId: number,
  incidentId: string,
): { requestId: number; state: ReplayUiState } {
  const requestId = previousRequestId + 1;
  return {
    requestId,
    state: { phase: "Preparing", requestId, incidentId },
  };
}

/** Late results for superseded requests must not overwrite newer UI state. */
export function shouldApplyReplayResult(
  current: ReplayUiState,
  requestId: number,
): boolean {
  if (current.phase === "Idle") return false;
  return current.requestId === requestId;
}

export function applyReplaySuccess(
  current: ReplayUiState,
  requestId: number,
  result: ViewIncidentInCs2Result,
): ReplayUiState {
  if (!shouldApplyReplayResult(current, requestId)) return current;
  return {
    phase: "Playing",
    requestId,
    incidentId: result.incident_id,
    result,
  };
}

export function applyReplayFailure(
  current: ReplayUiState,
  requestId: number,
  incidentId: string,
  code: string,
  message: string,
): ReplayUiState {
  if (!shouldApplyReplayResult(current, requestId)) return current;
  return { phase: "Failed", requestId, incidentId, code, message };
}

export function phaseLabel(phase: IncidentReplayUiPhase | ReplayUiState["phase"]): string {
  switch (phase) {
    case "Idle":
      return "Idle";
    case "Preparing":
      return "Preparing replay plan…";
    case "LaunchingCS2":
      return "Launching CS2…";
    case "Connecting":
      return "Connecting NetCon…";
    case "LoadingDemo":
      return "Loading Demo…";
    case "Seeking":
      return "Seeking incident…";
    case "Playing":
      return "Playing in CS2";
    case "Failed":
      return "Replay failed";
    default:
      return String(phase);
  }
}
