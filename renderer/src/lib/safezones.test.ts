import { describe, expect, it } from "vitest";
import { logoBox, logoHidden } from "./safezones";
import type { FormatSpec, TimelineEvent } from "./timeline";

const reels: FormatSpec = {
  name: "9x16",
  width: 1080,
  height: 1920,
  safe_zone: { top: 0.1, right: 0.12, bottom: 0.2, left: 0.05 },
};

const x: FormatSpec = {
  name: "16x9",
  width: 1920,
  height: 1080,
  safe_zone: { top: 0.05, right: 0.05, bottom: 0.1, left: 0.05 },
};

describe("logoBox", () => {
  it("puts the logo inside the top-right corner of the safe area, 7% of the short side tall", () => {
    const box = logoBox(reels);
    expect(box.height).toBeCloseTo(75.6);
    expect(box.top).toBeCloseTo(192 + 21.6);
    expect(box.right).toBeCloseTo(129.6 + 21.6);
  });

  it("scales with the short side in landscape", () => {
    const box = logoBox(x);
    expect(box.height).toBeCloseTo(75.6);
    expect(box.top).toBeCloseTo(54 + 21.6);
    expect(box.right).toBeCloseTo(96 + 21.6);
  });
});

describe("logoHidden", () => {
  const events: TimelineEvent[] = [
    { type: "title", text: "Hello", start: 10, end: 40 },
    { type: "zoom", start: 50, end: 60, scale: 1.2, ease: "snap" },
  ];

  it("hides the logo while a title card is on screen, where the two would collide", () => {
    expect(logoHidden(events, 9)).toBe(false);
    expect(logoHidden(events, 10)).toBe(true);
    expect(logoHidden(events, 39)).toBe(true);
    expect(logoHidden(events, 40)).toBe(false);
    expect(logoHidden(events, 55)).toBe(false);
  });
});
