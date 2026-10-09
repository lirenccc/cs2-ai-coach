/** Desktop bootstrap helpers — no CS2 / analyzer wiring in P0.1. */

export const APP_NAME = "CS2 AI Coach";
export const APP_PHASE = "P0.1";

export function bootstrapBanner(): string {
  return `${APP_NAME} (${APP_PHASE})`;
}
