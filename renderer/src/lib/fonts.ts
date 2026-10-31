import { loadFont } from "@remotion/fonts";
import { useState } from "react";
import { staticFile } from "remotion";
import interLatin500 from "@fontsource/inter/files/inter-latin-500-normal.woff2";
import interLatinExt500 from "@fontsource/inter/files/inter-latin-ext-500-normal.woff2";
import interLatin from "@fontsource/inter/files/inter-latin-800-normal.woff2";
import interLatinExt from "@fontsource/inter/files/inter-latin-ext-800-normal.woff2";

export const FONT_WEIGHT = 800;
/** The lighter weight product sublines use; captions only need FONT_WEIGHT. */
export const TEXT_WEIGHT = 500;

const INTER: Record<number, { latin: string; latinExt: string }> = {
  [FONT_WEIGHT]: { latin: interLatin, latinExt: interLatinExt },
  [TEXT_WEIGHT]: { latin: interLatin500, latinExt: interLatinExt500 },
};

// Unicode ranges copied from @fontsource/inter 5.3.0's 800.css.
const LATIN =
  "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD";
const LATIN_EXT =
  "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF";

export type LoadedFont = { family: string; ready: boolean };

/**
 * Loads the brand font file when there is one, else the bundled Inter, which keeps renders
 * offline. `ready` turns true once the font is in `document.fonts`, so text can be measured.
 */
export function useCaptionFont(
  brandFamily: string,
  fontFile: string | null,
  weights: readonly (typeof FONT_WEIGHT | typeof TEXT_WEIGHT)[] = [FONT_WEIGHT],
): LoadedFont {
  const family = fontFile === null ? "Inter" : brandFamily;
  const [ready, setReady] = useState(false);
  // Starts loading during the first render, so loadFont's delayRender holds the first frame.
  useState(() => {
    const loads =
      fontFile === null
        ? weights.flatMap((weight) => [
            loadFont({ family, url: INTER[weight]!.latin, weight: String(weight), unicodeRange: LATIN }),
            loadFont({ family, url: INTER[weight]!.latinExt, weight: String(weight), unicodeRange: LATIN_EXT }),
          ])
        : [loadFont({ family, url: staticFile(fontFile) })];
    void Promise.all(loads).then(() => setReady(true));
    return null;
  });
  return { family, ready };
}
