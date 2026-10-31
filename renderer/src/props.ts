import type { CalculateMetadataFunction } from "remotion";
import type { Regions } from "./lib/camera";
import type { BundledFont } from "./lib/fonts";
import type { FormatSpec, Size, Timeline } from "./lib/timeline";

/** Props of the `Reel` composition: what `render/compose.py` writes to `build/props_<fmt>.json`. */
export type ReelProps = {
  timeline: Timeline;
  /** One of `timeline.formats[].name`. */
  format: FormatSpec["name"];
  /** Pixel size of `video`. */
  source: Size;
  /** Each A-roll clip's rectangle in `video`; a run's crop centre is a fraction of its clip's. */
  regions: Regions;
  /** The assembled A-roll, relative to the public dir. */
  video: string;
  /** Brand caption font file relative to the public dir; null loads `bundled_font`. */
  font_file: string | null;
  /** The bundled family to load when there is no brand font file; null when there is one. */
  bundled_font: BundledFont | null;
  /** Brand logo image relative to the public dir; null draws no logo. */
  logo_file: string | null;
}

/** Props of the `Product` composition: what `render/compose.py` writes for a product timeline. */
export type ProductProps = {
  timeline: Timeline;
  format: FormatSpec["name"];
  /** Brand font file relative to the public dir; null loads the bundled Inter. */
  font_file: string | null;
  /** Written for both compositions; product scenes load Inter whatever it names. */
  bundled_font: BundledFont | null;
  /** Brand logo image relative to the public dir; null draws no logo. */
  logo_file: string | null;
  /** Brand wordmark and mascot sprite sheet or GIF relative to the public dir; null when not configured. */
  wordmark_file: string | null;
  mascot_file: string | null;
}

export function formatOf(props: Pick<ReelProps, "timeline" | "format">): FormatSpec {
  const spec = props.timeline.formats.find((f) => f.name === props.format);
  if (spec === undefined) {
    const known = props.timeline.formats.map((f) => f.name).join(", ");
    throw new Error(`format ${props.format} is not in the timeline (it has ${known})`);
  }
  return spec;
}

export const reelMetadata: CalculateMetadataFunction<ReelProps> = ({ props }) => metadataOf(props);

export const productMetadata: CalculateMetadataFunction<ProductProps> = ({ props }) => metadataOf(props);

function metadataOf(props: Pick<ReelProps, "timeline" | "format">) {
  const format = formatOf(props);
  return {
    width: format.width,
    height: format.height,
    fps: props.timeline.fps,
    durationInFrames: Math.max(1, props.timeline.duration_frames),
  };
}
