import { Composition } from "remotion";
import { Product } from "./Product";
import { Reel } from "./Reel";
import { productMetadata, reelMetadata, type ProductProps, type ReelProps } from "./props";

// An empty one-second timeline so the Studio opens; renders always pass real props.
const defaultProps: ReelProps = {
  format: "9x16",
  source: { width: 1080, height: 1920 },
  regions: {},
  video: "assembled.mp4",
  font_file: null,
  bundled_font: "TikTok Sans",
  logo_file: null,
  timeline: {
    schema_version: 1,
    kind: "talk",
    title: "",
    language: null,
    fps: 30,
    duration_frames: 30,
    runs: [],
    words: [],
    events: [],
    scenes: [],
    formats: [{ name: "9x16", width: 1080, height: 1920, safe_zone: { top: 0.1, right: 0.12, bottom: 0.2, left: 0.05 } }],
    captions: {
      enabled: true,
      style: "clean",
      font: "TikTok Sans",
      max_words_per_page: 3,
      max_chars_per_page: null,
      keep_with_next: [],
      uppercase: false,
      hide_during_broll: false,
      highlight_color: "#FFD400",
      text_color: "#FFFFFF",
      stroke_color: "#000000",
    },
    brand: { primary: "#111111", accent: "#FFD400", logo: "", wordmark: null, mascot: null },
    music_path: null,
  },
};

const productDefaults: ProductProps = {
  format: "16x9",
  font_file: null,
  bundled_font: "Inter",
  logo_file: null,
  wordmark_file: null,
  mascot_file: null,
  timeline: {
    ...defaultProps.timeline,
    kind: "product",
    formats: [{ name: "16x9", width: 1920, height: 1080, safe_zone: { top: 0.05, right: 0.05, bottom: 0.12, left: 0.05 } }],
  },
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="Reel" component={Reel} defaultProps={defaultProps} calculateMetadata={reelMetadata} />
      <Composition id="Product" component={Product} defaultProps={productDefaults} calculateMetadata={productMetadata} />
    </>
  );
};
