// Runs one recording script in headless Chromium: `node runner.mjs <config.json>`.
// Exit 1: the script failed (its error on stderr). Exit 3: the browser could not run.

import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { createStudio } from './studio.mjs';

const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const viewport = { width: config.width, height: config.height };
const scriptName = path.basename(config.script);

function scriptFailed(err) {
  const message = err instanceof Error ? err.message : String(err);
  // Only the script's own frames help its author; Playwright's internals do not.
  const frames = String(err?.stack ?? '')
    .split('\n')
    .filter(line => line.includes(scriptName))
    .map(line => line.trim());
  console.error(`error: ${message}`);
  for (const line of frames.slice(0, 3)) console.error(`  ${line}`);
  process.exitCode = 1;
}

let take;
try {
  take = await import(pathToFileURL(config.script).href);
  if (typeof take.default !== 'function') {
    throw new Error(`${scriptName} must export a default async function take(r)`);
  }
} catch (err) {
  scriptFailed(err);
}

if (process.exitCode !== 1) {
  const { chromium } = createRequire(path.join(config.playwright, 'package.json'))('playwright');
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (err) {
    console.error(`error: Chromium did not start: ${err.message}`);
    process.exit(3);
  }
  try {
    const context = await browser.newContext({
      ...(take.contextOptions ?? {}),
      viewport,
      deviceScaleFactor: 1,
    });
    context.setDefaultTimeout(30_000);
    const { studio, finish } = await createStudio({
      context,
      out: config.out,
      quality: config.quality,
      viewport,
    });
    await take.default(studio);
    await finish();
  } catch (err) {
    scriptFailed(err);
  } finally {
    await browser.close().catch(() => {});
  }
}
