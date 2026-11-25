import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

/** Dieselbe {{var}}-Ersetzung wie LanguageContext.tsx::t, mit den zwei
 * analysisStatus-Vorlagen als Mini-Wörterbuch -- genug, um
 * analysisStatus.ts::formatAnalysisStatusTooltip gegen einen realistischen
 * `t()` zu testen, ohne die echten JSON-Wörterbücher zu importieren. */
const FAKE_DICT: Record<string, string> = {
  'analysisStatus.tooltipWithReasons': '{{label}}: {{reasons}}',
};
const fakeT = (key: string, vars?: Record<string, string | number>) => {
  const template = FAKE_DICT[key] ?? key;
  if (!vars) return template;
  return Object.entries(vars).reduce((acc, [k, v]) => acc.replace(`{{${k}}}`, String(v)), template);
};

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ t: fakeT }),
}));

import {
  CodeBlock,
  MarkdownContent,
  parseTableAlignment,
  parseText,
  splitTableRow,
  type KnownSource,
} from './MarkdownContent';

/** Rendert nur das, was `parseText` zurückgibt -- die Funktion selbst bleibt eine
 * reine Funktion ohne eigenen Component-Lifecycle, das Rendering dient allein
 * dazu, das erzeugte React-Tree über das DOM zu prüfen. */
function renderParsed(
  text: string,
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void,
  knownSources?: KnownSource[],
  theme = 'dark'
) {
  return render(<>{parseText(text, onFileClick, theme, knownSources)}</>);
}

describe('splitTableRow (reine Funktion)', () => {
  it('splits a basic row and trims each cell', () => {
    expect(splitTableRow('| a | b | c |')).toEqual(['a', 'b', 'c']);
    expect(splitTableRow('|  a  |  b  |')).toEqual(['a', 'b']);
  });

  it('works without leading/trailing pipes', () => {
    expect(splitTableRow('a | b')).toEqual(['a', 'b']);
  });

  it('unescapes an escaped pipe inside a cell instead of splitting on it', () => {
    expect(splitTableRow('a\\|b | c')).toEqual(['a|b', 'c']);
  });

  it('does not treat a pipe inside a backtick code span as a delimiter', () => {
    // Regression: a citation like `some|title.pdf` used to lose its closing
    // backtick because the bare pipe inside it was split as a column delimiter.
    expect(splitTableRow('`a|b` | c')).toEqual(['`a|b`', 'c']);
  });
});

describe('parseTableAlignment (reine Funktion)', () => {
  it('maps each separator marker to its alignment', () => {
    expect(parseTableAlignment('| :--- | ---: | :---: | --- |')).toEqual([
      'left', 'right', 'center', undefined,
    ]);
  });
});

describe('parseText — Code-Zitate', () => {
  it('renders a non-file backtick span as inline code, not a citation button', () => {
    const onFileClick = vi.fn();
    renderParsed('`SELECT * FROM X`', onFileClick);

    const code = screen.getByText('SELECT * FROM X');
    expect(code.tagName).toBe('CODE');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('turns a `file.ext:line` citation into a clickable button', () => {
    const onFileClick = vi.fn();
    renderParsed('`DISPATCHER.cbl:120`', onFileClick);

    fireEvent.click(screen.getByText('DISPATCHER.cbl:120'));
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', 120, undefined);
  });

  it('collapses a `file.ext:start-end` range down to its start line', () => {
    const onFileClick = vi.fn();
    renderParsed('`DISPATCHER.cbl:100-150`', onFileClick);

    fireEvent.click(screen.getByText('DISPATCHER.cbl:100-150'));
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', 100, undefined);
  });

  it('shows the code icon for a plain source file, not the document icon', () => {
    renderParsed('`DISPATCHER.cbl`', vi.fn());
    const button = screen.getByRole('button');
    expect(button.querySelector('.lucide-code')).toBeTruthy();
    expect(button.querySelector('.lucide-book-open')).toBeNull();
  });

  it('resolves a bare filename against a known source by basename (path fallback)', () => {
    // Ein Modell zitiert oft nur den Dateinamen statt des vollen Pfads -- das
    // muss trotzdem den echten (verschachtelten) Pfad öffnen, sonst sucht die
    // Oberfläche die Datei fälschlich im Repo-Wurzelverzeichnis.
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'src/programs/DISPATCHER.cbl', source_id: 42 }];
    renderParsed('`DISPATCHER.cbl`', onFileClick, knownSources);

    fireEvent.click(screen.getByText('DISPATCHER.cbl'));
    expect(onFileClick).toHaveBeenCalledWith('src/programs/DISPATCHER.cbl', undefined, '42');
  });

  it('resolves an extensionless knowledge-source title exactly, with the document icon', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'Deployment Guide', source_id: 'conf-9' }];
    renderParsed('`Deployment Guide`', onFileClick, knownSources);

    const button = screen.getByRole('button');
    expect(button.querySelector('.lucide-book-open')).toBeTruthy();
    fireEvent.click(button);
    expect(onFileClick).toHaveBeenCalledWith('Deployment Guide', undefined, 'conf-9');
  });

  it('strips a stray `:page` suffix off an extensionless title before matching it', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'Deployment Guide', source_id: 'conf-9' }];
    renderParsed('`Deployment Guide:3`', onFileClick, knownSources);

    fireEvent.click(screen.getByText('Deployment Guide:3'));
    expect(onFileClick).toHaveBeenCalledWith('Deployment Guide', 3, 'conf-9');
  });

  // O-120: eine zitierte Datei, die nicht uneingeschränkt analysiert ist,
  // trägt einen Warn-Punkt + erklärenden Tooltip statt unkommentiert wie
  // jede andere Quelle auszusehen.
  it('marks a citation whose source has a non-complete analysis status', () => {
    const knownSources: KnownSource[] = [
      { file: 'PAYROLL.cbl', analysis_status: 'partial', analysis_reasons: ['mismatched input'] },
    ];
    renderParsed('`PAYROLL.cbl`', vi.fn(), knownSources);

    const button = screen.getByRole('button');
    expect(button.querySelector('[data-testid="analysis-status-dot"]')).toBeTruthy();
    expect(button.getAttribute('title')).toContain('mismatched input');
  });

  it('leaves a citation without a non-complete analysis status unmarked', () => {
    const knownSources: KnownSource[] = [{ file: 'OK.cbl' }];
    renderParsed('`OK.cbl`', vi.fn(), knownSources);

    const button = screen.getByRole('button');
    expect(button.querySelector('[data-testid="analysis-status-dot"]')).toBeNull();
    expect(button.getAttribute('title')).toBeNull();
  });
});

describe('parseText — Zitate ohne Backticks (Tabellenzellen-Fallback)', () => {
  it('recognizes a known source title in plain text and leaves the rest untouched', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'DISPATCHER.cbl', source_id: 5 }];
    const { container } = renderParsed('Siehe DISPATCHER.cbl für Details', onFileClick, knownSources);

    expect(container.textContent).toBe('Siehe DISPATCHER.cbl für Details');
    fireEvent.click(screen.getByText('DISPATCHER.cbl'));
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', undefined, '5');
  });

  it('prefers the longer of two overlapping known titles instead of matching a substring', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'A.cbl' }, { file: 'SUB-A.cbl' }];
    renderParsed('SUB-A.cbl', onFileClick, knownSources);

    // Ein einziger Button für den vollen Titel -- nicht zwei (ein Treffer für
    // "A.cbl" als Teilstring plus liegengebliebener Text "SUB-").
    expect(screen.getAllByRole('button')).toHaveLength(1);
    fireEvent.click(screen.getByText('SUB-A.cbl'));
    expect(onFileClick).toHaveBeenCalledWith('SUB-A.cbl', undefined, undefined);
  });

  it('leaves plain text alone when no known sources are given', () => {
    renderParsed('Siehe DISPATCHER.cbl für Details', vi.fn(), undefined);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('marks a backtick-less citation the same way as a backtick one (O-120)', () => {
    const knownSources: KnownSource[] = [{ file: 'DISPATCHER.cbl', analysis_status: 'skipped', analysis_reasons: [] }];
    renderParsed('Siehe DISPATCHER.cbl für Details', vi.fn(), knownSources);

    const button = screen.getByRole('button');
    expect(button.querySelector('[data-testid="analysis-status-dot"]')).toBeTruthy();
  });
});

describe('parseText — Fettdruck und <br>', () => {
  it('renders **bold** as a strong element', () => {
    renderParsed('Das ist **wichtig**.', vi.fn());
    const strong = screen.getByText('wichtig');
    expect(strong.tagName).toBe('STRONG');
  });

  it('splits a literal <br> tag into a real line break', () => {
    const { container } = renderParsed('Zeile1<br>Zeile2', vi.fn());
    expect(container.querySelectorAll('br')).toHaveLength(1);
    expect(container.textContent).toBe('Zeile1Zeile2');
  });
});

describe('MarkdownContent — Blockstruktur', () => {
  it('renders an ATX heading with its level and keeps citations inside it clickable', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'DISPATCHER.cbl' }];
    render(<MarkdownContent content="## Siehe `DISPATCHER.cbl`" onFileClick={onFileClick} theme="dark" knownSources={knownSources} />);

    const heading = screen.getByRole('heading', { level: 2 });
    fireEvent.click(screen.getByText('DISPATCHER.cbl'));
    expect(heading.textContent).toContain('DISPATCHER.cbl');
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', undefined, undefined);
  });

  it('renders a thematic break as <hr>', () => {
    const { container } = render(<MarkdownContent content={'before\n\n---\n\nafter'} onFileClick={vi.fn()} theme="dark" />);
    expect(container.querySelector('hr')).toBeTruthy();
    expect(container.textContent).toContain('before');
    expect(container.textContent).toContain('after');
  });

  it('groups consecutive blockquote lines into one blockquote', () => {
    const { container } = render(<MarkdownContent content={'> Zeile 1\n> Zeile 2'} onFileClick={vi.fn()} theme="dark" />);
    const blockquotes = container.querySelectorAll('blockquote');
    expect(blockquotes).toHaveLength(1);
    expect(blockquotes[0].textContent).toBe('Zeile 1\nZeile 2');
  });

  it('keeps a paragraph\'s internal line breaks', () => {
    const { container } = render(<MarkdownContent content={'Zeile 1\nZeile 2'} onFileClick={vi.fn()} theme="dark" />);
    const paragraph = container.querySelector('p')!;
    expect(paragraph.textContent).toBe('Zeile 1\nZeile 2');
  });

  it('renders nothing for empty content', () => {
    const { container } = render(<MarkdownContent content="" onFileClick={vi.fn()} theme="dark" />);
    expect(container.innerHTML).toBe('');
  });
});

describe('MarkdownContent — GFM-Tabelle', () => {
  const table = [
    '| Name | Wert |',
    '| :--- | ---: |',
    '| A | 1 |',
    '| B | 2 |',
  ].join('\n');

  it('renders header and body cells with the declared per-column alignment', () => {
    const { container } = render(<MarkdownContent content={table} onFileClick={vi.fn()} theme="dark" />);

    const headers = container.querySelectorAll('th');
    expect(headers).toHaveLength(2);
    expect(headers[0].textContent).toBe('Name');
    expect(headers[0].style.textAlign).toBe('left');
    expect(headers[1].style.textAlign).toBe('right');

    const rows = container.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);
    const firstRowCells = rows[0].querySelectorAll('td');
    expect(firstRowCells[0].textContent).toBe('A');
    expect(firstRowCells[0].style.textAlign).toBe('left');
    expect(firstRowCells[1].style.textAlign).toBe('right');
  });

  it('keeps a citation inside a table cell clickable', () => {
    const onFileClick = vi.fn();
    const content = ['| Quelle | Status |', '| --- | --- |', '| `DISPATCHER.cbl:10` | offen |'].join('\n');
    render(<MarkdownContent content={content} onFileClick={onFileClick} theme="dark" />);

    fireEvent.click(screen.getByText('DISPATCHER.cbl:10'));
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', 10, undefined);
  });
});

describe('MarkdownContent — Codeblöcke', () => {
  it('extracts the fenced language and code, surrounded by the normal text blocks', () => {
    const content = "davor\n```python\nprint('hi')\n```\ndanach";
    const { container } = render(<MarkdownContent content={content} onFileClick={vi.fn()} theme="dark" />);

    expect(container.textContent).toContain('davor');
    expect(container.textContent).toContain('danach');
    expect(screen.getByText('python')).toBeTruthy();
    expect(container.querySelector('pre code')!.textContent).toBe("print('hi')\n");
  });

  it('keeps code-block source line locators stable across rerenders', () => {
    const content = 'Intro\n```java\nclass A {}\n```\nEnd';
    const { container, rerender } = render(
      <MarkdownContent content={content} onFileClick={vi.fn()} theme="dark" />,
    );
    const block = container.querySelector('[data-document-line-start="2"]')!;
    expect(block.getAttribute('data-document-line-start')).toBe('2');
    expect(block.getAttribute('data-document-line-end')).toBe('4');

    rerender(<MarkdownContent content={content} onFileClick={vi.fn()} theme="dark" />);
    const rerenderedBlock = container.querySelector('[data-document-line-start="2"]')!;
    expect(rerenderedBlock.getAttribute('data-document-line-start')).toBe('2');
    expect(rerenderedBlock.getAttribute('data-document-line-end')).toBe('4');
  });

  it('falls back to a generic label when the fence has no language', () => {
    render(<MarkdownContent content={'```\nplain\n```'} onFileClick={vi.fn()} theme="dark" />);
    expect(screen.getByText('code')).toBeTruthy();
  });
});

describe('CodeBlock — Kopieren', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  afterEach(() => {
    Reflect.deleteProperty(navigator, 'clipboard');
  });

  // Bewusst echte Zeit statt vi.useFakeTimers(): Fake-Timer blockieren sich
  // zusammen mit waitFor/findBy* selbst (React/testing-library pollen intern
  // über echte Timer) -- derselbe Befund wie schon bei O-100 (LogsSettingsTab).
  it('shows a confirmation after copying and reverts it after a moment', async () => {
    render(<CodeBlock language="python" code="print('hi')" theme="dark" />);

    fireEvent.click(screen.getByText('common.copy'));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("print('hi')"));
    expect(await screen.findByText('common.copied')).toBeTruthy();

    expect(await screen.findByText('common.copy', {}, { timeout: 2500 })).toBeTruthy();
  }, 4000);
});

describe('MarkdownContent — gekürzte Dateizitate im Chat', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });
  afterEach(() => { Reflect.deleteProperty(navigator, 'clipboard'); });

  const renderChat = (content: string, onFileClick = vi.fn(), knownSources?: KnownSource[]) => {
    render(<MarkdownContent content={content} onFileClick={onFileClick} theme="dark" knownSources={knownSources} compactCitations />);
    return onFileClick;
  };

  it('shows only the file name and opens the full path', () => {
    const onFileClick = renderChat('Siehe `src/main/java/Foo.java:12`.');
    fireEvent.click(screen.getByRole('button', { name: 'src/main/java/Foo.java:12' }));
    expect(screen.getByText('Foo.java:12')).toBeTruthy();
    expect(screen.queryByText('src/main/java/Foo.java:12')).toBeNull();
    expect(onFileClick).toHaveBeenCalledWith('src/main/java/Foo.java', 12, undefined);
  });

  it('offers the full path to copy and the code view on hover', async () => {
    const onFileClick = renderChat('Siehe `src/main/java/Foo.java:12`.');
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'src/main/java/Foo.java:12' }));
    expect(await screen.findByText('src/main/java/Foo.java')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'pathCard.copy' }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith('src/main/java/Foo.java'));

    fireEvent.click(screen.getByRole('button', { name: 'pathCard.view' }));
    expect(onFileClick).toHaveBeenCalledWith('src/main/java/Foo.java', 12, undefined);
    expect(screen.queryByText('src/main/java/Foo.java')).toBeNull();
  });

  it('shortens a path written without backticks and links it to its known source', () => {
    const onFileClick = renderChat('Siehe src/A.cbl:3 und https://x.org/docs/B.html.', vi.fn(), [{ file: 'repo/src/A.cbl', source_id: 7 }]);
    fireEvent.click(screen.getByRole('button', { name: 'src/A.cbl:3' }));
    expect(onFileClick).toHaveBeenCalledWith('repo/src/A.cbl', 3, '7');
    expect(screen.getByText(/https:\/\/x\.org\/docs\/B\.html/)).toBeTruthy();
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('keeps titles and inline code that are no files as written', () => {
    renderChat('`Release 1/2` und `a/b`', vi.fn(), [{ file: 'Release 1/2' }]);
    expect(screen.getByText('Release 1/2')).toBeTruthy();
    expect(screen.getByText('a/b')).toBeTruthy();
  });

  it('writes citations out in full without the option', () => {
    render(<MarkdownContent content="Siehe `src/main/java/Foo.java` und src/B.java." onFileClick={vi.fn()} theme="dark" />);
    expect(screen.getByText('src/main/java/Foo.java')).toBeTruthy();
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });
});

describe('MarkdownContent — Listen', () => {
  const noop = () => {};

  it('renders dash and asterisk bullets as one unordered list instead of literal markers', () => {
    const { container } = render(<MarkdownContent content={'Intro\n- eins\n* zwei\n+ drei'} onFileClick={noop} theme="dark" />);
    const items = container.querySelectorAll('ul > li');
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toBe('eins');
    expect(container.textContent).not.toContain('- eins');
  });

  it('renders an ordered list and keeps its start number', () => {
    const { container } = render(<MarkdownContent content={'3. drei\n4. vier'} onFileClick={noop} theme="dark" />);
    const list = container.querySelector('ol')!;
    expect(list.getAttribute('start')).toBe('3');
    expect(list.querySelectorAll('li')).toHaveLength(2);
  });

  it('nests deeper-indented items under the previous item', () => {
    const { container } = render(<MarkdownContent content={'- [Installation](#installation)\n  - [Prerequisites](#prerequisites)\n  - [IMS](#ims)\n- [License](#license)'} onFileClick={noop} theme="dark" />);
    const top = container.querySelectorAll(':scope [data-markdown-root] > ul > li');
    expect(top).toHaveLength(2);
    expect(top[0].querySelectorAll('ul > li')).toHaveLength(2);
    expect(container.textContent).not.toContain('](#');
  });

  it('joins a continuation line into its item and ends the list at a blank line before prose', () => {
    const { container } = render(<MarkdownContent content={'- erster Punkt\n  geht weiter\n\nNeuer Absatz'} onFileClick={noop} theme="dark" />);
    expect(container.querySelector('li')!.textContent).toBe('erster Punkt\ngeht weiter');
    expect(container.querySelector('p')!.textContent).toBe('Neuer Absatz');
  });

  it('keeps a loose list together across blank lines between items', () => {
    const { container } = render(<MarkdownContent content={'- a\n\n- b'} onFileClick={noop} theme="dark" />);
    expect(container.querySelectorAll('ul')).toHaveLength(1);
    expect(container.querySelectorAll('li')).toHaveLength(2);
  });

  it('renders task list items as checkboxes', () => {
    render(<MarkdownContent content={'- [x] fertig\n- [ ] offen'} onFileClick={noop} theme="dark" />);
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(boxes.map(b => b.checked)).toEqual([true, false]);
  });

  it('keeps citations clickable inside list items', () => {
    const onFileClick = vi.fn();
    render(<MarkdownContent content={'- `CCPAURQY` – definiert in `CCPAURQY.cpy:30`'} onFileClick={onFileClick} theme="dark" />);
    fireEvent.click(screen.getByRole('button', { name: /CCPAURQY\.cpy/ }));
    expect(onFileClick).toHaveBeenCalledWith('CCPAURQY.cpy', 30, undefined);
  });

  it('does not turn a thematic break or a bold line into a list', () => {
    const { container } = render(<MarkdownContent content={'**Fett** am Anfang\n\n---'} onFileClick={noop} theme="dark" />);
    expect(container.querySelector('ul')).toBeNull();
    expect(container.querySelector('hr')).not.toBeNull();
  });
});

describe('parseText — Links, Bilder und Hervorhebungen', () => {
  const noop = () => {};

  it('renders an external link that opens in a new tab without leaking the opener', () => {
    renderParsed('Siehe [Doku](https://example.com/doku "Titel").', noop);
    const link = screen.getByRole('link', { name: 'Doku' });
    expect(link.getAttribute('href')).toBe('https://example.com/doku');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('links a bare URL without swallowing trailing punctuation', () => {
    renderParsed('Lizenz: http://www.apache.org/licenses/LICENSE-2.0.', noop);
    expect(screen.getByRole('link').getAttribute('href')).toBe('http://www.apache.org/licenses/LICENSE-2.0');
  });

  it('never creates a javascript: link', () => {
    const { container } = renderParsed('[klick](javascript:alert(1))', noop);
    expect(container.querySelector('a')).toBeNull();
  });

  it('shows images as a labelled placeholder instead of loading them', () => {
    const { container } = renderParsed('![Version](https://img.shields.io/badge/v1.svg)', noop);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByRole('img', { name: 'Version' }).getAttribute('title')).toBe('https://img.shields.io/badge/v1.svg');
  });

  it('handles a linked badge image', () => {
    renderParsed('[![Build](https://ci/badge.svg)](https://ci/job)', noop);
    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe('https://ci/job');
    expect(link.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe('Build');
  });

  it('renders *italic*, _italic_ and ~~strike~~ but leaves snake_case and code alone', () => {
    const { container } = renderParsed('*eins* _zwei_ ~~drei~~ my_var_name `a_b_c` 2 * 3 * 4', noop);
    expect([...container.querySelectorAll('em')].map(e => e.textContent)).toEqual(['eins', 'zwei']);
    expect(container.querySelector('del')!.textContent).toBe('drei');
    expect(container.textContent).toContain('my_var_name');
    expect(container.textContent).toContain('2 * 3 * 4');
  });

  it('leaves a bracketed chat citation without a URL as text', () => {
    const { container } = renderParsed('Quelle [COPAUA0C.cbl:178] im Text', noop);
    expect(container.querySelector('a')).toBeNull();
    expect(container.textContent).toContain('[COPAUA0C.cbl:178]');
  });
});

describe('MarkdownContent — Links im Dokument', () => {
  it('scrolls to the matching heading for an in-document anchor', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    render(<MarkdownContent content={'- [Business Logic](#business-logic)\n\n## Business Logic\nText'} onFileClick={() => {}} theme="dark" />);
    fireEvent.click(screen.getByRole('link', { name: 'Business Logic' }));
    expect(scrollIntoView).toHaveBeenCalled();
    expect((scrollIntoView.mock.contexts[0] as HTMLElement).id).toBe('business-logic');
  });

  it('opens a relative link resolved against the document folder in its knowledge source', () => {
    const onFileClick = vi.fn();
    render(<MarkdownContent content={'[Fluss](../../diagrams/flow.md#L12)'} onFileClick={onFileClick} theme="dark" basePath="app/ext/docs/README.md" baseSourceId="7" />);
    fireEvent.click(screen.getByRole('button', { name: 'Fluss' }));
    expect(onFileClick).toHaveBeenCalledWith('app/diagrams/flow.md', 12, '7');
  });
});
