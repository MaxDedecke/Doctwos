/**
 * O-036: der Datei-Baum einer Wissensquelle wird gefenstert gerendert. Siehe
 * VirtualizedSessionList.test.tsx für die Begründung des offsetHeight-Mocks.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { FileTreeList } from './FileTreeList';

function makeFileList(count: number): string[] {
  return Array.from({ length: count }, (_, i) => `programs/PROG${i}.cbl`);
}

function renderTree(props: Partial<React.ComponentProps<typeof FileTreeList>> = {}) {
  const defaults: React.ComponentProps<typeof FileTreeList> = {
    filesList: [],
    sourceId: 1,
    selectedFile: null,
    collapsedFolders: {},
    toggleFolder: vi.fn(),
    onFileSelect: vi.fn(),
    theme: 'dark',
  };
  return render(
    <LanguageProvider>
      <FileTreeList {...defaults} {...props} />
    </LanguageProvider>
  );
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
    renderTree({ filesList: makeFileList(2000), sourceType: 'Folder' });

    const renderedFiles = screen.getAllByText(/^PROG\d+\.cbl$/);
    expect(renderedFiles.length).toBeGreaterThan(0);
    expect(renderedFiles.length).toBeLessThan(2000);
  });

  it('renders folders and files for a small, nested tree', () => {
    renderTree({ filesList: ['src/PROG1.cbl', 'src/copybooks/CB1.cpy', 'README.md'] });

    expect(screen.getByText('src')).toBeTruthy();
    expect(screen.getByText('copybooks')).toBeTruthy();
    expect(screen.getByText('PROG1.cbl')).toBeTruthy();
    expect(screen.getByText('CB1.cpy')).toBeTruthy();
    expect(screen.getByText('README.md')).toBeTruthy();
  });

  it('hides files under a collapsed folder', () => {
    renderTree({ filesList: ['src/PROG1.cbl', 'README.md'], collapsedFolders: { src: true } });

    expect(screen.getByText('src')).toBeTruthy();
    expect(screen.queryByText('PROG1.cbl')).toBeNull();
    expect(screen.getByText('README.md')).toBeTruthy();
  });

  it('calls toggleFolder with the folder path when a folder row is clicked', () => {
    const toggleFolder = vi.fn();
    renderTree({ filesList: ['src/PROG1.cbl'], toggleFolder });

    fireEvent.click(screen.getByText('src'));

    expect(toggleFolder).toHaveBeenCalledWith('src');
  });

  it('calls onFileSelect with the file path and source id when a file row is clicked', () => {
    const onFileSelect = vi.fn();
    renderTree({ filesList: ['src/PROG1.cbl'], sourceId: 42, onFileSelect });

    fireEvent.click(screen.getByText('PROG1.cbl'));

    expect(onFileSelect).toHaveBeenCalledWith('src/PROG1.cbl', 42);
  });

  // O-120: eine nicht uneingeschränkt analysierte Datei bekommt ein Badge
  // und einen erklärenden Tooltip -- eine unauffällige Datei bleibt unverändert.
  it('marks a file with a non-complete analysis status', () => {
    renderTree({
      filesList: ['PAYROLL.cbl'],
      fileStatus: { 'PAYROLL.cbl': { status: 'partial', reasons: ['mismatched input'] } },
    });

    const row = screen.getByText('PAYROLL.cbl').closest('button');
    expect(row).not.toBeNull();
    expect(row!.querySelector('[data-testid="analysis-status-dot"]')).not.toBeNull();
    expect(row!.getAttribute('title')).toContain('mismatched input');
  });

  it('does not mark a file with no entry in fileStatus', () => {
    renderTree({
      filesList: ['CLEAN.cbl', 'PAYROLL.cbl'],
      fileStatus: { 'PAYROLL.cbl': { status: 'skipped', reasons: [] } },
    });

    const cleanRow = screen.getByText('CLEAN.cbl').closest('button');
    expect(cleanRow!.querySelector('[data-testid="analysis-status-dot"]')).toBeNull();
    expect(cleanRow!.getAttribute('title')).toBe('CLEAN.cbl');
  });
});
