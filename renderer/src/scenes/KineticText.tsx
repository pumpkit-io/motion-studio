import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";
import { FONT_WEIGHT, type LoadedFont } from "../lib/fonts";
import type { Palette } from "../lib/palette";
import type { TimelineKineticText } from "../lib/timeline";
import { Backdrop } from "./Backdrop";
import { EXIT_FRAMES, Kinetic } from "./Kinetic";

// A short line is a punch at 150 px; a longer one drops to 110 px with a quicker stagger.
const SHORT_LINE = 24;

/** Lines that spring in word by word, each replacing the last, over a dim backdrop. */
export const KineticText: React.FC<{ scene: TimelineKineticText; palette: Palette; font: LoadedFont; unit: number }> = ({
  scene,
  palette,
  font,
  unit,
}) => {
  const { width } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Backdrop palette={palette} unit={unit} glow={0.6} />
      {scene.lines.map((line, i) => {
        const duration = line.end - line.start;
        const short = line.words.map((w) => w.text).join(" ").length <= SHORT_LINE;
        return (
          <Sequence key={i} from={line.start - scene.start} durationInFrames={duration} name={`line ${i + 1}`}>
            <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
              <Kinetic
                words={line.words}
                size={(short ? 150 : 110) * unit}
                family={font.family}
                weight={FONT_WEIGHT}
                color={palette.text}
                accent={palette.accent}
                out={duration - EXIT_FRAMES}
                stagger={short ? 3 : 2}
                maxWidth={width * 0.83}
              />
            </AbsoluteFill>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
