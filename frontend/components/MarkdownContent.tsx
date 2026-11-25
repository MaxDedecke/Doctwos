import { CitationChip, CompactCitationsContext, TextWithPaths } from '@/components/CitationChip';
import { FILE_LIKE_RE } from '@/lib/citationLabel';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn, copyToClipboard } from "@/lib/utils";
import { MermaidDiagram } from '@/components/MermaidDiagram';
import { HighlightedCode } from '@/components/HighlightedCode';
import { highlightLanguage } from '@/lib/codeHighlight';
import { Check, Image as ImageIcon, Layers } from 'lucide-react';
import React, { createContext, useContext, useState } from 'react';

interface CodeBlockProps {
  language: string;
  code: string;
  theme: string;
  showLineNumbers?: boolean;
  startLine?: number;
}

/**
 * Reusable CodeBlock component that renders a stylized code window
 * with language badge and copy-to-clipboard functionality.
 */
export const CodeBlock: React.FC<CodeBlockProps> = ({ language, code, theme, showLineNumbers = false, startLine = 1 }) => {
  const { t } = useLanguage();
  const [copied, setCopied] = useState(false);

  if (language.toLowerCase() === 'mermaid') {
    // Ein Key erzeugt bei geändertem Diagramm oder Farbschema eine frische
    // Renderer-Instanz; dadurch bleibt kein SVG der vorherigen Antwort sichtbar.
    return <MermaidDiagram key={`${theme}:${code}`} code={code} theme={theme} />;
  }

  const handleCopy = async () => {
    const success = await copyToClipboard(code);
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className={cn(
      "rounded-lg border overflow-hidden my-4 shadow-xl transition-colors duration-200",
      theme === 'dark' ? "border-ds-zinc-800 bg-ds-zinc-950/80" : "border-ds-zinc-200 bg-ds-zinc-50/90"
    )}>
      <div className={cn(
        "flex items-center justify-between px-4 py-2 border-b text-[0.6875rem] font-mono transition-colors duration-200",
        theme === 'dark' ? "border-ds-zinc-800 bg-ds-zinc-900/40 text-ds-zinc-400" : "border-ds-zinc-200 bg-ds-zinc-200/50 text-ds-zinc-650"
      )}>
        <span className="capitalize font-semibold">{language || 'code'}</span>
        <button
          type="button"
          onClick={handleCopy}
          id="copy-code-btn"
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded border transition-all text-xs font-medium",
            theme === 'dark'
              ? "bg-ds-zinc-900 hover:bg-ds-zinc-800 text-ds-zinc-300 border-ds-zinc-800 hover:border-ds-zinc-750"
              : "bg-ds-white hover:bg-ds-zinc-100 text-ds-zinc-750 border-ds-zinc-200 hover:border-ds-zinc-300"
          )}
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-ds-emerald-500" />
              <span className="text-ds-emerald-500 font-semibold">{t('common.copied')}</span>
            </>
          ) : (
            <>
              <Layers className="w-3 h-3" />
              <span>{t('common.copy')}</span>
            </>
          )}
        </button>
      </div>
      <pre className={cn(
        "p-4 overflow-x-auto max-w-full text-sm font-mono leading-relaxed no-scrollbar",
        theme === 'dark' ? "text-ds-zinc-300 bg-ds-black/20" : "text-ds-zinc-800 bg-ds-black/5"
      )}>
        <code><HighlightedCode code={code} language={highlightLanguage(language)} firstLine={showLineNumbers ? startLine : undefined} /></code>
      </pre>
    </div>
  );
};

/**
 * Parses markdown inline text to render files and documents as interactive badges,
 * and bold text as bold elements.
 */
export interface KnownSource {
  file: string;
  lines?: Array<number | null>;
  source_id?: number | string | null;
  // O-120: nur gesetzt, wenn die zugrunde liegende Datei nicht uneingeschränkt
  // analysiert ist (siehe backend/core/analysis_status.py) -- fehlt es, gilt
  // das Zitat als unauffällig.
  analysis_status?: 'partial' | 'text_fallback' | 'skipped' | 'error';
  analysis_reasons?: string[];
}

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const BR_TAG_SPLIT_RE = /(<br\s*\/?>)/gi;
const BR_TAG_TEST_RE = /^<br\s*\/?>$/i;

/**
 * Local models frequently skip the backtick citation format inside table cells
 * even though the prompt asks for it there too (see the citation_note in
 * backend/services/chat_service.py) -- this recognizes a known knowledge-source title as plain
 * text, optionally followed by a `:page` or `:start-end` suffix the model
 * sometimes appends, so the citation still becomes clickable without backticks.
 */
const renderPlainKnownSources = (
  segment: string,
  keyPrefix: string,
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void,
  theme: string,
  knownSources: KnownSource[]
): React.ReactNode[] => {
  const candidates = [...knownSources].filter(s => s.file).sort((a, b) => b.file.length - a.file.length);
  const plainText = (text: string, key: string) => (
    <TextWithPaths key={key} text={text} knownSources={knownSources} theme={theme} onFileClick={onFileClick} />
  );
  if (candidates.length === 0) return [plainText(segment, keyPrefix)];
  // Nicht mitten in einem längeren Pfad oder Namen: `src/A.cbl` ist keine Nennung von `A.cbl`.
  const pattern = new RegExp(`(?<![\\w/\\\\.-])(${candidates.map(s => escapeRegExp(s.file)).join('|')})(?::(\\d+)(?:-\\d+)?)?`, 'gi');

  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let idx = 0;
  while ((match = pattern.exec(segment)) !== null) {
    if (match.index > lastIndex) nodes.push(plainText(segment.slice(lastIndex, match.index), `${keyPrefix}-text-${idx}`));
    const title = match[1];
    const knownSource = candidates.find(s => s.file.toLowerCase() === title.toLowerCase());
    nodes.push(
      <CitationChip
        key={`${keyPrefix}-plain-${idx++}`}
        cited={match[0]}
        path={title}
        line={match[2] ? parseInt(match[2], 10) : undefined}
        isDoc
        source={knownSource}
        theme={theme}
        onFileClick={onFileClick}
      />
    );
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < segment.length) nodes.push(plainText(segment.slice(lastIndex), `${keyPrefix}-text-end`));
  return nodes.length > 0 ? nodes : [segment];
};

/** Wohin relative Links eines Dokuments zeigen: Pfad des Dokuments und seine Wissensquelle. */
interface MarkdownLinkBase {
  basePath?: string;
  sourceId?: string;
  onFileClick?: (filePath: string, line?: number, sourceId?: string) => void;
}
const MarkdownLinkContext = createContext<MarkdownLinkBase>({});

const SAFE_URL_RE = /^(https?:|mailto:)/i;

/** Löst einen relativen Link gegen den Ordner des Dokuments auf (`../a/b.md` → `docs/a/b.md`). */
export const resolveRelativePath = (basePath: string | undefined, target: string): string => {
  const clean = target.replace(/^\.\//, '');
  if (clean.startsWith('/')) return clean.replace(/^\/+/, '');
  const parts = (basePath || '').split('/').slice(0, -1);
  for (const segment of clean.split('/')) {
    if (segment === '..') parts.pop();
    else if (segment && segment !== '.') parts.push(segment);
  }
  return parts.join('/');
};

const MarkdownLink: React.FC<{ href: string; title?: string; theme: string; children: React.ReactNode }> = ({ href, title, theme, children }) => {
  const { basePath, sourceId, onFileClick } = useContext(MarkdownLinkContext);
  const linkClass = cn(
    "underline underline-offset-2 transition-colors duration-200",
    theme === 'dark' ? "text-ds-blue-400 decoration-ds-blue-400/40 hover:text-ds-blue-300" : "text-ds-blue-650 decoration-ds-blue-650/40 hover:text-ds-blue-700"
  );
  if (SAFE_URL_RE.test(href)) {
    return <a href={href} title={title || href} target="_blank" rel="noopener noreferrer" className={linkClass}>{children}</a>;
  }
  if (href.startsWith('#')) {
    // Sprungmarken wie GitHub-Inhaltsverzeichnisse zielen auf die Überschriften-IDs desselben Dokuments.
    const anchor = decodeURIComponent(href.slice(1));
    return (
      <a
        href={href}
        title={title}
        className={linkClass}
        onClick={(event) => {
          event.preventDefault();
          const root = (event.currentTarget as HTMLElement).closest('[data-markdown-root]');
          const target = root?.querySelector(`[id="${slugifyDocumentHeading(anchor).replace(/"/g, '')}"]`)
            ?? root?.querySelector(`[id="${anchor.replace(/"/g, '')}"]`);
          target?.scrollIntoView({ block: 'start' });
        }}
      >
        {children}
      </a>
    );
  }
  const [pathPart, linePart] = href.split('#');
  if (onFileClick && pathPart && !/^[a-z][a-z0-9+.-]*:/i.test(pathPart)) {
    const resolved = resolveRelativePath(basePath, decodeURIComponent(pathPart));
    const line = linePart?.match(/^L(\d+)/)?.[1];
    return (
      <button
        type="button"
        title={title || resolved}
        className={cn(linkClass, "cursor-pointer")}
        onClick={() => onFileClick(resolved, line ? parseInt(line, 10) : undefined, sourceId)}
      >
        {children}
      </button>
    );
  }
  // Unbekanntes Schema (etwa javascript:) wird nicht verlinkt.
  return <span title={title}>{children}</span>;
};

/**
 * Bilder werden nicht geladen: externe Adressen verließen das eigene Netz (On-Premise),
 * relative Pfade kennt der Viewer nicht als abrufbare Datei. Stattdessen ein beschrifteter Platzhalter.
 */
const MarkdownImage: React.FC<{ alt: string; src: string; theme: string }> = ({ alt, src, theme }) => {
  const label = alt || src.split('/').pop() || src;
  return (
    <span
      role="img"
      aria-label={label}
      title={src}
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded border align-middle text-xs",
        theme === 'dark' ? "border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-300" : "border-ds-zinc-200 bg-ds-zinc-100 text-ds-zinc-650"
      )}
    >
      <ImageIcon aria-hidden="true" className="w-3 h-3 shrink-0" />
      {label}
    </span>
  );
};

// Bild oder Link (eine Klammerebene im Linktext, damit [![Badge](bild)](ziel) passt), <Autolink> oder nackte URL.
const INLINE_LINK_SPLIT_RE = /(!?\[(?:[^[\]]|\[[^[\]]*\])*\]\(\s*<?[^\s)>]+>?(?:\s+"[^"]*")?\s*\)|<https?:\/\/[^>\s]+>|https?:\/\/[^\s<>()[\]`]*[^\s<>()[\].,;:!?'"`])/g;
const INLINE_LINK_RE = /^(!?)\[((?:[^[\]]|\[[^[\]]*\])*)\]\(\s*<?([^\s)>]+)>?(?:\s+"([^"]*)")?\s*\)$/;
// **fett**, ~~durchgestrichen~~, *kursiv* und _kursiv_ (Unterstriche nur an Wortgrenzen, damit snake_case unberührt bleibt).
const EMPHASIS_SPLIT_RE = /(\*\*[^*]+\*\*|~~[^~\n]+~~|(?<![*\w])\*(?![\s*])[^*\n]+?(?<!\s)\*(?![*\w])|(?<![\w])_(?![\s_])[^_\n]+?(?<!\s)_(?![\w]))/g;
const ITALIC_RE = /^(?:\*(?![\s*])[^*\n]+?(?<!\s)\*|_(?![\s_])[^_\n]+?(?<!\s)_)$/;

const parseTextSegment = (
  text: string,
  keyPrefix: string,
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void,
  theme: string,
  knownSources?: KnownSource[]
) => {
  if (!text) return "";
  const backtickParts = text.split(/(`[^`]+`)/g);
  return backtickParts.map((bp, i) => {
    if (bp.startsWith('`') && bp.endsWith('`')) {
      const codeVal = bp.slice(1, -1);

      // Support for file.ext:line syntax, and file.ext:start-end ranges (LLMs
      // sometimes cite a whole block instead of a single line) -- collapse a
      // range down to its start line rather than leaving it stuck in filePath,
      // which used to break the lookup (see file.ext:start-end unresolved bug).
      let filePath = codeVal;
      let line: number | undefined = undefined;
      const lineMatch = codeVal.match(/^(.+\.\w+):(\d+)(?:-\d+)?$/);
      if (lineMatch) {
        filePath = lineMatch[1];
        line = parseInt(lineMatch[2], 10);
      }

      // Knowledge-source pages (e.g. Confluence/Jira) have no file extension, so they
      // never match the extension regex below -- they're recognized instead by an exact
      // (case-insensitive) match against the sources already resolved for this message.
      let knownSource = knownSources?.find(s => s.file.toLowerCase() === filePath.toLowerCase());

      // Despite the prompt telling it not to, a model sometimes appends a `:page` or
      // `:start-end` suffix to an extensionless knowledge-source title too, mirroring the
      // file:line syntax above -- strip it before the exact-title lookup instead of
      // failing to match on the raw (still-suffixed) string.
      if (!knownSource && !lineMatch) {
        const pageSuffixMatch = filePath.match(/^(.+):(\d+)(?:-\d+)?$/);
        if (pageSuffixMatch) {
          const maybeSource = knownSources?.find(s => s.file.toLowerCase() === pageSuffixMatch[1].toLowerCase());
          if (maybeSource) {
            knownSource = maybeSource;
            filePath = pageSuffixMatch[1];
            line = parseInt(pageSuffixMatch[2], 10);
          }
        }
      }

      // A model frequently cites just the bare filename (`DISPATCHER.cbl`) instead of the
      // full repo-relative path -- mirrors the by_basename fallback in resolve_cited_sources
      // (backend/services/chat_sources.py) that already resolved this same citation to its full path in
      // knownSources. Without this, the exact-match lookup above misses, the button falls
      // back to the bare filename as its fetch path, and the editor opens empty (file not
      // found at repo root) instead of the actual nested file.
      if (!knownSource && knownSources && /\.\w+$/.test(filePath)) {
        const baseName = filePath.toLowerCase().split('/').pop();
        knownSource = knownSources.find(s => (s.file.split('/').pop() || '').toLowerCase() === baseName);
        if (knownSource) filePath = knownSource.file;
      }

      const isFile = knownSource !== undefined || FILE_LIKE_RE.test(filePath);
      if (isFile) {
        return (
          <CitationChip
            key={`${keyPrefix}-${i}`}
            id={`file-link-${codeVal.replace(/[^a-zA-Z0-9]/g, "-")}`}
            cited={codeVal}
            path={filePath}
            line={line}
            isDoc={knownSource !== undefined || /\.(pdf|docx|doc|md|txt)$/i.test(filePath)}
            source={knownSource}
            theme={theme}
            onFileClick={onFileClick}
          />
        );
      }
      return (
        <code key={`${keyPrefix}-${i}`} className={cn(
          "px-1.5 py-0.5 mx-0.5 rounded font-mono text-xs border transition-colors duration-200 break-words",
          theme === 'dark'
            ? "bg-ds-zinc-900 text-ds-pink-400 border-ds-zinc-800/80"
            : "bg-ds-zinc-100 text-ds-pink-650 border-ds-zinc-200"
        )}>
          {codeVal}
        </code>
      );
    }

    return bp.split(INLINE_LINK_SPLIT_RE).map((lp, l) => {
      const linkKey = `${keyPrefix}-${i}-l${l}`;
      const link = lp.match(INLINE_LINK_RE);
      if (link) {
        const [, bang, label, target, title] = link;
        if (bang) return <MarkdownImage key={linkKey} alt={label} src={target} theme={theme} />;
        return (
          <MarkdownLink key={linkKey} href={target} title={title} theme={theme}>
            {parseTextSegment(label, linkKey, onFileClick, theme, knownSources)}
          </MarkdownLink>
        );
      }
      if (/^<https?:\/\/[^>\s]+>$/.test(lp) || /^https?:\/\//.test(lp)) {
        const href = lp.replace(/^<|>$/g, '');
        return <MarkdownLink key={linkKey} href={href} theme={theme}>{href}</MarkdownLink>;
      }
      return lp.split(EMPHASIS_SPLIT_RE).map((bp2, j) => {
        const partKey = `${linkKey}-${j}`;
        if (bp2.startsWith('**') && bp2.endsWith('**') && bp2.length > 4) {
          return (
            <strong key={partKey} className={cn("font-bold transition-colors duration-200", theme === 'dark' ? "text-ds-white" : "text-ds-zinc-950")}>
              {bp2.slice(2, -2)}
            </strong>
          );
        }
        if (bp2.startsWith('~~') && bp2.endsWith('~~') && bp2.length > 4) {
          return <del key={partKey}>{bp2.slice(2, -2)}</del>;
        }
        if (ITALIC_RE.test(bp2)) {
          return <em key={partKey}>{bp2.slice(1, -1)}</em>;
        }
        // Citations that lack backticks altogether (a common gap for local models,
        // especially inside table cells) still get a chance to resolve against
        // knownSources here, instead of only ever rendering as inert plain text.
        return renderPlainKnownSources(bp2, partKey, onFileClick, theme, knownSources ?? []);
      });
    });
  });
};

/**
 * Entry point for inline markdown parsing. Splits out literal `<br>`/`<br/>` tags
 * first -- some models emit them as a manual line break inside a single Markdown
 * table cell (GFM table syntax has no real newline), and without this they show up
 * as inert literal text instead of separating the lines they're meant to divide.
 */
export const parseText = (
  text: string,
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void,
  theme: string,
  knownSources?: KnownSource[]
) => {
  if (!text) return "";
  const lineParts = text.split(BR_TAG_SPLIT_RE);
  if (lineParts.length === 1) {
    return parseTextSegment(text, "s0", onFileClick, theme, knownSources);
  }
  return lineParts.map((part, li) =>
    BR_TAG_TEST_RE.test(part)
      ? <br key={`br-${li}`} />
      : parseTextSegment(part, `s${li}`, onFileClick, theme, knownSources)
  );
};

interface MarkdownContentProps {
  content: string;
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void;
  theme: string;
  knownSources?: KnownSource[];
  showLineNumbers?: boolean;
  /** Dateizitate im Text als Dateiname, voller Pfad beim Überfahren (Chat). */
  compactCitations?: boolean;
  /** Pfad des angezeigten Dokuments; relative Links werden dagegen aufgelöst. */
  basePath?: string;
  /** Wissensquelle des Dokuments, in der relative Links geöffnet werden. */
  baseSourceId?: string;
}

const HEADING_SIZE_CLASSES: Record<number, string> = {
  1: "text-xl font-bold mt-2",
  2: "text-lg font-bold mt-2",
  3: "text-base font-semibold mt-1",
  4: "text-[0.9375rem] font-semibold",
  5: "text-[0.9375rem] font-semibold",
  6: "text-[0.9375rem] font-semibold",
};

/**
 * Splits a GFM table row (`| a | b |`) into trimmed cell strings, unescaping
 * `\|` so literal pipes can appear inside a cell. Pipes inside a `` `code` ``
 * span are never treated as delimiters -- otherwise a citation like
 * `` `some|title.pdf` `` would be split mid-token and lose its closing
 * backtick, silently falling back to plain (unclickable) text.
 */
export const splitTableRow = (line: string): string[] => {
  let trimmed = line.trim();
  if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
  if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1);

  const cells: string[] = [];
  let current = '';
  let inCode = false;
  for (const ch of trimmed) {
    if (ch === '`') {
      inCode = !inCode;
      current += ch;
    } else if (ch === '|' && !inCode) {
      if (current.endsWith('\\')) {
        current = current.slice(0, -1) + '|';
      } else {
        cells.push(current);
        current = '';
      }
    } else {
      current += ch;
    }
  }
  cells.push(current);
  return cells.map(cell => cell.trim());
};

/** A separator row's cells all look like `---`, `:---`, `---:` or `:---:`. */
const isTableSeparatorLine = (line: string): boolean => {
  const trimmed = line.trim();
  if (!trimmed.includes('|') && !/^:?-+:?$/.test(trimmed)) return false;
  const cells = splitTableRow(trimmed);
  return cells.length > 0 && cells.every(cell => /^:?-+:?$/.test(cell));
};

type ColumnAlign = 'left' | 'center' | 'right' | undefined;

export const parseTableAlignment = (separatorLine: string): ColumnAlign[] =>
  splitTableRow(separatorLine).map(cell => {
    const left = cell.startsWith(':');
    const right = cell.endsWith(':');
    if (left && right) return 'center';
    if (right) return 'right';
    if (left) return 'left';
    return undefined;
  });

interface MarkdownTableProps {
  header: string[];
  align: ColumnAlign[];
  rows: string[][];
  theme: string;
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void;
  knownSources?: KnownSource[];
}

const MarkdownTable: React.FC<MarkdownTableProps> = ({ header, align, rows, theme, onFileClick, knownSources }) => {
  return (
    <div className={cn(
      "overflow-x-auto rounded-lg border my-4 no-scrollbar",
      theme === 'dark' ? "border-ds-zinc-800" : "border-ds-zinc-200"
    )}>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className={theme === 'dark' ? "bg-ds-zinc-900/60" : "bg-ds-zinc-100/80"}>
            {header.map((cell, i) => (
              <th
                key={i}
                style={{ textAlign: align[i] || 'left' }}
                className={cn(
                  "px-3 py-2 font-semibold border-b whitespace-normal",
                  theme === 'dark' ? "text-ds-white border-ds-zinc-800" : "text-ds-zinc-950 border-ds-zinc-200"
                )}
              >
                {parseText(cell, onFileClick, theme, knownSources)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr
              key={ri}
              className={cn(
                "border-b last:border-b-0",
                theme === 'dark' ? "border-ds-zinc-800/60" : "border-ds-zinc-200/80"
              )}
            >
              {header.map((_, ci) => (
                <td
                  key={ci}
                  style={{ textAlign: align[ci] || 'left' }}
                  className="px-3 py-2 align-top whitespace-normal"
                >
                  {row[ci] !== undefined ? parseText(row[ci], onFileClick, theme, knownSources) : null}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const LIST_ITEM_RE = /^(\s*)([-*+]|\d{1,9}[.)])[ \t]+(.*)$/;
const TASK_RE = /^\[([ xX])\]\s+(.*)$/;

interface MarkdownListItem {
  lines: string[];
  startLine: number;
  endLine: number;
  checked: boolean | null;
  children: MarkdownListNode[];
}

interface MarkdownListNode {
  ordered: boolean;
  start: number;
  items: MarkdownListItem[];
}

const indentWidth = (whitespace: string) => whitespace.replace(/\t/g, '    ').length;

/** Zeilen, die eine Liste beenden statt in ihren letzten Punkt einzufließen. */
const startsOtherBlock = (line: string) =>
  /^(#{1,6})\s/.test(line) || /^>/.test(line) || /^ {0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line) || line.trim().startsWith('|');

/**
 * Liest eine Liste ab `start`. Tiefere Einrückung (ab zwei Zeichen mehr) öffnet eine Unterliste,
 * eingerückte oder direkt folgende Zeilen gehören zum letzten Punkt, eine Leerzeile beendet die
 * Liste nur, wenn danach kein weiterer Punkt kommt.
 */
export const parseMarkdownList = (lines: string[], start: number): { list: MarkdownListNode; end: number } => {
  const first = lines[start].match(LIST_ITEM_RE)!;
  const root: MarkdownListNode = { ordered: /\d/.test(first[2]), start: parseInt(first[2], 10) || 1, items: [] };
  const stack: Array<{ node: MarkdownListNode; indent: number }> = [{ node: root, indent: indentWidth(first[1]) }];
  let lastItem: MarkdownListItem | null = null;
  let previousBlank = false;
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      let next = i + 1;
      while (next < lines.length && !lines[next].trim()) next++;
      const following = lines[next];
      const continues = following !== undefined && (LIST_ITEM_RE.test(following)
        ? indentWidth(following.match(LIST_ITEM_RE)![1]) >= stack[0].indent
        : indentWidth(following.match(/^\s*/)![0]) > stack[0].indent);
      if (!continues) {
        // Leerzeilen nach der Liste gehören weder zu ihr noch an den Anfang des nächsten Absatzes.
        i = next;
        break;
      }
      previousBlank = true;
      i = next;
      continue;
    }
    const match = line.match(LIST_ITEM_RE);
    if (match) {
      const indent = indentWidth(match[1]);
      if (indent < stack[0].indent) break;
      while (stack.length > 1 && indent < stack[stack.length - 1].indent) stack.pop();
      let top = stack[stack.length - 1];
      if (lastItem && indent >= top.indent + 2) {
        const child: MarkdownListNode = { ordered: /\d/.test(match[2]), start: parseInt(match[2], 10) || 1, items: [] };
        lastItem.children.push(child);
        stack.push({ node: child, indent });
        top = stack[stack.length - 1];
      }
      const task = match[3].match(TASK_RE);
      lastItem = {
        lines: [task ? task[2] : match[3]],
        startLine: i,
        endLine: i,
        checked: task ? task[1].toLowerCase() === 'x' : null,
        children: [],
      };
      top.node.items.push(lastItem);
      previousBlank = false;
      i++;
      continue;
    }
    const indented = indentWidth(line.match(/^\s*/)![0]) > stack[0].indent;
    if (lastItem && (indented || (!previousBlank && !startsOtherBlock(line)))) {
      // Fortsetzung des zuletzt geöffneten (tiefsten) Punkts.
      let deepest = lastItem;
      while (deepest.children.length) {
        const items = deepest.children[deepest.children.length - 1].items;
        deepest = items[items.length - 1];
      }
      deepest.lines.push(line.trim());
      deepest.endLine = i;
      previousBlank = false;
      i++;
      continue;
    }
    break;
  }
  return { list: root, end: i };
};

const MarkdownList: React.FC<{
  node: MarkdownListNode;
  depth: number;
  baseLine: number;
  theme: string;
  showLineNumbers: boolean;
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void;
  knownSources?: KnownSource[];
}> = ({ node, depth, baseLine, theme, showLineNumbers, onFileClick, knownSources }) => {
  const ListTag = node.ordered ? 'ol' : 'ul';
  const bullet = node.ordered ? 'list-decimal' : depth === 0 ? 'list-disc' : depth === 1 ? 'list-[circle]' : 'list-[square]';
  return (
    <ListTag
      start={node.ordered && node.start !== 1 ? node.start : undefined}
      className={cn(bullet, "pl-6 space-y-1 text-[0.9375rem] leading-relaxed", depth === 0 ? "my-2" : "mt-1", theme === 'dark' ? "marker:text-ds-zinc-500" : "marker:text-ds-zinc-400")}
    >
      {node.items.map((item, index) => (
        <li
          key={index}
          data-document-line-start={baseLine + item.startLine}
          data-document-line-end={baseLine + item.endLine}
          className={cn("whitespace-pre-wrap scroll-mt-4", item.checked !== null && "list-none -ml-5")}
        >
          {showLineNumbers && <span aria-hidden="true" className="mr-2 inline-block w-7 select-none text-right text-xs text-ds-zinc-500/70">{baseLine + item.startLine}</span>}
          {item.checked !== null && (
            <input type="checkbox" checked={item.checked} readOnly disabled className="mr-2 align-middle" aria-label={item.checked ? 'erledigt' : 'offen'} />
          )}
          {parseText(item.lines.join('\n'), onFileClick, theme, knownSources)}
          {item.children.map((child, childIndex) => (
            <MarkdownList key={childIndex} node={child} depth={depth + 1} baseLine={baseLine} theme={theme} showLineNumbers={showLineNumbers} onFileClick={onFileClick} knownSources={knownSources} />
          ))}
        </li>
      ))}
    </ListTag>
  );
};

/**
 * Renders a non-code chunk of text, splitting out ATX-style heading lines
 * (`#` .. `######`) into real heading elements, lists into `<ul>`/`<ol>` and
 * GFM-style pipe tables into real `<table>` elements, instead of leaving the
 * literal `#`/`-`/`|` characters in a plain paragraph.
 */
const renderTextBlock = (
  block: string,
  blockKey: number,
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void,
  theme: string,
  knownSources: KnownSource[] | undefined,
  baseLine: number,
  showLineNumbers: boolean,
) => {
  const lines = block.split('\n');
  const elements: React.ReactNode[] = [];
  let paragraphBuffer: string[] = [];
  let paragraphStartLine = baseLine;
  let paragraphEndLine = baseLine;

  const flushParagraph = (idx: number) => {
    if (paragraphBuffer.length === 0) return;
    const text = paragraphBuffer.join('\n');
    elements.push(
      <p
        key={`${blockKey}-p-${idx}`}
        data-document-line-start={paragraphStartLine}
        data-document-line-end={paragraphEndLine}
        className="leading-relaxed whitespace-pre-wrap text-[0.9375rem] scroll-mt-4"
      >
        {showLineNumbers ? lines.slice(paragraphStartLine - baseLine, paragraphEndLine - baseLine + 1).map((lineText, lineIndex) => (
          <span key={lineIndex} className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-3">
            <span aria-hidden="true" className="select-none text-right text-ds-zinc-500/70">{paragraphStartLine + lineIndex}</span>
            <span>{parseText(lineText || ' ', onFileClick, theme, knownSources)}</span>
          </span>
        )) : parseText(text, onFileClick, theme, knownSources)}
      </p>
    );
    paragraphBuffer = [];
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph(i);
      const level = Math.min(headingMatch[1].length, 6);
      const HeadingTag = `h${level}` as keyof JSX.IntrinsicElements;
      elements.push(
        <HeadingTag
          key={`${blockKey}-h-${i}`}
          id={slugifyDocumentHeading(headingMatch[2])}
          data-document-line-start={baseLine + i}
          data-document-line-end={baseLine + i}
          className={cn(HEADING_SIZE_CLASSES[level], theme === 'dark' ? "text-ds-white" : "text-ds-zinc-950", "scroll-mt-4")}
        >
          {showLineNumbers && <span aria-hidden="true" className="mr-3 inline-block w-7 select-none text-right text-xs font-normal text-ds-zinc-500/70">{baseLine + i}</span>}
          {parseText(headingMatch[2], onFileClick, theme, knownSources)}
        </HeadingTag>
      );
      i++;
      continue;
    }

    if (/^ {0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushParagraph(i);
      elements.push(
        <hr
          key={`${blockKey}-hr-${i}`}
          data-document-line-start={baseLine + i}
          data-document-line-end={baseLine + i}
          className={cn("my-4 border-t", theme === 'dark' ? "border-ds-zinc-800" : "border-ds-zinc-200")}
        />
      );
      i++;
      continue;
    }

    const blockquoteMatch = line.match(/^>\s?(.*)$/);
    if (blockquoteMatch) {
      flushParagraph(i);
      const quoteLines = [blockquoteMatch[1]];
      let k = i + 1;
      while (k < lines.length) {
        const m = lines[k].match(/^>\s?(.*)$/);
        if (!m) break;
        quoteLines.push(m[1]);
        k++;
      }
      elements.push(
        <blockquote
          key={`${blockKey}-bq-${i}`}
          data-document-line-start={baseLine + i}
          data-document-line-end={baseLine + k - 1}
          className={cn(
            "border-l-4 pl-3 py-1 my-3 rounded-r leading-relaxed whitespace-pre-wrap text-[0.9375rem] scroll-mt-4",
            theme === 'dark' ? "border-ds-zinc-700 bg-ds-zinc-900/30 text-ds-zinc-400" : "border-ds-zinc-300 bg-ds-zinc-100/60 text-ds-zinc-600"
          )}
        >
          {parseText(quoteLines.join("\n"), onFileClick, theme, knownSources)}
        </blockquote>
      );
      i = k;
      continue;
    }

    if (LIST_ITEM_RE.test(line)) {
      flushParagraph(i);
      const { list, end } = parseMarkdownList(lines, i);
      elements.push(
        <MarkdownList
          key={`${blockKey}-list-${i}`}
          node={list}
          depth={0}
          baseLine={baseLine}
          theme={theme}
          showLineNumbers={showLineNumbers}
          onFileClick={onFileClick}
          knownSources={knownSources}
        />
      );
      i = end;
      continue;
    }

    const nextLine = lines[i + 1];
    if (line.trim().includes('|') && nextLine !== undefined && isTableSeparatorLine(nextLine)) {
      flushParagraph(i);
      const header = splitTableRow(line);
      const align = parseTableAlignment(nextLine);
      let j = i + 2;
      const rows: string[][] = [];
      while (j < lines.length && lines[j].trim().includes('|') && !isTableSeparatorLine(lines[j])) {
        rows.push(splitTableRow(lines[j]));
        j++;
      }
      elements.push(
        <div
          key={`${blockKey}-table-${i}`}
          data-document-line-start={baseLine + i}
          data-document-line-end={baseLine + j - 1}
        >
          <MarkdownTable
            header={header}
            align={align}
            rows={rows}
            theme={theme}
            onFileClick={onFileClick}
            knownSources={knownSources}
          />
        </div>
      );
      i = j;
      continue;
    }

    if (paragraphBuffer.length === 0) paragraphStartLine = baseLine + i;
    paragraphBuffer.push(line);
    paragraphEndLine = baseLine + i;
    i++;
  }
  flushParagraph(lines.length);

  return <React.Fragment key={blockKey}>{elements}</React.Fragment>;
};

function slugifyDocumentHeading(heading: string) {
  return heading
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, '')
    .trim()
    .replace(/\s+/g, '-');
}

/**
 * Main MarkdownContent component that parses blocks of code and normal paragraphs,
 * transforming them into HTML elements with syntax highlights and link badges.
 */
export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, onFileClick, theme, knownSources, showLineNumbers = false, compactCitations = false, basePath, baseSourceId }) => {
  if (!content) return null;
  const parts = content.split(/(```[\s\S]*?```)/g);
  return (
    <CompactCitationsContext.Provider value={compactCitations}>
    <MarkdownLinkContext.Provider value={{ basePath, sourceId: baseSourceId, onFileClick }}>
    <div data-markdown-root="" className={cn("space-y-3 transition-colors duration-200", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")}>
      {parts.map((part, index) => {
        // Compute offsets from immutable preceding parts. Mutating a render-
        // scoped counter inside `map` violates React's render purity and can
        // also make citation/document line locators unstable across renders.
        const startLine = 1 + parts
          .slice(0, index)
          .reduce((line, previous) => line + (previous.match(/\n/g) || []).length, 0);
        const endLine = startLine + (part.match(/\n/g) || []).length;
        if (part.startsWith('```') && part.endsWith('```')) {
          const match = part.match(/```(\w*)\n([\s\S]*?)```/);
          const lang = match ? match[1] : 'code';
          const code = match ? match[2] : part.slice(3, -3);
          return (
            <div
              key={index}
              data-document-line-start={startLine}
              data-document-line-end={endLine}
            >
              <CodeBlock language={lang} code={code} theme={theme} showLineNumbers={showLineNumbers} startLine={startLine + (match ? 1 : 0)} />
            </div>
          );
        } else {
          return renderTextBlock(part, index, onFileClick, theme, knownSources, startLine, showLineNumbers);
        }
      })}
    </div>
    </MarkdownLinkContext.Provider>
    </CompactCitationsContext.Provider>
  );
};
