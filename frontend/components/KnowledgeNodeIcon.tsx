import React from 'react';
import { Code2, FileText, Globe2 } from 'lucide-react';

export type KnowledgeNodeIconKind = 'code' | 'document' | 'web';

const WEB_SOURCE_TYPES = new Set([
  'confluence',
  'jira',
  'web',
  'webpage',
  'webdav',
  'url',
  'http',
  'https',
]);

function textValue(value: unknown): string {
  return typeof value === 'string' ? value.toLowerCase() : '';
}

/**
 * Resolve the visual kind for all node shapes used by graph, search, topics,
 * link-manager and reference lists. The metadata names intentionally cover
 * both API responses and the small view-specific wrapper objects.
 */
export function getKnowledgeNodeIconKind(node: any): KnowledgeNodeIconKind {
  if (!node) return 'document';

  const nodeType = textValue(node.node_type || node.type || node.kind);
  const entityType = textValue(node.entity_type || node.entityType);
  const meta = node.node_meta || node.meta || {};
  const metaType = textValue(meta.type || meta.source_type || meta.sourceType);
  const sourceType = textValue(
    node.source_type || node.sourceType || meta.source_type || meta.sourceType ||
    (nodeType === 'knowledge_source' ? meta.type : '')
  );
  const url = node.url || node.node_url || node.nodeUrl;

  if (
    nodeType === 'entity' ||
    nodeType === 'code' ||
    nodeType === 'cobol' ||
    nodeType === 'jcl' ||
    nodeType === 'git' ||
    nodeType === 'copybook' ||
    nodeType === 'external' ||
    ['program', 'section', 'paragraph', 'data_item', 'file_fd', 'sql_table', 'sql_block'].includes(entityType)
  ) {
    return 'code';
  }

  // A document belonging to a Git source is a code file, while a document
  // from a browser-backed source is represented by a globe.
  if (sourceType === 'git' || metaType === 'git') return 'code';
  if (WEB_SOURCE_TYPES.has(sourceType) || WEB_SOURCE_TYPES.has(metaType)) return 'web';
  if (typeof url === 'string' && /^https?:\/\//i.test(url)) return 'web';

  return 'document';
}

interface KnowledgeNodeIconProps {
  node: any;
  className?: string;
  title?: string;
}

export function KnowledgeNodeIcon({ node, className, title }: KnowledgeNodeIconProps) {
  const kind = getKnowledgeNodeIconKind(node);
  const Icon = kind === 'code' ? Code2 : kind === 'web' ? Globe2 : FileText;
  return <Icon className={className} aria-hidden={title ? undefined : true} aria-label={title} />;
}

/** Draw the same icon family inside a force-graph canvas node. */
export function drawKnowledgeNodeIcon(node: any, ctx: CanvasRenderingContext2D, globalScale: number) {
  const kind = getKnowledgeNodeIconKind(node);
  const x = node.x ?? 0;
  const y = node.y ?? 0;
  const size = Math.max(5, Math.min(8, 7 / Math.max(globalScale, 0.01)));
  const strokeWidth = Math.max(0.7, 1.1 / Math.max(globalScale, 0.01));

  ctx.save();
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.94)';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.94)';
  ctx.lineWidth = strokeWidth;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  if (kind === 'code') {
    ctx.font = `700 ${size}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('</>', x, y + 0.25 / Math.max(globalScale, 0.01));
  } else if (kind === 'web') {
    ctx.beginPath();
    ctx.arc(x, y, size * 0.52, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.ellipse(x, y, size * 0.22, size * 0.52, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x - size * 0.5, y);
    ctx.lineTo(x + size * 0.5, y);
    ctx.stroke();
  } else {
    const halfWidth = size * 0.42;
    const halfHeight = size * 0.55;
    ctx.beginPath();
    ctx.rect(x - halfWidth, y - halfHeight, halfWidth * 2, halfHeight * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x - halfWidth * 0.55, y - size * 0.12);
    ctx.lineTo(x + halfWidth * 0.55, y - size * 0.12);
    ctx.moveTo(x - halfWidth * 0.55, y + size * 0.18);
    ctx.lineTo(x + halfWidth * 0.55, y + size * 0.18);
    ctx.stroke();
  }

  ctx.restore();
}
