import { Gif } from "@remotion/gif";
import { Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { spriteFrameAt, spriteSheetStyle } from "../lib/sprite";
import type { TimelineGifMascot, TimelineMascot } from "../lib/timeline";

/** The brand mascot `height` tall, playing its sprite sheet or GIF at its own frame timings. */
export const Mascot: React.FC<{
  mascot: TimelineMascot | TimelineGifMascot;
  file: string;
  height: number;
  startFrame?: number;
}> = ({ mascot, file, height, startFrame = 0 }) =>
  mascot.type === "gif" ? (
    <GifMascot mascot={mascot} file={file} height={height} startFrame={startFrame} />
  ) : (
    <SpriteMascot mascot={mascot} file={file} height={height} startFrame={startFrame} />
  );

const SpriteMascot: React.FC<{ mascot: TimelineMascot; file: string; height: number; startFrame: number }> = ({
  mascot,
  file,
  height,
  startFrame,
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

const GifMascot: React.FC<{ mascot: TimelineGifMascot; file: string; height: number; startFrame: number }> = ({
  mascot,
  file,
  height,
  startFrame,
}) => {
  const width = (height * mascot.width) / mascot.height;
  return (
    <div style={{ width, height }}>
      <Sequence from={startFrame} layout="none">
        {/* The canvas stays at the GIF's own size and CSS scales it, so pixel art is not smoothed. */}
        <Gif
          src={staticFile(file)}
          width={mascot.width}
          height={mascot.height}
          loopBehavior="loop"
          style={{ width, height, display: "block", imageRendering: "pixelated" }}
        />
      </Sequence>
    </div>
  );
};
