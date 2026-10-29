import { useCallback } from 'react';
import type { ChatSession, Project } from '@/types/domain';

type ProjectChoice = Pick<Project, 'id' | 'name'> & { status?: string | null; url?: string | null };

/**
 * Was beim Projektwechsel mit dem Chat geschieht:
 * - `new`: neuer Chat, Ansichten schließen (Projektauswahl in Kopfzeile und Seitenleiste)
 * - `reset-if-foreign`: neuer Chat nur, wenn die aktive Sitzung zu einem anderen Projekt gehört
 *   (Suche, Graph-Fokus)
 * - `keep`: der Chat bleibt (eine Sitzung wird geladen und bringt ihr Projekt mit)
 */
export type ChatOnProjectChange = 'new' | 'reset-if-foreign' | 'keep';

type Options = {
  selectedProject: ProjectChoice | null;
  sessions: ChatSession[];
  activeSessionId: number | null;
  selectProject: (project: Project | null) => Promise<void>;
  startNewChat: () => void;
  resetChatSession: () => void;
  clearSelection: () => void;
  clearFileReferences: () => void;
  invalidateFileContent: () => void;
  onGeneralContext: () => void;
  onStillAnalyzing: (project: ProjectChoice) => void;
};

/**
 * Projektwechsel als ein Übergang, egal von wo er ausgelöst wird. Reihenfolge:
 * 1. Gleiches Projekt: nichts. Noch in Analyse: Hinweis, nichts ändern.
 * 2. Chat nach `chat` behandeln; ein neuer Chat bricht einen laufenden Stream ab.
 * 3. Laufende projektbezogene Anfragen entwerten (Dateiinhalt, Referenzen) und alles leeren, was am
 *    alten Projekt hängt (Auswahl in allen Panels, Objektfokus, Historie, Chat-Pin).
 * 4. Neues Projekt setzen und laden; dessen späte Antworten verwirft `useProjects` selbst.
 */
export function useProjectTransition(options: Options) {
  const {
    selectedProject, sessions, activeSessionId, selectProject, startNewChat, resetChatSession,
    clearSelection, clearFileReferences, invalidateFileContent, onGeneralContext, onStillAnalyzing,
  } = options;

  return useCallback(async (project: ProjectChoice | null, { chat }: { chat: ChatOnProjectChange }) => {
    if (project ? selectedProject?.id === project.id : !selectedProject) return;
    // status/url sind nur bei angebundenem Git gesetzt; ein Projekt ohne Git bleibt wählbar.
    if (project?.url && project.status !== 'completed') {
      onStillAnalyzing(project);
      return;
    }
    const activeSession = sessions.find(session => session.id === activeSessionId);
    if (chat === 'new') {
      startNewChat();
    } else if (chat === 'reset-if-foreign' && activeSessionId && activeSession
      && activeSession.project_id !== (project?.id ?? null)) {
      resetChatSession();
    }
    invalidateFileContent();
    clearFileReferences();
    clearSelection();
    await selectProject(project as Project | null);
    if (!project) onGeneralContext();
  }, [activeSessionId, clearFileReferences, clearSelection, invalidateFileContent, onGeneralContext, onStillAnalyzing,
    resetChatSession, selectProject, selectedProject, sessions, startNewChat]);
}
