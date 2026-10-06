/**
 * Erkennung von PERFORM- und MOVE-Anweisungen im angezeigten COBOL-Quelltext. Der Editor
 * macht sie damit klickbar (anpinnen, zum Absatz springen, Feld erfragen), ohne dass der
 * Parser dafür eigene Entities anlegen muss; Absätze und Datenfelder kommen weiterhin aus
 * den vorhandenen Entities.
 */

export type StatementVerb = 'PERFORM' | 'MOVE';

export interface StatementKeyword {
  verb: StatementVerb;
  /** 1-basierte Spalten, Ende exklusiv (wie Monaco). */
  startColumn: number;
  endColumn: number;
}

export interface CobolStatement {
  verb: StatementVerb;
  startLine: number;
  endLine: number;
  /** Anweisungstext (Folgezeilen zusammengefasst, Einrückung entfernt). */
  text: string;
  /** PERFORM: Absatz-/Section-Namen; MOVE: Quell- und Zielfelder (Literale ausgenommen). */
  names: string[];
}

const KEYWORD_RE = /(?<![\w-])(PERFORM|MOVE)(?![\w-])/gi;
const MAX_STATEMENT_LINES = 8;

/** Verben, die eine neue Anweisung einleiten und eine laufende beenden. */
const STATEMENT_STARTERS = new Set([
  'ACCEPT', 'ADD', 'CALL', 'CLOSE', 'COMPUTE', 'CONTINUE', 'DELETE', 'DISPLAY', 'DIVIDE', 'ELSE',
  'END-IF', 'END-EVALUATE', 'END-PERFORM', 'END-READ', 'EVALUATE', 'EXEC', 'EXIT', 'GO', 'GOBACK',
  'IF', 'INITIALIZE', 'INSPECT', 'MOVE', 'MULTIPLY', 'NEXT', 'OPEN', 'PERFORM', 'READ', 'REWRITE',
  'SEARCH', 'SET', 'SORT', 'START', 'STOP', 'STRING', 'SUBTRACT', 'UNSTRING', 'WHEN', 'WRITE',
]);
const PERFORM_NON_TARGETS = new Set(['UNTIL', 'VARYING', 'WITH', 'TEST', 'FOREVER', 'BEFORE', 'AFTER']);
const MOVE_NON_NAMES = new Set(['TO', 'CORRESPONDING', 'CORR', 'FUNCTION', 'ALL', 'OF', 'IN', 'ROUNDED']);

/** Kommentarzeile (Fixformat: `*` oder `/` in Spalte 7; frei: `*>`). */
export function isCommentLine(line: string): boolean {
  if (/^\s*\*>/.test(line)) return true;
  return line.length >= 7 && (line[6] === '*' || line[6] === '/');
}

/** Alle PERFORM-/MOVE-Schlüsselwörter einer Zeile (nicht in END-PERFORM, nicht in Kommentaren). */
export function findStatementKeywords(line: string): StatementKeyword[] {
  if (isCommentLine(line)) return [];
  const found: StatementKeyword[] = [];
  KEYWORD_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = KEYWORD_RE.exec(line)) !== null) {
    // Treffer innerhalb eines Literals ('MOVE' …) ausschließen.
    const quotes = (line.slice(0, match.index).match(/['"]/g) || []).length;
    if (quotes % 2 === 1) continue;
    found.push({
      verb: match[1].toUpperCase() as StatementVerb,
      startColumn: match.index + 1,
      endColumn: match.index + 1 + match[1].length,
    });
  }
  return found;
}

/** Das Schlüsselwort unter dem Mausklick (1-basierte Spalte), falls eines getroffen wurde. */
export function keywordAtColumn(line: string, column: number): StatementKeyword | null {
  return findStatementKeywords(line).find(k => column >= k.startColumn && column <= k.endColumn) ?? null;
}

function stripSequenceArea(line: string): string {
  // Fixformat: Spalten 1–6 Folgenummern, ab Spalte 73 Kennung.
  return line.length >= 7 && /^[\d\s]{6}/.test(line) ? line.slice(6, 72) : line;
}

function tokenize(text: string): string[] {
  return text.replace(/[.,;]/g, ' $& ').split(/\s+/).filter(Boolean).filter(token => !/^[,;]$/.test(token));
}

function nameOf(token: string): string | null {
  const upper = token.toUpperCase();
  if (/^['"]/.test(token) || /^[+-]?\d/.test(token) || upper === '.') return null;
  return /^[A-Z][\w-]*$/.test(upper) ? upper : null;
}

/**
 * Die vollständige Anweisung ab dem Schlüsselwort: Folgezeilen gehören dazu, bis ein Punkt
 * kommt oder eine Zeile mit einem neuen Verb beginnt.
 */
export function readStatement(lines: string[], lineNumber: number, keyword: StatementKeyword): CobolStatement {
  const first = stripSequenceArea(lines[lineNumber - 1] ?? '');
  const startOffset = Math.max(0, keyword.startColumn - 1 - ((lines[lineNumber - 1] ?? '').length - first.length));
  const parts: string[] = [first.slice(startOffset).trim()];
  let endLine = lineNumber;
  while (
    !/\.\s*$/.test(parts[parts.length - 1])
    && endLine < lines.length
    && endLine - lineNumber < MAX_STATEMENT_LINES
  ) {
    const next = lines[endLine];
    if (isCommentLine(next)) { endLine += 1; continue; }
    const body = stripSequenceArea(next).trim();
    const firstWord = (body.split(/\s+/)[0] || '').replace(/\.$/, '').toUpperCase();
    if (!body || STATEMENT_STARTERS.has(firstWord)) break;
    parts.push(body);
    endLine += 1;
  }
  const text = parts.join('\n');

  const tokens = tokenize(text.replace(/\n/g, ' ')).slice(1);
  const names: string[] = [];
  if (keyword.verb === 'PERFORM') {
    const head = nameOf(tokens[0] ?? '');
    if (head && !PERFORM_NON_TARGETS.has(head) && !STATEMENT_STARTERS.has(head) && (tokens[1] ?? '').toUpperCase() !== 'TIMES') {
      names.push(head);
      const thru = (tokens[1] ?? '').toUpperCase();
      if (thru === 'THRU' || thru === 'THROUGH') {
        const tail = nameOf(tokens[2] ?? '');
        if (tail) names.push(tail);
      }
    }
  } else {
    for (const token of tokens) {
      const upper = token.toUpperCase();
      if (upper === '.' || (STATEMENT_STARTERS.has(upper) && names.length > 0)) break;
      const name = nameOf(token);
      if (name && !MOVE_NON_NAMES.has(name) && !names.includes(name)) names.push(name);
    }
  }
  return { verb: keyword.verb, startLine: lineNumber, endLine, text, names };
}
