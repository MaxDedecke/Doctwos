/**
 * Ablauf-Modell der Process-View: aus den (je Knoten einzeln geladenen)
 * Ein-Hop-Projektionen wird eine zeitlich geordnete Zeilenliste. Die
 * Reihenfolge stammt aus der Aufrufzeile im Quellcode (`locator.start_line`),
 * nicht aus einer Ablaufnummer — die schreibt der Parser bisher nicht.
 * Datenzugriffe zwischen zwei Steuerungsschritten werden zu einer Zeile
 * zusammengefasst, damit Feldverwendungen den Ablauf nicht überfluten.
 */

export interface FlowNode {
  id: string;
  kind: string;
  label: string;
  entity_id?: number | null;
  locator: { file_path: string; start_line: number; source_id?: number | null };
}
export interface FlowTransition {
  id: string;
  source: string;
  target: string;
  kind: string;
  certainty: 'certain' | 'possible' | 'unresolved';
  code_edge_types: string[];
  condition?: string | null;
  meta?: Record<string, unknown>;
  locator: { file_path: string; start_line: number; source_id?: number | null };
}
export interface FlowProjection {
  nodes: FlowNode[];
  transitions: FlowTransition[];
}

export type FlowLane = 'control' | 'data' | 'external';
export type DataVerb = 'read' | 'write' | 'use';

export interface DataAccess {
  id: string;
  verb: DataVerb;
  target: string;
  line: number;
  filePath: string;
  sourceId?: number | null;
  certainty: FlowTransition['certainty'];
}

export interface FlowRow {
  key: string;
  depth: number;
  lane: FlowLane;
  /** Knoten-ID des Schritts (nicht bei Datenzeilen). */
  nodeId?: string;
  entityId?: number | null;
  label: string;
  line: number;
  filePath: string;
  sourceId?: number | null;
  certainty: FlowTransition['certainty'];
  transitionKind?: string;
  condition?: string | null;
  cycle?: 'recursion' | 'cycle';
  multiTarget?: boolean;
  expandable: boolean;
  expanded: boolean;
  /** Aufgeklappt, aber die Unterschritte sind noch nicht geladen. */
  needsLoad: boolean;
  /** Ziel eines Schritts ohne eigene Datei (offener Aufruf). */
  unresolved?: boolean;
  accesses?: DataAccess[];
  counts?: Record<DataVerb, number>;
  targets?: string[];
}

const READ_TYPES = new Set(['READS']);
const WRITE_TYPES = new Set(['WRITES']);

export function dataVerb(types: string[]): DataVerb {
  if (types.some(type => WRITE_TYPES.has(type))) return 'write';
  if (types.some(type => READ_TYPES.has(type))) return 'read';
  return 'use';
}

const MAX_ROWS = 800;

export function buildFlowRows(
  rootId: string,
  projections: ReadonlyMap<string, FlowProjection>,
  expanded: ReadonlySet<string>,
): { rows: FlowRow[]; capped: boolean } {
  const nodeIndex = new Map<string, FlowNode>();
  projections.forEach(projection => projection.nodes.forEach(node => nodeIndex.set(node.id, node)));
  const root = nodeIndex.get(rootId);
  const rows: FlowRow[] = [];
  let capped = false;
  if (!root) return { rows, capped };

  const push = (row: FlowRow) => {
    if (rows.length >= MAX_ROWS) { capped = true; return; }
    rows.push(row);
  };

  const walk = (nodeId: string, depth: number, path: ReadonlySet<string>, prefix: string) => {
    const projection = projections.get(nodeId);
    if (!projection) return;
    const outgoing = projection.transitions
      .filter(transition => transition.source === nodeId)
      .sort((a, b) => a.locator.start_line - b.locator.start_line || a.id.localeCompare(b.id));

    let run: FlowTransition[] = [];
    const flushRun = () => {
      if (run.length === 0) return;
      const accesses: DataAccess[] = run.map(transition => ({
        id: transition.id,
        verb: dataVerb(transition.code_edge_types),
        target: nodeIndex.get(transition.target)?.label || '?',
        line: transition.locator.start_line,
        filePath: transition.locator.file_path,
        sourceId: transition.locator.source_id,
        certainty: transition.certainty,
      }));
      const counts: Record<DataVerb, number> = { read: 0, write: 0, use: 0 };
      accesses.forEach(access => { counts[access.verb] += 1; });
      const key = `${prefix}/data@${accesses[0].line}`;
      push({
        key, depth, lane: 'data',
        label: '', line: accesses[0].line, filePath: accesses[0].filePath, sourceId: accesses[0].sourceId,
        certainty: accesses.every(a => a.certainty === 'certain') ? 'certain' : 'possible',
        expandable: true, expanded: expanded.has(key), needsLoad: false,
        accesses, counts,
        targets: [...new Set(accesses.map(a => a.target).filter(name => name && name !== '?' && name !== 'unresolved target'))],
      });
      run = [];
    };

    for (const transition of outgoing) {
      if (transition.kind === 'data_access') { run.push(transition); continue; }
      flushRun();
      const target = nodeIndex.get(transition.target);
      if (!target) continue;
      const key = `${prefix}/${transition.id}`;
      const external = transition.kind === 'external_call' || target.kind === 'external_call';
      const recursive = transition.source === transition.target;
      const looped = recursive || path.has(target.id);
      const cycle: FlowRow['cycle'] = recursive ? 'recursion' : looped ? 'cycle' : undefined;
      const expandable = !external && !looped && target.entity_id != null;
      const isExpanded = expandable && expanded.has(key);
      push({
        key, depth, lane: external ? 'external' : 'control',
        nodeId: target.id, entityId: target.entity_id,
        label: target.label, line: transition.locator.start_line,
        filePath: transition.locator.file_path, sourceId: transition.locator.source_id,
        certainty: transition.certainty, transitionKind: transition.kind, condition: transition.condition,
        cycle, multiTarget: transition.meta?.multiple_targets === true,
        expandable, expanded: isExpanded, needsLoad: isExpanded && !projections.has(target.id),
        unresolved: external,
      });
      if (isExpanded) walk(target.id, depth + 1, new Set([...path, target.id]), key);
    }
    flushRun();
  };

  push({
    key: 'root', depth: 0, lane: 'control', nodeId: root.id, entityId: root.entity_id,
    label: root.label, line: root.locator.start_line, filePath: root.locator.file_path,
    sourceId: root.locator.source_id, certainty: 'certain',
    expandable: false, expanded: true, needsLoad: !projections.has(root.id),
  });
  walk(root.id, 1, new Set([root.id]), 'root');
  return { rows, capped };
}
