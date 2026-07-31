import React, { useState } from 'react';
import { Check, Layers, BookOpen, Code } from 'lucide-react';
import { cn, copyToClipboard } from "@/lib/utils";
import { useLanguage } from '@/lib/i18n/LanguageContext';

interface CodeBlockProps {
  language: string;
  code: string;
  theme: string;
}

/**
 * Reusable CodeBlock component that renders a stylized code window
 * with language badge and copy-to-clipboard functionality.
 */
export const CodeBlock: React.FC<CodeBlockProps> = ({ language, code, theme }) => {
  const { t } = useLanguage();
  const [copied, setCopied] = useState(false);

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
      theme === 'dark' ? "border-zinc-800 bg-zinc-950/80" : "border-zinc-200 bg-zinc-50/90"
    )}>
      <div className={cn(
        "flex items-center justify-between px-4 py-2 border-b text-[11px] font-mono transition-colors duration-200",
        theme === 'dark' ? "border-zinc-800 bg-zinc-900/40 text-zinc-400" : "border-zinc-200 bg-zinc-200/50 text-zinc-650"
      )}>
        <span className="capitalize font-semibold">{language || 'code'}</span>
        <button 
          type="button"
          onClick={handleCopy}
          id="copy-code-btn"
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded border transition-all text-xs font-medium",
            theme === 'dark' 
              ? "bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border-zinc-800 hover:border-zinc-750" 
              : "bg-white hover:bg-zinc-100 text-zinc-750 border-zinc-200 hover:border-zinc-300"
          )}
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-emerald-500" />
              <span className="text-emerald-500 font-semibold">{t('common.copied')}</span>
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
        theme === 'dark' ? "text-zinc-300 bg-black/20" : "text-zinc-800 bg-black/5"
      )}>
        <code>{code}</code>
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
  source_id?: string | null;
}

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const BR_TAG_SPLIT_RE = /(<br\s*\/?>)/gi;
const BR_TAG_TEST_RE = /^<br\s*\/?>$/i;

/**
 * Local models frequently skip the backtick citation format inside table cells
 * even though the prompt asks for it there too (see the citation_note in
 * backend/api/chat.py) -- this recognizes a known knowledge-source title as plain
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
  if (candidates.length === 0) return [segment];
  const pattern = new RegExp(`(${candidates.map(s => escapeRegExp(s.file)).join('|')})(?::(\\d+)(?:-\\d+)?)?`, 'gi');

  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let idx = 0;
  while ((match = pattern.exec(segment)) !== null) {
    if (match.index > lastIndex) nodes.push(segment.slice(lastIndex, match.index));
    const title = match[1];
    const knownSource = candidates.find(s => s.file.toLowerCase() === title.toLowerCase());
    const line = match[2] ? parseInt(match[2], 10) : undefined;
    nodes.push(
      <button
        type="button"
        key={`${keyPrefix}-plain-${idx++}`}
        onClick={() => onFileClick(title, line, knownSource?.source_id ?? undefined)}
        className={cn(
          "px-1.5 py-0.5 mx-0.5 rounded font-mono text-xs inline-flex items-center gap-1 border transition-all cursor-pointer align-middle max-w-full truncate",
          theme === 'dark'
            ? "bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 border-indigo-500/20"
            : "bg-indigo-50 text-indigo-650 hover:bg-indigo-100 border-indigo-200"
        )}
      >
        <BookOpen className="w-3 h-3 text-emerald-400 shrink-0" />
        <span className="truncate">{match[0]}</span>
      </button>
    );
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < segment.length) nodes.push(segment.slice(lastIndex));
  return nodes.length > 0 ? nodes : [segment];
};

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

      const isFile = knownSource !== undefined || /\b[\w\-\.\/]+\.(py|cob|cbl|cpy|java|js|ts|json|md|txt|yml|yaml|css|html|pdf|docx|doc|jcl|proc)\b/i.test(filePath);
      if (isFile) {
        const isDoc = knownSource !== undefined || /\.(pdf|docx|doc|md|txt)$/i.test(filePath);
        return (
          <button
            key={`${keyPrefix}-${i}`}
            type="button"
            id={`file-link-${codeVal.replace(/[^a-zA-Z0-9]/g, "-")}`}
            onClick={() => onFileClick(filePath, line, knownSource?.source_id ?? undefined)}
            className={cn(
              "px-1.5 py-0.5 mx-0.5 rounded font-mono text-xs inline-flex items-center gap-1 border transition-all cursor-pointer align-middle max-w-full truncate",
              theme === 'dark'
                ? "bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 border-indigo-500/20"
                : "bg-indigo-50 text-indigo-650 hover:bg-indigo-100 border-indigo-200"
            )}
          >
            {isDoc ? <BookOpen className="w-3 h-3 text-emerald-400 shrink-0" /> : <Code className="w-3 h-3 shrink-0" />}
            <span className="truncate">{codeVal}</span>
          </button>
        );
      }
      return (
        <code key={`${keyPrefix}-${i}`} className={cn(
          "px-1.5 py-0.5 mx-0.5 rounded font-mono text-xs border transition-colors duration-200 break-words",
          theme === 'dark'
            ? "bg-zinc-900 text-pink-400 border-zinc-800/80"
            : "bg-zinc-100 text-pink-650 border-zinc-200"
        )}>
          {codeVal}
        </code>
      );
    }

    const boldParts = bp.split(/(\*\*[^*]+\*\*)/g);
    return boldParts.map((bp2, j) => {
      const partKey = `${keyPrefix}-${i}-${j}`;
      if (bp2.startsWith('**') && bp2.endsWith('**')) {
        return (
          <strong key={partKey} className={cn("font-bold transition-colors duration-200", theme === 'dark' ? "text-white" : "text-zinc-950")}>
            {bp2.slice(2, -2)}
          </strong>
        );
      }
      // Citations that lack backticks altogether (a common gap for local models,
      // especially inside table cells) still get a chance to resolve against
      // knownSources here, instead of only ever rendering as inert plain text.
      return knownSources && knownSources.length > 0
        ? renderPlainKnownSources(bp2, partKey, onFileClick, theme, knownSources)
        : bp2;
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
}

const HEADING_SIZE_CLASSES: Record<number, string> = {
  1: "text-xl font-bold mt-2",
  2: "text-lg font-bold mt-2",
  3: "text-base font-semibold mt-1",
  4: "text-[15px] font-semibold",
  5: "text-[15px] font-semibold",
  6: "text-[15px] font-semibold",
};

/**
 * Splits a GFM table row (`| a | b |`) into trimmed cell strings, unescaping
 * `\|` so literal pipes can appear inside a cell. Pipes inside a `` `code` ``
 * span are never treated as delimiters -- otherwise a citation like
 * `` `some|title.pdf` `` would be split mid-token and lose its closing
 * backtick, silently falling back to plain (unclickable) text.
 */
const splitTableRow = (line: string): string[] => {
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

const parseTableAlignment = (separatorLine: string): ColumnAlign[] =>
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

const MarkdownTable: React.FC<MarkdownTableProps> = ({ header, align, rows, theme, onFileClick, knownSources }) => (
  <div className={cn(
    "overflow-x-auto rounded-lg border my-4 no-scrollbar",
    theme === 'dark' ? "border-zinc-800" : "border-zinc-200"
  )}>
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className={theme === 'dark' ? "bg-zinc-900/60" : "bg-zinc-100/80"}>
          {header.map((cell, i) => (
            <th
              key={i}
              style={{ textAlign: align[i] || 'left' }}
              className={cn(
                "px-3 py-2 font-semibold border-b whitespace-normal",
                theme === 'dark' ? "text-white border-zinc-800" : "text-zinc-950 border-zinc-200"
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
              theme === 'dark' ? "border-zinc-800/60" : "border-zinc-200/80"
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

/**
 * Renders a non-code chunk of text, splitting out ATX-style heading lines
 * (`#` .. `######`) into real heading elements and GFM-style pipe tables
 * into real `<table>` elements, instead of leaving the literal `#`/`|`
 * characters in a plain paragraph.
 */
const renderTextBlock = (
  block: string,
  blockKey: number,
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void,
  theme: string,
  knownSources?: KnownSource[]
) => {
  const lines = block.split('\n');
  const elements: React.ReactNode[] = [];
  let paragraphBuffer: string[] = [];

  const flushParagraph = (idx: number) => {
    if (paragraphBuffer.length === 0) return;
    const text = paragraphBuffer.join('\n');
    elements.push(
      <p key={`${blockKey}-p-${idx}`} className="leading-relaxed whitespace-pre-wrap text-[15px]">
        {parseText(text, onFileClick, theme, knownSources)}
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
          className={cn(HEADING_SIZE_CLASSES[level], theme === 'dark' ? "text-white" : "text-zinc-950")}
        >
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
          className={cn("my-4 border-t", theme === 'dark' ? "border-zinc-800" : "border-zinc-200")}
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
          className={cn(
            "border-l-4 pl-3 py-1 my-3 rounded-r leading-relaxed whitespace-pre-wrap text-[15px]",
            theme === 'dark' ? "border-zinc-700 bg-zinc-900/30 text-zinc-400" : "border-zinc-300 bg-zinc-100/60 text-zinc-600"
          )}
        >
          {parseText(quoteLines.join('\n'), onFileClick, theme, knownSources)}
        </blockquote>
      );
      i = k;
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
        <MarkdownTable
          key={`${blockKey}-table-${i}`}
          header={header}
          align={align}
          rows={rows}
          theme={theme}
          onFileClick={onFileClick}
          knownSources={knownSources}
        />
      );
      i = j;
      continue;
    }

    paragraphBuffer.push(line);
    i++;
  }
  flushParagraph(lines.length);

  return <React.Fragment key={blockKey}>{elements}</React.Fragment>;
};

/**
 * Main MarkdownContent component that parses blocks of code and normal paragraphs,
 * transforming them into HTML elements with syntax highlights and link badges.
 */
export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, onFileClick, theme, knownSources }) => {
  if (!content) return null;
  const parts = content.split(/(```[\s\S]*?```)/g);
  return (
    <div className={cn("space-y-3 transition-colors duration-200", theme === 'dark' ? "text-zinc-200" : "text-zinc-800")}>
      {parts.map((part, index) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const match = part.match(/```(\w*)\n([\s\S]*?)```/);
          const lang = match ? match[1] : 'code';
          const code = match ? match[2] : part.slice(3, -3);
          return <CodeBlock key={index} language={lang} code={code} theme={theme} />;
        } else {
          return renderTextBlock(part, index, onFileClick, theme, knownSources);
        }
      })}
    </div>
  );
};
