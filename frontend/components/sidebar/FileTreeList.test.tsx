/**
 * O-036: der Datei-Baum einer Wissensquelle wird gefenstert gerendert. Siehe
 * VirtualizedSessionList.test.tsx für die Begründung des offsetHeight-Mocks.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FileTreeList } from './FileTreeList';

function makeFileList(count: number): string[] {
  return Array.from({ length: count }, (_, i) => `programs/PROG${i}.cbl`);
}

describe('FileTreeList', () => {
  let offsetHeightSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    offsetHeightSpy = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(150);
  });

  afterEach(() => {
    offsetHeightSpy.mockRestore();
  });

  it('renders only a windowed subset of a large flat file list, not all of them', () => {
    render(
      <FileTreeList
        filesList={makeFileList(2000)}
        sourceId={1}
        sourceType="Folder"
        selectedFile={null}
        collapsedFolders={{}}
        toggleFolder={vi.fn()}
        onFileSelect={vi.fn()}
        theme="dark"
      />
    );

    const renderedFiles = screen.getAllByText(/^PROG\d+\.cbl$/);
    expect(renderedFiles.length).toBeGreaterThan(0);
    expect(renderedFiles.length).toBeLessThan(2000);
  });

  it('renders folders and files for a small, nested tree', () => {
    render(
      <FileTreeList
        filesList={['src/PROG1.cbl', 'src/copybooks/CB1.cpy', 'README.md']}
        sourceId={1}
        selectedFile={null}
        collapsedFolders={{}}
        toggleFolder={vi.fn()}
        onFileSelect={vi.fn()}
        theme="dark"
      />
    );

    expect(screen.getByText('src')).toBeTruthy();
    expect(screen.getByText('copybooks')).toBeTruthy();
    expect(screen.getByText('PROG1.cbl')).toBeTruthy();
    expect(screen.getByText('CB1.cpy')).toBeTruthy();
    expect(screen.getByText('README.md')).toBeTruthy();
  });

  it('hides files under a collapsed folder', () => {
    render(
      <FileTreeList
        filesList={['src/PROG1.cbl', 'README.md']}
        sourceId={1}
        selectedFile={null}
        collapsedFolders={{ src: true }}
        toggleFolder={vi.fn()}
        onFileSelect={vi.fn()}
        theme="dark"
      />
    );

    expect(screen.getByText('src')).toBeTruthy();
    expect(screen.queryByText('PROG1.cbl')).toBeNull();
    expect(screen.getByText('README.md')).toBeTruthy();
  });

  it('calls toggleFolder with the folder path when a folder row is clicked', () => {
    const toggleFolder = vi.fn();
    render(
      <FileTreeList
        filesList={['src/PROG1.cbl']}
        sourceId={1}
        selectedFile={null}
        collapsedFolders={{}}
        toggleFolder={toggleFolder}
        onFileSelect={vi.fn()}
        theme="dark"
      />
    );

    fireEvent.click(screen.getByText('src'));

    expect(toggleFolder).toHaveBeenCalledWith('src');
  });

  it('calls onFileSelect with the file path and source id when a file row is clicked', () => {
    const onFileSelect = vi.fn();
    render(
      <FileTreeList
        filesList={['src/PROG1.cbl']}
        sourceId={42}
        selectedFile={null}
        collapsedFolders={{}}
        toggleFolder={vi.fn()}
        onFileSelect={onFileSelect}
        theme="dark"
      />
    );

    fireEvent.click(screen.getByText('PROG1.cbl'));

    expect(onFileSelect).toHaveBeenCalledWith('src/PROG1.cbl', 42);
  });
});
