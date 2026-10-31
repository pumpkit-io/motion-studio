export type {
  Crop,
  FormatSpec,
  Run,
  SafeZone,
  Timeline,
  TimelineBrand,
  TimelineBroll,
  TimelineCaptionPill,
  TimelineCaptions,
  TimelineFlash,
  TimelineFootage,
  TimelineHeadlineWord,
  TimelineHighlight,
  TimelineImage,
  TimelineKineticText,
  TimelineLogoOutro,
  TimelineMask,
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
