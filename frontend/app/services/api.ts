import axios from 'axios';

declare global {
    interface Window {
        __DOCTUS_API_URL__?: string;
    }
}

// Gesetzt von app/layout.tsx zur Request-Zeit (server-seitig, aus dem
// Container-ENV gelesen) — nicht NEXT_PUBLIC_*, das waere build-time
// in den JS-Bundle eingebacken und wuerde pro Kunde ein eigenes Image
// erfordern.
export const API_URL = (typeof window !== 'undefined' && window.__DOCTUS_API_URL__) || 'http://localhost:8000';

// Die Session läuft über eine httpOnly-Cookie (siehe backend/core/auth_dependency.py),
// axios sendet Cookies bei cross-origin Requests nicht automatisch mit.
axios.defaults.withCredentials = true;

// Läuft die Session ab (14-Tage-Cookie) oder wird sie ungültig (Backend-Neustart
// mit rotiertem SESSION_SECRET_KEY), liefert das Backend 401. Ohne globales
// Handling würde danach jeder Request nur still fehlschlagen (console.error) und
// die UI bliebe eingeloggt, aber leer. Statt hier hart neu zu laden (Loop-Gefahr,
// da der initiale /auth/me-Check selbst 401 liefert, wenn niemand angemeldet ist),
// feuern wir ein Event; page.tsx schaltet daraufhin zurück auf die LoginView.
// Die Rejection wird weiterhin durchgereicht, damit vorhandene .catch-Handler laufen.
axios.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error?.response?.status === 401 && typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('doctus:unauthorized'));
        }
        return Promise.reject(error);
    }
);

export const api = {
    getMe: () => axios.get(`${API_URL}/auth/me`),
    login: (username: string, password: string) => axios.post(`${API_URL}/auth/login`, { username, password }),
    logout: () => axios.post(`${API_URL}/auth/logout`),
    changePassword: (old_password: string, new_password: string) =>
        axios.post(`${API_URL}/auth/change-password`, { old_password, new_password }),
    getProjects: () => axios.get(`${API_URL}/projects`),
    getProject: (id: number) => axios.get(`${API_URL}/projects/${id}`),
    createProject: (data: { name: string; description?: string; team_id?: number; color?: string }) => axios.post(`${API_URL}/projects`, data),
    updateProject: (id: number, data: { name?: string; description?: string; color?: string; is_archived?: boolean; expose_code_analysis_globally?: boolean }) => axios.patch(`${API_URL}/projects/${id}`, data),
    deleteProject: (id: number) => axios.delete(`${API_URL}/projects/${id}`),
    getTypingStatement: () => axios.get(`${API_URL}/chat/typing-statement`),
    completeProject: (id: number, data: { promote_source_ids: number[] }) => axios.post(`${API_URL}/projects/${id}/complete`, data),
    attachRepository: (projectId: number, data: any) => axios.post(`${API_URL}/projects/${projectId}/repository`, data),
    detachRepository: (projectId: number) => axios.delete(`${API_URL}/projects/${projectId}/repository`),
    getProjectFiles: (id: number) => axios.get(`${API_URL}/projects/${id}/files`),
    testConnector: (data: { type: string; username?: string; token: string; url?: string }) => axios.post(`${API_URL}/connectors/test`, data),
    getConnectorRepos: (data: { type: string; username?: string; token: string; url?: string }) => axios.post(`${API_URL}/connectors/repos`, data),
    getConnectorBranches: (data: { type: string; username?: string; token?: string; repo_name: string; url?: string }) => axios.post(`${API_URL}/connectors/branches`, data),
    getProjectStats: (id: number) => axios.get(`${API_URL}/projects/${id}/stats`),
    getKnowledgeSources: () => axios.get(`${API_URL}/knowledge-sources`),
    getProjectKnowledgeSources: (projectId: number) => axios.get(`${API_URL}/projects/${projectId}/knowledge-sources`),
    createKnowledgeSource: (data: any) => axios.post(`${API_URL}/knowledge-sources`, data),
    updateKnowledgeSourceInterval: (id: number, sync_interval_minutes: number) => axios.patch(`${API_URL}/knowledge-sources/${id}`, { sync_interval_minutes }),
    updateKnowledgeSourceContextNote: (id: number, context_note: string) => axios.patch(`${API_URL}/knowledge-sources/${id}`, { context_note }),
    deleteKnowledgeSource: (id: number) => axios.delete(`${API_URL}/knowledge-sources/${id}`),
    getKnowledgeSourceContent: (id: number, path?: string) => axios.get(`${API_URL}/knowledge-sources/${id}/content`, { params: path ? { path } : {} }),
    getKnowledgeSourceFiles: (id: number) => axios.get(`${API_URL}/knowledge-sources/${id}/files`),
    resolveWebOrigin: (id: number, url: string, theme?: string) => axios.get(`${API_URL}/knowledge-sources/${id}/resolve`, { params: { url, theme } }),
    uploadLocalDocument: (formData: FormData) => axios.post(`${API_URL}/knowledge-sources/upload`, formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    }),
    createFolderWatchSource: (data: { name: string; folder_path: string; project_id?: number | null }) =>
        axios.post(`${API_URL}/knowledge-sources/folder`, data),
    createGitSource: (data: { name: string; url: string; branch: string; username?: string; token?: string; project_id?: number | null; team_id?: number | null; sparse_paths?: string[] | null }) =>
        axios.post(`${API_URL}/knowledge-sources/git`, data),
    getProjectEntities: (id: number) => axios.get(`${API_URL}/projects/${id}/entities`),
    // projectId ist der aktuelle Projekt-Kontext des Aufrufers (Code-Editor etc.) --
    // fehlt er (Allgemein-Modus), gilt serverseitig das Default-Deny-Opt-in für
    // projektübergreifende Sichtbarkeit von Code-Analyse-Objekten (siehe
    // backend/core/projects.py::assert_project_code_visible_in_context).
    resolveEntity: (sourceId: number, path: string, projectId?: number | null) =>
        axios.get(`${API_URL}/entities/resolve`, { params: { source_id: sourceId, path, project_id: projectId ?? undefined } }),
    getEntity: (id: number, projectId?: number | null) =>
        axios.get(`${API_URL}/entities/${id}`, { params: { project_id: projectId ?? undefined } }),
    getEntityNeighbors: (id: number, options?: { types?: string[]; direction?: 'in' | 'out' | 'both'; projectId?: number | null }) =>
        axios.get(`${API_URL}/entities/${id}/neighbors`, {
            params: {
                types: options?.types?.join(','),
                direction: options?.direction || 'both',
                project_id: options?.projectId ?? undefined,
            },
        }),
    syncProjectRepository: (id: number) => axios.post(`${API_URL}/projects/${id}/sync`),
    syncKnowledgeSource: (id: number) => axios.post(`${API_URL}/knowledge-sources/${id}/sync`),
    getProjectReferences: (projectId: number, filePath: string, entityName?: string) => axios.get(`${API_URL}/projects/${projectId}/references`, { params: { file_path: filePath, entity_name: entityName } }),
    getChatSessions: () => axios.get(`${API_URL}/chat/sessions`),
    getChatMessages: (sessionId: number) => axios.get(`${API_URL}/chat/sessions/${sessionId}/messages`),
    getChatSessionByUuid: (uuid: string) => axios.get(`${API_URL}/chat/sessions/by-uuid/${uuid}`),
    getChatMessagesByUuid: (uuid: string) => axios.get(`${API_URL}/chat/sessions/by-uuid/${uuid}/messages`),
    deleteChatSession: (sessionId: number) => axios.delete(`${API_URL}/chat/sessions/${sessionId}`),
    updateChatSessionSnapshot: (sessionId: number, snapshot: any) =>
        axios.patch(`${API_URL}/chat/sessions/${sessionId}/snapshot`, { snapshot }),
    updateChatMessageFeedback: (messageId: number, feedback: 'up' | 'down' | null) =>
        axios.patch(`${API_URL}/chat/messages/${messageId}/feedback`, { feedback }),
    getModelInfo: () => axios.get(`${API_URL}/model-info`),
    getModels: () => axios.get(`${API_URL}/models`),
    updateModelInfo: (data: { llm: string }) => axios.post(`${API_URL}/model-info`, data),
    searchGlobal: (q: string, opts?: { types?: string; projectId?: number; sourceId?: number; limit?: number; signal?: AbortSignal }) =>
        axios.get(`${API_URL}/search`, {
            params: { q, types: opts?.types, project_id: opts?.projectId, source_id: opts?.sourceId, limit: opts?.limit },
            signal: opts?.signal,
        }),
    getTeams: () => axios.get(`${API_URL}/teams`),
    // name/user_id sind Query-Params (FastAPI-Konvention fuer einfache Scalar-Parameter ohne Pydantic-Body).
    createTeam: (name: string) => axios.post(`${API_URL}/teams`, null, { params: { name } }),
    updateTeam: (id: number, name: string) => axios.patch(`${API_URL}/teams/${id}`, null, { params: { name } }),
    deleteTeam: (id: number) => axios.delete(`${API_URL}/teams/${id}`),
    getTeamMembers: (id: number) => axios.get(`${API_URL}/teams/${id}/members`),
    addTeamMember: (teamId: number, userId: number) => axios.post(`${API_URL}/teams/${teamId}/members`, null, { params: { user_id: userId } }),
    removeTeamMember: (teamId: number, userId: number) => axios.delete(`${API_URL}/teams/${teamId}/members/${userId}`),
    getUsers: () => axios.get(`${API_URL}/users`),
    // Nutzerverwaltung (F-004, superuser-only). createUser/resetUserPassword liefern
    // initial_password genau einmal zurück — es wird nirgends gespeichert.
    createUser: (data: { username: string; name?: string; email?: string; role: 'superuser' | 'user'; password?: string }) =>
        axios.post(`${API_URL}/users`, data),
    updateUser: (id: number, data: { name?: string; email?: string; role?: 'superuser' | 'user'; is_active?: boolean }) =>
        axios.patch(`${API_URL}/users/${id}`, data),
    resetUserPassword: (id: number, password?: string) =>
        axios.post(`${API_URL}/users/${id}/reset-password`, { password: password || null }),
    unlockUser: (id: number) => axios.post(`${API_URL}/users/${id}/unlock`),
    getDiscoverableProjects: () => axios.get(`${API_URL}/projects/discoverable`),
    requestProjectAccess: (projectId: number) => axios.post(`${API_URL}/projects/${projectId}/request-access`),
    getProjectAccessRequests: (projectId: number) => axios.get(`${API_URL}/projects/${projectId}/access-requests`),
    resolveProjectAccessRequest: (projectId: number, requestId: number, status: 'approved' | 'rejected') =>
        axios.post(`${API_URL}/projects/${projectId}/access-requests/${requestId}/resolve`, { status }),
    getProjectMembers: (projectId: number) => axios.get(`${API_URL}/projects/${projectId}/members`),
    addProjectMember: (projectId: number, userId: number, role: 'admin' | 'member' = 'member') =>
        axios.post(`${API_URL}/projects/${projectId}/members`, { user_id: userId, role }),
    updateProjectMemberRole: (projectId: number, userId: number, role: 'admin' | 'member') =>
        axios.patch(`${API_URL}/projects/${projectId}/members/${userId}`, { role }),
    removeProjectMember: (projectId: number, userId: number) =>
        axios.delete(`${API_URL}/projects/${projectId}/members/${userId}`),
    generateDiagnosticsBundle: () => axios.post(`${API_URL}/diagnostics/generate`),
    getDiagnosticsRuns: () => axios.get(`${API_URL}/diagnostics/runs`),
    getJobs: () => axios.get(`${API_URL}/jobs`),
    resumeJob: (kind: string, id: number) => axios.post(`${API_URL}/jobs/${kind}/${id}/resume`),
};
