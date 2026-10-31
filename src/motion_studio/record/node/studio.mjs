// The helper library a recording script drives: `export default async function take(r) {...}`
// receives the object createStudio returns. Reference: docs/cli.md, `record web`.

import fs from 'node:fs';
import path from 'node:path';

// Marker and element names become IDs such as `c2.m.v1_shown`, so they never hold a dot.
const NAME = /^[A-Za-z0-9_][A-Za-z0-9_-]*$/;
const TAIL_MS = 500;
const PARK_MARGIN = 60;
const EDGE_INSET = 8;

// Headless Chromium draws no cursor, so every page gets this one, driven by real mouse events.
const CURSOR_SCRIPT = `(() => {
  if (window !== window.top || window.__msCursor) return;
  window.__msCursor = true;
  const make = () => {
    const c = document.createElement('div');
    c.setAttribute('data-recorder-cursor', '');
    c.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24"><path d="M4 2 L4 19 L8.5 14.8 L11.6 21.5 L14.4 20.2 L11.3 13.6 L17.5 13.4 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, {position: 'fixed', left: '-100px', top: '-100px', zIndex: 2147483647, pointerEvents: 'none', transform: 'translate(-4px,-2px)', transformOrigin: '4px 2px', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.35))', transition: 'transform .08s'});
    document.documentElement.appendChild(c);
    let moved = false;
    const place = (x, y) => { c.style.left = x + 'px'; c.style.top = y + 'px'; };
    document.addEventListener('mousemove', e => { moved = true; place(e.clientX, e.clientY); }, true);
    document.addEventListener('mousedown', e => {
      c.style.transform = 'translate(-4px,-2px) scale(.82)';
      const r = document.createElement('div');
      Object.assign(r.style, {position: 'fixed', left: (e.clientX - 22) + 'px', top: (e.clientY - 22) + 'px', width: '44px', height: '44px', borderRadius: '50%', background: 'rgba(234,108,58,.35)', border: '2px solid rgba(234,108,58,.9)', zIndex: 2147483646, pointerEvents: 'none', transition: 'transform .45s ease-out, opacity .45s ease-out', transform: 'scale(.3)', opacity: '1'});
      document.documentElement.appendChild(r);
      requestAnimationFrame(() => requestAnimationFrame(() => { r.style.transform = 'scale(1.4)'; r.style.opacity = '0'; }));
      setTimeout(() => r.remove(), 600);
    }, true);
    document.addEventListener('mouseup', () => { c.style.transform = 'translate(-4px,-2px)'; }, true);
    // A new document has had no mousemove yet, so it asks the recorder where the cursor is.
    window.__recorderCursorAt?.().then(p => { if (!moved) place(p.x, p.y); });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', make); else make();
})();`;

const easeInOut = t => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const round1 = v => Math.round(v * 10) / 10;
const now = () => Date.now() / 1000;

export async function createStudio({ context, out, quality, viewport }) {
  const frames = [];
  const writes = [];
  const markers = [];
  const track = [];
  let capturing = false;
  let down = false;
  let cursor = { x: Math.round(viewport.width / 2), y: Math.round(viewport.height * 0.6) };
  const sample = () => track.push({ t: now(), x: cursor.x, y: cursor.y, down });

  await context.exposeBinding('__recorderCursorAt', () => cursor);
  await context.addInitScript(CURSOR_SCRIPT);
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  fs.mkdirSync(path.join(out, 'f'), { recursive: true });

  cdp.on('Page.screencastFrame', ({ data, metadata, sessionId }) => {
    const file = `f/${String(frames.length).padStart(6, '0')}.jpg`;
    frames.push({ file, t: metadata.timestamp ?? now() });
    writes.push(fs.promises.writeFile(path.join(out, file), Buffer.from(data, 'base64')));
    // Frames still arrive while the session closes; their acks fail and nothing waits on them.
    cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
  });

  const isLocator = target => target && typeof target.boundingBox === 'function';
  const locate = target => (typeof target === 'string' ? page.locator(target) : target);
  const describe = target => (typeof target === 'string' ? `'${target}'` : String(target));

  async function boxOf(target) {
    if (typeof target === 'object' && !isLocator(target) && 'w' in target && 'h' in target) {
      return { x: target.x, y: target.y, w: target.w, h: target.h };
    }
    const box = await locate(target).boundingBox();
    if (box === null) throw new Error(`${describe(target)} is not visible on the page`);
    return { x: box.x, y: box.y, w: box.width, h: box.height };
  }

  async function pointOf(target, offset) {
    if (typeof target === 'object' && !isLocator(target) && !('w' in target)) {
      return { x: target.x, y: target.y };
    }
    if (typeof target === 'string' || isLocator(target)) await locate(target).scrollIntoViewIfNeeded();
    const box = await boxOf(target);
    return { x: box.x + box.w / 2 + (offset?.x ?? 0), y: box.y + box.h / 2 + (offset?.y ?? 0) };
  }

  async function startCapture() {
    if (capturing) return;
    await page.mouse.move(cursor.x, cursor.y);
    await cdp.send('Page.startScreencast', {
      format: 'jpeg',
      quality,
      maxWidth: viewport.width,
      maxHeight: viewport.height,
      everyNthFrame: 1,
    });
    capturing = true;
    sample();
  }

  const r = {
    page,
    context,
    viewport: { ...viewport },

    /** Where the fake cursor is now, in viewport pixels. */
    get cursor() {
      return { ...cursor };
    },

    /** Open a page; the first one starts the capture once it has loaded. */
    async goto(url, options = {}) {
      await page.goto(url, { waitUntil: 'load', ...options });
      await startCapture();
    },

    /** Start capturing the page as it is, for scripts that load it without `goto`. */
    startCapture,

    /** Glide the cursor to an element's centre (plus `offset`) or a point, eased in and out. */
    async moveTo(target, { offset, ms, park } = {}) {
      const dest = await pointOf(target, offset);
      const from = { ...cursor };
      const dist = Math.hypot(dest.x - from.x, dest.y - from.y);
      const duration = ms ?? Math.min(1100, 300 + dist * 0.5);
      const steps = Math.max(6, Math.round(duration / 16));
      for (let i = 1; i <= steps; i++) {
        const e = easeInOut(i / steps);
        cursor = { x: round1(from.x + (dest.x - from.x) * e), y: round1(from.y + (dest.y - from.y) * e) };
        await page.mouse.move(cursor.x, cursor.y);
        sample();
        await page.waitForTimeout(duration / steps);
      }
      if (park) await r.park(park);
    },

    /** Glide to the target and click it, with a ripple under the cursor. */
    async click(target, { offset, ms, park } = {}) {
      await r.moveTo(target, { offset, ms });
      await page.waitForTimeout(120);
      await page.mouse.down();
      down = true;
      sample();
      await page.waitForTimeout(90);
      await page.mouse.up();
      down = false;
      sample();
      await page.waitForTimeout(200);
      if (park) await r.park(park);
    },

    /** Click the target (skipped when it is null) and type `text` key by key. */
    async type(target, text, { delay = 45, park } = {}) {
      if (target !== null && target !== undefined) await r.click(target);
      await page.keyboard.type(text, { delay });
      if (park) await r.park(park);
    },

    async press(key, { park } = {}) {
      await page.keyboard.press(key);
      if (park) await r.park(park);
    },

    /**
     * Move the cursor just off `region` (a selector, Locator, {x, y, w, h} box, or a list of
     * them) so it never covers what the shot is about. A cursor already clear stays put.
     */
    async park(region, { margin = PARK_MARGIN } = {}) {
      const boxes = await Promise.all((Array.isArray(region) ? region : [region]).map(boxOf));
      const left = Math.min(...boxes.map(b => b.x)) - margin;
      const top = Math.min(...boxes.map(b => b.y)) - margin;
      const right = Math.max(...boxes.map(b => b.x + b.w)) + margin;
      const bottom = Math.max(...boxes.map(b => b.y + b.h)) + margin;
      const { x, y } = cursor;
      if (x < left || x > right || y < top || y > bottom) return;
      const fits = p =>
        p.x >= EDGE_INSET && p.x <= viewport.width - EDGE_INSET &&
        p.y >= EDGE_INSET && p.y <= viewport.height - EDGE_INSET;
      const options = [
        { x: left, y },
        { x: right, y },
        { x, y: top },
        { x, y: bottom },
      ].filter(fits);
      const corners = [
        { x: EDGE_INSET, y: EDGE_INSET },
        { x: viewport.width - EDGE_INSET, y: EDGE_INSET },
        { x: EDGE_INSET, y: viewport.height - EDGE_INSET },
        { x: viewport.width - EDGE_INSET, y: viewport.height - EDGE_INSET },
      ];
      const distance = p => Math.hypot(p.x - x, p.y - y);
      const cx = (left + right) / 2;
      const cy = (top + bottom) / 2;
      const dest = options.length
        ? options.reduce((a, b) => (distance(b) < distance(a) ? b : a))
        : corners.reduce((a, b) =>
            Math.hypot(b.x - cx, b.y - cy) > Math.hypot(a.x - cx, a.y - cy) ? b : a);
      await r.moveTo(dest);
    },

    /**
     * Record marker `name` now, on the clip's clock, with the on-screen box of each element in
     * `elements` ({name: selector | Locator | {x, y, w, h}}), addressed later as `<clip>.e.<name>`.
     */
    async mark(name, elements = {}) {
      const t = now();
      if (!capturing) throw new Error(`mark('${name}') before the capture started: call r.goto() first`);
      if (!NAME.test(name)) throw new Error(`marker name '${name}' may only hold letters, digits, _ and -`);
      if (markers.some(m => m.name === name)) throw new Error(`marker '${name}' is already marked`);
      const boxes = [];
      for (const [element, target] of Object.entries(elements)) {
        if (!NAME.test(element)) {
          throw new Error(`element name '${element}' may only hold letters, digits, _ and -`);
        }
        const box = await boxOf(target).catch(err => {
          throw new Error(`mark('${name}'): element '${element}': ${err.message}`);
        });
        boxes.push({ name: element, ...box });
      }
      markers.push({ name, t, elements: boxes });
    },

    async wait(ms) {
      await page.waitForTimeout(ms);
    },
  };

  // Stops the capture and writes take.json for the Python side to encode.
  const finish = async () => {
    if (!capturing) throw new Error('the script never started the capture: open a page with r.goto()');
    await page.waitForTimeout(TAIL_MS);
    const end = now();
    await cdp.send('Page.stopScreencast');
    await Promise.all(writes);
    if (frames.length === 0) throw new Error('the browser sent no frames');
    const take = { viewport, frames, end, markers, cursor: track };
    fs.writeFileSync(path.join(out, 'take.json'), JSON.stringify(take));
  };
  return { studio: r, finish };
}
