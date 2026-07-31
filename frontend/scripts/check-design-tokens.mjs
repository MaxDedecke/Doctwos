import { readFileSync, readdirSync } from 'node:fs';
import { extname, join } from 'node:path';

const roots = ['components'];
const sourceExtensions = new Set(['.ts', '.tsx', '.js', '.jsx']);
const palette = '(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black)';
const hardTailwindColor = new RegExp(`\\b(?:text|bg|border|ring|outline|shadow|fill|stroke|from|via|to)-${palette}(?:-|\\b)`);
const hexColor = /#[0-9a-f]{3,8}\b/i;
const failures = [];

function visit(path) {
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const child = join(path, entry.name);
    if (entry.isDirectory()) visit(child);
    if (!entry.isFile() || !sourceExtensions.has(extname(entry.name))) continue;

    readFileSync(child, 'utf8').split(/\r?\n/).forEach((line, index) => {
      if (hardTailwindColor.test(line) || hexColor.test(line)) {
        failures.push(`${child}:${index + 1}:${line.trim()}`);
      }
    });
  }
}

roots.forEach(visit);
if (failures.length) {
  console.error('Design-token violation: use ds token classes or CSS variables.');
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('Design-token check passed.');
