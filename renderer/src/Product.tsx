import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";
import { FONT_WEIGHT, TEXT_WEIGHT, useCaptionFont, type LoadedFont } from "./lib/fonts";
import { paletteOf, type Palette } from "./lib/palette";
import type { TimelineScene } from "./lib/timeline";
import type { ProductProps } from "./props";
import { Footage } from "./scenes/Footage";
import { TitleCard } from "./scenes/TitleCard";

// Sizes in the components are 1920-wide pixels, after the Pumpkit launch video.
const REFERENCE_WIDTH = 1920;

/** A product video: its scenes back to back on the brand's backdrop. */
export const Product: React.FC<ProductProps> = ({ timeline, font_file }) => {
  const { width } = useVideoConfig();
  const font = useCaptionFont(timeline.captions.font, font_file, [FONT_WEIGHT, TEXT_WEIGHT]);
  const palette = paletteOf(timeline.brand);
  const unit = width / REFERENCE_WIDTH;
  return (
    <AbsoluteFill style={{ backgroundColor: palette.background }}>
      {timeline.scenes.map((scene) => (
        <Sequence key={scene.id} from={scene.start} durationInFrames={scene.end - scene.start} name={scene.id}>
          <SceneView scene={scene} palette={palette} font={font} unit={unit} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

const SceneView: React.FC<{ scene: TimelineScene; palette: Palette; font: LoadedFont; unit: number }> = ({
  scene,
  ...look
}) => {
  switch (scene.type) {
    case "title_card":
      return <TitleCard scene={scene} {...look} />;
    case "footage":
      return <Footage scene={scene} {...look} />;
  }
};
