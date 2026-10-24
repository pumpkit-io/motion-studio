import type { Box } from "./camera";
import type { FormatSpec } from "./timeline";

/** The part of the frame clear of platform UI, in px. */
export function safeBox(format: FormatSpec): Box {
  const { top, right, bottom, left } = format.safe_zone;
  return {
    x: format.width * left,
    y: format.height * top,
    width: format.width * (1 - left - right),
    height: format.height * (1 - top - bottom),
  };
}
