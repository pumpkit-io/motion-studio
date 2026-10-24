import { describe, expect, it } from "vitest";
import type { Run, Timeline, TimelineEvent } from "./timeline";
import { coverTransform, framingAt, layoutFor, scaleAt } from "./camera";

const vertical = { width: 1080, height: 1920 };
const square = { width: 1000, height: 1000 };

describe("coverTransform", () => {
  it("fills a 9x16 frame from a square source, face at x = 0.5 and y = 0.4", () => {
    const t = coverTransform(square, vertical, { cx: 0.5, cy: 0.4 }, 1);
    // Cover scale is 1920 / 1000; the source is 1920 px wide, 840 px of it are cut.
    expect(t.scale).toBeCloseTo(1.92);
    expect(t.x).toBeCloseTo(-420);
    expect(t.y).toBeCloseTo(0);
  });

  it("clamps the pan so a face at the edge never shows an empty strip", () => {
    const right = coverTransform(square, vertical, { cx: 0.98, cy: 0.5 }, 1);
    expect(right.x).toBeCloseTo(1080 - 1920);
    const left = coverTransform(square, vertical, { cx: 0.0, cy: 0.5 }, 1);
    expect(left.x).toBe(0);
  });

  it("pans vertically when zoomed in, placing the face at 40% of the frame height", () => {
    const t = coverTransform(vertical, vertical, { cx: 0.5, cy: 0.5 }, 1.2);
    expect(t.scale).toBeCloseTo(1.2);
    // Face at 0.5 * 1920 * 1.2 = 1152 px of the scaled source must land at 768 px.
    expect(t.y).toBeCloseTo(768 - 1152);
    expect(t.x).toBeCloseTo(540 - 648);
  });

  it("clamps the vertical pan at the top and bottom", () => {
    const top = coverTransform(vertical, vertical, { cx: 0.5, cy: 0.05 }, 1.1);
    expect(top.y).toBe(0);
    const bottom = coverTransform(vertical, vertical, { cx: 0.5, cy: 1 }, 1.1);
    expect(bottom.y).toBeCloseTo(1920 - 1920 * 1.1);
  });

  it("never scales below cover, so a scale under 1 still fills the frame", () => {
    const t = coverTransform(vertical, vertical, { cx: 0.5, cy: 0.5 }, 0.8);
    expect(t.scale).toBe(1);
    expect(t.x).toBe(0);
    expect(t.y).toBe(0);
  });
});

describe("layoutFor", () => {
  it("covers when the source and the format share an orientation", () => {
    expect(layoutFor(vertical, { width: 1080, height: 1350 })).toEqual({
      mode: "cover",
      box: { x: 0, y: 0, width: 1080, height: 1350 },
    });
  });

  it("uses fit-blur for a 16x9 format from a vertical source, the sharp video centred", () => {
    expect(layoutFor(vertical, { width: 1920, height: 1080 })).toEqual({
      mode: "fitBlur",
      box: { x: (1920 - 607.5) / 2, y: 0, width: 607.5, height: 1080 },
    });
  });

  it("covers a 9x16 format from a landscape source", () => {
    expect(layoutFor({ width: 1920, height: 1080 }, vertical).mode).toBe("cover");
  });
});

function run(out_in: number, out_out: number, base_scale = 1, crop = { cx: 0.5, cy: 0.5 }): Run {
  return {
    base_scale,
    clip: "c1",
    crop,
    face: true,
    out_in,
    out_out,
    segment: "s",
    src_in_s: out_in / 30,
    src_out_s: out_out / 30,
  };
}

function timeline(runs: Run[], events: TimelineEvent[] = []): Pick<Timeline, "fps" | "runs" | "events"> {
  return { fps: 30, runs, events };
}

describe("scaleAt", () => {
  it("uses the run's base scale, so the jump-cut punch alternates per run", () => {
    const t = timeline([run(0, 30, 1), run(30, 60, 1.08)]);
    expect(scaleAt(t, 10)).toBe(1);
    expect(scaleAt(t, 30)).toBe(1.08);
    expect(scaleAt(t, 59)).toBe(1.08);
  });

  it("replaces the punch with a snap zoom that settles within 4 frames", () => {
    const t = timeline([run(0, 90, 1.08)], [{ type: "zoom", start: 20, end: 50, scale: 1.2, ease: "snap" }]);
    expect(scaleAt(t, 19)).toBe(1.08);
    expect(scaleAt(t, 20)).toBeCloseTo(1.08, 2);
    expect(scaleAt(t, 24)).toBeCloseTo(1.2, 2);
    expect(scaleAt(t, 40)).toBeCloseTo(1.2, 3);
  });

  it("eases a smooth zoom over 10 frames, halfway at frame 5", () => {
    const t = timeline([run(0, 90)], [{ type: "zoom", start: 20, end: 60, scale: 1.2, ease: "smooth" }]);
    expect(scaleAt(t, 22)).toBeGreaterThan(1);
    expect(scaleAt(t, 22)).toBeLessThan(1.1);
    expect(scaleAt(t, 25)).toBeCloseTo(1.1, 3);
    expect(scaleAt(t, 30)).toBeCloseTo(1.2, 3);
  });

  it("eases back to the base scale after a zoom that ends inside a run", () => {
    const t = timeline([run(0, 90)], [{ type: "zoom", start: 10, end: 40, scale: 1.2, ease: "smooth" }]);
    expect(scaleAt(t, 39)).toBeCloseTo(1.2, 3);
    expect(scaleAt(t, 45)).toBeCloseTo(1.1, 3);
    expect(scaleAt(t, 50)).toBe(1);
  });

  it("drops a zoom at once when it ends on a cut", () => {
    const t = timeline([run(0, 40), run(40, 90, 1.08)], [{ type: "zoom", start: 10, end: 40, scale: 1.2, ease: "smooth" }]);
    expect(scaleAt(t, 40)).toBe(1.08);
  });

  it("multiplies a push-in, linear from 1.0 at its start to its scale at its end", () => {
    const t = timeline([run(0, 100, 1.08)], [{ type: "push", start: 0, end: 100, scale: 1.1 }]);
    expect(scaleAt(t, 0)).toBeCloseTo(1.08);
    expect(scaleAt(t, 50)).toBeCloseTo(1.08 * 1.05);
    expect(scaleAt(t, 100 - 1)).toBeCloseTo(1.08 * (1 + 0.1 * 0.99));
  });

  it("composes a zoom inside a push: the zoom replaces the base, the push multiplies it", () => {
    const t = timeline(
      [run(0, 100, 1.08)],
      [
        { type: "push", start: 0, end: 100, scale: 1.1 },
        { type: "zoom", start: 50, end: 90, scale: 1.2, ease: "snap" },
      ],
    );
    expect(scaleAt(t, 60)).toBeCloseTo(1.2 * 1.06, 3);
  });

  it("ignores overlays when computing the camera scale", () => {
    const t = timeline([run(0, 90)], [{ type: "title", start: 0, end: 90, text: "hi" }]);
    expect(scaleAt(t, 45)).toBe(1);
  });
});

describe("framingAt on one clip", () => {
  it("frames each run on its own face centre, without smoothing across the cut", () => {
    const t = timeline([run(0, 30, 1.2, { cx: 0.2, cy: 0.5 }), run(30, 60, 1.2, { cx: 0.8, cy: 0.5 })]);
    const before = framingAt(t, 29, vertical, {}, vertical).camera;
    const after = framingAt(t, 30, vertical, {}, vertical).camera;
    expect(before.x).toBe(0);
    expect(after.x).toBeCloseTo(1080 - 1080 * 1.2);
  });

  it("holds the last run's framing past the end of the timeline", () => {
    const t = timeline([run(0, 30, 1.08)]);
    expect(framingAt(t, 31, vertical, {}, vertical).camera.scale).toBeCloseTo(1.08);
  });
});

describe("framingAt", () => {
  // A portrait take and a landscape take centred, unscaled, in one square canvas.
  const canvas = { width: 1920, height: 1920 };
  const regions = {
    c1: { x: 420, y: 0, width: 1080, height: 1920 },
    c2: { x: 0, y: 420, width: 1920, height: 1080 },
  };
  const landscape = { width: 1920, height: 1080 };
  const mixed = timeline([
    { ...run(0, 30), clip: "c1" },
    { ...run(30, 60, 1, { cx: 0.5, cy: 0.5 }), clip: "c2" },
  ]);

  /** The canvas rectangle the output frame shows. */
  function shown(t: { scale: number; x: number; y: number }, frame: { width: number; height: number }) {
    return {
      left: -t.x / t.scale,
      top: -t.y / t.scale,
      right: (frame.width - t.x) / t.scale,
      bottom: (frame.height - t.y) / t.scale,
    };
  }

  it("fills a 9x16 frame from the landscape take's own region, never the padding", () => {
    const { camera, layout } = framingAt(mixed, 40, canvas, regions, vertical);
    const r = regions.c2;
    const view = shown(camera, layout.box);
    expect(layout.mode).toBe("cover");
    expect(view.left).toBeGreaterThanOrEqual(r.x - 1e-6);
    expect(view.top).toBeCloseTo(r.y);
    expect(view.right).toBeLessThanOrEqual(r.x + r.width + 1e-6);
    expect(view.bottom).toBeCloseTo(r.y + r.height);
    // The face centre of the landscape take lands in the middle of the frame's width.
    expect(camera.x + (r.x + 0.5 * r.width) * camera.scale).toBeCloseTo(540);
  });

  it("frames the portrait take from its region in the same canvas", () => {
    const { camera, layout } = framingAt(mixed, 10, canvas, regions, vertical);
    const view = shown(camera, layout.box);
    expect(view.left).toBeCloseTo(420);
    expect(view.right).toBeCloseTo(1500);
    expect(camera.scale).toBeCloseTo(1);
  });

  it("chooses the layout per run: fit-blur for the portrait take in 16x9, cover for the landscape one", () => {
    expect(framingAt(mixed, 10, canvas, regions, landscape).layout.mode).toBe("fitBlur");
    expect(framingAt(mixed, 40, canvas, regions, landscape).layout.mode).toBe("cover");
  });

  it("uses the whole canvas for a clip with no region", () => {
    const { region } = framingAt(timeline([run(0, 30)]), 0, vertical, {}, vertical);
    expect(region).toEqual({ x: 0, y: 0, width: 1080, height: 1920 });
  });
});
