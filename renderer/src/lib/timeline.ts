export type {
  Crop,
  FormatSpec,
  Run,
  SafeZone,
  Timeline,
  TimelineBrand,
  TimelineBroll,
  TimelineCaptions,
  TimelineFootage,
  TimelineHeadlineWord,
  TimelineImage,
  TimelineKineticText,
  TimelineLogoOutro,
  TimelineMascot,
  TimelineProof,
  TimelinePush,
  TimelineTitle,
  TimelineTitleCard,
  TimelineWord,
  TimelineZoom,
} from "../types.gen";
import type { Timeline } from "../types.gen";

export type TimelineEvent = Timeline["events"][number];

export type TimelineScene = Timeline["scenes"][number];

export type Size = { width: number; height: number };
