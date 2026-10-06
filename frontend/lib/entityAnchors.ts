/**
 * Wo im angezeigten Quelltext ein Wissensobjekt anklickbar ist. Der Parser liefert pro Objekt
 * nur eine Startzeile; die ist aber nicht immer die Zeile mit dem Namen:
 *  - Java: bei annotierten Deklarationen (`@Override`, `@SpringBean`, …) steht dort die Annotation,
 *    der Name erst in einer der Folgezeilen;
 *  - Lambdas und anonyme Klassen heißen `<lambda@Zeile:Spalte>` und haben keinen Namen im Text;
 *  - COBOL/JCL/SQL: Programm-ID, EXEC-Ressourcen und DD-Datasets stehen in Folgezeilen;
 *  - Dateiobjekte (Compilation-Unit, Copybook, JCL-Datei, Properties …) haben gar keine Stelle.
 * `computeEntityAnchor` bestimmt die genaue Textstelle oder meldet, dass es keine gibt.
 */

export interface AnchorEntity {
  name: string;
  type?: string | null;
  start_line?: number | null;
  end_line?: number | null;
}

export interface EntityAnchor {
  /** 1-basierte Zeile und Spalten (Ende exklusiv), wie Monaco sie erwartet. */
  line: number;
  startColumn: number;
  endColumn: number;
}

/** Objekte, die eine ganze Datei darstellen: kein Textanker, Zugriff über die Dateikopfzeile. */
export const FILE_LEVEL_TYPES = new Set([
  'compilation_unit', 'properties_file', 'html_document', 'xml_document', 'groovy_file',
  'javascript_file', 'shell_script', 'sql_script', 'jcl_file', 'copybook', 'maven_project',
  'maven_source_root',
]);

/** Reihenfolge, in der ein Dateiobjekt als „das“ Objekt der Datei gewählt wird. */
const FILE_LEVEL_PRIORITY = [
  'compilation_unit', 'copybook', 'jcl_file', 'maven_project', 'properties_file', 'html_document',
  'xml_document', 'groovy_file', 'javascript_file', 'shell_script', 'sql_script',
];

export function pickFileLevelEntity<T extends AnchorEntity>(entities: T[]): T | null {
  const fileLevel = entities.filter(ent => ent.type != null && FILE_LEVEL_TYPES.has(ent.type));
  for (const type of FILE_LEVEL_PRIORITY) {
    const match = fileLevel.find(ent => ent.type === type);
    if (match) return match;
  }
  return fileLevel[0] ?? null;
}

const DEFAULT_WINDOW = 15;
const WIDE_WINDOW_TYPES = new Set(['program', 'exec_resource', 'exec_operation', 'jcl_dataset', 'sql_include']);

const escapeRegex = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Namensvarianten, nach denen im Text gesucht wird (Maven: `group:artifact` → `artifact`). */
function nameCandidates(ent: AnchorEntity): string[] {
  const name = ent.name;
  if (!name) return [];
  if (ent.type?.startsWith('maven_')) {
    const last = name.split(/[:/]/).pop() ?? name;
    return last && last !== name ? [last, name] : [name];
  }
  return [name];
}

export function wordRegex(name: string): RegExp {
  return new RegExp(`(?<![\\w$-])${escapeRegex(name)}(?![\\w$-])`, 'i');
}

/** Beginnt eine Zeile (ggf. mitten in einer mehrzeiligen Annotation) mit Annotationstext? */
function annotationSkipper() {
  let depth = 0;
  return (line: string): boolean => {
    const trimmed = line.trim();
    if (depth > 0 || trimmed.startsWith('@')) {
      for (const ch of trimmed) {
        if (ch === '(') depth += 1;
        else if (ch === ')') depth = Math.max(0, depth - 1);
      }
      return true;
    }
    return false;
  };
}

type LineReader = (lineNumber: number) => string;

/** Anker für Objekte, deren Name nicht im Text steht (Lambda, anonyme Klasse, Initializer, EXEC/SQL, Formular). */
function patternAnchor(ent: AnchorEntity, startLine: number, getLine: LineReader): EntityAnchor | null {
  const text = getLine(startLine);
  const at = (index: number, length: number): EntityAnchor => ({ line: startLine, startColumn: index + 1, endColumn: index + 1 + length });
  const encoded = /^<\w+@(\d+):(\d+)>$/.exec(ent.name);
  const column = encoded ? Number(encoded[2]) : 0;
  switch (ent.type) {
    case 'lambda': {
      const index = text.indexOf('->', Math.max(0, column - 1));
      return index >= 0 ? at(index, 2) : (text.indexOf('->') >= 0 ? at(text.indexOf('->'), 2) : null);
    }
    case 'anonymous_class': {
      const index = text.indexOf('{', Math.max(0, column - 2));
      return index >= 0 ? at(index, 1) : null;
    }
    case 'initializer': {
      const match = /\bstatic\b|\{/.exec(text);
      return match ? at(match.index, match[0].length) : null;
    }
    case 'exec_block': {
      const match = /\bEXEC\b(?:\s+\w+)?/i.exec(text);
      return match ? at(match.index, match[0].length) : null;
    }
    case 'sql_block': {
      const match = /\bEXEC\s+SQL\b/i.exec(text);
      return match ? at(match.index, match[0].length) : null;
    }
    case 'html_form': {
      const match = /<form\b/i.exec(text);
      return match ? at(match.index, match[0].length) : null;
    }
    default:
      return null;
  }
}

export function computeEntityAnchor(ent: AnchorEntity, getLine: LineReader, lineCount: number): EntityAnchor | null {
  const startLine = ent.start_line ?? 0;
  if (!startLine || startLine > lineCount) return null;
  if (ent.type && FILE_LEVEL_TYPES.has(ent.type)) return null;

  const patterned = patternAnchor(ent, startLine, getLine);
  if (patterned) return patterned;
  if (/^<[\w-]+@\d+(:\d+)?>$/.test(ent.name) || ent.name === '<clinit>' || ent.name === '<current-page>') return null;

  const window = WIDE_WINDOW_TYPES.has(ent.type ?? '') ? 60 : DEFAULT_WINDOW;
  // EXEC-/JCL-Objekte tragen den genauen Zeilenbereich; bei den übrigen (Java, Maven …) ist das
  // Ende nicht immer verlässlich, dort zählt nur das Suchfenster.
  const bounded = ent.type?.startsWith('exec_') || ent.type?.startsWith('jcl_') || ent.type === 'sql_include';
  const lastLine = Math.min(lineCount, startLine + window, bounded ? Math.max(startLine, ent.end_line ?? startLine) : lineCount);
  const candidates = nameCandidates(ent);

  for (const candidate of candidates) {
    const regex = wordRegex(candidate);
    const skipsAnnotation = annotationSkipper();
    for (let lineNumber = startLine; lineNumber <= lastLine; lineNumber++) {
      const text = getLine(lineNumber);
      if (skipsAnnotation(text)) continue;
      const match = regex.exec(text);
      if (match) return { line: lineNumber, startColumn: match.index + 1, endColumn: match.index + 1 + match[0].length };
    }
  }

  // Letzter Ausweg wie bisher: Teilstring in der Startzeile.
  const first = getLine(startLine);
  for (const candidate of candidates) {
    const index = first.toLowerCase().indexOf(candidate.toLowerCase());
    if (index >= 0) return { line: startLine, startColumn: index + 1, endColumn: index + 1 + candidate.length };
  }
  return null;
}
