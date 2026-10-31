import { staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { spriteFrameAt, spriteSheetStyle } from "../lib/sprite";
import type { TimelineMascot } from "../lib/timeline";

/** The brand mascot `height` tall, playing its sprite sheet at the sheet's own frame timings. */
export const Mascot: React.FC<{ mascot: TimelineMascot; file: string; height: number; startFrame?: number }> = ({
  mascot,
  file,
  height,
  startFrame = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const index = spriteFrameAt(mascot.frames, mascot.loops, ((frame - startFrame) / fps) * 1000);
  return (
    <div
      style={{
        ...spriteSheetStyle(mascot, mascot.frames[index]!, height),
        backgroundImage: `url(${staticFile(file)})`,
      }}
    />
  );
};
