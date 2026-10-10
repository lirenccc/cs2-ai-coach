import { describe, expect, it } from "vitest";
import { APP_NAME, APP_PHASE, bootstrapBanner } from "./bootstrap";

describe("desktop bootstrap", () => {
  it("exposes product identity for the shell", () => {
    expect(APP_NAME).toBe("CS2 AI Coach");
    expect(APP_PHASE).toBe("P1.4");
    expect(bootstrapBanner()).toBe("CS2 AI Coach (P1.4)");
  });
});
