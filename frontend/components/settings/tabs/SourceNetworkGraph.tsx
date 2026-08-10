"use client";

import React from 'react';
import { AlertCircle, ArrowLeft, ArrowRight, Loader2, Waypoints } from 'lucide-react';
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

  // Anteilige Position entlang jeder Kante, an der ein kleiner Pfeil sitzt.
  // Gerade Linien statt Bezier-Kurven, damit die Pfeile nicht rotiert werden
  // müssen (siehe Kommentar unten) — bei bis zu MAX_VISIBLE_NODES Kanten, die
  // alle auf denselben Hub-Punkt zulaufen, ist ein einfacher Fächer optisch
  // genauso klar wie eine S-Kurve.
  const ARROW_FRACTIONS = [0.22, 0.5, 0.78];

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
          {/* Kanten-Layer: dünner statischer "Draht" als SVG-Overlay. Die eigentliche
              Richtungsanzeige übernehmen die kleinen Pfeil-Icons weiter unten (als
              normales HTML statt SVG-Marker, damit sie unter preserveAspectRatio="none"
              nicht mitverzerrt werden). */}
          <svg
            className="absolute inset-0 w-full h-full overflow-visible"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            {nodes.map((node, i) => {
              const y = nodeY(i);
              return (
                <line
                  key={node.id}
                  x1={NODE_X}
                  y1={y}
                  x2={DOCTUS_X + 4}
                  y2={DOCTUS_Y}
                  stroke={edgeColor(node.status)}
                  strokeWidth={0.35}
                  opacity={node.status === 'error' ? 0.35 : 0.25}
                />
              );
            })}
          </svg>

          {/* Pfeil-Ebene: pro Kante ein paar kleine, versetzt pulsierende Pfeile statt
              einer gestrichelten Linie — dadurch ist die Flussrichtung auf einen Blick
              erkennbar statt nur "irgendein Strich". Aktuell immer Quelle -> Doctus
              (node.direction === 'in'); für eine künftige Rückrichtung wählt ArrowIcon
              bereits pro Knoten das passende Symbol. */}
          {nodes.map((node, i) => {
            const y1 = nodeY(i);
            const x1 = NODE_X, x2 = DOCTUS_X + 4, y2 = DOCTUS_Y;
            const color = edgeColor(node.status);
            const ArrowIcon = node.direction === 'out' ? ArrowRight : ArrowLeft;
            const speedClass = node.status === 'error'
              ? ""
              : node.status === 'syncing' ? "animate-ds-arrow-pulse-fast" : "animate-ds-arrow-pulse";
            return ARROW_FRACTIONS.map((f, arrowIdx) => {
              const x = x1 + (x2 - x1) * f;
              const py = y1 + (y2 - y1) * f;
              return (
                <div
                  key={`${node.id}-${arrowIdx}`}
                  className={cn("absolute", speedClass)}
                  style={{
                    left: `${x}%`,
                    top: `${py}%`,
                    color,
                    opacity: node.status === 'error' ? 0.4 : undefined,
                    transform: node.status === 'error' ? 'translate(-50%, -50%)' : undefined,
                    animationDelay: node.status === 'error' ? undefined : `${arrowIdx * 0.28 + i * 0.06}s`,
                  }}
                >
                  <ArrowIcon className="w-3 h-3" strokeWidth={2.75} />
                </div>
              );
            });
          })}

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
