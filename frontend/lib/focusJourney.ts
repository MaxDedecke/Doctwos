/**
 * Fokuswechsel im gruppierten Wissensgraphen als Fahrt: erst Ebene für Ebene zurück bis zur
 * obersten Ebene, dann Gruppe für Gruppe hinein bis zum neuen Fokusobjekt, jeweils mit kurzem Halt,
 * damit man sieht, wo man herkommt und wo das Ziel liegt.
 */
export const JOURNEY_CAMERA_MS = 400;
export const JOURNEY_PAUSE_MS = 150;

/** Aufgeklappte Gruppen nach jedem Schritt zurück: je Schritt die tiefste Ebene zu. */
export function journeyUpSteps(expanded: string[]): string[][] {
  const depth = (key: string) => key.split('.').length;
  const steps: string[][] = [];
  let open = [...expanded];
  while (open.length) {
    const deepest = Math.max(...open.map(depth));
    open = open.filter(key => depth(key) < deepest);
    steps.push(open);
  }
  return steps;
}

export type FocusRequest = { key: string; entity_id?: number; file_path?: string; source_id?: number | string | null; chunk_id?: number };
