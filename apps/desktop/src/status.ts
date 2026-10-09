import type { BridgeError } from "./types";

export type StatusKind = "loading" | "ready" | "error";

export function analyzerPill(kind: StatusKind, status: string | undefined): {
  ok: boolean;
  text: string;
} {
  if (kind === "ready") {
    return { ok: status === "ok", text: (status ?? "unknown").toUpperCase() };
  }
  return { ok: false, text: kind.toUpperCase() };
}

export function analyzerErrorText(error: BridgeError): string {
  return `${error.code}: ${error.message}`;
}
