import type { CalculateMetadataFunction } from "remotion";
import type { Regions } from "./lib/camera";
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
  /** Brand caption font file relative to the public dir; null loads the bundled Inter. */
  font_file: string | null;
  /** Brand logo image relative to the public dir; null draws no logo. */
  logo_file: string | null;
};

export function formatOf(props: ReelProps): FormatSpec {
  const spec = props.timeline.formats.find((f) => f.name === props.format);
  if (spec === undefined) {
    const known = props.timeline.formats.map((f) => f.name).join(", ");
    throw new Error(`format ${props.format} is not in the timeline (it has ${known})`);
  }
  return spec;
}

export const reelMetadata: CalculateMetadataFunction<ReelProps> = ({ props }) => {
  const format = formatOf(props);
  return {
    width: format.width,
    height: format.height,
    fps: props.timeline.fps,
    durationInFrames: Math.max(1, props.timeline.duration_frames),
  };
};
