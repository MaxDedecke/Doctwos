import type { WorkspaceDocument } from '@/types/domain';
import { useEffect, useRef } from 'react';

const normalizeLocatorText = (value: string) =>
  value.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();

function findDocumentLocatorTarget(container: HTMLElement, selectedDoc: WorkspaceDocument) {
  if (selectedDoc.urlAnchor) {
    let anchor = selectedDoc.urlAnchor.replace(/^#/, '');
    try {
      anchor = decodeURIComponent(anchor);
    } catch {
      // Keep the source-provided anchor when it is not valid percent encoding.
    }
    const anchorTarget = Array.from(container.querySelectorAll<HTMLElement>('[id], [name]'))
      .find(element => element.id === anchor || element.getAttribute('name') === anchor);
    if (anchorTarget) return anchorTarget;
  }

  if (selectedDoc.section) {
    const section = normalizeLocatorText(selectedDoc.section);
    const headings = Array.from(container.querySelectorAll<HTMLElement>('h1, h2, h3, h4, h5, h6'));
    const exactHeading = headings.find(element => normalizeLocatorText(element.innerText || element.textContent || '') === section);
    const partialHeading = exactHeading || headings.find(element =>
      normalizeLocatorText(element.innerText || element.textContent || '').includes(section)
    );
    if (partialHeading) return partialHeading;
  }

  if (selectedDoc.startLine != null) {
    const lineTargets = Array.from(container.querySelectorAll<HTMLElement>('[data-document-line-start]'));
    const exactLine = lineTargets.find(element => {
      const start = Number(element.dataset.documentLineStart);
      const end = Number(element.dataset.documentLineEnd ?? start);
      return start <= selectedDoc.startLine! && end >= selectedDoc.startLine!;
    });
    if (exactLine) return exactLine;
    const nearestLine = lineTargets
      .map(element => ({ element, distance: Math.abs(Number(element.dataset.documentLineStart) - selectedDoc.startLine!) }))
      .sort((a, b) => a.distance - b.distance)[0];
    if (nearestLine) return nearestLine.element;
  }

  if (selectedDoc.excerpt) {
    const excerpt = normalizeLocatorText(selectedDoc.excerpt).slice(0, 120);
    if (excerpt) {
      const blocks = Array.from(container.querySelectorAll<HTMLElement>('p, blockquote, pre'));
      const excerptBlock = blocks.find(element => normalizeLocatorText(element.innerText || element.textContent || '').includes(excerpt));
      if (excerptBlock) return excerptBlock;
    }
  }
  return null;
}


export function useDocumentLocator(
  activeRightTab: 'code' | 'doc' | 'weborigin' | 'graph',
  selectedDoc: WorkspaceDocument | null,
  content: string,
  format: string,
  isLoading: boolean,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (activeRightTab !== 'doc' || !selectedDoc || isLoading) return;
    const frame = requestAnimationFrame(() => {
      const container = containerRef.current;
      if (!container) return;
      container.querySelectorAll('.document-reference-highlight').forEach(element => {
        element.classList.remove('document-reference-highlight');
      });
      const target = findDocumentLocatorTarget(container, selectedDoc);
      if (!target) return;
      target.classList.add('document-reference-highlight');
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    return () => cancelAnimationFrame(frame);
  }, [activeRightTab, content, format, isLoading, selectedDoc]);
  return containerRef;
}
