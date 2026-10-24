export type {
  Crop,
  FormatSpec,
  Run,
  SafeZone,
  Timeline,
  TimelineBrand,
  TimelineBroll,
  TimelineCaptions,
  TimelineImage,
  TimelinePush,
  TimelineTitle,
  TimelineWord,
  TimelineZoom,
} from "../types.gen";
import type { Timeline } from "../types.gen";

export type TimelineEvent = Timeline["events"][number];

export type Size = { width: number; height: number };
