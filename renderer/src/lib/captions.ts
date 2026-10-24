import { createTikTokStyleCaptions, type Caption } from "@remotion/captions";
import type { TimelineEvent, TimelineWord } from "./timeline";

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
 * word, character or width cap, after a sentence end, and before a long silence. A one-word page
 * then joins or rebalances with a neighbour, unless a sentence end or long silence cuts it off.
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

  // `hardAfter[k]` is true when page k closed at a sentence end, before a long silence, or at the last word.
  const pages: TimelineWord[][] = [];
  const hardAfter: boolean[] = [];
  let page: TimelineWord[] = [];
  words.forEach((word, i) => {
    if (page.length > 0 && !fits([...page, word])) {
      const last = page[page.length - 1]!;
      const carried = page.length > 1 && keep.has(normalise(last.text)) ? [page.pop()!] : [];
      pages.push(page);
      hardAfter.push(false);
      page = carried;
    }
    page.push(word);
    const next = words[i + 1];
    if (next === undefined || SENTENCE_END.test(word.text) || next.start_ms - word.end_ms >= SILENCE_BREAK_MS) {
      pages.push(page);
      hardAfter.push(true);
      page = [];
    }
  });

  // Splits `ws` into two pages of at least two words each, or returns null when no split keeps the caps.
  const rebalance = (ws: TimelineWord[]): [TimelineWord[], TimelineWord[]] | null => {
    const sizes = [];
    for (let n = 2; n <= ws.length - 2; n++) sizes.push(n);
    sizes.sort((a, b) => Math.abs(ws.length - 2 * a) - Math.abs(ws.length - 2 * b) || b - a);
    for (const n of sizes) {
      const head = ws.slice(0, n);
      const tail = ws.slice(n);
      if (fits(head) && fits(tail) && !keep.has(normalise(head[n - 1]!.text))) return [head, tail];
    }
    return null;
  };

  // A lone word joins a neighbour across a break that is not hard: the previous page first, else the next.
  // The start and end of the words count as hard, so a lone word never crosses a sentence end or silence.
  const absorb = (k: number, into: number): boolean => {
    const lo = Math.min(k, into);
    const merged = [...pages[lo]!, ...pages[lo + 1]!];
    if (fits(merged)) {
      pages.splice(lo, 2, merged);
      hardAfter.splice(lo, 1);
      return true;
    }
    const split = rebalance(merged);
    if (split === null) return false;
    pages.splice(lo, 2, ...split);
    hardAfter[lo] = false;
    return true;
  };
  for (let k = 0; k < pages.length; k++) {
    if (pages[k]!.length !== 1 || !fits(pages[k]!)) continue;
    const prevOpen = k > 0 && !hardAfter[k - 1];
    const nextOpen = k < pages.length - 1 && !hardAfter[k];
    const count = pages.length;
    if (prevOpen && absorb(k, k - 1)) {
      if (pages.length < count) k--;
    } else if (nextOpen) {
      absorb(k, k + 1);
    }
  }

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

/** True while `hide` is on and a full-frame B-roll clip or image covers the speaker at `frame`. */
export function captionsHidden(hide: boolean, events: readonly TimelineEvent[], frame: number): boolean {
  if (!hide) return false;
  return events.some(
    (e) => (e.type === "broll" || e.type === "image") && e.mode === "full" && frame >= e.start && frame < e.end,
  );
}
