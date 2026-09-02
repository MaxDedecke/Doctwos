import { DOC_FILE_RE } from './workspaceSelection';

/**
 * Resolves whether a reference points at a local document, a web-origin
 * source, or ordinary code. Both global and panel navigation use this helper
 * so the same reference always selects the same view type.
 */
export function resolveReferenceTarget(
  path: string | null,
  sourceId: any,
  connectedSources: any[] | null,
) {
  const cleanPath = path ? path.split('#')[0] : null;
  let resolvedSourceId = sourceId;

  if (!resolvedSourceId && cleanPath && connectedSources) {
    const clickedFilename = cleanPath.split('/').pop()?.toLowerCase();
    let cleanClickedFilename = clickedFilename;
    const prefixMatch = clickedFilename?.match(/^\d+_(.+)$/);
    if (prefixMatch) {
      cleanClickedFilename = prefixMatch[1];
    }

    const matchedSource = connectedSources.find((source) => {
      if (source.type?.toLowerCase() !== 'local') return false;
      const sourceFilename = source.name?.toLowerCase();
      const spacesFilename = source.spaces?.filename?.toLowerCase();
      return sourceFilename === cleanClickedFilename || spacesFilename === cleanClickedFilename ||
        sourceFilename === clickedFilename || spacesFilename === clickedFilename;
    });
    if (matchedSource) {
      resolvedSourceId = matchedSource.id;
    }
  }

  const matchedSource = resolvedSourceId && connectedSources
    ? connectedSources.find((source) => source.id === resolvedSourceId)
    : null;
  const isWebOrigin = !!(matchedSource && (
    matchedSource.type?.toLowerCase() === 'confluence' ||
    matchedSource.type?.toLowerCase() === 'jira'
  ));

  return {
    isDoc: cleanPath ? DOC_FILE_RE.test(cleanPath) : false,
    isWebOrigin,
    resolvedSourceId,
  };
}
