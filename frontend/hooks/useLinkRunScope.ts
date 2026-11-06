import { useEffect, useState, type SetStateAction } from 'react';
import { api, API_URL } from '@/app/services/api';
import { EMPTY_LINK_RUN_SCOPE, scopeFromFilter, type LinkRunScope, type LinkScopeOptions } from '@/lib/linkRunScope';

interface State { projectId: number | null; options: LinkScopeOptions | null; scope: LinkRunScope; touched: boolean }

/** Wählbare Typen und Quellen eines Projekts; die Auswahl beginnt mit der des letzten Laufs im Projekt. */
export function useLinkRunScope(projectId: number | null | undefined, open: boolean) {
  const [state, setState] = useState<State>({ projectId: null, options: null, scope: EMPTY_LINK_RUN_SCOPE, touched: false });

  useEffect(() => {
    if (!projectId || !open) return;
    let active = true;
    api.fetch(`${API_URL}/projects/${projectId}/link-recommendations/scope-options`)
      .then(response => (response.ok ? response.json() : null))
      .then((options: LinkScopeOptions | null) => {
        if (!active || !options || !Array.isArray(options.languages) || !Array.isArray(options.doc_sources)) return;
        setState(previous => previous.projectId === projectId && previous.touched
          ? { ...previous, options }
          : { projectId, options, scope: scopeFromFilter(options.last_filter, options), touched: false });
      })
      .catch(() => { /* Ohne Optionen bleibt der Lauf uneingeschränkt. */ });
    return () => { active = false; };
  }, [projectId, open]);

  const current = state.projectId === (projectId ?? null);
  const setScope = (next: SetStateAction<LinkRunScope>) => setState(previous => ({
    ...previous,
    projectId: projectId ?? null,
    scope: typeof next === 'function' ? next(current ? previous.scope : EMPTY_LINK_RUN_SCOPE) : next,
    touched: true,
  }));
  return {
    options: current ? state.options : null,
    scope: current ? state.scope : EMPTY_LINK_RUN_SCOPE,
    setScope,
  };
}
