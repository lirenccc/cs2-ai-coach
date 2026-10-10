/** Presentation labels only — never used as identity keys. */

const RULE_LABELS: Record<string, string> = {
  R001: "Opening Death",
  R002: "Untraded Death",
  R003: "Advantage Loss Candidate",
};

const INCIDENT_TYPE_LABELS: Record<string, string> = {
  OPENING_DEATH: "Opening Death",
  UNTRADED_DEATH: "Untraded Death",
  ADVANTAGE_LOSS_CANDIDATE: "Advantage Loss Candidate",
};

export function ruleLabel(ruleId: string): string {
  return RULE_LABELS[ruleId] ?? ruleId;
}

export function incidentTypeLabel(incidentType: string): string {
  return INCIDENT_TYPE_LABELS[incidentType] ?? incidentType;
}

export function playerDisplayName(
  playerIdentityId: string | null | undefined,
  nameById: Map<string, string | null | undefined>,
): string {
  if (!playerIdentityId) {
    return "Unresolved / unknown";
  }
  const name = nameById.get(playerIdentityId);
  if (name && name.trim()) {
    return name;
  }
  return "Unknown player";
}

export function sideLabel(side: string | null | undefined): string {
  if (side === "ct") return "CT";
  if (side === "t") return "T";
  return "—";
}
