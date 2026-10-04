import { describe, expect, it } from 'vitest';

import { sourceEmbeddingState } from './embeddingModel';

describe('sourceEmbeddingState', () => {
  it('raises no reindex alarm when the source stores no model of its own', () => {
    expect(sourceEmbeddingState(null, 'bge-m3')).toEqual({ label: 'bge-m3', mismatch: false });
    expect(sourceEmbeddingState('  ', 'bge-m3')).toEqual({ label: 'bge-m3', mismatch: false });
    expect(sourceEmbeddingState(undefined, 'bge-m3')).toEqual({ label: 'bge-m3', mismatch: false });
  });

  it('flags a stored model that differs from the active profile', () => {
    expect(sourceEmbeddingState('qwen3-embedding:4b', 'bge-m3')).toEqual({ label: 'qwen3-embedding:4b', mismatch: true });
    expect(sourceEmbeddingState('bge-m3', 'bge-m3')).toEqual({ label: 'bge-m3', mismatch: false });
  });
});
