import type { CSSProperties } from "react";

/** The frame showing `elapsedMs` after the sprite starts; `loops` of 0 plays forever. */
export function spriteFrameAt(frames: readonly { ms: number }[], loops: number, elapsedMs: number): number {
  const total = frames.reduce((sum, f) => sum + f.ms, 0);
  if (elapsedMs <= 0 || total <= 0) return 0;
  if (loops > 0 && elapsedMs >= total * loops) return frames.length - 1;
  let t = elapsedMs % total;
  for (let i = 0; i < frames.length; i++) {
    t -= frames[i]!.ms;
    if (t < 0) return i;
  }
  return frames.length - 1;
}

export type SheetSize = { sheet_width: number; sheet_height: number; frame_width: number; frame_height: number };

/** A box `height` tall showing one frame of the sheet as its background, unsmoothed. */
export function spriteSheetStyle(sheet: SheetSize, frame: { x: number; y: number }, height: number) {
  const scale = height / sheet.frame_height;
  return {
    width: sheet.frame_width * scale,
    height,
    backgroundSize: `${sheet.sheet_width * scale}px ${sheet.sheet_height * scale}px`,
    backgroundPosition: `${-frame.x * scale}px ${-frame.y * scale}px`,
    backgroundRepeat: "no-repeat",
    imageRendering: "pixelated",
  } satisfies CSSProperties;
}
