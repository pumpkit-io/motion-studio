import { AbsoluteFill } from "remotion";
import { Broll } from "./layers/Broll";
import { BaseVideo } from "./layers/BaseVideo";
import { Captions } from "./layers/Captions";
import { Logo } from "./layers/Logo";
import { Titles } from "./layers/Titles";
import { useCaptionFont } from "./lib/fonts";
import { formatOf, type ReelProps } from "./props";

/** The finished video for one format: camera-moved A-roll, B-roll, logo, titles, then captions on top. */
export const Reel: React.FC<ReelProps> = (props) => {
  const { timeline } = props;
  const format = formatOf(props);
  const font = useCaptionFont(timeline.captions.font, props.font_file);
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {timeline.runs.length > 0 ? <BaseVideo props={props} format={format} /> : null}
      <Broll events={timeline.events} format={format} />
      {props.logo_file !== null ? <Logo file={props.logo_file} format={format} events={timeline.events} /> : null}
      <Titles events={timeline.events} format={format} brand={timeline.brand} fontFamily={font.family} />
      <Captions words={timeline.words} settings={timeline.captions} brand={timeline.brand} format={format} font={font} />
    </AbsoluteFill>
  );
};
