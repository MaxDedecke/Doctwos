import { describe, expect, it } from 'vitest';
import { getSelectionViewType, seedSelectionForPanelType } from './workspaceSelection';

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

describe('seedSelectionForPanelType', () => {
  const codeFocus = { selectedFile: 'src/Main.java', selectedDoc: null, selectedEntity: { id: 1, name: 'Main' } };

  it('gives a new doc or web view nothing when a code object has the focus', () => {
    expect(seedSelectionForPanelType('doc', codeFocus)).toEqual({ selectedFile: null, selectedDoc: null, selectedEntity: null });
    expect(seedSelectionForPanelType('webview', codeFocus)).toEqual({ selectedFile: null, selectedDoc: null, selectedEntity: null });
  });

  it('gives a new code view the code file and object, but never a document', () => {
    expect(seedSelectionForPanelType('code', codeFocus)).toEqual(codeFocus);
    expect(seedSelectionForPanelType('code', { selectedFile: 'docs/manual.pdf', selectedDoc: { name: 'manual.pdf' }, selectedEntity: null }))
      .toEqual({ selectedFile: null, selectedDoc: null, selectedEntity: null });
  });

  it('hands a document to a doc view, a web page to a web view, and the focus to mirroring views', () => {
    const doc = { selectedFile: null, selectedDoc: { name: 'manual.pdf' }, selectedEntity: null };
    expect(seedSelectionForPanelType('doc', doc).selectedDoc).toEqual({ name: 'manual.pdf' });
    expect(seedSelectionForPanelType('webview', { selectedFile: null, selectedDoc: { name: 'x', isWebOrigin: true }, selectedEntity: null }).selectedDoc)
      .toEqual({ name: 'x', isWebOrigin: true });
    expect(seedSelectionForPanelType('graph', codeFocus)).toBe(codeFocus);
    expect(seedSelectionForPanelType('callgraph', codeFocus)).toBe(codeFocus);
  });
});
