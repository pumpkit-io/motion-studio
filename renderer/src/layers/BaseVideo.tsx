import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame } from "remotion";
import { framingAt, regionTransform, type Transform } from "../lib/camera";
import type { FormatSpec } from "../lib/timeline";
import type { ReelProps } from "../props";

export const BaseVideo: React.FC<{ props: ReelProps; format: FormatSpec }> = ({ props, format }) => {
  const frame = useCurrentFrame();
  const { source, timeline } = props;
  const src = staticFile(props.video);
  const { region, layout, camera } = framingAt(timeline, frame, source, props.regions, format);
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {layout.mode === "fitBlur" ? (
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <OffthreadVideo
            src={src}
            muted
            // Overscaled so the blur's soft edges stay outside the frame.
            style={placed(source, regionTransform(region, format, { cx: 0.5, cy: 0.5 }, 1.15), "blur(40px) brightness(0.55)")}
          />
        </AbsoluteFill>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: layout.box.x,
          top: layout.box.y,
          width: layout.box.width,
          height: layout.box.height,
          overflow: "hidden",
        }}
      >
        <OffthreadVideo src={src} style={placed(source, camera)} />
      </div>
    </AbsoluteFill>
  );
};

function placed(source: ReelProps["source"], t: Transform, filter?: string): React.CSSProperties {
  return {
    position: "absolute",
    left: 0,
    top: 0,
    width: source.width,
    height: source.height,
    maxWidth: "none",
    transformOrigin: "0 0",
    transform: `translate(${t.x}px, ${t.y}px) scale(${t.scale})`,
    filter,
  };
}
