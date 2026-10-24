import { Img, staticFile, useCurrentFrame } from "remotion";
import { logoBox, logoHidden } from "../lib/safezones";
import type { FormatSpec, TimelineEvent } from "../lib/timeline";

export const Logo: React.FC<{ file: string; format: FormatSpec; events: TimelineEvent[] }> = ({ file, format, events }) => {
  const frame = useCurrentFrame();
  if (logoHidden(events, frame)) return null;
  const box = logoBox(format);
  return (
    <Img
      src={staticFile(file)}
      style={{ position: "absolute", top: box.top, right: box.right, height: box.height, width: "auto", opacity: 0.92 }}
    />
  );
};
