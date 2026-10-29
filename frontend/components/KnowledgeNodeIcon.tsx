import {
  AlignLeft, BookOpen, Braces, Cog, ExternalLink, File, FileCode2, FileText, Files, Globe, Hash, Layers, Lightbulb, Link2, Tag, Ticket,
  type LucideIcon,
} from 'lucide-react';
import type { ReactElement } from 'react';
import {
  getGraphNodeIconKind, getGraphNodeIconName, type GraphIconKind, type GraphNodeIconName, type GraphTaxonomyNode,
} from '@/lib/graphTaxonomy';

export type KnowledgeNodeIconKind = GraphIconKind;
type IconNode = GraphTaxonomyNode & { x?: number; y?: number };

const NODE_ICONS: Record<GraphNodeIconName, LucideIcon> = {
  insight: Lightbulb,
  cobol: FileCode2,
  jcl: Cog,
  copybook: BookOpen,
  git: Braces,
  code: Braces,
  external: ExternalLink,
  confluence: Globe,
  web: Link2,
  jira: Ticket,
  pdf: FileText,
  file: File,
  txt: AlignLeft,
  md: Hash,
  document: Files,
  group: Layers,
  topic: Tag,
};

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
  /** Filter legends pass the category directly instead of a representative node. */
  category?: string;
  className?: string;
  title?: string;
}

export function KnowledgeNodeIcon({ node, category, className, title }: KnowledgeNodeIconProps) {
  const Icon = NODE_ICONS[getGraphNodeIconName(node, category)];
  return <Icon className={className} aria-hidden={title ? undefined : true} aria-label={title} />;
}

type SvgElement = [string, Record<string, string | number>];
const canvasPaths = new Map<GraphNodeIconName, Path2D[]>();

function svgElementPath([tag, attrs]: SvgElement): string | null {
  const n = (key: string) => Number(attrs[key] ?? 0);
  switch (tag) {
    case 'path': return String(attrs.d ?? '');
    case 'line': return `M${n('x1')} ${n('y1')}L${n('x2')} ${n('y2')}`;
    case 'circle':
    case 'ellipse': {
      const rx = tag === 'circle' ? n('r') : n('rx'), ry = tag === 'circle' ? n('r') : n('ry');
      return `M${n('cx') - rx} ${n('cy')}a${rx} ${ry} 0 1 0 ${2 * rx} 0a${rx} ${ry} 0 1 0 ${-2 * rx} 0`;
    }
    case 'rect': {
      const x = n('x'), y = n('y'), w = n('width'), h = n('height'), r = Math.min(n('rx'), w / 2, h / 2);
      return `M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}`
        + `h${-(w - 2 * r)}a${r} ${r} 0 0 1 ${-r} ${-r}v${-(h - 2 * r)}a${r} ${r} 0 0 1 ${r} ${-r}Z`;
    }
    case 'polyline':
    case 'polygon': return `M${String(attrs.points ?? '').trim()}${tag === 'polygon' ? 'Z' : ''}`;
    default: return null;
  }
}

/** Lucide's 24×24 outlines as Path2D, so canvas nodes show the same glyph as lists and filters. */
function iconCanvasPaths(name: GraphNodeIconName): Path2D[] {
  const cached = canvasPaths.get(name);
  if (cached) return cached;
  // lucide-react exports only components; the outline data is the iconNode prop of the forwardRef render result.
  const icon = NODE_ICONS[name] as unknown as { render?: (props: object, ref: null) => ReactElement<{ iconNode?: SvgElement[] }> };
  const elements = icon.render?.({}, null)?.props.iconNode ?? [];
  const paths = elements.flatMap(element => {
    const d = svgElementPath(element);
    return d ? [new Path2D(d)] : [];
  });
  canvasPaths.set(name, paths);
  return paths;
}

/** Draw the same icon family inside a force-graph canvas node. */
export function drawKnowledgeNodeIcon(node: IconNode | null | undefined, ctx: CanvasRenderingContext2D, globalScale: number, sizeScale = 1, nodeRadius?: number) {
  if (typeof Path2D === 'undefined') return;
  const x = node?.x ?? 0;
  const y = node?.y ?? 0;
  // Beim Herauszoomen wächst das Symbol in Weltkoordinaten mit; es darf den Knoten nie füllen, sonst bleibt kein farbiger Rand.
  const size = Math.max(5, Math.min(8, 7 / Math.max(globalScale, 0.01))) * sizeScale;
  const cappedSize = nodeRadius ? Math.min(size, nodeRadius * 0.8) : size;
  const strokeWidth = Math.min(Math.max(0.7, 1.1 / Math.max(globalScale, 0.01)) * Math.sqrt(sizeScale), cappedSize * 0.12);
  const unit = cappedSize / 24;

  ctx.save();
  ctx.translate(x - cappedSize / 2, y - cappedSize / 2);
  ctx.scale(unit, unit);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.94)';
  ctx.lineWidth = strokeWidth / unit;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  iconCanvasPaths(getGraphNodeIconName(node)).forEach(path => ctx.stroke(path));
  ctx.restore();
}
