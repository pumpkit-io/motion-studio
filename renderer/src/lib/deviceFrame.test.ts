import { describe, expect, it } from "vitest";
import { cameraAt, footagePlayback, frameLayout, frameTransform, restCamera } from "./deviceFrame";
import type { TimelineFootage } from "./timeline";

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

describe("frameTransform with a camera", () => {
  it("puts the camera's footage point on the canvas centre, scaled by its zoom", () => {
    const layout = frameLayout({ width: 1600, height: 900 }, hd);
    const t = frameTransform(layout, hd, { enter: 1, camera: { cx: 500, cy: 250, zoom: 2 } });
    // Footage (500, 250) is frame (500, 44 + 250); twice that from the corner lands on (960, 540).
    expect(t.scale).toBeCloseTo(2);
    expect(t.x + 500 * 2).toBeCloseTo(960);
    expect(t.y + (44 + 250) * 2).toBeCloseTo(540);
  });
});

type Key = TimelineFootage["camera"][number];

describe("cameraAt", () => {
  const layout = frameLayout({ width: 1600, height: 900 }, hd);
  const rest = restCamera(layout);
  const post: Key = { frame: 30, cx: 500, cy: 250, zoom: 1.8, ease: "smooth" };

  it("rests on the whole frame without moves, and before the first one", () => {
    expect(cameraAt([], 50, layout, 30)).toEqual(rest);
    expect(cameraAt([post], 29, layout, 30)).toEqual(rest);
  });

  it("eases a smooth move from where the camera was over 0.7 s, then holds", () => {
    expect(cameraAt([post], 30, layout, 30)).toEqual(rest);
    // 21 frames at 30 fps; the ease is symmetric, so half-way in time is half-way in space.
    const half = cameraAt([post], 40.5, layout, 30);
    expect(half.cx).toBeCloseTo((rest.cx + 500) / 2);
    expect(half.cy).toBeCloseTo((rest.cy + 250) / 2);
    expect(half.zoom).toBeCloseTo(1.4);
    const early = cameraAt([post], 33, layout, 30);
    expect(early.zoom - 1).toBeLessThan((half.zoom - 1) / 2);
    expect(cameraAt([post], 51, layout, 30)).toEqual({ cx: 500, cy: 250, zoom: 1.8 });
    expect(cameraAt([post], 400, layout, 30)).toEqual({ cx: 500, cy: 250, zoom: 1.8 });
  });

  it("cuts on a snap move", () => {
    const snap: Key = { ...post, ease: "snap" };
    expect(cameraAt([snap], 29, layout, 30)).toEqual(rest);
    expect(cameraAt([snap], 30, layout, 30)).toEqual({ cx: 500, cy: 250, zoom: 1.8 });
  });

  it("starts a move that interrupts another from where the camera is", () => {
    const back: Key = { frame: 40.5, cx: 800, cy: 450, zoom: 1, ease: "snap" };
    const next: Key = { frame: 40.5, cx: 1200, cy: 600, zoom: 1.4, ease: "smooth" };
    const half = cameraAt([post], 40.5, layout, 30);
    expect(cameraAt([post, next], 40.5, layout, 30)).toEqual(half);
    expect(cameraAt([post, back], 40.5, layout, 30)).toEqual(rest);
  });

  it("shows the whole frame, title bar included, on a zoom of 1", () => {
    const full: Key = { frame: 0, cx: 800, cy: 450, zoom: 1, ease: "snap" };
    expect(cameraAt([full], 10, layout, 30)).toEqual(rest);
  });
});

describe("footagePlayback", () => {
  it("starts at the in-point's frame and plays at the scene's rate", () => {
    const playback = footagePlayback({ src_in_s: 1.5, rate: 2 }, 30);
    expect(playback).toEqual({ trimBefore: 45, playbackRate: 2 });
  });
});
