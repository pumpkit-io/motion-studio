import { createTikTokStyleCaptions, type Caption } from "@remotion/captions";
import type { TimelineWord } from "./timeline";

/** A gap this long between words always starts a new page. */
const SILENCE_BREAK_MS = 700;
/** How long a page stays up after its last word when the next page is not due yet. */
const HOLD_MS = 500;
const SENTENCE_END = /[.!?…]["'»”)]*$/;

export type PagingOptions = {
  maxWords: number;
  /** From the language's caption rules; null for no character cap. */
  maxChars: number | null;
  /** Widest line in px, measured with `measure`. */
  maxWidth: number;
  /** Width in px of `text` in the caption font. */
  measure: (text: string) => number;
  /** Words that never end a page that broke because it was full. */
  keepWithNext: readonly string[];
  uppercase: boolean;
};

export type PageWord = { text: string; fromMs: number; toMs: number; emphasis: boolean };

export type CaptionPage = {
  startMs: number;
  endMs: number;
  words: PageWord[];
  /** Font scale that fits the page in `maxWidth`: below 1 only for a single over-long word. */
  fit: number;
};

/**
 * Pages kept words for word-by-word captions. A page closes when the next word would break the
 * word, character or width cap, after a sentence end, and before a long silence.
 */
export function pageCaptions(words: readonly TimelineWord[], options: PagingOptions): CaptionPage[] {
  if (words.length === 0) return [];
  const display = (ws: readonly TimelineWord[]) => {
    const text = ws.map((w) => w.text).join(" ");
    return options.uppercase ? text.toUpperCase() : text;
  };
  const fits = (ws: readonly TimelineWord[]) => {
    const text = display(ws);
    return (
      ws.length <= options.maxWords &&
      (options.maxChars === null || text.length <= options.maxChars) &&
      options.measure(text) <= options.maxWidth
    );
  };
  const keep = new Set(options.keepWithNext.map(normalise));

  const pages: TimelineWord[][] = [];
  let page: TimelineWord[] = [];
  words.forEach((word, i) => {
    if (page.length > 0 && !fits([...page, word])) {
      const last = page[page.length - 1]!;
      const carried = page.length > 1 && keep.has(normalise(last.text)) ? [page.pop()!] : [];
      pages.push(page);
      page = carried;
    }
    page.push(word);
    const next = words[i + 1];
    if (next === undefined || SENTENCE_END.test(word.text) || next.start_ms - word.end_ms >= SILENCE_BREAK_MS) {
      pages.push(page);
      page = [];
    }
  });

  const captions: Caption[] = pages.flatMap((ws) =>
    ws.map((w, i) => ({
      text: ` ${w.text}`,
      startMs: w.start_ms,
      endMs: w.end_ms,
      timestampMs: (w.start_ms + w.end_ms) / 2,
      confidence: null,
      pageBreakAfter: i === ws.length - 1,
    })),
  );
  const { pages: tiktok } = createTikTokStyleCaptions({ captions, combineTokensWithinMilliseconds: Infinity });

  return tiktok.map((p, k) => {
    const ws = pages[k]!;
    const lastEnd = ws[ws.length - 1]!.end_ms;
    const due = p.startMs + p.durationMs;
    const isLast = k === tiktok.length - 1;
    return {
      startMs: p.startMs,
      endMs: isLast ? due : Math.min(due, lastEnd + HOLD_MS),
      words: p.tokens.map((t, i) => ({
        text: t.text.trim(),
        fromMs: t.fromMs,
        toMs: t.toMs,
        emphasis: ws[i]!.emphasis,
      })),
      fit: Math.min(1, options.maxWidth / Math.max(1, options.measure(display(ws)))),
    };
  });
}

function normalise(word: string): string {
  return word.toLowerCase().replace(/[^\p{L}\p{N}'’]/gu, "");
}
