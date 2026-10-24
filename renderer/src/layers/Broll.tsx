import { AbsoluteFill, Img, interpolate, OffthreadVideo, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Box } from "../lib/camera";
import { safeBox } from "../lib/safezones";
import type { FormatSpec, TimelineBroll, TimelineEvent, TimelineImage } from "../lib/timeline";

const CROSSFADE_FRAMES = 6;
/** Ken Burns over the whole overlay: scale 1.0 to 1.08 with a pan of 3% of the width. */
const KENBURNS_SCALE = 1.08;
const KENBURNS_PAN = 0.03;

type Overlay = TimelineBroll | TimelineImage;

export const Broll: React.FC<{ events: TimelineEvent[]; format: FormatSpec }> = ({ events, format }) => {
  const overlays = events.filter((e): e is Overlay => e.type === "broll" || e.type === "image");
  return (
    <>
      {overlays.map((o) => (
        <Sequence key={`${o.asset}-${o.start}`} from={o.start} durationInFrames={o.end - o.start} layout="none">
          {o.mode === "full" ? <FullOverlay overlay={o} /> : <PipOverlay overlay={o} format={format} />}
        </Sequence>
      ))}
    </>
  );
};

/** Opacity of a fade in and out at both ends of a `duration`-frame overlay. */
function fade(frame: number, duration: number): number {
  const edge = Math.max(1, Math.min(CROSSFADE_FRAMES, Math.floor(duration / 2)));
  return interpolate(frame, [0, edge, duration - edge, duration], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

const FullOverlay: React.FC<{ overlay: Overlay }> = ({ overlay }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ opacity: fade(frame, overlay.end - overlay.start), overflow: "hidden" }}>
      <Media overlay={overlay} />
    </AbsoluteFill>
  );
};

/** A rounded card in the upper third of the safe area; on landscape formats, top right, clear of the speaker. */
const PipOverlay: React.FC<{ overlay: Overlay; format: FormatSpec }> = ({ overlay, format }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const safe = safeBox(format);
  const card = pipBox(format, safe);
  const enter = spring({ frame, fps, config: { damping: 18, stiffness: 160 } });
  return (
    <div
      style={{
        position: "absolute",
        left: card.x,
        top: card.y,
        width: card.width,
        height: card.height,
        overflow: "hidden",
        borderRadius: Math.min(format.width, format.height) * 0.03,
        boxShadow: "0 24px 60px rgba(0, 0, 0, 0.5)",
        opacity: fade(frame, overlay.end - overlay.start),
        transform: `scale(${interpolate(enter, [0, 1], [0.9, 1])})`,
      }}
    >
      <Media overlay={overlay} />
    </div>
  );
};

function pipBox(format: FormatSpec, safe: Box): Box {
  const portrait = format.height > format.width;
  const width = format.width * (portrait ? 0.62 : 0.3);
  const height = (width * 3) / 4;
  const x = portrait ? safe.x + (safe.width - width) / 2 : safe.x + safe.width - width;
  return { x, y: safe.y + format.height * 0.04, width, height };
}

const Media: React.FC<{ overlay: Overlay }> = ({ overlay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fill: React.CSSProperties = { width: "100%", height: "100%", objectFit: "cover" };
  if (overlay.type === "broll") {
    return <OffthreadVideo src={staticFile(overlay.src)} muted trimBefore={Math.round(overlay.asset_in_s * fps)} style={fill} />;
  }
  const t = overlay.motion === "kenburns" ? frame / Math.max(1, overlay.end - overlay.start) : 0;
  const scale = 1 + (KENBURNS_SCALE - 1) * t;
  // The pan grows with the scale and stays inside the overscan, so no edge ever shows.
  const pan = -KENBURNS_PAN * t * 100;
  return <Img src={staticFile(overlay.src)} style={{ ...fill, transform: `scale(${scale}) translateX(${pan}%)` }} />;
};
