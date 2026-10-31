import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { TimelineHeadlineWord } from "../lib/timeline";

export const EXIT_FRAMES = 6;

/** Words that spring up one after another, then blur away over the scene's last frames. */
export const Kinetic: React.FC<{
  words: TimelineHeadlineWord[];
  size: number;
  family: string;
  weight: number;
  color: string;
  accent: string;
  /** Local frame the exit starts at. */
  out: number;
  delay?: number;
  stagger?: number;
  maxWidth: number;
}> = ({ words, size, family, weight, color, accent, out, delay = 0, stagger = 3, maxWidth }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exit = interpolate(frame, [out, out + EXIT_FRAMES], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        gap: `0 ${size * 0.26}px`,
        fontFamily: family,
        fontWeight: weight,
        fontSize: size,
        letterSpacing: -size * 0.035,
        lineHeight: 1.05,
        color,
        maxWidth,
        textAlign: "center",
        opacity: 1 - exit,
        transform: `translateY(${-exit * 40 * (size / 128)}px) scale(${1 - exit * 0.04})`,
        filter: `blur(${exit * 10}px)`,
      }}
    >
      {words.map((word, i) => {
        const s = spring({ frame: frame - delay - i * stagger, fps, config: { damping: 14, stiffness: 170, mass: 0.7 } });
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              transform: `translateY(${(1 - s) * size * 0.7}px) scale(${0.7 + 0.3 * s})`,
              opacity: Math.min(1, s * 1.4),
              filter: `blur(${(1 - Math.min(1, s)) * 12}px)`,
              color: word.accent ? accent : undefined,
            }}
          >
            {word.text}
          </span>
        );
      })}
    </div>
  );
};
