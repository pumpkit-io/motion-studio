import { describe, expect, it } from "vitest";
import type { TimelineWord } from "./timeline";
import { pageCaptions, type PagingOptions } from "./captions";

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
    const pages = pageCaptions(words("one two three four five six seven"), options);
    expect(texts(pages)).toEqual(["one two three", "four five six", "seven"]);
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
    const pages = pageCaptions(words("uno due tre quattro", ["due"]), options);
    expect(pages[0]).toMatchObject({ startMs: 0, endMs: 1050 });
    expect(pages[0]?.words[1]).toEqual({ text: "due", fromMs: 350, toMs: 650, emphasis: true });
    expect(pages[1]).toMatchObject({ startMs: 1050, endMs: 1350 });
  });

  it("keeps a page up through a short gap but clears it during a long one", () => {
    const ws = words("prima dopo");
    ws[1] = { ...ws[1]!, start_ms: 3000, end_ms: 3300 };
    const pages = pageCaptions(ws, options);
    expect(pages[0]?.endMs).toBe(300 + 500);
  });

  it("returns no pages without words", () => {
    expect(pageCaptions([], options)).toEqual([]);
  });
});
