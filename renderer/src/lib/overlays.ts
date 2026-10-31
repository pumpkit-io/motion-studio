import { interpolate, spring } from "remotion";
import type { TimelineEvent, TimelineFlash, TimelineHighlight, TimelineMask } from "./timeline";

/** Timing of the scene overlays, after the Pumpkit launch video. */

const HIGHLIGHT_IN_S = 0.1;
const HIGHLIGHT_OUT_S = 0.2;
// A tag hanging off a box that ends past this fraction of the footage's width would run off it.
const LABEL_EDGE = 0.8;

type EventOf<T extends TimelineEvent["type"]> = Extract<TimelineEvent, { type: T }>;

/** One scene's events of one type, in timeline order. */
export function sceneEvents<T extends TimelineEvent["type"]>(
  events: readonly TimelineEvent[],
  scene: string,
  type: T,
): EventOf<T>[] {
  return events.filter((e): e is EventOf<T> => e.type === type && "scene" in e && e.scene === scene);
}

/** `grow` is how much of the box's width is drawn, springing in from its left edge. */
export function highlightAt(h: TimelineHighlight, frame: number, fps: number): { grow: number; opacity: number } {
  if (frame < h.start || frame >= h.end) return { grow: 0, opacity: 0 };
  const length = h.end - h.start;
  // A highlight shorter than its fades shares its frames between them.
  const fadeIn = Math.min(HIGHLIGHT_IN_S * fps, length / 3);
  const fadeOut = Math.min(HIGHLIGHT_OUT_S * fps, length / 3);
  const opacity = interpolate(frame, [h.start, h.start + fadeIn, h.end - fadeOut, h.end], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const grow = spring({ frame: frame - h.start, fps, config: { damping: 15, stiffness: 140 } });
  return { grow, opacity };
}

export function labelOnLeft(h: TimelineHighlight, footageWidth: number): boolean {
  return h.x + h.w > footageWidth * LABEL_EDGE;
}

export function maskShown(m: TimelineMask, frame: number): boolean {
  return frame >= m.start && frame < m.end;
}

export function flashOpacity(f: TimelineFlash, frame: number): number {
  if (frame < f.start || frame >= f.end) return 0;
  return f.strength * (1 - (frame - f.start) / (f.end - f.start));
}
