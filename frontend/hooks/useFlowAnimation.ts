"use client";

import { useCallback, useEffect, useMemo, useState } from 'react';
import { flowView, nextFlowCursor, type FlowCursor, type FlowView } from '@/lib/processFlowPaths';

export const FLOW_STEP_MS = 900;
export const FLOW_SPEEDS = [0.5, 1, 2] as const;

const EMPTY_VIEW: FlowView = { activeEdgeId: null, trailEdgeIds: new Set(), activeNodeId: null, trailNodeIds: new Set() };

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener?.('change', listener);
    return () => query.removeEventListener?.('change', listener);
  }, []);
  return reduced;
}

/**
 * O-381: Dauerschleife über die Pfade der Process View. Standard aus; läuft nur bei vorhandenen
 * Pfaden und ohne `prefers-reduced-motion`. Ein Pfadwechsel (neue Daten, andere Wurzel) setzt zurück.
 */
export function useFlowAnimation(
  paths: string[][],
  endpoints: Map<string, { source: string; target: string }>,
  rootId: string,
) {
  const reducedMotion = usePrefersReducedMotion();
  const [on, setOn] = useState(false);
  const [paused, setPaused] = useState(false);
  const [speedIndex, setSpeedIndex] = useState(1);
  const [fixedPath, setFixedPath] = useState<number | null>(null);
  const [cursor, setCursor] = useState<FlowCursor>({ path: 0, step: 0 });

  // Neue Pfade (andere Daten, Filter, Wurzel) setzen zurück. Der Abgleich beim Rendern ist das von React
  // empfohlene Muster für abgeleiteten Zustand und vermeidet einen zusätzlichen Render durch einen Effekt.
  const signature = useMemo(() => `${rootId}|${paths.map(path => path.join('>')).join('|')}`, [paths, rootId]);
  const [seenSignature, setSeenSignature] = useState(signature);
  if (seenSignature !== signature) {
    setSeenSignature(signature);
    setCursor({ path: 0, step: 0 });
    setFixedPath(null);
  }

  const supported = !reducedMotion && paths.length > 0;
  const running = on && supported && !paused;
  const stepMs = FLOW_STEP_MS / FLOW_SPEEDS[speedIndex];

  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => setCursor(current => nextFlowCursor(paths, current, fixedPath)), stepMs);
    return () => clearInterval(timer);
  }, [running, paths, fixedPath, stepMs]);

  const selectPath = useCallback((index: number | null) => {
    setFixedPath(index);
    setCursor({ path: index ?? 0, step: 0 });
  }, []);

  const view = useMemo(
    () => (on && supported ? flowView(paths, cursor, endpoints, rootId) : EMPTY_VIEW),
    [on, supported, paths, cursor, endpoints, rootId],
  );

  return {
    supported,
    reducedMotion,
    active: on && supported,
    paused,
    speed: FLOW_SPEEDS[speedIndex],
    fixedPath,
    cursor,
    pathCount: paths.length,
    pathLength: paths[Math.min(cursor.path, Math.max(0, paths.length - 1))]?.length ?? 0,
    view,
    toggle: () => { setOn(value => !value); setPaused(false); setCursor({ path: fixedPath ?? 0, step: 0 }); },
    togglePause: () => setPaused(value => !value),
    cycleSpeed: () => setSpeedIndex(index => (index + 1) % FLOW_SPEEDS.length),
    selectPath,
  };
}
