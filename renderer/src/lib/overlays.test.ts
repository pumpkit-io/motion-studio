import { describe, expect, it } from "vitest";
import { flashOpacity, highlightAt, labelOnLeft, maskShown, sceneEvents } from "./overlays";
import type { TimelineEvent, TimelineFlash, TimelineHighlight, TimelineMask } from "./timeline";

const box = { scene: "demo", clip: "c1", src_start_s: 4, src_end_s: 6, element: null, x: 200, y: 100, w: 600, h: 300 };
const highlight: TimelineHighlight = { ...box, type: "highlight", start: 100, end: 160, label: null };
const mask: TimelineMask = { ...box, type: "mask", start: 100, end: 160, color: null };
const flash: TimelineFlash = { type: "flash", scene: "demo", start: 60, end: 65, strength: 0.35 };

describe("highlightAt", () => {
  it("is hidden outside its frames", () => {
    expect(highlightAt(highlight, 99, 30).opacity).toBe(0);
    expect(highlightAt(highlight, 160, 30).opacity).toBe(0);
  });

  it("draws in from its left edge, then holds fully open", () => {
    const early = highlightAt(highlight, 102, 30);
    expect(early.grow).toBeGreaterThan(0);
    expect(early.grow).toBeLessThan(1);
    const held = highlightAt(highlight, 130, 30);
    expect(held.grow).toBeCloseTo(1, 2);
    expect(held.opacity).toBe(1);
  });

  it("fades out over its last 0.2 s", () => {
    expect(highlightAt(highlight, 154, 30).opacity).toBe(1);
    const fading = highlightAt(highlight, 157, 30).opacity;
    expect(fading).toBeGreaterThan(0);
    expect(fading).toBeLessThan(1);
  });
});

describe("maskShown", () => {
  it("covers exactly its start to its end, exclusive", () => {
    expect([99, 100, 159, 160].map((f) => maskShown(mask, f))).toEqual([false, true, true, false]);
  });
});

describe("flashOpacity", () => {
  it("starts at its strength and fades linearly to nothing at its end", () => {
    expect(flashOpacity(flash, 59)).toBe(0);
    expect(flashOpacity(flash, 60)).toBeCloseTo(0.35);
    expect(flashOpacity(flash, 62)).toBeCloseTo(0.21);
    expect(flashOpacity(flash, 65)).toBe(0);
  });
});

describe("labelOnLeft", () => {
  it("hangs the tag off the box's right end unless that runs off the footage", () => {
    expect(labelOnLeft(highlight, 1600)).toBe(false);
    expect(labelOnLeft({ ...highlight, x: 1000 }, 1600)).toBe(true);
  });
});

describe("sceneEvents", () => {
  it("keeps one scene's events of the given types", () => {
    const events: TimelineEvent[] = [highlight, mask, flash, { ...mask, scene: "other" }];
    expect(sceneEvents(events, "demo", "mask")).toEqual([mask]);
    expect(sceneEvents(events, "demo", "highlight")).toEqual([highlight]);
  });
});
