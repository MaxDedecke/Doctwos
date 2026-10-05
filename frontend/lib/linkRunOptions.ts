// Optionen eines Entity-Link-Laufs (O-183). Grenzen und Standardwerte spiegeln `LinkRunParams` im Parser und die
// Query-Parameter von `POST /projects/{id}/link-recommendations/compute`; die API prüft sie ein zweites Mal.

export type LinkRunOptionKey =
  | 'reviewConcurrency'
  | 'reviewBatchSize'
  | 'topKSemantic'
  | 'topKKeyword'
  | 'mergeThreshold'
  | 'minScoreSemantic'
  | 'minScoreKeyword';

export interface LinkRunOptionField {
  key: LinkRunOptionKey;
  param: string;
  min: number;
  max: number;
  step: number;
  /** Standardwert des Servers, nur als Platzhalter gezeigt. */
  placeholder: string;
}

export const LINK_RUN_OPTION_FIELDS: LinkRunOptionField[] = [
  { key: 'reviewConcurrency', param: 'review_concurrency', min: 1, max: 8, step: 1, placeholder: '1' },
  { key: 'reviewBatchSize', param: 'review_batch_size', min: 0, max: 50, step: 1, placeholder: '0' },
  { key: 'topKSemantic', param: 'top_k_semantic', min: 1, max: 200, step: 1, placeholder: '20' },
  { key: 'topKKeyword', param: 'top_k_keyword', min: 1, max: 500, step: 1, placeholder: '50' },
  { key: 'mergeThreshold', param: 'merge_threshold', min: 0, max: 1, step: 0.05, placeholder: '0.9' },
  { key: 'minScoreSemantic', param: 'min_score_semantic', min: 0, max: 1, step: 0.05, placeholder: '0.45' },
  { key: 'minScoreKeyword', param: 'min_score_keyword', min: 0, max: 1, step: 0.05, placeholder: '0.3' },
];

export type LinkRunOptions = Partial<Record<LinkRunOptionKey, number>> & { dedupeByChunk?: boolean };

export function clampRunOption(field: LinkRunOptionField, value: number): number {
  return Math.min(field.max, Math.max(field.min, value));
}

/** Query-Anteil für den Compute-Aufruf: nur gesetzte Werte, auf die Grenzen begrenzt, sonst gilt der Server-Standard. */
export function linkRunOptionsQuery(options: LinkRunOptions): string {
  const params = new URLSearchParams();
  for (const field of LINK_RUN_OPTION_FIELDS) {
    const value = options[field.key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      params.set(field.param, String(clampRunOption(field, value)));
    }
  }
  if (options.dedupeByChunk) params.set('dedupe_by_chunk', 'true');
  return params.toString();
}
