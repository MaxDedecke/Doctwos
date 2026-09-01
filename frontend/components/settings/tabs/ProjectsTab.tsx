"use client";

import React, { useState, useEffect } from 'react';
import { Check, CheckCircle2, Database, Edit, Loader2, Plus, Trash2, UserPlus, Users, X } from 'lucide-react';
import { cn } from "@/lib/utils";
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { DEFAULT_PROJECT_COLOR } from '@/lib/designTokens';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Aus SettingsModal herausgelöster 'projects'-Tab (docs/TECH_DEBT_CLEANUP_PLAN.md
// §5, Schritt 2 — letzter Tab). Der Tab kapselt sein gesamtes lokales Domänen-
// Modell: Projekt-Mitglieder/Zugriffsanfragen, Discoverable-Projects, Projekt-
// Abschluss/Promote, Inline-Edit und projektbezogene User-Kandidaten. projects/
// selectedProject/connectedSources sind geteilter App-Zustand und kommen via
// useSettings(). Der Einstieg "Neues Projekt" läuft über onNewProject (Navigation
// gehört dem Modal). Das Laden beim Betreten passiert im mount-Effekt unten.
interface ProjectsTabProps {
  onNewProject: () => void;
}

export const ProjectsTab: React.FC<ProjectsTabProps> = ({ onNewProject }) => {
  const { t } = useLanguage();
  const {
    theme,
    projects,
    setProjects,
    selectedProject,
    setSelectedProject,
    setFiles,
    connectedSources,
    setConnectedSources,
    showToast,
    currentUser,
  } = useSettings();

  const [editingProjectId, setEditingProjectId] = useState<number | null>(null);
  const [editProjectName, setEditProjectName] = useState("");
  const [editProjectDescription, setEditProjectDescription] = useState("");
  const [editProjectColor, setEditProjectColor] = useState("");
  const [editProjectExposeGlobally, setEditProjectExposeGlobally] = useState(false);
  const [isSavingProject, setIsSavingProject] = useState(false);

  // Project members / access-requests local states
  const [expandedProjectMembersId, setExpandedProjectMembersId] = useState<number | null>(null);
  const [projectMembers, setProjectMembers] = useState<Record<number, any[]>>({});
  const [projectMemberCandidates, setProjectMemberCandidates] = useState<Record<number, any[]>>({});
  const [projectAccessRequests, setProjectAccessRequests] = useState<Record<number, any[]>>({});
  const [addProjectMemberUserId, setAddProjectMemberUserId] = useState<string>("");
  const [addProjectMemberRole, setAddProjectMemberRole] = useState<'admin' | 'member'>("member");
  const [discoverableProjects, setDiscoverableProjects] = useState<any[]>([]);
  const [isLoadingDiscoverable, setIsLoadingDiscoverable] = useState(false);
  const [requestingAccessProjectId, setRequestingAccessProjectId] = useState<number | null>(null);

  // Project completion / promote-to-global local state
  const [completingProjectId, setCompletingProjectId] = useState<number | null>(null);
  const [promoteSourceIds, setPromoteSourceIds] = useState<Set<number>>(new Set());
  const [isCompletingProject, setIsCompletingProject] = useState(false);
  const [pendingAccessProjectIds, setPendingAccessProjectIds] = useState<Set<number>>(new Set());

  const isProjectAdmin = (project: any): boolean => {
    if (!project) return false;
    if (currentUser?.is_admin) return true;
    if (project.creator_id === currentUser?.id) return true;
    const own = (projectMembers[project.id] || []).find((m: any) => m.user_id === currentUser?.id);
    return own?.role === 'admin';
  };

  const refreshProjectMembers = async (projectId: number) => {
    try {
      const res = await api.getProjectMembers(projectId);
      setProjectMembers(prev => ({ ...prev, [projectId]: res.data }));
      return res.data;
    } catch (err) {
      console.error("Failed to load project members", err);
      return [];
    }
  };

  const refreshProjectAccessRequests = async (projectId: number) => {
    try {
      const res = await api.getProjectAccessRequests(projectId);
      setProjectAccessRequests(prev => ({ ...prev, [projectId]: res.data }));
    } catch (err) {
      // Non-admins get a 403 here — expected, just means no pending-requests section to show.
      setProjectAccessRequests(prev => ({ ...prev, [projectId]: [] }));
    }
  };

  const refreshProjectMemberCandidates = async (projectId: number) => {
    try {
      const res = await api.getProjectMemberCandidates(projectId);
      setProjectMemberCandidates(prev => ({ ...prev, [projectId]: res.data }));
    } catch (err) {
      // Only project admins may load candidates. Other project members simply
      // get no add-member list.
      setProjectMemberCandidates(prev => ({ ...prev, [projectId]: [] }));
    }
  };

  const handleToggleProjectMembersExpand = async (project: any) => {
    if (expandedProjectMembersId === project.id) {
      setExpandedProjectMembersId(null);
      return;
    }
    setExpandedProjectMembersId(project.id);
    setAddProjectMemberUserId("");
    const members = projectMembers[project.id] || await refreshProjectMembers(project.id);
    const admin = currentUser?.is_admin || project.creator_id === currentUser?.id
      || (members || []).find((m: any) => m.user_id === currentUser?.id)?.role === 'admin';
    if (admin) {
      await Promise.all([
        refreshProjectAccessRequests(project.id),
        refreshProjectMemberCandidates(project.id),
      ]);
    }
  };

  const handleAddProjectMember = async (projectId: number) => {
    if (!addProjectMemberUserId) return;
    try {
      await api.addProjectMember(projectId, Number(addProjectMemberUserId), addProjectMemberRole);
      setAddProjectMemberUserId("");
      setAddProjectMemberRole("member");
      showToast(t('settings.toast.memberAdded'), "success");
      await refreshProjectMembers(projectId);
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.memberAddFailed'), "error");
    }
  };

  const handleUpdateProjectMemberRole = async (projectId: number, userId: number, role: 'admin' | 'member') => {
    try {
      await api.updateProjectMemberRole(projectId, userId, role);
      showToast(t('settings.projects.members.roleChanged'), "success");
      await refreshProjectMembers(projectId);
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.projects.members.roleChangeFailed'), "error");
    }
  };

  const handleRemoveProjectMember = async (projectId: number, userId: number) => {
    try {
      await api.removeProjectMember(projectId, userId);
      showToast(t('settings.toast.memberRemoved'), "success");
      await refreshProjectMembers(projectId);
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.memberRemoveFailed'), "error");
    }
  };

  const handleResolveAccessRequest = async (projectId: number, requestId: number, status: 'approved' | 'rejected') => {
    try {
      await api.resolveProjectAccessRequest(projectId, requestId, status);
      showToast(status === 'approved' ? t('settings.toast.accessRequestApproved') : t('settings.toast.accessRequestRejected'), "success");
      await refreshProjectAccessRequests(projectId);
      if (status === 'approved') await refreshProjectMembers(projectId);
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.accessRequestResolveFailed'), "error");
    }
  };

  const refreshDiscoverableProjects = async () => {
    setIsLoadingDiscoverable(true);
    try {
      const res = await api.getDiscoverableProjects();
      setDiscoverableProjects(res.data);
    } catch (err) {
      console.error("Failed to load discoverable projects", err);
    } finally {
      setIsLoadingDiscoverable(false);
    }
  };

  // Laden beim Betreten des Tabs (die Komponente mountet nur, wenn das Modal offen
  // und projects aktiv ist).
  useEffect(() => {
    // pendingAccessProjectIds already starts out empty (see useState above) —
    // this tab fully unmounts on tab switch, so there's nothing to reset here.
    (async () => {
      await refreshDiscoverableProjects();
    })();
  }, []);

  const handleRequestProjectAccess = async (projectId: number) => {
    setRequestingAccessProjectId(projectId);
    try {
      const res = await api.requestProjectAccess(projectId);
      showToast(res.data?.message || t('settings.toast.accessRequested'), "success");
      if (res.data?.status === 'pending') {
        setPendingAccessProjectIds(prev => new Set(prev).add(projectId));
      } else if (res.data?.status === 'approved') {
        await refreshDiscoverableProjects();
      }
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.accessRequestFailed'), "error");
    } finally {
      setRequestingAccessProjectId(null);
    }
  };


  const handleProjectSelect = async (project: any) => {
    setSelectedProject(project);
    showToast(t('settings.toast.projectFocused', { name: project.name }), "success");
    try {
      const filesRes = await api.getProjectFiles(project.id);
      setFiles(filesRes.data);
    } catch (err) {
      console.error(err);
      showToast(t('settings.toast.filesFetchFailed'), "error");
    }
  };

  const handleDeleteProject = async (projectId: number, projectName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(t('settings.confirm.deleteProject', { name: projectName }))) {
      return;
    }
    try {
      await api.deleteProject(projectId);
      showToast(t('settings.toast.projectDeleted', { name: projectName }), "success");
      const res = await api.getProjects();
      setProjects(res.data);
      if (selectedProject?.id === projectId) {
        setSelectedProject(null);
        setFiles([]);
      }
    } catch (err) {
      console.error(err);
      showToast(t('settings.toast.projectDeleteFailed'), "error");
    }
  };

  const handleToggleCompleteProject = (projectId: number) => {
    if (completingProjectId === projectId) {
      setCompletingProjectId(null);
      return;
    }
    setCompletingProjectId(projectId);
    setPromoteSourceIds(new Set());
  };

  const togglePromoteSource = (sourceId: number) => {
    setPromoteSourceIds(prev => {
      const next = new Set(prev);
      if (next.has(sourceId)) next.delete(sourceId); else next.add(sourceId);
      return next;
    });
  };

  const handleConfirmCompleteProject = async (project: any) => {
    setIsCompletingProject(true);
    try {
      await api.completeProject(project.id, { promote_source_ids: Array.from(promoteSourceIds) });
      const [projectsRes, sourcesRes] = await Promise.all([api.getProjects(), api.getKnowledgeSources()]);
      setProjects(projectsRes.data);
      setConnectedSources(sourcesRes.data);
      if (selectedProject?.id === project.id) {
        setSelectedProject(null);
        setFiles([]);
      }
      setCompletingProjectId(null);
      setPromoteSourceIds(new Set());
      showToast(t('settings.toast.projectCompleted', { name: project.name }), "success");
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.projectCompleteFailed'), "error");
    } finally {
      setIsCompletingProject(false);
    }
  };

  return (
                    <div className="space-y-6 w-full min-w-0">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>
                            {t('settings.projects.activeTitle')}
                          </h4>
                          <Button
                            type="button"
                            size="sm"
                            onClick={() => onNewProject()}
                            className="bg-ds-indigo-650 hover:bg-ds-indigo-700 text-ds-white rounded-lg px-3.5 h-8 text-xs font-bold shadow-md shadow-ds-indigo-600/15 flex items-center gap-1.5 transition-all shrink-0"
                          >
                            <Plus className="w-3.5 h-3.5" />
                            <span>{t('settings.projects.newProject')}</span>
                          </Button>
                        </div>
                        <div className="space-y-2">
                          {projects.length === 0 ? (
                            <div className={cn(
                              "text-xs italic p-3.5 border rounded-lg transition-colors",
                              theme === 'dark' ? "text-ds-zinc-500 bg-ds-zinc-950/40 border-ds-zinc-800/60" : "text-ds-zinc-500 bg-ds-zinc-50 border-ds-zinc-200"
                            )}>
                              {t('settings.projects.empty')}
                            </div>
                          ) : (
                            projects.map(project => {
                              const isActive = selectedProject?.id === project.id;
                              const isEditing = editingProjectId === project.id;
                              if (isEditing) {
                                return (
                                  <div
                                    key={project.id}
                                    className={cn(
                                      "p-4 rounded-lg border space-y-4 w-full min-w-0 overflow-hidden",
                                      theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
                                    )}
                                  >
                                    <div className="text-xs font-bold uppercase tracking-wider text-ds-zinc-500">
                                      Projekt bearbeiten
                                    </div>
                                    <div className="space-y-3">
                                      <div className="space-y-1">
                                        <label className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-450">
                                          Name
                                        </label>
                                        <input
                                          type="text"
                                          value={editProjectName}
                                          onChange={(e) => setEditProjectName(e.target.value)}
                                          className={cn(
                                            "w-full h-8 rounded-lg text-xs font-semibold px-2.5 border outline-none",
                                            theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-100" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800"
                                          )}
                                        />
                                      </div>
                                      <div className="space-y-1">
                                        <label className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-450">
                                          Beschreibung
                                        </label>
                                        <Textarea
                                          value={editProjectDescription}
                                          onChange={(e) => setEditProjectDescription(e.target.value)}
                                          className={cn(
                                            "w-full text-xs font-medium px-2.5 py-1.5 border outline-none min-h-[60px]",
                                            theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-100" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800"
                                          )}
                                        />
                                      </div>
                                      <div className="space-y-1">
                                        <label className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-455">
                                          Projekt-Farbe
                                        </label>
                                        <div className="flex items-center gap-3">
                                          <input
                                            type="color"
                                            value={editProjectColor}
                                            onChange={(e) => setEditProjectColor(e.target.value)}
                                            className="w-10 h-8 p-0.5 rounded-lg border border-ds-zinc-200 dark:border-ds-zinc-800 bg-transparent cursor-pointer"
                                          />
                                          <span className="text-xs font-semibold text-ds-zinc-500">{editProjectColor}</span>
                                        </div>
                                      </div>
                                      <label className="flex items-start gap-2 cursor-pointer">
                                        <input
                                          type="checkbox"
                                          checked={editProjectExposeGlobally}
                                          onChange={(e) => setEditProjectExposeGlobally(e.target.checked)}
                                          className="mt-0.5"
                                        />
                                        <span className="space-y-0.5">
                                          <span className={cn("block text-xs font-semibold", theme === 'dark' ? "text-ds-zinc-100" : "text-ds-zinc-800")}>
                                            In Allgemein-Suche &amp; -Graph-Ansicht sichtbar
                                          </span>
                                          <span className="block text-[10px] font-medium text-ds-zinc-450">
                                            Standardmäßig aus: Code-Analyse-Objekte dieses Projekts (Entities, Call-Graph)
                                            bleiben außerhalb des Projekts unsichtbar, bis dies hier aktiviert wird.
                                          </span>
                                        </span>
                                      </label>
                                    </div>
                                    <div className="flex items-center gap-2 justify-end pt-1">
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => setEditingProjectId(null)}
                                        className="h-8 text-xs font-bold px-3 rounded-lg"
                                      >
                                        Abbrechen
                                      </Button>
                                      <Button
                                        type="button"
                                        size="sm"
                                        disabled={isSavingProject || !editProjectName.trim()}
                                        onClick={async () => {
                                          setIsSavingProject(true);
                                          try {
                                            const updatedProj = await api.updateProject(project.id, {
                                              name: editProjectName.trim(),
                                              description: editProjectDescription.trim() || undefined,
                                              color: editProjectColor,
                                              expose_code_analysis_globally: editProjectExposeGlobally
                                            });
                                            setProjects(prev => prev.map(p => p.id === project.id ? { ...p, ...updatedProj.data } : p));
                                            if (selectedProject?.id === project.id) {
                                              setSelectedProject({ ...selectedProject, ...updatedProj.data });
                                            }
                                            showToast("Projekt aktualisiert", "success");
                                            setEditingProjectId(null);
                                          } catch (err) {
                                            console.error(err);
                                            showToast("Fehler beim Aktualisieren", "error");
                                          } finally {
                                            setIsSavingProject(false);
                                          }
                                        }}
                                        className="bg-ds-indigo-650 hover:bg-ds-indigo-700 text-ds-white rounded-lg px-3.5 h-8 text-xs font-bold"
                                      >
                                        {isSavingProject ? <Loader2 className="w-3 h-3 animate-spin" /> : "Speichern"}
                                      </Button>
                                    </div>
                                  </div>
                                );
                              }
                              return (
                                <div
                                  key={project.id}
                                  className={cn(
                                    "p-4 rounded-lg border transition-all flex flex-col gap-3.5 w-full min-w-0 overflow-hidden",
                                    isActive
                                      ? (theme === 'dark' ? "border-ds-indigo-500/40 bg-ds-indigo-500/5" : "border-ds-indigo-400 bg-ds-indigo-50/40")
                                      : (theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800/80 hover:border-ds-zinc-700/80" : "bg-ds-zinc-50 border-ds-zinc-200 hover:border-ds-zinc-300")
                                  )}
                                >
                                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 w-full">
                                    <div className="space-y-1 min-w-0 flex-1 sm:pr-4">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <div
                                          className="w-2.5 h-2.5 rounded-full shrink-0 border border-ds-black/10 dark:border-ds-white/10"
                                          style={{ backgroundColor: project.color || DEFAULT_PROJECT_COLOR }}
                                        />
                                        <span className={cn("font-semibold text-xs truncate max-w-[150px] sm:max-w-none", theme === 'dark' ? "text-ds-zinc-100" : "text-ds-zinc-800")}>{project.name}</span>
                                        {isActive && (
                                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-ds-emerald-500/10 text-ds-emerald-500 border border-ds-emerald-500/20">
                                            {t('settings.projects.activeFocus')}
                                          </span>
                                        )}
                                        {project.is_archived && (
                                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-ds-zinc-500/10 text-ds-zinc-500 border border-ds-zinc-500/20">
                                            {t('settings.projects.completedBadge')}
                                          </span>
                                        )}
                                      </div>
                                    </div>

                                    <div className="flex items-center gap-2 shrink-0 w-full sm:w-auto justify-end">
                                      <Button
                                        type="button"
                                        size="sm"
                                        id={`set-focus-btn-${project.id}`}
                                        onClick={() => handleProjectSelect(project)}
                                        className={cn(
                                          "h-8 text-xs font-bold px-3.5 rounded-lg transition-all border shadow-sm",
                                          isActive
                                            ? (theme === 'dark'
                                                ? "bg-ds-indigo-500/10 border-ds-indigo-500/20 text-ds-indigo-400 hover:bg-ds-indigo-500/25"
                                                : "bg-ds-indigo-50 border-ds-indigo-200 text-ds-indigo-700 hover:bg-ds-indigo-100")
                                            : (project.url && project.status !== 'completed'
                                                ? (theme === 'dark'
                                                    ? "bg-ds-zinc-800 border-ds-zinc-700/50 text-ds-zinc-500 cursor-not-allowed"
                                                    : "bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-400 cursor-not-allowed")
                                                : (theme === 'dark'
                                                    ? "bg-ds-indigo-600 border-ds-indigo-600 text-ds-white hover:bg-ds-indigo-500 hover:border-ds-indigo-500"
                                                    : "bg-ds-indigo-600 border-ds-indigo-600 text-ds-white hover:bg-ds-indigo-700 hover:border-ds-indigo-700"))
                                        )}
                                      >
                                        {project.url && project.status === 'parsing'
                                          ? t('settings.projects.button.analyzing')
                                          : project.url && project.status === 'pending'
                                            ? t('settings.projects.button.queued')
                                            : project.url && project.status === 'error'
                                              ? t('settings.projects.button.error')
                                              : isActive ? t('settings.projects.button.active') : t('settings.projects.select')}
                                      </Button>

                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        onClick={(e) => handleDeleteProject(project.id, project.name, e)}
                                        title={t('settings.projects.deleteTitle')}
                                        className={cn(
                                          "h-8 w-8 rounded-lg border flex items-center justify-center transition-all",
                                          "text-ds-red-500 border-ds-red-500/20 hover:border-ds-red-500/40 hover:bg-ds-red-500/10 hover:text-ds-red-650 dark:hover:text-ds-red-400"
                                        )}
                                      >
                                        <Trash2 className="w-4 h-4" />
                                      </Button>

                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => handleToggleProjectMembersExpand(project)}
                                        title={t('settings.projects.members.toggleTitle')}
                                        className={cn(
                                          "h-8 w-8 rounded-lg border flex items-center justify-center transition-all text-ds-zinc-500",
                                          theme === 'dark' ? "border-ds-zinc-700/60 hover:bg-ds-zinc-800/60" : "border-ds-zinc-200 hover:bg-ds-zinc-100"
                                        )}
                                      >
                                        <Users className="w-4 h-4" />
                                      </Button>

                                      {isProjectAdmin(project) && (
                                        <Button
                                          type="button"
                                          variant="ghost"
                                          size="icon"
                                          onClick={() => {
                                            setEditingProjectId(project.id);
                                            setEditProjectName(project.name);
                                            setEditProjectDescription(project.description || "");
                                            setEditProjectColor(project.color || DEFAULT_PROJECT_COLOR);
                                            setEditProjectExposeGlobally(Boolean(project.expose_code_analysis_globally));
                                          }}
                                          title={t('settings.projects.editTitle') || "Projekt bearbeiten"}
                                          className={cn(
                                            "h-8 w-8 rounded-lg border flex items-center justify-center transition-all text-ds-zinc-500",
                                            theme === 'dark' ? "border-ds-zinc-700/60 hover:bg-ds-zinc-800/60" : "border-ds-zinc-200 hover:bg-ds-zinc-100"
                                          )}
                                        >
                                          <Edit className="w-4 h-4" />
                                        </Button>
                                      )}

                                      {!project.is_archived && isProjectAdmin(project) && (
                                        <Button
                                          type="button"
                                          variant="ghost"
                                          size="icon"
                                          onClick={() => handleToggleCompleteProject(project.id)}
                                          title={t('settings.projects.completeTitle')}
                                          className={cn(
                                            "h-8 w-8 rounded-lg border flex items-center justify-center transition-all",
                                            completingProjectId === project.id
                                              ? "text-ds-emerald-500 border-ds-emerald-500/40 bg-ds-emerald-500/10"
                                              : "text-ds-zinc-500 " + (theme === 'dark' ? "border-ds-zinc-700/60 hover:bg-ds-zinc-800/60" : "border-ds-zinc-200 hover:bg-ds-zinc-100")
                                          )}
                                        >
                                          <CheckCircle2 className="w-4 h-4" />
                                        </Button>
                                      )}
                                    </div>
                                  </div>

                                  {/* Project completion: decide which sources become global knowledge */}
                                  {completingProjectId === project.id && (
                                    <div className={cn(
                                      "pt-3 border-t space-y-2.5",
                                      theme === 'dark' ? "border-ds-zinc-800/40" : "border-ds-zinc-200/60"
                                    )}>
                                      <div className={cn("text-[9px] font-bold uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-550")}>
                                        {t('settings.projects.complete.title')}
                                      </div>
                                      <p className={cn("text-[11px]", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-500")}>
                                        {t('settings.projects.complete.description')}
                                      </p>
                                      {connectedSources.filter(src => src.project_id === project.id).length === 0 ? (
                                        <p className={cn("text-[11px] italic", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-500")}>
                                          {t('settings.projects.complete.noSources')}
                                        </p>
                                      ) : (
                                        <div className="space-y-1">
                                          {connectedSources.filter(src => src.project_id === project.id).map(src => (
                                            <label
                                              key={src.id}
                                              className={cn(
                                                "flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-[11px] cursor-pointer transition-colors",
                                                theme === 'dark' ? "border-ds-zinc-800 hover:bg-ds-zinc-900" : "border-ds-zinc-200 hover:bg-ds-zinc-50"
                                              )}
                                            >
                                              <input
                                                type="checkbox"
                                                checked={promoteSourceIds.has(src.id)}
                                                onChange={() => togglePromoteSource(src.id)}
                                                className="accent-indigo-600"
                                              />
                                              <Database className="w-3 h-3 text-ds-indigo-500 shrink-0" />
                                              <span className="truncate">{src.name} ({src.type})</span>
                                            </label>
                                          ))}
                                        </div>
                                      )}
                                      <div className="flex items-center gap-2 pt-1">
                                        <Button
                                          type="button"
                                          size="sm"
                                          disabled={isCompletingProject}
                                          onClick={() => handleConfirmCompleteProject(project)}
                                          className="h-7 text-[11px] font-bold px-3 rounded-lg bg-ds-emerald-600 hover:bg-ds-emerald-700 text-ds-white"
                                        >
                                          {isCompletingProject ? (
                                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                          ) : (
                                            t('settings.projects.complete.confirm')
                                          )}
                                        </Button>
                                        <Button
                                          type="button"
                                          size="sm"
                                          variant="ghost"
                                          disabled={isCompletingProject}
                                          onClick={() => setCompletingProjectId(null)}
                                          className="h-7 text-[11px] font-semibold px-3 rounded-lg text-ds-zinc-500"
                                        >
                                          {t('settings.projects.complete.cancel')}
                                        </Button>
                                      </div>
                                    </div>
                                  )}

                                  {/* Project members & access requests */}
                                  {expandedProjectMembersId === project.id && (
                                    <div className={cn(
                                      "pt-3 border-t space-y-3",
                                      theme === 'dark' ? "border-ds-zinc-800/40" : "border-ds-zinc-200/60"
                                    )}>
                                      <div className="space-y-1.5">
                                        {(projectMembers[project.id] || []).length === 0 ? (
                                          <div className={cn("text-[11px] italic py-1", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-500")}>
                                            {t('settings.projects.members.empty')}
                                          </div>
                                        ) : (
                                          (projectMembers[project.id] || []).map((member: any) => (
                                            <div
                                              key={member.id}
                                              className={cn(
                                                "flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-xs",
                                                theme === 'dark' ? "bg-ds-zinc-900/60" : "bg-ds-white border border-ds-zinc-200"
                                              )}
                                            >
                                              <span className={cn("truncate font-medium", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}>
                                                {member.user_name || member.user_email}
                                              </span>
                                              <div className="flex items-center gap-1.5 shrink-0">
                                                {member.role === 'admin' ? (
                                                  <span className={cn("text-[9px] font-bold uppercase", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-450")}>
                                                    {t('settings.projects.members.roleAdmin')}
                                                  </span>
                                                ) : isProjectAdmin(project) && project.creator_id !== member.user_id ? (
                                                  <Select
                                                    value={member.role === 'admin' ? 'admin' : 'member'}
                                                    onValueChange={(value) => handleUpdateProjectMemberRole(project.id, member.user_id, value as 'admin' | 'member')}
                                                  >
                                                    <SelectTrigger className="h-6 text-[9px] font-bold uppercase px-1.5 w-auto gap-1">
                                                      <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                      <SelectItem value="member">{t('settings.projects.members.roleMember')}</SelectItem>
                                                      <SelectItem value="admin">{t('settings.projects.members.roleAdmin')}</SelectItem>
                                                    </SelectContent>
                                                  </Select>
                                                ) : (
                                                  <span className={cn("text-[9px] font-bold uppercase", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-450")}>
                                                    {member.role === 'admin' ? t('settings.projects.members.roleAdmin') : t('settings.projects.members.roleMember')}
                                                  </span>
                                                )}
                                                {isProjectAdmin(project) && project.creator_id !== member.user_id && (
                                                  <Button
                                                    type="button"
                                                    variant="ghost"
                                                    size="icon"
                                                    onClick={() => handleRemoveProjectMember(project.id, member.user_id)}
                                                    title={t('settings.projects.members.removeMemberTitle')}
                                                    className="h-6 w-6 rounded text-ds-red-500 hover:bg-ds-red-500/10 shrink-0"
                                                  >
                                                    <X className="w-3 h-3" />
                                                  </Button>
                                                )}
                                              </div>
                                            </div>
                                          ))
                                        )}
                                      </div>

                                      {isProjectAdmin(project) && (() => {
                                        const memberIds = new Set((projectMembers[project.id] || []).map((m: any) => m.user_id));
                                        const availableUsers = (projectMemberCandidates[project.id] || []).filter((u: any) => !memberIds.has(u.id));
                                        return availableUsers.length > 0 ? (
                                          <div className="flex items-center gap-2">
                                            <Select value={addProjectMemberUserId} onValueChange={setAddProjectMemberUserId}>
                                              <SelectTrigger className="h-8 text-xs font-semibold flex-1 min-w-0">
                                                <SelectValue placeholder={t('settings.projects.members.addMemberPlaceholder')} />
                                              </SelectTrigger>
                                              <SelectContent>
                                                {availableUsers.map((u: any) => (
                                                  <SelectItem key={u.id} value={String(u.id)}>{u.name || u.email}</SelectItem>
                                                ))}
                                              </SelectContent>
                                            </Select>
                                            <Select value={addProjectMemberRole} onValueChange={(value) => setAddProjectMemberRole(value as 'admin' | 'member')}>
                                              <SelectTrigger className="h-8 text-xs font-semibold w-auto shrink-0 gap-1">
                                                <SelectValue placeholder={t('settings.projects.members.addMemberRolePlaceholder')} />
                                              </SelectTrigger>
                                              <SelectContent>
                                                <SelectItem value="member">{t('settings.projects.members.roleMember')}</SelectItem>
                                                <SelectItem value="admin">{t('settings.projects.members.roleAdmin')}</SelectItem>
                                              </SelectContent>
                                            </Select>
                                            <Button
                                              type="button"
                                              size="sm"
                                              disabled={!addProjectMemberUserId}
                                              onClick={() => handleAddProjectMember(project.id)}
                                              className="h-8 px-2.5 rounded-lg bg-ds-indigo-650 hover:bg-ds-indigo-700 text-ds-white shrink-0"
                                            >
                                              <UserPlus className="w-3.5 h-3.5" />
                                            </Button>
                                          </div>
                                        ) : null;
                                      })()}

                                      {isProjectAdmin(project) && (projectAccessRequests[project.id] || []).length > 0 && (
                                        <div className="space-y-1.5">
                                          <div className={cn("text-[9px] font-bold uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-550")}>
                                            {t('settings.projects.members.pendingRequests')}
                                          </div>
                                          {(projectAccessRequests[project.id] || []).map((req: any) => (
                                            <div
                                              key={req.id}
                                              className={cn(
                                                "flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-xs",
                                                theme === 'dark' ? "bg-ds-zinc-900/60" : "bg-ds-white border border-ds-zinc-200"
                                              )}
                                            >
                                              <span className={cn("truncate font-medium", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}>
                                                {req.user_name || req.user_email}
                                              </span>
                                              <div className="flex items-center gap-1 shrink-0">
                                                <Button
                                                  type="button"
                                                  variant="ghost"
                                                  size="icon"
                                                  onClick={() => handleResolveAccessRequest(project.id, req.id, 'approved')}
                                                  title={t('settings.projects.members.approveTitle')}
                                                  className="h-6 w-6 rounded text-ds-emerald-500 hover:bg-ds-emerald-500/10"
                                                >
                                                  <Check className="w-3.5 h-3.5" />
                                                </Button>
                                                <Button
                                                  type="button"
                                                  variant="ghost"
                                                  size="icon"
                                                  onClick={() => handleResolveAccessRequest(project.id, req.id, 'rejected')}
                                                  title={t('settings.projects.members.rejectTitle')}
                                                  className="h-6 w-6 rounded text-ds-red-500 hover:bg-ds-red-500/10"
                                                >
                                                  <X className="w-3.5 h-3.5" />
                                                </Button>
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  )}

                                  {/* Mapped Knowledge Sources */}
                                  {connectedSources.filter(src => src.project_id === project.id).length > 0 && (
                                    <div className={cn(
                                      "pt-3 border-t text-[11px] space-y-2",
                                      theme === 'dark' ? "border-ds-zinc-800/40" : "border-ds-zinc-200/60"
                                    )}>
                                      <div className={cn("text-[9px] font-bold uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-550")}>
                                        {t('settings.projects.linkedSources')}
                                      </div>
                                      <div className="flex flex-wrap gap-1.5">
                                        {connectedSources.filter(src => src.project_id === project.id).map((src) => {
                                          const spacesText = Array.isArray(src.spaces)
                                            ? src.spaces.join(', ')
                                            : (src.spaces && typeof src.spaces === 'object' && (src.spaces as any).filename
                                                ? (src.spaces as any).filename
                                                : '');
                                          return (
                                            <span
                                              key={src.id}
                                              className={cn(
                                                "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium border shadow-sm",
                                                theme === 'dark' ? "bg-ds-indigo-500/10 border-ds-indigo-500/20 text-ds-indigo-400" : "bg-ds-indigo-50 border-ds-indigo-200 text-ds-indigo-700"
                                              )}
                                              title={`${t('settings.projects.linkedWithBranch', { name: src.name })}${spacesText ? t('settings.projects.areasSuffix', { spaces: spacesText }) : ''}`}
                                            >
                                              <Database className="w-2.5 h-2.5" />
                                              {src.name} ({src.type})
                                            </span>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>

                      {(isLoadingDiscoverable || discoverableProjects.length > 0) && (
                        <div className="space-y-3">
                          <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>
                            {t('settings.projects.discoverable.title')}
                          </h4>
                          <div className="space-y-2">
                            {isLoadingDiscoverable ? (
                              <div className="flex items-center justify-center py-4">
                                <Loader2 className="w-4 h-4 animate-spin text-ds-zinc-500" />
                              </div>
                            ) : (
                              discoverableProjects.map((project: any) => (
                                <div
                                  key={project.id}
                                  className={cn(
                                    "p-3.5 rounded-lg border flex items-center justify-between gap-3 w-full min-w-0",
                                    theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800/80" : "bg-ds-zinc-50 border-ds-zinc-200"
                                  )}
                                >
                                  <div className="min-w-0 flex-1">
                                    <div className={cn("font-semibold text-xs truncate", theme === 'dark' ? "text-ds-zinc-100" : "text-ds-zinc-800")}>{project.name}</div>
                                    {project.description && (
                                      <div className={cn("text-[11px] truncate", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-500")}>{project.description}</div>
                                    )}
                                  </div>
                                  <Button
                                    type="button"
                                    size="sm"
                                    disabled={requestingAccessProjectId === project.id || pendingAccessProjectIds.has(project.id)}
                                    onClick={() => handleRequestProjectAccess(project.id)}
                                    className={cn(
                                      "h-8 text-xs font-bold px-3 rounded-lg shrink-0",
                                      pendingAccessProjectIds.has(project.id)
                                        ? (theme === 'dark' ? "bg-ds-zinc-800 text-ds-zinc-500" : "bg-ds-zinc-100 text-ds-zinc-450")
                                        : "bg-ds-indigo-650 hover:bg-ds-indigo-700 text-ds-white"
                                    )}
                                  >
                                    {requestingAccessProjectId === project.id ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : pendingAccessProjectIds.has(project.id) ? (
                                      t('settings.projects.discoverable.pending')
                                    ) : (
                                      t('settings.projects.discoverable.requestButton')
                                    )}
                                  </Button>
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      )}
                    </div>
  );
};
