import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { FONT_WEIGHT, type LoadedFont } from "../lib/fonts";
import type { Palette } from "../lib/palette";
import type { TimelineLogoOutro, TimelineMascot } from "../lib/timeline";
import { Backdrop } from "./Backdrop";
import { Mascot } from "./Mascot";

const FADE_FRAMES = 18;

export type BrandArt = { wordmark: string | null; mascot: { sheet: TimelineMascot; file: string } | null };

/** Mascot and wordmark slide together, the tagline and URL rise under them, then all fades to black. */
export const LogoOutro: React.FC<{
  scene: TimelineLogoOutro;
  palette: Palette;
  font: LoadedFont;
  unit: number;
  art: BrandArt;
}> = ({ scene, palette, font, unit, art }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const duration = scene.end - scene.start;
  const enter = (delay: number, damping = 14) =>
    spring({ frame: frame - delay, fps, config: { damping, stiffness: 120 } });
  const mascotIn = enter(0);
  const wordIn = enter(6);
  // The launch video's 1.6 s and 2.2 s, pulled in on a short outro so the URL still lands.
  const tagIn = enter(Math.round(Math.min(fps * 1.6, duration * 0.3)), 16);
  const urlIn = enter(Math.round(Math.min(fps * 2.2, duration * 0.4)), 16);
  const fade = interpolate(frame, [duration - FADE_FRAMES, duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const mascot = scene.mascot ? art.mascot : null;
  return (
    <AbsoluteFill>
      <Backdrop palette={palette} unit={unit} glow={1.1} />
      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          transform: `scale(${interpolate(frame, [0, duration], [0.97, 1.03])})`,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-end", gap: 30 * unit }}>
          {mascot !== null ? (
            <div style={{ transform: `translateX(${(1 - mascotIn) * -160 * unit}px)`, opacity: Math.min(1, mascotIn * 1.4) }}>
              <Mascot mascot={mascot.sheet} file={mascot.file} height={300 * unit} startFrame={4} />
            </div>
          ) : null}
          {art.wordmark !== null ? (
            <div
              style={{
                paddingBottom: (mascot !== null ? 18 : 0) * unit,
                transform: `translateX(${(1 - wordIn) * 120 * unit}px)`,
                opacity: Math.min(1, wordIn * 1.4),
              }}
            >
              <Img src={staticFile(art.wordmark)} style={{ height: 240 * unit, display: "block" }} />
            </div>
          ) : null}
        </div>
        {scene.tagline.length > 0 ? (
          <div
            style={{
              marginTop: 40 * unit,
              fontFamily: font.family,
              fontSize: 52 * unit,
              fontWeight: FONT_WEIGHT,
              letterSpacing: -unit,
              color: palette.text,
              opacity: tagIn,
              transform: `translateY(${(1 - tagIn) * 24 * unit}px)`,
            }}
          >
            {scene.tagline.map((word, i) => (
              <span key={i} style={{ color: word.accent ? palette.accent : undefined }}>
                {i > 0 ? " " : ""}
                {word.text}
              </span>
            ))}
          </div>
        ) : null}
        {scene.url !== null ? (
          <div
            style={{
              marginTop: 30 * unit,
              fontFamily: font.family,
              fontSize: 32 * unit,
              fontWeight: FONT_WEIGHT,
              backgroundColor: palette.text,
              color: palette.background,
              padding: `${10 * unit}px ${22 * unit}px`,
              borderRadius: 999,
              opacity: urlIn,
              transform: `translateY(${(1 - urlIn) * 20 * unit}px)`,
            }}
          >
            {scene.url}
          </div>
        ) : null}
      </AbsoluteFill>
      <AbsoluteFill style={{ backgroundColor: "#000000", opacity: fade }} />
    </AbsoluteFill>
  );
};
