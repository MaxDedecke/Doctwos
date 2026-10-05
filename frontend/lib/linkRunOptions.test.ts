import { describe, expect, it } from 'vitest';
import { LINK_RUN_OPTION_FIELDS, clampRunOption, linkRunOptionsQuery } from './linkRunOptions';

describe('linkRunOptionsQuery', () => {
  it('sendet nichts, solange keine Option gesetzt ist', () => {
    expect(linkRunOptionsQuery({})).toBe('');
    expect(linkRunOptionsQuery({ dedupeByChunk: false })).toBe('');
  });

  it('übernimmt nur gesetzte Werte unter den Parameternamen der API', () => {
    const query = new URLSearchParams(
      linkRunOptionsQuery({ reviewConcurrency: 4, reviewBatchSize: 0, mergeThreshold: 0.8, dedupeByChunk: true }),
    );
    expect(Object.fromEntries(query)).toEqual({
      review_concurrency: '4',
      review_batch_size: '0',
      merge_threshold: '0.8',
      dedupe_by_chunk: 'true',
    });
  });

  it('begrenzt Werte auf die Grenzen der API und ignoriert ungültige', () => {
    const query = new URLSearchParams(
      linkRunOptionsQuery({ reviewConcurrency: 99, topKSemantic: -3, mergeThreshold: Number.NaN }),
    );
    expect(query.get('review_concurrency')).toBe('8');
    expect(query.get('top_k_semantic')).toBe('1');
    expect(query.has('merge_threshold')).toBe(false);
  });

  it('führt für jedes Feld einen eigenen Parameter', () => {
    expect(new Set(LINK_RUN_OPTION_FIELDS.map(field => field.param)).size).toBe(LINK_RUN_OPTION_FIELDS.length);
    expect(clampRunOption(LINK_RUN_OPTION_FIELDS[0], 0)).toBe(1);
  });
});
