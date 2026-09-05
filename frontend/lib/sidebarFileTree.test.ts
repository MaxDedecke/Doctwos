import { describe, expect, it } from 'vitest';
import { buildFileTree, flattenVisibleFileTree } from './sidebarFileTree';

describe('buildFileTree', () => {
  it('nests files under their folder path', () => {
    const tree = buildFileTree(['a/b/c.cbl', 'a/d.cbl', 'e.cbl']);

    expect(Object.keys(tree).sort()).toEqual(['a', 'e.cbl']);
    expect(tree.a.type).toBe('folder');
    expect(tree.a.path).toBe('a');
    expect(Object.keys(tree.a.children!).sort()).toEqual(['b', 'd.cbl']);
    expect(tree.a.children!.b.type).toBe('folder');
    expect(tree.a.children!.b.children!['c.cbl'].type).toBe('file');
    expect(tree.a.children!.b.children!['c.cbl'].path).toBe('a/b/c.cbl');
    expect(tree['e.cbl'].type).toBe('file');
  });
});

describe('flattenVisibleFileTree', () => {
  it('lists folders before files, alphabetically within each group, at every level', () => {
    const tree = buildFileTree(['zeta.cbl', 'alpha/one.cbl', 'beta/two.cbl']);

    const rows = flattenVisibleFileTree(tree, {});

    expect(rows.map(r => r.node.path)).toEqual([
      'alpha', 'alpha/one.cbl', 'beta', 'beta/two.cbl', 'zeta.cbl',
    ]);
  });

  it('assigns depth based on nesting level', () => {
    const tree = buildFileTree(['a/b/c.cbl']);

    const rows = flattenVisibleFileTree(tree, {});

    expect(rows).toEqual([
      { node: expect.objectContaining({ path: 'a' }), depth: 0 },
      { node: expect.objectContaining({ path: 'a/b' }), depth: 1 },
      { node: expect.objectContaining({ path: 'a/b/c.cbl' }), depth: 2 },
    ]);
  });

  it('omits every descendant of a collapsed folder', () => {
    const tree = buildFileTree(['a/b/c.cbl', 'a/d.cbl', 'e.cbl']);

    const rows = flattenVisibleFileTree(tree, { a: true });

    // 'a' itself stays visible (collapsed, not hidden), but nothing under it does.
    expect(rows.map(r => r.node.path)).toEqual(['a', 'e.cbl']);
  });

  it('only hides descendants of the specific collapsed folder, not sibling subtrees', () => {
    const tree = buildFileTree(['a/x.cbl', 'b/y.cbl']);

    const rows = flattenVisibleFileTree(tree, { a: true });

    expect(rows.map(r => r.node.path)).toEqual(['a', 'b', 'b/y.cbl']);
  });

  it('returns an empty list for an empty tree', () => {
    expect(flattenVisibleFileTree({}, {})).toEqual([]);
  });
});
