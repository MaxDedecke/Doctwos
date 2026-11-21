/**
 * Schlanke Syntaxhervorhebung für Codeblöcke im Chat (COBOL, JCL, Java, SQL), ohne zusätzliche Bibliothek.
 * Sie färbt nur Schlüsselwörter, Zeichenketten, Kommentare und Zahlen; was sie nicht kennt, bleibt Text.
 */

export type TokenKind = 'keyword' | 'string' | 'comment' | 'number' | 'text';
export interface Token { text: string; kind: TokenKind }

export type HighlightLanguage = 'cobol' | 'jcl' | 'java' | 'sql';

const ALIASES: Record<string, HighlightLanguage> = {
  cobol: 'cobol', cbl: 'cobol', cob: 'cobol', cpy: 'cobol', copybook: 'cobol',
  jcl: 'jcl', proc: 'jcl',
  java: 'java',
  sql: 'sql', db2: 'sql',
};

const words = (list: string) => new Set(list.split(/\s+/).filter(Boolean));
const KEYWORDS: Record<HighlightLanguage, Set<string>> = {
  cobol: words(`ACCEPT ADD ALSO AND CALL CANCEL CLOSE COMPUTE CONTINUE COPY DELETE DISPLAY DIVIDE DIVISION ELSE END-EVALUATE
    END-IF END-PERFORM END-READ END-EXEC EVALUATE EXEC EXIT FD FILLER GOBACK GO IF INITIALIZE INSPECT INTO IS MOVE MULTIPLY
    NOT OCCURS OF OPEN OR OTHER PERFORM PIC PICTURE PROCEDURE PROGRAM-ID READ REDEFINES RETURN REWRITE SECTION SELECT SET
    STOP STRING SUBTRACT THEN THRU TIMES TO UNSTRING UNTIL USING VALUE VALUES VARYING WHEN WORKING-STORAGE LINKAGE WRITE
    COMP COMP-3 IDENTIFICATION ENVIRONMENT DATA FILE FILE-CONTROL INPUT-OUTPUT CONFIGURATION CICS SQL RUN BY GIVING
    SEARCH SORT MERGE ALL INITIAL FROM RESP ZERO ZEROS ZEROES SPACE SPACES HIGH-VALUES LOW-VALUES TRUE FALSE`),
  jcl: words(`JOB EXEC DD PGM PROC DSN DSNAME DISP SYSOUT SPACE UNIT VOL DCB COND PARM REGION CLASS MSGCLASS NOTIFY TIME
    SET INCLUDE JCLLIB ORDER IF THEN ELSE ENDIF PEND NEW OLD SHR MOD CATLG DELETE KEEP PASS`),
  java: words(`abstract assert boolean break byte case catch char class const continue default do double else enum extends
    final finally float for goto if implements import instanceof int interface long native new package private protected
    public return short static strictfp super switch synchronized this throw throws transient try var void volatile while
    record sealed permits yield true false null`),
  sql: words(`SELECT FROM WHERE AND OR NOT INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE INDEX VIEW DROP ALTER JOIN LEFT
    RIGHT INNER OUTER ON GROUP BY ORDER HAVING AS DISTINCT UNION ALL NULL IS IN EXISTS BETWEEN LIKE DECLARE CURSOR FOR
    OPEN FETCH CLOSE COMMIT ROLLBACK WITH FETCH FIRST ROWS ONLY CASE WHEN THEN ELSE END`),
};
const CASE_INSENSITIVE: Record<HighlightLanguage, boolean> = { cobol: true, jcl: true, java: false, sql: true };

export function highlightLanguage(language: string): HighlightLanguage | null {
  return ALIASES[language.trim().toLowerCase()] ?? null;
}

/** Sprache aus der Dateiendung, z. B. für die Vorschau zitierter Zeilen. */
export function languageForPath(path: string): HighlightLanguage | null {
  const extension = path.split('.').pop() ?? '';
  return highlightLanguage(extension);
}

function lineComment(line: string, language: HighlightLanguage): number {
  if (language === 'cobol') {
    // Festes Format: '*' oder '/' in Spalte 7; freies Format: '*>' irgendwo.
    if (line.length > 6 && (line[6] === '*' || line[6] === '/')) return 0;
    const inline = line.indexOf('*>');
    return inline;
  }
  if (language === 'jcl') return line.startsWith('//*') ? 0 : -1;
  if (language === 'sql') return line.indexOf('--');
  return line.indexOf('//');
}

const TOKEN_RE = /("(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)*'?)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_@][\w-]*)|(\s+|[^\w\s"']+)/g;

function tokenizeLine(line: string, language: HighlightLanguage, inBlock: boolean): { tokens: Token[]; inBlock: boolean } {
  const tokens: Token[] = [];
  let rest = line;
  if (language === 'java' && inBlock) {
    const end = rest.indexOf('*/');
    if (end < 0) return { tokens: [{ text: rest, kind: 'comment' }], inBlock: true };
    tokens.push({ text: rest.slice(0, end + 2), kind: 'comment' });
    rest = rest.slice(end + 2);
  }
  let comment = '';
  const commentAt = lineComment(rest, language);
  if (commentAt >= 0) {
    comment = rest.slice(commentAt);
    rest = rest.slice(0, commentAt);
  }
  let block = false;
  if (language === 'java') {
    const start = rest.indexOf('/*');
    if (start >= 0) {
      const end = rest.indexOf('*/', start + 2);
      if (end < 0) {
        comment = rest.slice(start) + comment;
        rest = rest.slice(0, start);
        block = true;
      }
    }
  }
  const keywords = KEYWORDS[language];
  for (const match of rest.matchAll(TOKEN_RE)) {
    const [text, string, number, word] = match;
    if (string) tokens.push({ text, kind: 'string' });
    else if (number) tokens.push({ text, kind: 'number' });
    else if (word) {
      const key = CASE_INSENSITIVE[language] ? word.toUpperCase() : word;
      tokens.push({ text, kind: keywords.has(key) || (language === 'java' && word.startsWith('@')) ? 'keyword' : 'text' });
    } else tokens.push({ text, kind: 'text' });
  }
  if (comment) tokens.push({ text: comment, kind: 'comment' });
  return { tokens, inBlock: block };
}

/** Tokens je Zeile; Java-Blockkommentare dürfen über Zeilen laufen. */
export function highlightLines(code: string, language: HighlightLanguage): Token[][] {
  let inBlock = false;
  return code.split('\n').map(line => {
    const result = tokenizeLine(line, language, inBlock);
    inBlock = result.inBlock;
    return result.tokens;
  });
}

export const TOKEN_CLASS: Record<TokenKind, string> = {
  keyword: 'text-ds-indigo-500 font-semibold',
  string: 'text-ds-emerald-600 dark:text-ds-emerald-400',
  comment: 'text-ds-zinc-500 italic',
  number: 'text-ds-amber-600 dark:text-ds-amber-400',
  text: '',
};
