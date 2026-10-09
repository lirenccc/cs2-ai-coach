import { invoke } from "@tauri-apps/api/core";
import type { AnalyzerHealth, DesktopHealth } from "./types";

export async function getDesktopHealth(): Promise<DesktopHealth> {
  return invoke<DesktopHealth>("desktop_health");
}

export async function getAnalyzerHealth(): Promise<AnalyzerHealth> {
  return invoke<AnalyzerHealth>("analyzer_health");
}
