// Records page.html: a mark with element boxes, a click that shows #result, then a park off it.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const page = path.join(path.dirname(fileURLToPath(import.meta.url)), 'page.html');

export default async function take(r) {
  await r.goto('file://' + page);
  await r.wait(400);
  await r.mark('start', { title: '#title', body: '#body', go: '#go' });
  await r.click('#go');
  await r.mark('clicked');
  await r.wait(300);
  await r.mark('shown', { result: '#result' });
  await r.moveTo('#result');
  await r.park('#result');
  await r.wait(1500);
  if (process.env.RECORD_REFERENCE) await r.page.screenshot({ path: process.env.RECORD_REFERENCE });
  await r.mark('end');
}
