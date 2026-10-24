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
  events: (TimelineZoom | TimelinePush | TimelineBroll | TimelineImage | TimelineTitle)[];
  formats: FormatSpec[];
  fps: number;
  language: string | null;
  /**
   * Music bed relative to the project; null for none.
   */
  music_path: string | null;
  runs: Run[];
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
   * #RRGGBB; #RGB is accepted and expanded.
   */
  primary: string;
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
