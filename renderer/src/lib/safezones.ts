import type { Box } from "./camera";
import type { FormatSpec, TimelineEvent } from "./timeline";

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

export type LogoBox = { top: number; right: number; height: number };

const LOGO_HEIGHT = 0.07;
const LOGO_MARGIN = 0.02;

/** Where the brand logo sits: the top-right corner of the safe area, sized by the short side. */
export function logoBox(format: FormatSpec): LogoBox {
  const unit = Math.min(format.width, format.height);
  const margin = unit * LOGO_MARGIN;
  return {
    top: format.height * format.safe_zone.top + margin,
    right: format.width * format.safe_zone.right + margin,
    height: unit * LOGO_HEIGHT,
  };
}

/** Title cards span the top of the safe area, so the logo steps aside while one is shown. */
export function logoHidden(events: TimelineEvent[], frame: number): boolean {
  return events.some((e) => e.type === "title" && frame >= e.start && frame < e.end);
}
