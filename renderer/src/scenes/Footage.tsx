import { AbsoluteFill, interpolate, OffthreadVideo, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { cameraAt, cssTransform, footagePlayback, frameLayout, frameTransform } from "../lib/deviceFrame";
import type { LoadedFont } from "../lib/fonts";
import type { Palette } from "../lib/palette";
import type { TimelineFootage } from "../lib/timeline";
import { Backdrop } from "./Backdrop";
import { BROWSER_BODY, BrowserBar } from "./BrowserFrame";
import { EXIT_FRAMES } from "./Kinetic";
import { TERMINAL_BODY, TerminalBar } from "./TerminalFrame";

/** A screen recording in a browser or terminal window that tilts in, follows its camera moves, then blurs out. */
export const Footage: React.FC<{ scene: TimelineFootage; palette: Palette; font: LoadedFont; unit: number }> = ({
  scene,
  palette,
  font,
  unit,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const duration = scene.end - scene.start;
  const canvas = { width, height };
  const layout = frameLayout(scene, canvas);
  const enter = spring({ frame, fps, config: { damping: 18, stiffness: 110 } });
  const exit = interpolate(frame, [duration - EXIT_FRAMES, duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const camera = cameraAt(scene.camera, scene.start + frame, layout, fps);
  const transform = frameTransform(layout, canvas, { enter, camera });
  const terminal = scene.device_frame === "terminal";
  return (
    <AbsoluteFill>
      <Backdrop palette={palette} unit={unit} />
      <AbsoluteFill style={{ perspective: 2200 * unit, opacity: 1 - exit, filter: `blur(${exit * 8}px)` }}>
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: layout.content.width,
            height: layout.bar + layout.content.height,
            transformOrigin: "0 0",
            transform: cssTransform(transform),
            borderRadius: 18 * unit,
            overflow: "hidden",
            boxShadow: `0 ${40 * unit}px ${120 * unit}px rgba(0, 0, 0, 0.55), 0 0 0 ${unit}px rgba(255, 255, 255, 0.08)`,
            backgroundColor: terminal ? TERMINAL_BODY : BROWSER_BODY,
          }}
        >
          {terminal ? (
            <TerminalBar height={layout.bar} title={scene.address} font={font} />
          ) : (
            <BrowserBar height={layout.bar} address={scene.address} font={font} />
          )}
          <div style={{ position: "relative", width: layout.content.width, height: layout.content.height, overflow: "hidden" }}>
            <OffthreadVideo
              src={staticFile(scene.src)}
              muted
              {...footagePlayback(scene, fps)}
              style={{ width: layout.content.width, height: layout.content.height, display: "block" }}
            />
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
