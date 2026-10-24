import { interpolate, Sequence, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { readableOn } from "../lib/colour";
import { FONT_WEIGHT } from "../lib/fonts";
import { safeBox } from "../lib/safezones";
import type { FormatSpec, TimelineBrand, TimelineEvent, TimelineTitle } from "../lib/timeline";

const OUT_FRAMES = 8;

export const Titles: React.FC<{
  events: TimelineEvent[];
  format: FormatSpec;
  brand: TimelineBrand;
  fontFamily: string;
}> = ({ events, format, brand, fontFamily }) => {
  const titles = events.filter((e): e is TimelineTitle => e.type === "title");
  return (
    <>
      {titles.map((t) => (
        <Sequence key={`${t.start}-${t.text}`} from={t.start} durationInFrames={t.end - t.start} layout="none">
          <TitleCard title={t} format={format} brand={brand} fontFamily={fontFamily} />
        </Sequence>
      ))}
    </>
  );
};

/** A bold card on the brand's primary colour, near the top of the safe area. */
const TitleCard: React.FC<{ title: TimelineTitle; format: FormatSpec; brand: TimelineBrand; fontFamily: string }> = ({
  title,
  format,
  brand,
  fontFamily,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const duration = title.end - title.start;
  const enter = spring({ frame, fps, config: { damping: 16, stiffness: 170 } });
  const exit = spring({ frame: frame - (duration - OUT_FRAMES), fps, durationInFrames: OUT_FRAMES, config: { damping: 200 } });
  const shown = enter - exit;
  const safe = safeBox(format);
  const unit = Math.min(format.width, format.height);
  return (
    <div
      style={{
        position: "absolute",
        left: safe.x,
        top: safe.y + format.height * 0.04,
        width: safe.width,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          maxWidth: safe.width * 0.88,
          padding: `${unit * 0.022}px ${unit * 0.04}px`,
          borderRadius: unit * 0.02,
          backgroundColor: brand.primary,
          color: readableOn(brand.primary),
          fontFamily,
          fontWeight: FONT_WEIGHT,
          fontSize: unit * 0.062,
          lineHeight: 1.12,
          letterSpacing: "-0.02em",
          textAlign: "center",
          opacity: shown,
          transform: `translateY(${interpolate(shown, [0, 1], [unit * 0.03, 0])}px) scale(${interpolate(shown, [0, 1], [0.92, 1])})`,
        }}
      >
        {title.text}
      </div>
    </div>
  );
};
