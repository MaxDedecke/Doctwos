/**
 * Kurzform von Dateizitaten im Antworttext: Im Text steht nur der Dateiname, der volle Pfad bleibt
 * erreichbar. Alles, was nicht klar wie ein Dateipfad aussieht, bleibt unverändert.
 */

const FILE_EXTENSIONS = 'py|cob|cbl|cpy|bms|jcl|proc|java|groovy|jsp|js|jsx|ts|tsx|c|h|cpp|hpp|cs|go|rs|php|rb|sh|sql|'
  + 'json|xml|xsd|xsl|xslt|yml|yaml|toml|ini|cfg|conf|properties|gradle|css|html|md|adoc|asciidoc|txt|csv|pdf|docx|doc';

export const FILE_LIKE_RE = new RegExp(`\\b[\\w\\-./]+\\.(${FILE_EXTENSIONS})\\b`, 'i');

/** Mindestens ein Ordner, kein Teil einer URL oder eines längeren Pfads. */
const PLAIN_PATH_RE = new RegExp(
  `(?<![\\w./:\\\\-])((?:[\\w.-]+[/\\\\])+[\\w.-]+\\.(?:${FILE_EXTENSIONS}))(?::(\\d+)(?:-\\d+)?)?(?![\\w/\\\\-])`,
  'gi',
);

export type PlainPathPart = string | { cited: string; path: string; line?: number };

export function compactCitationLabel(cited: string): string {
  const name = cited.split(/[/\\]/).pop() ?? cited;
  return /\.\w+(?::\d+(?:-\d+)?)?$/.test(name) ? name : cited;
}

/** Trennt ausgeschriebene Dateipfade ohne Backticks vom übrigen Text. */
export function splitPlainPaths(text: string): PlainPathPart[] {
  const parts: PlainPathPart[] = [];
  let last = 0;
  for (const match of text.matchAll(PLAIN_PATH_RE)) {
    if (/^www\./i.test(match[1])) continue;
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push({ cited: match[0], path: match[1], line: match[2] ? parseInt(match[2], 10) : undefined });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

/** Ob die Kurzform an dieser Antwort überhaupt etwas ändert. */
export function hasCompactableCitation(text: string): boolean {
  return text.split(/```[\s\S]*?```/).some((part) =>
    part.split(/`/).some((piece) => splitPlainPaths(piece).some((item) => typeof item !== 'string')));
}
