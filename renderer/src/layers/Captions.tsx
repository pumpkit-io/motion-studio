import { measureText } from "@remotion/layout-utils";
import { useMemo } from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { pageCaptions, type PageWord } from "../lib/captions";
import { FONT_WEIGHT } from "../lib/fonts";
import { safeBox } from "../lib/safezones";
import type { FormatSpec, TimelineBrand, TimelineCaptions, TimelineWord } from "../lib/timeline";

/** Word pop of the `pop` style: the active word grows to this scale. */
const POP_SCALE = 1.08;

type Props = {
  words: TimelineWord[];
  settings: TimelineCaptions;
  brand: TimelineBrand;
  format: FormatSpec;
  font: { family: string; ready: boolean };
};

/** Word-by-word captions, one line per page, sitting on the bottom edge of the safe area. */
export const Captions: React.FC<Props> = ({ words, settings, brand, format, font }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const safe = safeBox(format);
  const fontSize = Math.min(format.width, format.height) * 0.07;
  // Leaves room for the active word's pop and the stroke.
  const maxWidth = safe.width * 0.88;

  const pages = useMemo(() => {
    if (!settings.enabled || !font.ready) return [];
    return pageCaptions(words, {
      maxWords: settings.max_words_per_page,
      maxChars: settings.max_chars_per_page,
      maxWidth,
      measure: (text) => measureText({ text, fontFamily: font.family, fontSize, fontWeight: FONT_WEIGHT }).width,
      keepWithNext: settings.keep_with_next,
      uppercase: settings.uppercase,
    });
  }, [words, settings, font, fontSize, maxWidth]);

  const nowMs = (frame / fps) * 1000;
  const page = pages.find((p) => nowMs >= p.startMs && nowMs < p.endMs);
  if (page === undefined) return null;
  // The active word stays lit through the gap after it, until the next word starts.
  const active = page.words.filter((w) => w.fromMs <= nowMs).length - 1;

  return (
    <div
      style={{
        position: "absolute",
        left: safe.x,
        width: safe.width,
        // Bottom of the caption line sits a little above the safe area's bottom edge.
        bottom: format.height - (safe.y + safe.height) + format.height * 0.03,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          fontFamily: font.family,
          fontWeight: FONT_WEIGHT,
          fontSize: fontSize * page.fit,
          lineHeight: 1.1,
          whiteSpace: "nowrap",
          display: "flex",
          columnGap: "0.4em",
          textTransform: settings.uppercase ? "uppercase" : "none",
          WebkitTextStroke: `${fontSize * page.fit * 0.1}px ${settings.stroke_color}`,
          paintOrder: "stroke fill",
          textShadow: "0 4px 18px rgba(0, 0, 0, 0.35)",
        }}
      >
        {page.words.map((w, i) => (
          <Word
            key={`${page.startMs}-${i}`}
            word={w}
            active={i === active}
            nowMs={nowMs}
            settings={settings}
            brand={brand}
            fps={fps}
          />
        ))}
      </div>
    </div>
  );
};

const Word: React.FC<{
  word: PageWord;
  active: boolean;
  nowMs: number;
  settings: TimelineCaptions;
  brand: TimelineBrand;
  fps: number;
}> = ({ word, active, nowMs, settings, brand, fps }) => {
  const spoken = word.fromMs <= nowMs;
  let color = word.emphasis ? brand.accent : settings.text_color;
  let scale = 1;
  if (settings.style === "pop" && active) {
    color = settings.highlight_color;
    const pop = spring({ frame: ((nowMs - word.fromMs) / 1000) * fps, fps, config: { damping: 12, stiffness: 220 } });
    scale = 1 + (POP_SCALE - 1) * pop;
  } else if (settings.style === "karaoke" && spoken && !word.emphasis) {
    color = settings.highlight_color;
  }
  return (
    <span style={{ display: "inline-block", color, transform: `scale(${scale})` }}>{word.text}</span>
  );
};
