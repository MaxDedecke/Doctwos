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
  meta?: { control_path?: PathEntry[]; loop?: { kind: string; text?: string }; multiple_targets?: boolean } & Record<string, unknown>;
  locator: { file_path: string; start_line: number; source_id?: number | null };
}
/** Eintrag der Kontrollpfade, die Parser (COBOL und Java) an Kanten schreiben. */
export interface PathEntry {
  type: 'IF' | 'EVALUATE' | 'SWITCH' | 'LOOP' | string;
  branch?: string;
  condition?: string;
  subject?: string;
  when?: string;
  kind?: string;
  text?: string;
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
  /** Einrückungsstufe inkl. der Bedingungs-/Schleifen-Wächter davor. */
  indent: number;
  /** Nur bei Wächterzeilen: die Bedingung bzw. Schleife, unter der die folgenden Schritte stehen. */
  guard?: PathEntry;
  /** Eigene Schleife des Schritts (PERFORM ... UNTIL/VARYING/TIMES). */
  loop?: { kind: string; text?: string };
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

/** Ein reines PERFORM ... END-PERFORM ohne Kopf sagt nichts über den Ablauf. */
function visiblePath(transition: FlowTransition): PathEntry[] {
  const path = transition.meta?.control_path;
  if (!Array.isArray(path)) return [];
  return path.filter(entry => !(entry.type === 'LOOP' && entry.kind === 'INLINE'));
}

function samePathEntry(a: PathEntry | undefined, b: PathEntry | undefined): boolean {
  return !!a && !!b && JSON.stringify(a) === JSON.stringify(b);
}

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

  const walk = (nodeId: string, depth: number, indent: number, path: ReadonlySet<string>, prefix: string) => {
    const projection = projections.get(nodeId);
    if (!projection) return;
    const outgoing = projection.transitions
      .filter(transition => transition.source === nodeId)
      .sort((a, b) => a.locator.start_line - b.locator.start_line || a.id.localeCompare(b.id));

    let run: FlowTransition[] = [];
    let previousPath: PathEntry[] = [];
    const flushRun = () => {
      if (run.length === 0) return;
      // Datenzugriffe tragen keinen Kontrollpfad: ein Wächter davor endet hier.
      previousPath = [];
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
        key, depth, indent, lane: 'data',
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

      // Wächterzeilen für Bedingungen/Schleifen, die sich gegenüber dem
      // vorherigen Schritt geändert haben.
      const transitionPath = visiblePath(transition);
      let common = 0;
      while (common < transitionPath.length && samePathEntry(transitionPath[common], previousPath[common])) common += 1;
      transitionPath.slice(common).forEach((entry, offset) => {
        push({
          key: `${key}/guard${common + offset}`, depth, indent: indent + common + offset,
          lane: 'control', label: '', line: transition.locator.start_line,
          filePath: transition.locator.file_path, sourceId: transition.locator.source_id,
          certainty: 'certain', guard: entry, expandable: false, expanded: false, needsLoad: false,
        });
      });
      previousPath = transitionPath;
      const stepIndent = indent + transitionPath.length;

      const external = transition.kind === 'external_call' || target.kind === 'external_call';
      const recursive = transition.source === transition.target;
      const looped = recursive || path.has(target.id);
      const cycle: FlowRow['cycle'] = recursive ? 'recursion' : looped ? 'cycle' : undefined;
      const expandable = !external && !looped && target.entity_id != null;
      const isExpanded = expandable && expanded.has(key);
      const loop = transition.meta?.loop;
      push({
        key, depth, indent: stepIndent, lane: external ? 'external' : 'control', loop,
        nodeId: target.id, entityId: target.entity_id,
        label: target.label, line: transition.locator.start_line,
        filePath: transition.locator.file_path, sourceId: transition.locator.source_id,
        certainty: transition.certainty, transitionKind: transition.kind, condition: transition.condition,
        cycle, multiTarget: transition.meta?.multiple_targets === true,
        expandable, expanded: isExpanded, needsLoad: isExpanded && !projections.has(target.id),
        unresolved: external,
      });
      if (isExpanded) walk(target.id, depth + 1, stepIndent + 1, new Set([...path, target.id]), key);
    }
    flushRun();
  };

  push({
    key: 'root', depth: 0, indent: 0, lane: 'control', nodeId: root.id, entityId: root.entity_id,
    label: root.label, line: root.locator.start_line, filePath: root.locator.file_path,
    sourceId: root.locator.source_id, certainty: 'certain',
    expandable: false, expanded: true, needsLoad: !projections.has(root.id),
  });
  walk(root.id, 1, 1, new Set([root.id]), 'root');
  return { rows, capped };
}
