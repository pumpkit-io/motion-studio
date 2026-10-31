import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { FONT_WEIGHT, TEXT_WEIGHT, type LoadedFont } from "../lib/fonts";
import { withAlpha, type Palette } from "../lib/palette";
import type { TimelineTitleCard } from "../lib/timeline";
import { Backdrop } from "./Backdrop";
import { EXIT_FRAMES, Kinetic } from "./Kinetic";

/** Step number, headline and subline over a brighter backdrop, with a slow push-in. */
export const TitleCard: React.FC<{ scene: TimelineTitleCard; palette: Palette; font: LoadedFont; unit: number }> = ({
  scene,
  palette,
  font,
  unit,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const duration = scene.end - scene.start;
  const out = duration - EXIT_FRAMES;
  const bar = spring({ frame, fps, config: { damping: 20, stiffness: 120 } });
  const zoom = interpolate(frame, [0, duration], [1, 1.06]);
  const fade = interpolate(frame, [out, duration], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const subline = scene.subline?.split(/\s+/).map((text) => ({ text, accent: false })) ?? [];
  return (
    <AbsoluteFill>
      <Backdrop palette={palette} unit={unit} glow={1.2} />
      <AbsoluteFill
        style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", transform: `scale(${zoom})` }}
      >
        {scene.step !== null ? (
          <div
            style={{
              fontFamily: font.family,
              fontWeight: FONT_WEIGHT,
              fontSize: 30 * unit,
              letterSpacing: 6 * unit,
              color: palette.accent,
              marginBottom: 26 * unit,
              opacity: bar * fade,
              transform: `translateY(${(1 - bar) * 20 * unit}px)`,
            }}
          >
            {scene.step}
          </div>
        ) : null}
        <Kinetic
          words={scene.headline}
          size={128 * unit}
          family={font.family}
          weight={FONT_WEIGHT}
          color={palette.text}
          accent={palette.accent}
          out={out}
          maxWidth={width * 0.83}
        />
        {subline.length > 0 ? (
          <div style={{ marginTop: 34 * unit }}>
            <Kinetic
              words={subline}
              size={44 * unit}
              family={font.family}
              weight={TEXT_WEIGHT}
              color={withAlpha(palette.text, 0.72)}
              accent={palette.accent}
              out={out}
              delay={8}
              stagger={2}
              maxWidth={width * 0.83}
            />
          </div>
        ) : null}
        <div
          style={{
            marginTop: 46 * unit,
            height: 8 * unit,
            width: 220 * unit * bar,
            borderRadius: 4 * unit,
            backgroundColor: palette.accent,
            opacity: fade,
          }}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
