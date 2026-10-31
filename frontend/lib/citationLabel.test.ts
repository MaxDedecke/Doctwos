import { describe, expect, it } from 'vitest';
import { compactCitationLabel, hasCompactableCitation, splitPlainPaths } from './citationLabel';

describe('compactCitationLabel', () => {
  it('keeps the file name and the line of a path', () => {
    expect(compactCitationLabel('src/main/java/Foo.java')).toBe('Foo.java');
    expect(compactCitationLabel('src/main/java/Foo.java:12-20')).toBe('Foo.java:12-20');
    expect(compactCitationLabel('cbl\\COPAUS2C.cbl:43')).toBe('COPAUS2C.cbl:43');
  });

  it('leaves everything that does not look like a file as written', () => {
    expect(compactCitationLabel('Foo.java')).toBe('Foo.java');
    expect(compactCitationLabel('Release 1/2')).toBe('Release 1/2');
  });
});

describe('splitPlainPaths', () => {
  it('finds a written-out path with its line and keeps the text around it', () => {
    expect(splitPlainPaths('Siehe src/a/Foo.java:12, dort.')).toEqual([
      'Siehe ',
      { cited: 'src/a/Foo.java:12', path: 'src/a/Foo.java', line: 12 },
      ', dort.',
    ]);
  });

  it('does not touch URLs, prose or bare file names', () => {
    for (const text of [
      'https://example.com/docs/Foo.html',
      'www.example.com/Foo.html',
      'und/oder.später',
      'Foo.java allein',
    ]) {
      expect(splitPlainPaths(text)).toEqual([text]);
    }
  });
});

describe('hasCompactableCitation', () => {
  it('sees paths in text and inline code but not in code blocks', () => {
    expect(hasCompactableCitation('Siehe `src/a/Foo.java:3`.')).toBe(true);
    expect(hasCompactableCitation('Siehe src/a/Foo.java.')).toBe(true);
    expect(hasCompactableCitation('Siehe `Foo.java`.')).toBe(false);
    expect(hasCompactableCitation('```\nsrc/a/Foo.java\n```')).toBe(false);
  });
});
