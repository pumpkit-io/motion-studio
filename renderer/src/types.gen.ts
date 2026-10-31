// GENERATED from schemas/timeline.schema.json by scripts/gen_schemas.py. Do not edit.

/**
 * The resolved edit: `build/timeline.json`, the renderer's props.
 */
export interface Timeline {
  brand: TimelineBrand;
  captions: TimelineCaptions;
  duration_frames: number;
  /**
   * Overlays and camera moves, by start frame.
   */
  events: (
    | TimelineZoom
    | TimelinePush
    | TimelineBroll
    | TimelineImage
    | TimelineTitle
    | TimelineHighlight
    | TimelineMask
    | TimelineCaptionPill
    | TimelineFlash
  )[];
  formats: FormatSpec[];
  fps: number;
  /**
   * talk: runs of A-roll. product: scenes, and no runs.
   */
  kind: "talk" | "product";
  language: string | null;
  /**
   * Music bed relative to the project; null for none.
   */
  music_path: string | null;
  runs: Run[];
  /**
   * Product videos: scenes back to back in output order.
   */
  scenes: (TimelineTitleCard | TimelineFootage | TimelineKineticText | TimelineProof | TimelineLogoOutro)[];
  schema_version: 1;
  title: string;
  /**
   * Kept words in output order.
   */
  words: TimelineWord[];
}
export interface TimelineBrand {
  /**
   * #RRGGBB; #RGB is accepted and expanded.
   */
  accent: string;
  /**
   * Relative to the workspace.
   */
  logo: string;
  /**
   * Product videos only.
   */
  mascot: TimelineMascot | null;
  /**
   * #RRGGBB; #RGB is accepted and expanded.
   */
  primary: string;
  /**
   * Wordmark image relative to the workspace; product videos only.
   */
  wordmark: string | null;
}
export interface TimelineMascot {
  frame_height: number;
  frame_width: number;
  frames: TimelineSpriteFrame[];
  /**
   * Times the frames play before the last one holds; 0 is forever.
   */
  loops: number;
  /**
   * Sprite sheet image, relative to the workspace.
   */
  sheet: string;
  sheet_height: number;
  sheet_width: number;
}
export interface TimelineSpriteFrame {
  /**
   * How long the frame shows.
   */
  ms: number;
  /**
   * Left edge of the frame in the sheet, in sheet pixels.
   */
  x: number;
  y: number;
}
export interface TimelineCaptions {
  enabled: boolean;
  font: string;
  /**
   * Hide captions while a full-frame B-roll clip or image is on screen.
   */
  hide_during_broll: boolean;
  /**
   * #RRGGBB; #RGB is accepted and expanded.
   */
  highlight_color: string;
  /**
   * Words that never end a caption page.
   */
  keep_with_next: string[];
  /**
   * From the language's caption rules.
   */
  max_chars_per_page: number | null;
  max_words_per_page: number;
  /**
   * #RRGGBB; #RGB is accepted and expanded.
   */
  stroke_color: string;
  style: "pop" | "clean" | "karaoke";
  /**
   * #RRGGBB; #RGB is accepted and expanded.
   */
  text_color: string;
  uppercase: boolean;
}
export interface TimelineZoom {
  ease: "snap" | "smooth";
  end: number;
  scale: number;
  start: number;
  type: "zoom";
}
export interface TimelinePush {
  end: number;
  /**
   * Linear from 1.0 at start to this at end.
   */
  scale: number;
  start: number;
  type: "push";
}
export interface TimelineBroll {
  asset: string;
  asset_in_s: number;
  end: number;
  mode: "full" | "pip";
  /**
   * Asset file, relative to the project.
   */
  src: string;
  start: number;
  type: "broll";
}
export interface TimelineImage {
  asset: string;
  end: number;
  mode: "full" | "pip";
  motion: "kenburns" | "none";
  src: string;
  start: number;
  type: "image";
}
export interface TimelineTitle {
  end: number;
  start: number;
  text: string;
  type: "title";
}
/**
 * A box drawn on the footage, so it follows the camera.
 */
export interface TimelineHighlight {
  clip: string;
  /**
   * The element ID targeted, or null for a box.
   */
  element: string | null;
  /**
   * Output frame after the last one.
   */
  end: number;
  h: number;
  label: string | null;
  scene: string;
  /**
   * Source seconds where it ends.
   */
  src_end_s: number;
  /**
   * Source seconds of the first frame, on clip's clock.
   */
  src_start_s: number;
  /**
   * First output frame.
   */
  start: number;
  type: "highlight";
  w: number;
  /**
   * Left edge in footage pixels.
   */
  x: number;
  /**
   * Top edge in footage pixels.
   */
  y: number;
}
/**
 * A box of the footage filled over exactly start to end.
 */
export interface TimelineMask {
  clip: string;
  /**
   * Null: the device frame's background.
   */
  color: string | null;
  /**
   * The element ID targeted, or null for a box.
   */
  element: string | null;
  /**
   * Output frame after the last one.
   */
  end: number;
  h: number;
  scene: string;
  /**
   * Source seconds where it ends.
   */
  src_end_s: number;
  /**
   * Source seconds of the first frame, on clip's clock.
   */
  src_start_s: number;
  /**
   * First output frame.
   */
  start: number;
  type: "mask";
  w: number;
  /**
   * Left edge in footage pixels.
   */
  x: number;
  /**
   * Top edge in footage pixels.
   */
  y: number;
}
export interface TimelineCaptionPill {
  end: number;
  scene: string;
  start: number;
  text: string;
  type: "caption_pill";
}
export interface TimelineFlash {
  end: number;
  scene: string;
  start: number;
  /**
   * Opacity at start, fading to 0 at end.
   */
  strength: number;
  type: "flash";
}
export interface FormatSpec {
  height: number;
  name: "9x16" | "16x9" | "4x5";
  safe_zone: SafeZone;
  width: number;
}
/**
 * Fractions of the frame kept clear of platform UI on each side.
 */
export interface SafeZone {
  bottom: number;
  left: number;
  right: number;
  top: number;
}
/**
 * A continuous stretch of one clip. Runs follow each other with no gap in output time.
 */
export interface Run {
  /**
   * 1.0, or the jump-cut punch scale. A zoom event replaces it while active.
   */
  base_scale: number;
  clip: string;
  crop: Crop;
  /**
   * False when no face was seen; crop is then the frame centre.
   */
  face: boolean;
  /**
   * First output frame.
   */
  out_in: number;
  /**
   * Output frame after the last one.
   */
  out_out: number;
  segment: string;
  /**
   * Source seconds, on the frame grid.
   */
  src_in_s: number;
  src_out_s: number;
}
export interface Crop {
  /**
   * Face centre x, 0-1 of the mezzanine frame.
   */
  cx: number;
  /**
   * Face centre y, 0-1 of the mezzanine frame.
   */
  cy: number;
}
export interface TimelineTitleCard {
  /**
   * Output frame after the last one.
   */
  end: number;
  headline: TimelineHeadlineWord[];
  id: string;
  /**
   * First output frame.
   */
  start: number;
  step: string | null;
  subline: string | null;
  type: "title_card";
}
export interface TimelineHeadlineWord {
  /**
   * Drawn in the brand accent colour.
   */
  accent: boolean;
  text: string;
}
export interface TimelineFootage {
  address: string | null;
  /**
   * In frame order.
   */
  camera: TimelineCameraKey[];
  clip: string;
  device_frame: "browser" | "terminal";
  end: number;
  /**
   * Pixel height of the footage.
   */
  height: number;
  id: string;
  /**
   * Playback speed that fits src_in_s to src_out_s in the scene.
   */
  rate: number;
  /**
   * The recording's mezzanine, relative to the project.
   */
  src: string;
  /**
   * Source seconds of the scene's first frame.
   */
  src_in_s: number;
  /**
   * Source seconds where the scene ends.
   */
  src_out_s: number;
  start: number;
  type: "footage";
  /**
   * Pixel width of the footage.
   */
  width: number;
}
/**
 * Where a camera move starts and what it frames, in the footage's pixels.
 */
export interface TimelineCameraKey {
  /**
   * Footage x the camera centres on.
   */
  cx: number;
  /**
   * Footage y the camera centres on.
   */
  cy: number;
  ease: "smooth" | "snap";
  /**
   * Output frame where the move starts.
   */
  frame: number;
  /**
   * 1 is the whole frame, at rest.
   */
  zoom: number;
}
export interface TimelineKineticText {
  end: number;
  id: string;
  /**
   * Back to back from the scene's start.
   */
  lines: TimelineKineticLine[];
  start: number;
  type: "kinetic_text";
}
export interface TimelineKineticLine {
  end: number;
  start: number;
  words: TimelineHeadlineWord[];
}
export interface TimelineProof {
  badge: string | null;
  end: number;
  /**
   * Empty for an image on its own.
   */
  headline: TimelineHeadlineWord[];
  height: number | null;
  id: string;
  /**
   * The image, relative to the project.
   */
  src: string;
  start: number;
  subline: string | null;
  type: "proof";
  /**
   * Pixel size of the image, when ingest measured it.
   */
  width: number | null;
}
export interface TimelineLogoOutro {
  end: number;
  id: string;
  /**
   * Draw brand.mascot beside the wordmark.
   */
  mascot: boolean;
  /**
   * Set in type in place of the wordmark when brand has none.
   */
  name: string;
  start: number;
  /**
   * Empty for no tagline.
   */
  tagline: TimelineHeadlineWord[];
  type: "logo_outro";
  url: string | null;
}
export interface TimelineWord {
  emphasis: boolean;
  end_ms: number;
  id: string;
  /**
   * Output time.
   */
  start_ms: number;
  text: string;
}
