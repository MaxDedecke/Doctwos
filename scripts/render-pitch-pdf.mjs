#!/usr/bin/env node
/**
 * Rendert ein Pitch-Deck aus docs/pitch/ als PDF im Format 16:9.
 *
 * Das Deck ist eine Bildschirmfassung: .slide-inner steht bis zum
 * IntersectionObserver-Callback auf opacity:0. Ohne das hier erzwungene
 * .in-view drucken die Folien leer. Das Seitenformat entspricht exakt der
 * Entwurfsbreite von 1600x900 CSS-px, damit die Folien nicht ueberlaufen.
 *
 * Puppeteer ist keine Abhaengigkeit des Repos:
 *   npx --yes puppeteer@latest browsers install chrome
 *   npm i puppeteer   (im Verzeichnis, aus dem das Skript laeuft)
 *
 * Aufruf:
 *   node scripts/render-pitch-pdf.mjs docs/pitch/<deck>.html [<ziel>.pdf] [--light]
 */
import { resolve } from 'node:path';

const args = process.argv.slice(2);
const light = args.includes('--light');
const [src, dst] = args.filter((a) => !a.startsWith('--'));

if (!src) {
  console.error('Aufruf: node scripts/render-pitch-pdf.mjs <deck>.html [<ziel>.pdf] [--light]');
  process.exit(1);
}
const input = resolve(src);
const output = resolve(dst || input.replace(/\.html$/, '.pdf'));

let puppeteer;
try {
  puppeteer = (await import('puppeteer')).default;
} catch {
  console.error('puppeteer fehlt. Siehe Kopf dieser Datei.');
  process.exit(1);
}

const browser = await puppeteer.launch({
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--font-render-hinting=none'],
});
const page = await browser.newPage();
await page.emulateMediaFeatures([
  { name: 'prefers-color-scheme', value: light ? 'light' : 'dark' },
]);
await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 2 });
await page.goto('file://' + input, { waitUntil: 'networkidle0', timeout: 120000 });
await page.evaluate((theme) => {
  document.documentElement.setAttribute('data-theme', theme);
}, light ? 'light' : 'dark');
await page.evaluate(() => document.fonts.ready);
// Einblend-Animation ueberspringen - sonst bleiben die Folien leer
await page.evaluate(() => {
  document.querySelectorAll('.slide').forEach((s) => s.classList.add('in-view'));
});
await new Promise((r) => setTimeout(r, 1500));
await page.pdf({
  path: output,
  width: '16.667in',
  height: '9.375in',
  printBackground: true,
  preferCSSPageSize: true,
  margin: { top: 0, right: 0, bottom: 0, left: 0 },
});
await browser.close();
console.log(`${output} geschrieben (${light ? 'hell' : 'dunkel'}, 16:9)`);
