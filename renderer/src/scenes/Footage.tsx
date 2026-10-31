import { AbsoluteFill, interpolate, OffthreadVideo, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { cameraAt, cssTransform, footagePlayback, frameLayout, frameTransform } from "../lib/deviceFrame";
import type { LoadedFont } from "../lib/fonts";
import type { Palette } from "../lib/palette";
import type { TimelineFootage, TimelineHighlight, TimelineMask } from "../lib/timeline";
import { Backdrop } from "./Backdrop";
import { BROWSER_BODY, BrowserBar } from "./BrowserFrame";
import { EXIT_FRAMES } from "./Kinetic";
import { Highlights, Masks } from "./Overlays";

/**
 * A screen recording in a browser window that tilts in, follows its camera moves, then blurs out.
 * Masks and highlights sit on the footage, so they move with the camera.
 */
export const Footage: React.FC<{
  scene: TimelineFootage;
  highlights: TimelineHighlight[];
  masks: TimelineMask[];
  palette: Palette;
  font: LoadedFont;
  unit: number;
}> = ({ scene, highlights, masks, palette, font, unit }) => {
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
            backgroundColor: BROWSER_BODY,
          }}
        >
          <BrowserBar height={layout.bar} address={scene.address} font={font} />
          <div style={{ position: "relative", width: layout.content.width, height: layout.content.height, overflow: "hidden" }}>
            <OffthreadVideo
              src={staticFile(scene.src)}
              muted
              {...footagePlayback(scene, fps)}
              style={{ width: layout.content.width, height: layout.content.height, display: "block" }}
            />
            <Masks masks={masks} fill={BROWSER_BODY} frame={scene.start + frame} scale={layout.scale} unit={unit} />
            <Highlights
              highlights={highlights}
              footageWidth={scene.width}
              palette={palette}
              font={font}
              frame={scene.start + frame}
              scale={layout.scale}
              unit={unit}
            />
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
