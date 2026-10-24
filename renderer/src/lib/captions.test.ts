import { describe, expect, it } from "vitest";
import type { TimelineEvent, TimelineWord } from "./timeline";
import { captionsHidden, pageCaptions, type PagingOptions } from "./captions";

/** Words 300 ms long with 50 ms gaps, starting at 0. */
function words(text: string, emphasis: string[] = []): TimelineWord[] {
  return text.split(" ").map((w, i) => ({
    id: `c1.w${i}`,
    text: w,
    start_ms: i * 350,
    end_ms: i * 350 + 300,
    emphasis: emphasis.includes(w),
  }));
}

// A monospace stand-in for measureText: 50 px per character.
const mono = (text: string) => text.length * 50;

const options: PagingOptions = {
  maxWords: 3,
  maxChars: null,
  maxWidth: 10_000,
  measure: mono,
  keepWithNext: [],
  uppercase: false,
};

const texts = (pages: ReturnType<typeof pageCaptions>) => pages.map((p) => p.words.map((w) => w.text).join(" "));

describe("pageCaptions", () => {
  it("caps each page at max_words_per_page", () => {
    const pages = pageCaptions(words("one two three four five six seven eight"), options);
    expect(texts(pages)).toEqual(["one two three", "four five six", "seven eight"]);
  });

  it("caps a page by measured width, so long Italian words page alone", () => {
    // 600 px wide: "la" + "precipitevolissimevolmente" (29 chars with spaces) would be 1450 px.
    const pages = pageCaptions(words("la precipitevolissimevolmente sua risposta"), { ...options, maxWidth: 600 });
    expect(texts(pages)).toEqual(["la", "precipitevolissimevolmente", "sua risposta"]);
  });

  it("shrinks a single word wider than the page to fit", () => {
    const pages = pageCaptions(words("precipitevolissimevolmente"), { ...options, maxWidth: 650 });
    expect(pages[0]?.fit).toBeCloseTo(650 / (26 * 50));
    expect(pageCaptions(words("ciao"), options)[0]?.fit).toBe(1);
  });

  it("measures the uppercased text when captions are uppercase", () => {
    const measured: string[] = [];
    pageCaptions(words("ciao a tutti"), {
      ...options,
      uppercase: true,
      measure: (t) => {
        measured.push(t);
        return 0;
      },
    });
    expect(measured).toContain("CIAO A TUTTI");
  });

  it("caps a page by characters from the language's caption rules", () => {
    const pages = pageCaptions(words("questo progetto funziona bene"), { ...options, maxChars: 16 });
    expect(texts(pages)).toEqual(["questo progetto", "funziona bene"]);
  });

  it("never ends a full page on a keep-with-next word", () => {
    const pages = pageCaptions(words("ho visto il gatto nero"), { ...options, keepWithNext: ["il"] });
    expect(texts(pages)).toEqual(["ho visto", "il gatto nero"]);
  });

  it("matches keep-with-next words regardless of case and punctuation", () => {
    const pages = pageCaptions(words("Ho visto Il gatto"), { ...options, keepWithNext: ["il"] });
    expect(texts(pages)[0]).toBe("Ho visto");
  });

  it("starts a new page after a sentence ends", () => {
    const pages = pageCaptions(words("Ciao. Come stai oggi?"), options);
    expect(texts(pages)).toEqual(["Ciao.", "Come stai oggi?"]);
  });

  it("starts a new page after a long silence", () => {
    const ws = words("prima dopo");
    ws[1] = { ...ws[1]!, start_ms: 2000, end_ms: 2300 };
    expect(texts(pageCaptions(ws, options))).toEqual(["prima", "dopo"]);
  });

  it("times pages by their words and keeps word timing and emphasis", () => {
    const pages = pageCaptions(words("uno due tre quattro cinque", ["due"]), options);
    expect(pages[0]).toMatchObject({ startMs: 0, endMs: 1050 });
    expect(pages[0]?.words[1]).toEqual({ text: "due", fromMs: 350, toMs: 650, emphasis: true });
    expect(pages[1]).toMatchObject({ startMs: 1050, endMs: 1700 });
  });

  it("keeps a page up through a short gap but clears it during a long one", () => {
    const ws = words("prima dopo");
    ws[1] = { ...ws[1]!, start_ms: 3000, end_ms: 3300 };
    const pages = pageCaptions(ws, options);
    expect(pages[0]?.endMs).toBe(300 + 500);
  });

  it("merges a lone word that ends a sentence into the previous page", () => {
    const pages = pageCaptions(words("Oggi ho visto tutto."), options);
    expect(texts(pages)).toEqual(["Oggi ho", "visto tutto."]);
  });

  it("merges a lone word into a previous page that still has room", () => {
    // Carrying "il" leaves "ab cd" one word short; carrying "di" past the character cap leaves "il" alone.
    const pages = pageCaptions(words("ab cd il di efghijklmn"), { ...options, maxChars: 12, keepWithNext: ["il", "di"] });
    expect(texts(pages)).toEqual(["ab cd il", "di efghijklmn"]);
  });

  it("rebalances three words and a lone word into two pages of two", () => {
    const pages = pageCaptions(words("uno due tre quattro"), options);
    expect(texts(pages)).toEqual(["uno due", "tre quattro"]);
  });

  it("starts a merged page at its first word and holds it as before", () => {
    const pages = pageCaptions(words("uno due tre quattro"), options);
    expect(pages[0]).toMatchObject({ startMs: 0, endMs: 700 });
    expect(pages[1]).toMatchObject({ startMs: 700, endMs: 1350 });
  });

  it("keeps a lone word after a long silence off the previous page", () => {
    const ws = words("uno due tre");
    ws[2] = { ...ws[2]!, start_ms: 2000, end_ms: 2300 };
    expect(texts(pageCaptions(ws, options))).toEqual(["uno due", "tre"]);
  });

  it("keeps a lone word after a sentence end off the previous page", () => {
    expect(texts(pageCaptions(words("Ho finito. Grazie"), options))).toEqual(["Ho finito.", "Grazie"]);
  });

  it("leaves a word alone between a sentence end and a long silence", () => {
    const ws = words("Ho finito. Allora vediamo");
    ws[3] = { ...ws[3]!, start_ms: 3000, end_ms: 3300 };
    expect(texts(pageCaptions(ws, options))).toEqual(["Ho finito.", "Allora", "vediamo"]);
  });

  it("keeps the character and width caps when a lone word is rebalanced", () => {
    const chars = pageCaptions(words("aa bb cc dddddddd"), { ...options, maxChars: 14 });
    expect(texts(chars)).toEqual(["aa bb", "cc dddddddd"]);
    // "cc dddddddd" is 11 characters, so no split fits under 10 and the lone word stays.
    const tight = pageCaptions(words("aa bb cc dddddddd"), { ...options, maxChars: 10 });
    expect(texts(tight)).toEqual(["aa bb cc", "dddddddd"]);
    const wide = pageCaptions(words("aa bb cc dddddddd"), { ...options, maxWidth: 500 });
    expect(texts(wide)).toEqual(["aa bb cc", "dddddddd"]);
  });

  it("never ends a rebalanced page on a keep-with-next word", () => {
    const pages = pageCaptions(words("io vedo il gatto nero"), { ...options, maxWords: 4, keepWithNext: ["il"] });
    expect(texts(pages)).toEqual(["io vedo", "il gatto nero"]);
  });

  it("pages a single word wider than the page alone and shrinks it", () => {
    const pages = pageCaptions(words("ciao precipitevolissimevolmente"), { ...options, maxWidth: 650 });
    expect(texts(pages)).toEqual(["ciao", "precipitevolissimevolmente"]);
    expect(pages[1]?.fit).toBeCloseTo(650 / (26 * 50));
  });

  it("returns no pages without words", () => {
    expect(pageCaptions([], options)).toEqual([]);
  });
});

describe("captionsHidden", () => {
  const broll = (mode: "full" | "pip"): TimelineEvent => ({
    type: "broll",
    asset: "b1",
    src: "media/b1.mp4",
    start: 30,
    end: 60,
    asset_in_s: 0,
    mode,
  });
  const image: TimelineEvent = { type: "image", asset: "i1", src: "media/i1.png", start: 90, end: 120, mode: "full", motion: "none" };

  it("keeps captions over full-frame B-roll by default", () => {
    expect(captionsHidden(false, [broll("full")], 40)).toBe(false);
  });

  it("hides them only while a full-frame B-roll clip or image is on screen, when configured", () => {
    const events = [broll("full"), image];
    expect(captionsHidden(true, events, 29)).toBe(false);
    expect(captionsHidden(true, events, 30)).toBe(true);
    expect(captionsHidden(true, events, 59)).toBe(true);
    expect(captionsHidden(true, events, 60)).toBe(false);
    expect(captionsHidden(true, events, 100)).toBe(true);
  });

  it("keeps them over a picture-in-picture card", () => {
    expect(captionsHidden(true, [broll("pip")], 40)).toBe(false);
  });
});
