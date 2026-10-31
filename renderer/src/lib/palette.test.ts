import { describe, expect, it } from "vitest";
import { paletteOf, withAlpha } from "./palette";

describe("paletteOf", () => {
  it("puts light text on a dark brand colour and keeps the accent", () => {
    const p = paletteOf({ primary: "#141413", accent: "#D96B45", logo: "", wordmark: null, mascot: null });
    expect(p.background).toBe("#141413");
    expect(p.accent).toBe("#D96B45");
    expect(p.text).toBe("#FFFFFF");
  });

  it("puts dark text on a light brand colour", () => {
    expect(paletteOf({ primary: "#F7F5EF", accent: "#D96B45", logo: "", wordmark: null, mascot: null }).text).toBe("#111111");
  });
});

describe("withAlpha", () => {
  it("writes a #RRGGBB colour as rgba", () => {
    expect(withAlpha("#D96B45", 0.25)).toBe("rgba(217, 107, 69, 0.25)");
  });
});
