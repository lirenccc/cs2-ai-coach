import { describe, expect, it } from "vitest";
import { analyzerPill } from "./status";

describe("analyzer status pill", () => {
  it("treats only an ok health payload as ready", () => {
    expect(analyzerPill("ready", "ok")).toEqual({ ok: true, text: "OK" });
    expect(analyzerPill("ready", "degraded")).toEqual({
      ok: false,
      text: "DEGRADED",
    });
    expect(analyzerPill("error", undefined)).toEqual({
      ok: false,
      text: "ERROR",
    });
    expect(analyzerPill("loading", undefined)).toEqual({
      ok: false,
      text: "LOADING",
    });
  });
});
