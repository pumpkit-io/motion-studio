import { Composition } from "remotion";
import { Reel } from "./Reel";
import { reelMetadata, type ReelProps } from "./props";

// An empty one-second timeline so the Studio opens; renders always pass real props.
const defaultProps: ReelProps = {
  format: "9x16",
  source: { width: 1080, height: 1920 },
  regions: {},
  video: "assembled.mp4",
  font_file: null,
  logo_file: null,
  timeline: {
    schema_version: 1,
    title: "",
    language: null,
    fps: 30,
    duration_frames: 30,
    runs: [],
    words: [],
    events: [],
    formats: [{ name: "9x16", width: 1080, height: 1920, safe_zone: { top: 0.1, right: 0.12, bottom: 0.2, left: 0.05 } }],
    captions: {
      enabled: true,
      style: "pop",
      font: "Inter",
      max_words_per_page: 3,
      max_chars_per_page: null,
      keep_with_next: [],
      uppercase: false,
      hide_during_broll: false,
      highlight_color: "#FFD400",
      text_color: "#FFFFFF",
      stroke_color: "#000000",
    },
    brand: { primary: "#111111", accent: "#FFD400", logo: "" },
    music_path: null,
  },
};

export const RemotionRoot: React.FC = () => {
  return <Composition id="Reel" component={Reel} defaultProps={defaultProps} calculateMetadata={reelMetadata} />;
};
