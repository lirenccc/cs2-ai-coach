import { invoke } from "@tauri-apps/api/core";
import { asBridgeError } from "./bridgeError";
import type { AnalyzerHealth, DesktopHealth, SidecarStatus } from "./types";

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
