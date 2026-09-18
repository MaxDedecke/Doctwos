import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');

const srcDir = path.join(rootDir, 'node_modules', 'monaco-editor', 'min', 'vs');
const destDir = path.join(rootDir, 'public', 'monaco', 'vs');

if (!fs.existsSync(srcDir)) {
  console.warn('[copy-monaco] node_modules/monaco-editor/min/vs not found, skipping copy');
  process.exit(0);
}

fs.mkdirSync(destDir, { recursive: true });
fs.cpSync(srcDir, destDir, { recursive: true });
console.log(`[copy-monaco] Copied Monaco Editor assets from ${srcDir} to ${destDir}`);
