import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";
import { FONT_WEIGHT, TEXT_WEIGHT, useCaptionFont, type LoadedFont } from "./lib/fonts";
import { paletteOf, type Palette } from "./lib/palette";
import { sceneEvents } from "./lib/overlays";
import type { TimelineEvent, TimelineScene } from "./lib/timeline";
import type { ProductProps } from "./props";
import { Footage } from "./scenes/Footage";
import { CaptionPill, Flash } from "./scenes/Overlays";
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
          <SceneView scene={scene} events={timeline.events} palette={palette} font={font} unit={unit} />
        </Sequence>
      ))}
      {timeline.events.map((event, i) => {
        if (event.type !== "caption_pill" && event.type !== "flash") return null;
        return (
          <Sequence key={i} from={event.start} durationInFrames={event.end - event.start} name={`${event.scene} ${event.type}`}>
            {event.type === "flash" ? (
              <Flash flash={event} />
            ) : (
              <CaptionPill pill={event} palette={palette} font={font} unit={unit} />
            )}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const SceneView: React.FC<{
  scene: TimelineScene;
  events: TimelineEvent[];
  palette: Palette;
  font: LoadedFont;
  unit: number;
}> = ({ scene, events, ...look }) => {
  switch (scene.type) {
    case "title_card":
      return <TitleCard scene={scene} {...look} />;
    case "footage":
      return (
        <Footage
          scene={scene}
          highlights={sceneEvents(events, scene.id, "highlight")}
          masks={sceneEvents(events, scene.id, "mask")}
          {...look}
        />
      );
  }
};
