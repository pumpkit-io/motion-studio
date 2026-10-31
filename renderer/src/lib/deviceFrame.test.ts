import { describe, expect, it } from "vitest";
import { footagePlayback, frameLayout, frameTransform } from "./deviceFrame";

const hd = { width: 1920, height: 1080 };

describe("frameLayout", () => {
  it("shows 1600x900 footage at 1:1 in a browser frame on a 1920x1080 canvas", () => {
    const layout = frameLayout({ width: 1600, height: 900 }, hd);
    expect(layout.scale).toBe(1);
    expect(layout.content).toEqual({ width: 1600, height: 900 });
    expect(layout.bar).toBe(44);
  });

  it("scales other footage to the same room, keeping its aspect ratio", () => {
    const small = frameLayout({ width: 800, height: 450 }, hd);
    expect(small.scale).toBe(2);
    const tall = frameLayout({ width: 1200, height: 1200 }, hd);
    expect(tall.scale).toBeCloseTo(0.75);
    expect(tall.content.height).toBeCloseTo(900);
  });

  it("scales the chrome with a canvas other than 1920 wide", () => {
    const layout = frameLayout({ width: 1600, height: 900 }, { width: 960, height: 540 });
    expect(layout.scale).toBe(0.5);
    expect(layout.bar).toBe(22);
  });
});

describe("frameTransform", () => {
  it("centres the whole frame, chrome included, when the camera rests", () => {
    const layout = frameLayout({ width: 1600, height: 900 }, hd);
    const t = frameTransform(layout, hd, { enter: 1 });
    // The frame is 944 px tall, so its top sits at (1080 - 944) / 2 = 68 px.
    expect(t.x).toBeCloseTo(160);
    expect(t.y).toBeCloseTo(68);
    expect(t.scale).toBeCloseTo(1);
    expect(t.rotateX).toBe(0);
  });

  it("starts the entrance tilted and smaller", () => {
    const layout = frameLayout({ width: 1600, height: 900 }, hd);
    const t = frameTransform(layout, hd, { enter: 0 });
    expect(t.scale).toBeCloseTo(0.86);
    expect(t.rotateX).toBeGreaterThan(0);
    expect(t.rotateY).toBeLessThan(0);
  });
});

describe("footagePlayback", () => {
  it("starts at the in-point's frame and plays at the scene's rate", () => {
    const playback = footagePlayback({ src_in_s: 1.5, rate: 2 }, 30);
    expect(playback).toEqual({ trimBefore: 45, playbackRate: 2 });
  });
});
