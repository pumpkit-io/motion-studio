import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { readableOn } from "../lib/colour";
import { FONT_WEIGHT, TEXT_WEIGHT, type LoadedFont } from "../lib/fonts";
import { flashOpacity, highlightAt, labelOnLeft, maskShown } from "../lib/overlays";
import { withAlpha, type Palette } from "../lib/palette";
import type { TimelineCaptionPill, TimelineFlash, TimelineHighlight, TimelineMask } from "../lib/timeline";
import { EXIT_FRAMES } from "./Kinetic";

// Footage overlays are placed in footage pixels times `scale`, inside the frame the camera moves.
type OnFootage = { frame: number; scale: number; unit: number };

/** Masks over the footage, each shown for exactly its frames. `fill` is the frame's background. */
export const Masks: React.FC<OnFootage & { masks: TimelineMask[]; fill: string }> = ({ masks, fill, frame, scale }) => (
  <>
    {masks
      .filter((m) => maskShown(m, frame))
      .map((m, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: m.x * scale,
            top: m.y * scale,
            width: m.w * scale,
            height: m.h * scale,
            backgroundColor: m.color ?? fill,
          }}
        />
      ))}
  </>
);

/** Accent boxes that draw in around their targets, each with an optional tag. */
export const Highlights: React.FC<
  OnFootage & { highlights: TimelineHighlight[]; footageWidth: number; palette: Palette; font: LoadedFont }
> = ({ highlights, footageWidth, palette, font, frame, scale, unit }) => {
  const { fps } = useVideoConfig();
  return (
    <>
      {highlights.map((h, i) => {
        const { grow, opacity } = highlightAt(h, frame, fps);
        if (opacity === 0) return null;
        const left = labelOnLeft(h, footageWidth);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: h.x * scale,
              top: h.y * scale,
              width: h.w * scale * grow,
              height: h.h * scale,
              opacity,
            }}
          >
            <div
              style={{
                position: "absolute",
                inset: 0,
                borderRadius: 8 * unit,
                border: `${3 * unit}px solid ${palette.accent}`,
                backgroundColor: withAlpha(palette.accent, 0.12),
                boxShadow: `0 0 0 ${6 * unit}px ${withAlpha(palette.accent, 0.15)}`,
              }}
            />
            {h.label !== null ? (
              <div
                style={{
                  position: "absolute",
                  // Off the box's top-right corner, or its top-left near the footage's right edge.
                  left: left ? 0 : h.w * scale - 10 * unit,
                  top: -34 * unit,
                  transform: `scale(${grow})`,
                  transformOrigin: "left bottom",
                  whiteSpace: "nowrap",
                  fontFamily: font.family,
                  fontWeight: FONT_WEIGHT,
                  fontSize: 18 * unit,
                  color: readableOn(palette.accent),
                  backgroundColor: palette.accent,
                  padding: `${5 * unit}px ${12 * unit}px`,
                  borderRadius: 8 * unit,
                }}
              >
                {h.label}
              </div>
            ) : null}
          </div>
        );
      })}
    </>
  );
};

/** A line in a pill at the bottom of the canvas, rising in after the cut and leaving with the scene. */
export const CaptionPill: React.FC<{ pill: TimelineCaptionPill; palette: Palette; font: LoadedFont; unit: number }> = ({
  pill,
  palette,
  font,
  unit,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const duration = pill.end - pill.start;
  const rise = spring({ frame: frame - 8, fps, config: { damping: 16 } });
  const exit = interpolate(frame, [duration - EXIT_FRAMES, duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 54 * unit }}>
      <div
        style={{
          fontFamily: font.family,
          fontSize: 34 * unit,
          fontWeight: font.family === "Inter" ? 600 : TEXT_WEIGHT,
          color: palette.text,
          backgroundColor: withAlpha(palette.background, 0.82),
          border: `${unit}px solid ${withAlpha(palette.text, 0.14)}`,
          backdropFilter: `blur(${10 * unit}px)`,
          padding: `${16 * unit}px ${30 * unit}px`,
          borderRadius: 999,
          display: "flex",
          alignItems: "center",
          gap: 16 * unit,
          maxWidth: 1600 * unit,
          transform: `translateY(${(1 - rise) * 80 * unit}px)`,
          opacity: rise * (1 - exit),
          boxShadow: `0 ${12 * unit}px ${40 * unit}px rgba(0, 0, 0, 0.4)`,
        }}
      >
        <div style={{ flexShrink: 0, width: 14 * unit, height: 14 * unit, borderRadius: 3 * unit, backgroundColor: palette.accent }} />
        {pill.text}
      </div>
    </AbsoluteFill>
  );
};

/** White over the whole canvas on the cut, fading out. */
export const Flash: React.FC<{ flash: TimelineFlash }> = ({ flash }) => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{ backgroundColor: "#FFFFFF", opacity: flashOpacity(flash, flash.start + frame) }} />;
};
