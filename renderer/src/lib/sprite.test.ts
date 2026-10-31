import { describe, expect, it } from "vitest";
import { spriteFrameAt, spriteSheetStyle } from "./sprite";

// The first frames of the Pumpkit mascot's wave: a long hold, then quick steps.
const wave = [{ ms: 600 }, { ms: 80 }, { ms: 160 }];

describe("spriteFrameAt", () => {
  it("holds each frame for its own duration", () => {
    expect(spriteFrameAt(wave, 0, 0)).toBe(0);
    expect(spriteFrameAt(wave, 0, 599)).toBe(0);
    expect(spriteFrameAt(wave, 0, 600)).toBe(1);
    expect(spriteFrameAt(wave, 0, 679)).toBe(1);
    expect(spriteFrameAt(wave, 0, 680)).toBe(2);
  });

  it("loops forever when loops is 0", () => {
    expect(spriteFrameAt(wave, 0, 840)).toBe(0);
    expect(spriteFrameAt(wave, 0, 840 * 5 + 700)).toBe(2);
  });

  it("holds the last frame after playing loops times", () => {
    expect(spriteFrameAt(wave, 2, 840 + 650)).toBe(1);
    expect(spriteFrameAt(wave, 2, 840 * 2)).toBe(2);
    expect(spriteFrameAt(wave, 2, 99_999)).toBe(2);
  });

  it("shows the first frame before the sprite starts", () => {
    expect(spriteFrameAt(wave, 0, -300)).toBe(0);
  });
});

describe("spriteSheetStyle", () => {
  const sheet = { sheet_width: 8160, sheet_height: 832, frame_width: 544, frame_height: 416 };

  it("scales the sheet so one frame fills the box, offset to the frame", () => {
    const style = spriteSheetStyle(sheet, { x: 1088, y: 416 }, 208);
    expect(style.width).toBe(272);
    expect(style.height).toBe(208);
    expect(style.backgroundSize).toBe("4080px 416px");
    expect(style.backgroundPosition).toBe("-544px -208px");
  });

  it("draws the sheet without smoothing", () => {
    expect(spriteSheetStyle(sheet, { x: 0, y: 0 }, 416).imageRendering).toBe("pixelated");
  });
});
