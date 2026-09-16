import { Code2, FileText, Globe2 } from 'lucide-react';
import { getGraphNodeIconKind, type GraphIconKind, type GraphTaxonomyNode } from '@/lib/graphTaxonomy';

export type KnowledgeNodeIconKind = GraphIconKind;
type IconNode = GraphTaxonomyNode & { x?: number; y?: number };

/**
 * Resolve the visual kind for all node shapes used by graph, search, topics,
 * link-manager and reference lists. The metadata names intentionally cover
 * both API responses and the small view-specific wrapper objects.
 */
export function getKnowledgeNodeIconKind(node: IconNode | null | undefined): KnowledgeNodeIconKind {
  return getGraphNodeIconKind(node);
}

interface KnowledgeNodeIconProps {
  node: IconNode | null | undefined;
  className?: string;
  title?: string;
}

export function KnowledgeNodeIcon({ node, className, title }: KnowledgeNodeIconProps) {
  const kind = getKnowledgeNodeIconKind(node);
  const Icon = kind === 'code' ? Code2 : kind === 'web' ? Globe2 : FileText;
  return <Icon className={className} aria-hidden={title ? undefined : true} aria-label={title} />;
}

/** Draw the same icon family inside a force-graph canvas node. */
export function drawKnowledgeNodeIcon(node: IconNode | null | undefined, ctx: CanvasRenderingContext2D, globalScale: number) {
  const kind = getKnowledgeNodeIconKind(node);
  const x = node?.x ?? 0;
  const y = node?.y ?? 0;
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
