import { Composition } from "remotion";
import { Reel } from "./Reel";

// Placeholder metadata: a later ticket derives it from the timeline props via calculateMetadata.
export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Reel"
      component={Reel}
      durationInFrames={30}
      fps={30}
      width={1080}
      height={1920}
    />
  );
};
