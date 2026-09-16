import type { ChatMetadata, ChatReference } from '@/types/domain';
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
  /** End line of the focused object (entity focus only, O-090); unset for a bare line focus. */
  endLine?: number | null;
  label?: string | null;
  context?: string | null;
  sourceId?: FocusId;
  /** Stable parser entity identity; optional for legacy file/line pins. */
  entityId?: number | null;
  /** Open parser type/QName fields keep the focus language-neutral. */
  entityType?: string | null;
  qualifiedName?: string | null;
  breadcrumb?: string | null;
  program?: string | null;
  section?: string | null;
  paragraph?: string | null;
}

export interface ChatTurnFocus {
  project: ChatFocusProject | null;
  source: ChatFocusSource | null;
  pinned: ChatPinnedFocus | null;
}

type MessageMetadata = ChatMetadata | null | undefined;

function normalizePinnedFocus(value?: ChatMetadata['pinned'], fallback?: ChatReference): ChatPinnedFocus | null {
  if (!value?.filepath && !fallback?.file) return null;

  return {
    filepath: value?.filepath || fallback?.file || '',
    line: value?.line ?? fallback?.line ?? 0,
    endLine: value?.endLine ?? fallback?.end_line ?? null,
    label: value?.label ?? null,
    context: value?.context ?? null,
    sourceId: value?.sourceId ?? value?.source_id ?? fallback?.source_id ?? null,
    entityId: value?.entityId ?? value?.entity_id ?? fallback?.entity_id ?? null,
    entityType: value?.entityType ?? value?.entity_type ?? fallback?.entity_type ?? null,
    qualifiedName: value?.qualifiedName ?? value?.qualified_name ?? fallback?.qualified_name ?? null,
    breadcrumb: value?.breadcrumb ?? fallback?.breadcrumb ?? null,
    program: value?.program ?? fallback?.program ?? null,
    section: value?.section ?? fallback?.section ?? null,
    paragraph: value?.paragraph ?? fallback?.paragraph ?? null,
  };
}

/** Creates the immutable focus snapshot used by one chat turn. */
export function createChatTurnFocus(
  selectedProject: ChatFocusProject | null,
  selectedSource: ChatFocusSource | null,
  pinnedCode: ChatPinnedFocus | null,
): ChatTurnFocus {
  return {
    project: selectedProject ? { id: selectedProject.id, name: selectedProject.name } : null,
    source: selectedSource ? { id: selectedSource.id, name: selectedSource.name } : null,
    pinned: pinnedCode ? normalizePinnedFocus(pinnedCode) : null,
  };
}

/** Reads the canonical focus and supports messages saved before O-019. */
export function getChatTurnFocus(message: { metadata?: ChatMetadata } | null | undefined): ChatTurnFocus {
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
export function createChatMetadata(focus: ChatTurnFocus, extraMetadata: ChatMetadata = {}): ChatMetadata {
  const pinned = focus.pinned;
  const refs = pinned && pinned.line !== null && pinned.line !== undefined
      ? [{
        file: pinned.filepath,
        line: pinned.line,
        end_line: pinned.endLine ?? null,
        label: pinned.label ?? null,
        source_id: pinned.sourceId ?? null,
        entity_id: pinned.entityId ?? null,
        entity_type: pinned.entityType ?? null,
        qualified_name: pinned.qualifiedName ?? null,
        breadcrumb: pinned.breadcrumb ?? null,
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
      endLine: pinned.endLine ?? null,
      label: pinned.label ?? null,
      context: pinned.context ?? null,
      source_id: pinned.sourceId ?? null,
      entity_id: pinned.entityId ?? null,
      entity_type: pinned.entityType ?? null,
      qualified_name: pinned.qualifiedName ?? null,
      breadcrumb: pinned.breadcrumb ?? null,
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
    pinned_end_line: focus.pinned?.endLine ?? null,
    pinned_context: focus.pinned?.context ?? null,
    pinned_label: focus.pinned?.label ?? null,
    pinned_source_id: focus.pinned?.sourceId ?? null,
    pinned_entity_id: focus.pinned?.entityId ?? null,
  };
}
