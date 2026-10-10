import { invoke } from "@tauri-apps/api/core";
import type {
  AnalyzerHealth,
  DesktopHealth,
  ImportDemoResponse,
  MatchReview,
  ReplayControlAction,
  SidecarStatus,
  ViewIncidentInCs2Result,
} from "./types";
import { asBridgeError } from "./bridgeError";
import { assertReviewShape } from "./review/model";

export async function getDesktopHealth(): Promise<DesktopHealth> {
  return invoke<DesktopHealth>("desktop_health");
}

export async function getAnalyzerHealth(): Promise<AnalyzerHealth> {
  try {
    return await invoke<AnalyzerHealth>("analyzer_health");
  } catch (error) {
    throw asBridgeError(error);
  }
}

export async function getSidecarStatus(): Promise<SidecarStatus> {
  return invoke<SidecarStatus>("sidecar_status");
}

export async function importDemo(path: string): Promise<ImportDemoResponse> {
  try {
    return await invoke<ImportDemoResponse>("import_demo", { path });
  } catch (error) {
    throw asBridgeError(error);
  }
}

export async function getMatchReview(matchId: string): Promise<MatchReview> {
  try {
    // Tauri v2 IPC expects camelCase keys for snake_case Rust args.
    const raw = await invoke<unknown>("get_match_review", { matchId });
    return assertReviewShape(raw);
  } catch (error) {
    throw asBridgeError(error);
  }
}

/** High-level Click-to-CS2. Renderer sends only match/incident IDs. */
export async function viewIncidentInCs2(
  matchId: string,
  incidentId: string,
): Promise<ViewIncidentInCs2Result> {
  try {
    return await invoke<ViewIncidentInCs2Result>("view_incident_in_cs2", {
      matchId,
      incidentId,
    });
  } catch (error) {
    throw asBridgeError(error);
  }
}

export async function replayControl(action: ReplayControlAction): Promise<void> {
  try {
    await invoke<void>("replay_control", { action });
  } catch (error) {
    throw asBridgeError(error);
  }
}
