import { describe, expect, it } from 'vitest';
import { highlightLanguage, highlightLines, languageForPath } from './codeHighlight';

const kinds = (line: ReturnType<typeof highlightLines>[number]) =>
  line.filter(token => token.kind !== 'text').map(token => `${token.kind}:${token.text}`);

describe('code highlighting', () => {
  it('colors COBOL keywords, literals and fixed-format comments', () => {
    const [statement, comment] = highlightLines("           MOVE 'ABC' TO WS-NAME 12.\n      * Kommentar", 'cobol');
    expect(kinds(statement)).toEqual(['keyword:MOVE', "string:'ABC'", 'keyword:TO', 'number:12']);
    expect(kinds(comment)).toEqual(['comment:      * Kommentar']);
  });

  it('keeps Java block comments across lines and marks annotations', () => {
    const lines = highlightLines('@Override /* start\n still */ public int x = 1;', 'java');
    expect(kinds(lines[0])).toEqual(['keyword:@Override', 'comment:/* start']);
    expect(kinds(lines[1])).toEqual(['comment: still */', 'keyword:public', 'keyword:int', 'number:1']);
  });

  it('maps fence names and file extensions', () => {
    expect(highlightLanguage('CBL')).toBe('cobol');
    expect(languageForPath('app/jcl/RUN.jcl')).toBe('jcl');
    expect(languageForPath('README.md')).toBeNull();
  });
});
