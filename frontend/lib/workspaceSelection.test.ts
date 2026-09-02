import { describe, expect, it } from 'vitest';
import { getSelectionViewType } from './workspaceSelection';

describe('workspace selection classification', () => {
  it('classifies documents and markdown as document-panel content', () => {
    expect(getSelectionViewType('README.md', null)).toBe('doc');
    expect(getSelectionViewType('manual.DOCX', null)).toBe('doc');
  });

  it('classifies web origins before checking the file extension', () => {
    expect(getSelectionViewType('https://docs.example.test/index', { isWebOrigin: true })).toBe('webview');
  });

  it('classifies code files and empty selections correctly', () => {
    expect(getSelectionViewType('src/program.cbl', null)).toBe('code');
    expect(getSelectionViewType(null, null)).toBeNull();
  });

  it('ignores chunk suffixes when selecting a panel type', () => {
    expect(getSelectionViewType('docs/guide.md#chunk-4', null)).toBe('doc');
    expect(getSelectionViewType('src/program.cbl#chunk-4', null)).toBe('code');
  });
});
