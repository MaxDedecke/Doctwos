export type FocusId = number | string | null;

export interface ChatFocusProject {
  id: FocusId;
  name?: string | null;
}

export interface ChatFocusSource {
  id: FocusId;
  name?: string | null;
}

export interface ChatPinnedFocus {
  filepath: string;
  line: number;
  label?: string | null;
  context?: string | null;
  sourceId?: FocusId;
  program?: string | null;
  section?: string | null;
  paragraph?: string | null;
}

export interface ChatTurnFocus {
  project: ChatFocusProject | null;
  source: ChatFocusSource | null;
  pinned: ChatPinnedFocus | null;
}

type MessageMetadata = Record<string, any> | null | undefined;

function normalizePinnedFocus(value: any, fallback?: any): ChatPinnedFocus | null {
  if (!value?.filepath && !fallback?.file) return null;

  return {
    filepath: value?.filepath || fallback?.file,
    line: value?.line ?? fallback?.line ?? 0,
    label: value?.label ?? null,
    context: value?.context ?? null,
    sourceId: value?.sourceId ?? value?.source_id ?? fallback?.source_id ?? null,
    program: value?.program ?? fallback?.program ?? null,
    section: value?.section ?? fallback?.section ?? null,
    paragraph: value?.paragraph ?? fallback?.paragraph ?? null,
  };
}

/** Creates the immutable focus snapshot used by one chat turn. */
export function createChatTurnFocus(
  selectedProject: any | null,
  selectedSource: any | null,
  pinnedCode: ChatPinnedFocus | null,
): ChatTurnFocus {
  return {
    project: selectedProject ? { id: selectedProject.id, name: selectedProject.name } : null,
    source: selectedSource ? { id: selectedSource.id, name: selectedSource.name } : null,
    pinned: pinnedCode ? normalizePinnedFocus(pinnedCode) : null,
  };
}

/** Reads the canonical focus and supports messages saved before O-019. */
export function getChatTurnFocus(message: any): ChatTurnFocus {
  const metadata: MessageMetadata = message?.metadata;
  const canonical = metadata?.focus;
  const legacyRef = metadata?.refs?.[0];
  const legacyPinned = metadata?.pinned;

  if (canonical) {
    return {
      project: canonical.project ?? null,
      source: canonical.source ?? null,
      pinned: normalizePinnedFocus(canonical.pinned, legacyRef),
    };
  }

  return {
    project: metadata?.project ?? null,
    source: metadata?.source ?? null,
    pinned: normalizePinnedFocus(legacyPinned, legacyRef),
  };
}

/** Keeps the legacy metadata fields while making the shared snapshot explicit. */
export function createChatMetadata(focus: ChatTurnFocus, extraMetadata: Record<string, any> = {}) {
  const pinned = focus.pinned;
  const refs = pinned && pinned.line !== null && pinned.line !== undefined
    ? [{
        file: pinned.filepath,
        line: pinned.line,
        source_id: pinned.sourceId ?? null,
        program: pinned.program ?? null,
        section: pinned.section ?? null,
        paragraph: pinned.paragraph ?? null,
      }]
    : [];

  return {
    project: focus.project,
    source: focus.source,
    pinned: pinned ? {
      filepath: pinned.filepath,
      line: pinned.line,
      label: pinned.label ?? null,
      context: pinned.context ?? null,
      source_id: pinned.sourceId ?? null,
      program: pinned.program ?? null,
      section: pinned.section ?? null,
      paragraph: pinned.paragraph ?? null,
    } : null,
    refs,
    ...extraMetadata,
    focus,
  };
}

export function chatFocusRequestFields(focus: ChatTurnFocus) {
  return {
    project_id: focus.project?.id ?? null,
    source_id: focus.source?.id ?? null,
    pinned_file: focus.pinned?.filepath ?? null,
    pinned_line: focus.pinned?.line ?? null,
    pinned_context: focus.pinned?.context ?? null,
    pinned_label: focus.pinned?.label ?? null,
    pinned_source_id: focus.pinned?.sourceId ?? null,
  };
}
