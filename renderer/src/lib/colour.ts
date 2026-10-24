/** Black or white, whichever reads better on `hex` (WCAG relative luminance). */
export function readableOn(hex: string): string {
  // The config normalises every brand colour to #RRGGBB, so anything else is a contract break.
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (m === null) throw new Error(`expected a #RRGGBB colour, got ${JSON.stringify(hex)}`);
  const n = parseInt(m[1]!, 16);
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const l = 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
  // White wins while its contrast ratio beats black's: (1.05) / (l + 0.05) > (l + 0.05) / 0.05.
  return l < 0.179 ? "#FFFFFF" : "#111111";
}
