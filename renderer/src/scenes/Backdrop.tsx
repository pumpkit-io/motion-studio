import { AbsoluteFill, useCurrentFrame } from "remotion";
import { withAlpha, type Palette } from "../lib/palette";

const GRID_PX = 48;

/**
 * The brand-coloured ground every product scene sits on: two slow glows and a drifting grid,
 * after the Pumpkit launch video. `glow` scales the glows (a title card runs brighter).
 */
export const Backdrop: React.FC<{ palette: Palette; unit: number; glow?: number }> = ({ palette, unit, glow = 1 }) => {
  // The composition's frame, not the scene's, so the drift never jumps at a cut.
  const frame = useCurrentFrame();
  const a = frame / 90;
  const gx = 50 + Math.sin(a) * 18;
  const gy = 40 + Math.cos(a * 0.8) * 14;
  const grid = GRID_PX * unit;
  const line = withAlpha(palette.text, 0.045);
  const fade = "radial-gradient(ellipse at center, black 30%, transparent 80%)";
  return (
    <AbsoluteFill style={{ backgroundColor: palette.background }}>
      <AbsoluteFill
        style={{
          background: [
            `radial-gradient(${1100 * unit}px ${700 * unit}px at ${gx}% ${gy}%, ${withAlpha(palette.accent, 0.38 * glow)}, transparent 70%)`,
            `radial-gradient(${900 * unit}px ${600 * unit}px at ${100 - gx}% ${100 - gy}%, ${withAlpha(palette.text, 0.1 * glow)}, transparent 70%)`,
          ].join(", "),
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${line} 1px, transparent 1px), linear-gradient(90deg, ${line} 1px, transparent 1px)`,
          backgroundSize: `${grid}px ${grid}px`,
          backgroundPosition: `${(frame * 0.4 * unit) % grid}px ${(frame * 0.25 * unit) % grid}px`,
          maskImage: fade,
          WebkitMaskImage: fade,
        }}
      />
    </AbsoluteFill>
  );
};
