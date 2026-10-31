import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { readableOn } from "../lib/colour";
import { FONT_WEIGHT, TEXT_WEIGHT, type LoadedFont } from "../lib/fonts";
import { withAlpha, type Palette } from "../lib/palette";
import type { TimelineProof } from "../lib/timeline";
import { Backdrop } from "./Backdrop";
import { EXIT_FRAMES, Kinetic } from "./Kinetic";

// Boxes in 1920-wide pixels: beside a headline the image sits right of centre, alone it is centred.
const BESIDE = { cx: 1320, width: 920, height: 720 };
const ALONE = { cx: 960, width: 1240, height: 820 };

/** An image that rises and swings in, drifting slowly in 3D, with an optional headline and badge. */
export const Proof: React.FC<{ scene: TimelineProof; palette: Palette; font: LoadedFont; unit: number }> = ({
  scene,
  palette,
  font,
  unit,
}) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const duration = scene.end - scene.start;
  const rise = spring({ frame: frame - 4, fps, config: { damping: 13, stiffness: 120 } });
  const badge = spring({ frame: frame - 16, fps, config: { damping: 10, stiffness: 180 } });
  const drift = interpolate(frame, [0, duration], [0, 1]);
  const exit = interpolate(frame, [duration - EXIT_FRAMES, duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const beside = scene.headline.length > 0;
  const box = beside ? BESIDE : ALONE;
  const size = fit(scene, box.width * unit, box.height * unit);
  const subline = scene.subline?.split(/\s+/).map((text) => ({ text, accent: false })) ?? [];
  return (
    <AbsoluteFill>
      <Backdrop palette={palette} unit={unit} glow={1.3} />
      {beside ? (
        <AbsoluteFill style={{ justifyContent: "center", opacity: 1 - exit }}>
          <div style={{ marginLeft: 130 * unit, width: 640 * unit }}>
            <Kinetic
              words={scene.headline}
              size={128 * unit}
              family={font.family}
              weight={FONT_WEIGHT}
              color={palette.text}
              accent={palette.accent}
              out={duration}
              maxWidth={640 * unit}
            />
            {subline.length > 0 ? (
              <div style={{ marginTop: 26 * unit }}>
                <Kinetic
                  words={subline}
                  size={44 * unit}
                  family={font.family}
                  weight={TEXT_WEIGHT}
                  color={withAlpha(palette.text, 0.75)}
                  accent={palette.accent}
                  out={duration}
                  delay={8}
                  stagger={2}
                  maxWidth={640 * unit}
                />
              </div>
            ) : null}
          </div>
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill style={{ perspective: 1800 * unit, opacity: 1 - exit }}>
        <div
          style={{
            position: "absolute",
            left: box.cx * unit - size.width / 2,
            top: (height - (size.height ?? box.height * unit)) / 2 + (1 - rise) * 500 * unit,
            width: size.width,
            transform:
              `rotateY(${(beside ? -14 : -8) + drift * 8}deg) rotateX(${4 - drift * 3}deg) ` +
              `rotateZ(${(1 - rise) * 8}deg) scale(${0.85 + 0.15 * rise + drift * 0.03})`,
          }}
        >
          <Img
            src={staticFile(scene.src)}
            style={{
              display: "block",
              width: size.width,
              height: size.height ?? undefined,
              borderRadius: 28 * unit,
              boxShadow: `0 ${50 * unit}px ${140 * unit}px rgba(0, 0, 0, 0.6), 0 0 0 ${unit}px rgba(255, 255, 255, 0.1)`,
            }}
          />
          {scene.badge !== null ? (
            <div
              style={{
                position: "absolute",
                right: -30 * unit,
                top: -34 * unit,
                transform: `scale(${badge}) rotate(${(1 - badge) * -40 + 6}deg)`,
                backgroundColor: palette.accent,
                color: readableOn(palette.accent),
                fontFamily: font.family,
                fontWeight: FONT_WEIGHT,
                fontSize: 34 * unit,
                padding: `${14 * unit}px ${26 * unit}px`,
                borderRadius: 16 * unit,
                boxShadow: `0 ${14 * unit}px ${40 * unit}px ${withAlpha(palette.accent, 0.5)}`,
                whiteSpace: "nowrap",
              }}
            >
              {scene.badge}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** The image's size inside the box; an unmeasured image takes the box's width. */
function fit(image: { width: number | null; height: number | null }, width: number, height: number) {
  if (image.width === null || image.height === null) return { width, height: null };
  const scale = Math.min(width / image.width, height / image.height);
  return { width: image.width * scale, height: image.height * scale };
}
