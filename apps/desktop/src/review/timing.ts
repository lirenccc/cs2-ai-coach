/** Human-readable DemoTick display. Never assumes a global tick rate. */

export function formatDemoTick(
  demoTick: number,
  tickRate: number | null | undefined,
): string {
  if (tickRate != null && Number.isFinite(tickRate) && tickRate > 0) {
    const seconds = demoTick / tickRate;
    return `tick ${demoTick} (~${seconds.toFixed(1)}s @ ${tickRate} Hz)`;
  }
  return `tick ${demoTick}`;
}
