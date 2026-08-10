"use client";

import React from 'react';
import { AlertCircle, Loader2, Waypoints } from 'lucide-react';
import { cn } from "@/lib/utils";
import { DoctusIcon } from '@/components/Logo';
import { getConnectorMetadata } from '@/lib/sourceConnectors';

interface SourceNetworkGraphProps {
  sources: any[];
  theme: string;
  scopeLabel: string;
}

// Ab dieser Anzahl werden die restlichen Quellen zu einem einzelnen
// "+N weitere"-Knoten zusammengefasst, damit der Graph bei vielen Quellen
// (z.B. viele Confluence-Spaces) lesbar bleibt statt die Karte zu sprengen.
const MAX_VISIBLE_NODES = 6;

/**
 * Kompakte Netzwerk-Visualisierung: alle (gefilterten) Wissensquellen als
 * Knoten am rechten Rand, Doctus als Hub links. Pfeile zeigen die
 * Informationsrichtung an — aktuell ausschließlich Quelle -> Doctus (Ingest).
 * Für spätere bidirektionale Flüsse (z.B. Doctus schreibt zurück in eine
 * Wissensquelle) ist pro Knoten bereits ein `direction`-Feld vorgesehen,
 * das aktuell hart auf 'in' steht.
 */
export const SourceNetworkGraph: React.FC<SourceNetworkGraphProps> = ({ sources, theme, scopeLabel }) => {
  const visible = sources.slice(0, MAX_VISIBLE_NODES);
  const overflowCount = sources.length - visible.length;

  type Node = {
    id: string;
    name: string;
    status: 'syncing' | 'error' | 'synced' | 'ready';
    direction: 'in' | 'out';
    meta: ReturnType<typeof getConnectorMetadata>;
    isOverflow?: boolean;
  };

  const nodes: Node[] = visible.map((inst) => ({
    id: String(inst.id),
    name: inst.name,
    status: inst.sync_status === 'syncing' ? 'syncing'
      : inst.sync_status === 'error' ? 'error'
      : inst.last_synced_at ? 'synced'
      : 'ready',
    direction: 'in',
    meta: getConnectorMetadata(inst.type),
  }));

  if (overflowCount > 0) {
    nodes.push({
      id: '__overflow__',
      name: `+${overflowCount} weitere`,
      status: 'ready',
      direction: 'in',
      meta: getConnectorMetadata(undefined),
      isOverflow: true,
    });
  }

  const count = nodes.length;
  // Vertikale Position jedes Quellknotens in Prozent des Containers.
  const nodeY = (i: number) => count === 1 ? 50 : (100 / (count * 2)) + (i * 100) / count;

  const DOCTUS_X = 12;
  const DOCTUS_Y = 50;
  const NODE_X = 88;

  const edgeColor = (status: Node['status']) => {
    if (status === 'error') return theme === 'dark' ? '#f87171' : '#dc2626';
    if (status === 'syncing') return theme === 'dark' ? '#60a5fa' : '#2563eb';
    return theme === 'dark' ? '#52525b' : '#a1a1aa';
  };

  return (
    <div className={cn(
      "rounded-lg border p-4 sm:p-5 transition-colors duration-300",
      theme === 'dark' ? "bg-ds-zinc-900/40 border-ds-zinc-800/80" : "bg-ds-white/80 border-ds-zinc-200"
    )}>
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <Waypoints className={cn("w-4 h-4", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")} />
          <h5 className={cn("text-sm font-bold uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-450" : "text-ds-zinc-550")}>
            Quellen-Netzwerk
          </h5>
        </div>
        <span className={cn(
          "text-[11px] font-bold px-2 py-1 rounded-sm border shrink-0",
          theme === 'dark' ? "bg-ds-zinc-950/60 border-ds-zinc-800 text-ds-zinc-400" : "bg-ds-zinc-50 border-ds-zinc-200 text-ds-zinc-550"
        )}>
          {scopeLabel}
        </span>
      </div>

      {sources.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <DoctusIcon className="w-10 h-10 opacity-30 shrink-0" />
          <p className={cn("text-sm ml-4 max-w-sm leading-relaxed", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-450")}>
            Noch kein Netzwerk — sobald unten eine Quelle angebunden ist, erscheint hier der Informationsfluss in Doctus.
          </p>
        </div>
      ) : (
        <div className="relative w-full" style={{ height: Math.max(count * 56, 140) }}>
          {/* Kanten-Layer: reine SVG-Overlay, Knoten selbst sind normales HTML (siehe unten) */}
          <svg
            className="absolute inset-0 w-full h-full overflow-visible"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            <defs>
              {nodes.map((node) => (
                <marker
                  key={`marker-${node.id}`}
                  id={`arrow-${node.id}`}
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="5"
                  markerHeight="5"
                  orient="auto-start-reverse"
                >
                  <path d="M0,0 L10,5 L0,10 z" fill={edgeColor(node.status)} />
                </marker>
              ))}
            </defs>
            {nodes.map((node, i) => {
              const y = nodeY(i);
              const x1 = NODE_X, y1 = y;
              const x2 = DOCTUS_X + 4, y2 = DOCTUS_Y;
              // sanfte S-Kurve statt gerader Linie, damit sich die Kanten am Hub nicht überlappen
              const dx = (x1 - x2) * 0.5;
              const d = `M ${x1} ${y1} C ${x1 - dx} ${y1}, ${x2 + dx} ${y2}, ${x2} ${y2}`;
              const color = edgeColor(node.status);
              return (
                <path
                  key={node.id}
                  d={d}
                  fill="none"
                  stroke={color}
                  strokeWidth={node.status === 'syncing' ? 0.6 : 0.45}
                  strokeLinecap="round"
                  strokeDasharray="2.2 2.2"
                  markerEnd={`url(#arrow-${node.id})`}
                  className={cn(
                    node.status === 'syncing' ? "animate-ds-flow-fast" : node.status === 'error' ? "" : "animate-ds-flow"
                  )}
                  opacity={node.status === 'error' ? 0.7 : 0.85}
                />
              );
            })}
          </svg>

          {/* Doctus-Hub */}
          <div
            className="absolute flex flex-col items-center gap-1"
            style={{ left: `${DOCTUS_X}%`, top: `${DOCTUS_Y}%`, transform: 'translate(-50%, -50%)' }}
          >
            <div className={cn(
              "h-12 w-12 rounded-xl flex items-center justify-center border-2 shadow-md p-2",
              theme === 'dark' ? "bg-ds-zinc-950 border-ds-indigo-500/50" : "bg-ds-white border-ds-indigo-400"
            )}>
              <DoctusIcon className="w-full h-full" />
            </div>
            <span className={cn("text-[10px] font-extrabold uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}>
              Doctus
            </span>
          </div>

          {/* Quell-Knoten */}
          {nodes.map((node, i) => {
            const y = nodeY(i);
            return (
              <div
                key={node.id}
                className="absolute flex items-center gap-2"
                style={{ left: `${NODE_X}%`, top: `${y}%`, transform: 'translate(-100%, -50%)' }}
                title={node.name}
              >
                <div className={cn(
                  "flex items-center gap-1.5 pl-2 pr-2.5 py-1.5 rounded-lg border shadow-sm max-w-[150px]",
                  theme === 'dark' ? "bg-ds-zinc-950/80 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200",
                  node.isOverflow && "border-dashed"
                )}>
                  <div className="relative shrink-0">
                    <span className={node.meta.iconColor}>{node.meta.icon}</span>
                    {node.status === 'syncing' && (
                      <Loader2 className="w-2.5 h-2.5 text-ds-blue-400 animate-spin absolute -bottom-1 -right-1" />
                    )}
                    {node.status === 'error' && (
                      <AlertCircle className="w-2.5 h-2.5 text-ds-red-400 absolute -bottom-1 -right-1" />
                    )}
                  </div>
                  <span className={cn("text-[10px] font-bold truncate", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}>
                    {node.name}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
