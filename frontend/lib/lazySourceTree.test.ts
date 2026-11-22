import { describe, expect, it } from 'vitest';
import { flattenLazyTree, type LoadedDir } from './lazySourceTree';

const loaded = (entries: LoadedDir['entries'], nextOffset: number | null = null, total = entries.length): LoadedDir =>
  ({ entries, total, nextOffset, loading: false });

describe('lazy source tree rows', () => {
  it('shows a loading row until the first page arrives', () => {
    expect(flattenLazyTree({}, new Set())).toEqual([{ kind: 'loading', dir: '', depth: 0 }]);
  });

  it('nests children only under expanded folders and ends pages with a more row', () => {
    const dirs = {
      '': loaded([{ type: 'dir', name: 'src', path: 'src', files: 3 }, { type: 'file', name: 'README.md', path: 'README.md' }], 2, 5),
      src: loaded([{ type: 'file', name: 'MAIN.cbl', path: 'src/MAIN.cbl' }]),
    };
    expect(flattenLazyTree(dirs, new Set()).map(row => row.kind === 'entry' ? row.entry.path : row.kind))
      .toEqual(['src', 'README.md', 'more']);
    const open = flattenLazyTree(dirs, new Set(['src']));
    expect(open.map(row => row.kind === 'entry' ? `${row.depth}:${row.entry.path}` : row.kind))
      .toEqual(['0:src', '1:src/MAIN.cbl', '0:README.md', 'more']);
    expect(open[3]).toMatchObject({ kind: 'more', loaded: 2, total: 5 });
  });

  it('shows a loading row for an expanded folder that is still loading', () => {
    const dirs = { '': loaded([{ type: 'dir', name: 'src', path: 'src', files: 1 }]) };
    expect(flattenLazyTree(dirs, new Set(['src']))[1]).toEqual({ kind: 'loading', dir: 'src', depth: 1 });
  });
});
