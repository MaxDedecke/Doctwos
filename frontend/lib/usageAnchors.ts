/**
 * Textstelle einer Verwendung (Aufruf, Typname, Import, COPY, Feldzugriff …) im Quelltext. Die
 * Kante liefert die Zeile; Java-Kanten tragen zusätzlich Spalten (0-basiert, Ende exklusiv), bei
 * COBOL/JCL wird der Name des Ziels in der Anweisung gesucht.
 */
import { wordRegex, type EntityAnchor } from './entityAnchors';

export interface UsageReference<T = unknown> {
  edge_id: number;
  type: string;
  dst_name: string;
  resolution?: string;
  line: number;
  end_line?: number | null;
  start_column?: number | null;
  end_column?: number | null;
  target: T & { name: string };
}

const simpleName = (value: string) => value.split(/[.#:/]+/).filter(Boolean).pop() ?? value;

function columnAnchor(ref: UsageReference, text: string): EntityAnchor | null {
  const sc = ref.start_column;
  const ec = ref.end_column;
  if (sc == null || ec == null || ec <= sc || ec > text.length) return null;
  let start = sc;
  let segment = text.slice(sc, ec);

  if (ref.type === 'IMPORTS') {
    const match = /^(\s*import\s+(?:static\s+)?)([\w.$*]+)/.exec(segment);
    if (!match) return null;
    start = sc + match[1].length;
    segment = match[2];
  } else {
    const lead = segment.length - segment.trimStart().length;
    start += lead;
    segment = segment.trimStart();
    const cut = segment.search(/[(<]/);
    if (cut >= 0) segment = segment.slice(0, cut);
    segment = segment.trimEnd();
  }
  if (!segment) return null;

  // Qualifizierte Namen (`a.b.c`, `Typ::methode`): das Segment, das das Ziel benennt, sonst das letzte.
  const wanted = simpleName(ref.target.name).toLowerCase();
  const parts = [...segment.matchAll(/[\w$*-]+/g)];
  const pick = parts.find(p => p[0].toLowerCase() === wanted) ?? parts[parts.length - 1];
  if (!pick || pick.index === undefined) return null;
  return { line: ref.line, startColumn: start + pick.index + 1, endColumn: start + pick.index + pick[0].length + 1 };
}

export function computeUsageAnchor(ref: UsageReference, getLine: (lineNumber: number) => string, lineCount: number): EntityAnchor | null {
  if (!ref.line || ref.line > lineCount) return null;
  const sameLine = !ref.end_line || ref.end_line <= 0 || ref.end_line === ref.line;
  if (sameLine) {
    const byColumn = columnAnchor(ref, getLine(ref.line));
    if (byColumn) return byColumn;
  }
  const last = Math.min(lineCount, Math.max(ref.line, ref.end_line ?? ref.line), ref.line + 8);
  const names = [...new Set([simpleName(ref.dst_name), ref.dst_name, ref.target.name].filter(Boolean))];
  for (const name of names) {
    const regex = wordRegex(name);
    for (let lineNumber = ref.line; lineNumber <= last; lineNumber++) {
      const match = regex.exec(getLine(lineNumber));
      if (match) return { line: lineNumber, startColumn: match.index + 1, endColumn: match.index + 1 + match[0].length };
    }
  }
  return null;
}
