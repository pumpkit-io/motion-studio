import type { Size } from "./timeline";

/**
 * Geometry of footage in a device frame, after the Pumpkit launch video: 1600x900 footage sits
 * at 1:1 under a 44 px browser bar on a 1920x1080 canvas, and other sizes scale into that room.
 */

const REFERENCE_WIDTH = 1920;
const ROOM = { width: 1600, height: 900 };
const BAR = 44;
// The entrance starts this much smaller and tilted, then springs flat.
const ENTER_SCALE = 0.86;
const ENTER_TILT_X = 18;
const ENTER_TILT_Y = -12;

export type FrameLayout = {
  /** Output pixels per footage pixel at rest. */
  scale: number;
  /** The footage's box inside the frame, in output pixels. */
  content: Size;
  /** Height of the frame's title bar, in output pixels. */
  bar: number;
};

export function frameLayout(footage: Size, canvas: Size): FrameLayout {
  const unit = canvas.width / REFERENCE_WIDTH;
  const scale = Math.min((ROOM.width * unit) / footage.width, (ROOM.height * unit) / footage.height);
  return {
    scale,
    content: { width: footage.width * scale, height: footage.height * scale },
    bar: BAR * unit,
  };
}

/** Where the camera looks, in footage pixels, and how far it is zoomed in. */
export type Camera = { cx: number; cy: number; zoom: number };

/** The camera at rest: the whole frame, title bar included, centred on the canvas. */
export function restCamera(layout: FrameLayout): Camera {
  const { content, scale, bar } = layout;
  return { cx: content.width / scale / 2, cy: (content.height - bar) / scale / 2, zoom: 1 };
}

export type FrameTransform = {
  /** The canvas point the camera's target lands on. */
  pivotX: number;
  pivotY: number;
  /** The frame point, from its top-left corner, that sits on the pivot. */
  originX: number;
  originY: number;
  scale: number;
  rotateX: number;
  rotateY: number;
  /** The frame's top-left corner on the canvas, ignoring the tilt. */
  x: number;
  y: number;
};

/** `enter` runs from 0 to 1 over the entrance spring. */
export function frameTransform(
  layout: FrameLayout,
  canvas: Size,
  { enter, camera = restCamera(layout) }: { enter: number; camera?: Camera },
): FrameTransform {
  const scale = camera.zoom * (ENTER_SCALE + (1 - ENTER_SCALE) * enter);
  const originX = camera.cx * layout.scale;
  const originY = layout.bar + camera.cy * layout.scale;
  const pivotX = canvas.width / 2;
  const pivotY = canvas.height / 2;
  return {
    pivotX,
    pivotY,
    originX,
    originY,
    scale,
    rotateX: (1 - enter) * ENTER_TILT_X,
    rotateY: (1 - enter) * ENTER_TILT_Y,
    x: pivotX - originX * scale,
    y: pivotY - originY * scale,
  };
}

export function cssTransform(t: FrameTransform): string {
  return (
    `translate(${t.pivotX}px, ${t.pivotY}px) rotateX(${t.rotateX}deg) rotateY(${t.rotateY}deg) ` +
    `scale(${t.scale}) translate(${-t.originX}px, ${-t.originY}px)`
  );
}

/** OffthreadVideo props that play a footage scene from its in-point. */
export function footagePlayback(scene: { src_in_s: number; rate: number }, fps: number) {
  return { trimBefore: Math.round(scene.src_in_s * fps), playbackRate: scene.rate };
}
