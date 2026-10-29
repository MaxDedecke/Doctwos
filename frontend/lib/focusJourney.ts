/**
 * Fokuswechsel im gruppierten Wissensgraphen als Fahrt: erst Ebene für Ebene zurück bis zur
 * obersten Ebene, dann Gruppe für Gruppe hinein bis zum neuen Fokusobjekt, jeweils mit kurzem Halt,
 * damit man sieht, wo man herkommt und wo das Ziel liegt.
 */
export const JOURNEY_CAMERA_MS = 400;
export const JOURNEY_PAUSE_MS = 150;

/**
 * Vor dem Aufklappen fährt die Kamera nur so nah heran, dass der Inhalt danach im Bild erscheint und
 * nicht außerhalb (das wirkt sonst wie ein Fehler). Aufgeklappter Inhalt braucht etwa
 * JOURNEY_CONTENT_SPACING × √Anzahl Graph-Einheiten: gemessen an Syncope (133 Dateien) liegen so
 * 98 % des Inhalts im Bild.
 */
export const JOURNEY_CONTENT_SPACING = 85;
export const JOURNEY_ARRIVAL_RADIUS_PX = 20;

export function contentFitZoom(contents: number, shortSide: number): number {
  return (shortSide * 0.85) / (2 * JOURNEY_CONTENT_SPACING * Math.sqrt(Math.max(1, contents)));
}

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
