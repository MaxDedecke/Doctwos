/**
 * O-036: reine Hilfsfunktionen für den Datei-Baum der Seitenleiste, aus
 * Sidebar.tsx herausgelöst -- ohne DOM-/React-Abhängigkeit testbar, und von
 * `components/sidebar/FileTreeList.tsx` genutzt, um vor der Virtualisierung
 * nur die aktuell sichtbaren Zeilen (aufgeklappte Ordner) in eine flache
 * Liste zu bringen. Ein rekursiver Baum lässt sich nicht direkt fenstern --
 * die Virtualisierungsbibliothek braucht eine flache, indexierbare Liste.
 */

export interface FileTreeNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children?: Record<string, FileTreeNode>;
}

export function buildFileTree(filePaths: string[]): Record<string, FileTreeNode> {
  const root: Record<string, FileTreeNode> = {};
  for (const filePath of filePaths) {
    const parts = filePath.split('/');
    let current = root;
    let currentPath = '';
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isLast = i === parts.length - 1;
      if (!current[part]) {
        current[part] = {
          name: part,
          path: currentPath,
          type: isLast ? 'file' : 'folder',
          children: isLast ? undefined : {},
        };
      }
      if (!isLast) {
        current = current[part].children!;
      }
    }
  }
  return root;
}

function sortedChildKeys(children: Record<string, FileTreeNode>): string[] {
  return Object.keys(children).sort((a, b) => {
    const typeA = children[a].type;
    const typeB = children[b].type;
    if (typeA === typeB) return a.localeCompare(b);
    return typeA === 'folder' ? -1 : 1;
  });
}

export interface FlatTreeRow {
  node: FileTreeNode;
  depth: number;
}

/**
 * Flacht den Baum auf die aktuell sichtbaren Zeilen ab: Kinder eines
 * eingeklappten Ordners werden nicht mit aufgenommen. Reihenfolge und
 * Sortierung (Ordner vor Dateien, dann alphabetisch je Ebene) entsprechen
 * exakt dem vorherigen rekursiven Rendering.
 */
export function flattenVisibleFileTree(
  tree: Record<string, FileTreeNode>,
  collapsedFolders: Record<string, boolean>
): FlatTreeRow[] {
  const rows: FlatTreeRow[] = [];

  const visit = (node: FileTreeNode, depth: number) => {
    rows.push({ node, depth });
    if (node.type === 'folder' && node.children && !collapsedFolders[node.path]) {
      for (const key of sortedChildKeys(node.children)) {
        visit(node.children[key], depth + 1);
      }
    }
  };

  for (const key of sortedChildKeys(tree)) {
    visit(tree[key], 0);
  }

  return rows;
}
