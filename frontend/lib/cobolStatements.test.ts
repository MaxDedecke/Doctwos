import { describe, expect, it } from 'vitest';
import { findStatementKeywords, keywordAtColumn, readStatement } from './cobolStatements';

const fixed = (code: string) => `      ${code}`;

describe('cobolStatements', () => {
  it('finds PERFORM and MOVE but not END-PERFORM, comments or literals', () => {
    expect(findStatementKeywords(fixed('    PERFORM 1000-INIT')).map(k => k.verb)).toEqual(['PERFORM']);
    expect(findStatementKeywords(fixed('    END-PERFORM.'))).toEqual([]);
    expect(findStatementKeywords('      * PERFORM in a comment')).toEqual([]);
    expect(findStatementKeywords(fixed("    DISPLAY 'MOVE ME'"))).toEqual([]);
    expect(findStatementKeywords(fixed('    move a to b'))[0].verb).toBe('MOVE');
  });

  it('maps a click column to the keyword', () => {
    const line = fixed('    MOVE A TO B');
    const k = findStatementKeywords(line)[0];
    expect(keywordAtColumn(line, k.startColumn + 1)?.verb).toBe('MOVE');
    expect(keywordAtColumn(line, 1)).toBeNull();
  });

  it('reads the PERFORM target paragraphs, including THRU and ignoring counts', () => {
    const lines = [fixed('    PERFORM 2000-READ THRU 2000-EXIT'), fixed('    PERFORM 5 TIMES'), fixed('    PERFORM UNTIL DONE')];
    const k = (i: number) => findStatementKeywords(lines[i])[0];
    expect(readStatement(lines, 1, k(0)).names).toEqual(['2000-READ', '2000-EXIT']);
    expect(readStatement(lines, 2, k(1)).names).toEqual([]);
    expect(readStatement(lines, 3, k(2)).names).toEqual([]);
  });

  it('reads a MOVE across continuation lines until the period and skips literals', () => {
    const lines = [fixed("    MOVE 'X' TO WS-A"), fixed('         WS-B.'), fixed('    MOVE 1 TO WS-C.')];
    const statement = readStatement(lines, 1, findStatementKeywords(lines[0])[0]);
    expect(statement.endLine).toBe(2);
    expect(statement.names).toEqual(['WS-A', 'WS-B']);
    expect(statement.text).toContain("MOVE 'X' TO WS-A");
  });

  it('stops a statement at the next verb', () => {
    const lines = [fixed('    MOVE A TO B'), fixed('    ADD 1 TO C.')];
    const statement = readStatement(lines, 1, findStatementKeywords(lines[0])[0]);
    expect(statement.endLine).toBe(1);
    expect(statement.names).toEqual(['A', 'B']);
  });
});
