import { Easing, interpolate, spring } from "remotion";
import type { Crop, Run, Size, Timeline, TimelineZoom } from "./timeline";

/** Where the face centre lands in the output frame, as fractions of its width and height. */
export const FACE_TARGET = { x: 0.5, y: 0.4 } as const;

const SNAP_FRAMES = 4;
const SMOOTH_FRAMES = 10;

export type Transform = { scale: number; x: number; y: number };

export type Box = { x: number; y: number; width: number; height: number };

export type Layout = { mode: "cover" | "fitBlur"; box: Box };

type CameraTimeline = Pick<Timeline, "fps" | "runs" | "events">;

/**
 * Places a source of `source` size inside `frame`: scale about the top-left corner, then translate.
 * Cover-fits, multiplies by `scale` (never below cover), puts the crop centre at FACE_TARGET and
 * clamps the pan so the source always covers the whole frame.
 */
export function coverTransform(source: Size, frame: Size, crop: Crop, scale: number): Transform {
  const cover = Math.max(frame.width / source.width, frame.height / source.height);
  const k = cover * Math.max(1, scale);
  const pan = (frameLen: number, sourceLen: number, centre: number, target: number) => {
    const ideal = target * frameLen - centre * sourceLen * k;
    return clamp(ideal, frameLen - sourceLen * k, 0);
  };
  return {
    scale: k,
    x: pan(frame.width, source.width, crop.cx, FACE_TARGET.x),
    y: pan(frame.height, source.height, crop.cy, FACE_TARGET.y),
  };
}

/** A vertical source in a landscape format is shown whole over a blurred copy (fit-blur). */
export function layoutFor(source: Size, frame: Size): Layout {
  if (source.height > source.width && frame.width > frame.height) {
    const width = (frame.height * source.width) / source.height;
    return { mode: "fitBlur", box: { x: (frame.width - width) / 2, y: 0, width, height: frame.height } };
  }
  return { mode: "cover", box: { x: 0, y: 0, width: frame.width, height: frame.height } };
}

/** The run showing at `frame`; past the end, the last run. */
export function runAt(runs: readonly Run[], frame: number): Run | undefined {
  return runs.find((r) => frame >= r.out_in && frame < r.out_out) ?? runs[runs.length - 1];
}

/**
 * Camera scale at `frame`: the run's base scale (jump-cut punch), replaced by an active zoom and
 * multiplied by an active push-in.
 */
export function scaleAt(timeline: CameraTimeline, frame: number): number {
  const run = runAt(timeline.runs, frame);
  const base = run?.base_scale ?? 1;
  let scale = base;
  for (const event of timeline.events) {
    if (event.type === "zoom") {
      const p = zoomProgress(timeline, event, frame, run);
      if (p > 0) scale = base + (event.scale - base) * p;
    }
  }
  for (const event of timeline.events) {
    if (event.type === "push" && frame >= event.start && frame < event.end) {
      scale *= 1 + ((event.scale - 1) * (frame - event.start)) / (event.end - event.start);
    }
  }
  return scale;
}

/** How far a zoom has taken over from the base scale at `frame`, 0 to 1. */
function zoomProgress(timeline: CameraTimeline, zoom: TimelineZoom, frame: number, run: Run | undefined): number {
  const frames = zoom.ease === "snap" ? SNAP_FRAMES : SMOOTH_FRAMES;
  const ease = (t: number) =>
    zoom.ease === "snap"
      ? spring({ frame: t, fps: timeline.fps, durationInFrames: frames, config: { damping: 200 } })
      : interpolate(t, [0, frames], [0, 1], { easing: Easing.inOut(Easing.cubic), extrapolateRight: "clamp" });
  if (frame >= zoom.start && frame < zoom.end) return ease(frame - zoom.start);
  // Easing out across a cut would drift the next run's framing, so a zoom ending on a cut stops dead.
  const sameRun = run !== undefined && zoom.end > run.out_in;
  if (frame >= zoom.end && frame < zoom.end + frames && sameRun) return 1 - ease(frame - zoom.end);
  return 0;
}

/** The A-roll transform inside `box` at `frame`: that run's face centre and the camera scale. */
export function cameraAt(timeline: CameraTimeline, frame: number, source: Size, box: Size): Transform {
  const run = runAt(timeline.runs, frame);
  return coverTransform(source, box, run?.crop ?? { cx: 0.5, cy: 0.5 }, scaleAt(timeline, frame));
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
