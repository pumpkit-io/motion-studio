import { readableOn } from "./colour";
import type { TimelineBrand } from "./timeline";

/** The product composition's colours, all from the brand config. */
export type Palette = { background: string; accent: string; text: string };

export function paletteOf(brand: TimelineBrand): Palette {
  return { background: brand.primary, accent: brand.accent, text: readableOn(brand.primary) };
}

export function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
