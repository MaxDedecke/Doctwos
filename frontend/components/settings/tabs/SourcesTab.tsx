"use client";

import React from 'react';
import {
  GitBranch, RefreshCw, RefreshCcw, Link2, Loader2, Database, Layers,
  FileText, Code, Folder, Building2, Wrench, ClipboardList, Download, Pin, Trash2,
  Plus, Info, Calendar, AlertCircle, CheckCircle2
} from 'lucide-react';
import { cn } from "@/lib/utils";
import { api, API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useFeatures } from '@/lib/FeaturesContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { getConnectorMetadata } from '@/lib/sourceConnectors';
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SourceNetworkGraph } from './SourceNetworkGraph';

interface SourcesTabProps {
  selectedSourceRepoId: string;
  setSelectedSourceRepoId: (val: string) => void;
  onSetupSource: (typeName: string) => void;
  onAttachGit: (projectId: number) => void;
}

export const SourcesTab: React.FC<SourcesTabProps> = ({
  selectedSourceRepoId,
  setSelectedSourceRepoId,
  onSetupSource,
  onAttachGit
}) => {
  const { language, t } = useLanguage();
  const features = useFeatures();
  const {
    theme,
    projects,
    setProjects,
    connectedSources,
    setConnectedSources,
    pinnedSourceIds,
    togglePinSource,
    showToast,
    currentUser,
  } = useSettings();
  const [reindexingSourceId, setReindexingSourceId] = React.useState<number | null>(null);

  const handleDeleteSource = async (sourceId: string | number) => {
    if (!confirm(t('settings.confirm.deleteSource'))) return;

    const isMock = typeof sourceId === 'string' && sourceId.includes('conf-init');
    if (isMock) {
      setConnectedSources(prev => prev.filter(s => s.id !== sourceId));
      showToast(t('settings.toast.sourceRemoved'), "success");
      return;
    }

    try {
      await api.deleteKnowledgeSource(typeof sourceId === 'string' ? parseInt(sourceId) : sourceId);
      setConnectedSources(prev => prev.filter(s => s.id !== sourceId));
      showToast(t('settings.toast.sourceDeleted'), "success");
    } catch (err) {
      console.error(err);
      showToast(t('settings.toast.sourceDeleteFailed'), "error");
    }
  };

  const handleSyncSource = async (sourceId: string | number, sourceName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const isMock = typeof sourceId === 'string' && sourceId.includes('conf-init');
    if (isMock) {
      showToast(t('settings.toast.mockSyncNotAllowed'), "error");
      return;
    }
    try {
      showToast(t('settings.toast.syncStarted', { name: sourceName }), "success");
      const idVal = typeof sourceId === 'string' ? parseInt(sourceId) : sourceId;
      await api.syncKnowledgeSource(idVal);
    } catch (err) {
      console.error(err);
      showToast(t('settings.toast.sourceSyncFailed'), "error");
    }
  };

  const handleFullReindex = async (sourceId: string | number, sourceName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!currentUser?.is_admin) return;
    const idVal = typeof sourceId === 'string' ? parseInt(sourceId) : sourceId;
    if (Number.isNaN(idVal)) return;
    if (!confirm(t('settings.confirm.fullReindexSource', { name: sourceName }))) return;

    setReindexingSourceId(idVal);
    try {
      await api.reindexKnowledgeSource(idVal);
      setConnectedSources(prev => prev.map(source => source.id === idVal ? {
        ...source,
        sync_status: 'pending',
        progress: 0,
        progress_message: t('settings.toast.fullReindexQueued'),
      } : source));
      showToast(t('settings.toast.fullReindexStarted', { name: sourceName }), "success");
    } catch (err) {
      console.error(err);
      showToast(t('settings.toast.fullReindexFailed'), "error");
    } finally {
      setReindexingSourceId(null);
    }
  };

  const handleIntervalChange = async (sourceId: string | number, minutes: number) => {
    const idVal = typeof sourceId === 'string' ? parseInt(sourceId) : sourceId;
    if (Number.isNaN(idVal)) return;
    const prev = connectedSources;
    setConnectedSources(prev.map(s => s.id === idVal ? { ...s, sync_interval_minutes: minutes } : s));
    try {
      await api.updateKnowledgeSourceInterval(idVal, minutes);
    } catch (err) {
      console.error(err);
      setConnectedSources(prev);
      showToast(t('settings.toast.intervalUpdateFailed'), "error");
    }
  };

  const handleContextNoteBlur = async (sourceId: string | number, note: string) => {
    const idVal = typeof sourceId === 'string' ? parseInt(sourceId) : sourceId;
    if (Number.isNaN(idVal)) return;
    const prev = connectedSources;
    const current = prev.find(s => s.id === idVal);
    if (current && (current.context_note || "") === note) return; // unverändert, kein Request nötig
    setConnectedSources(prev.map(s => s.id === idVal ? { ...s, context_note: note } : s));
    try {
      await api.updateKnowledgeSourceContextNote(idVal, note);
    } catch (err) {
      console.error(err);
      setConnectedSources(prev);
      showToast(t('settings.toast.contextNoteUpdateFailed'), "error");
    }
  };

  const availableConnectors = [
    { name: "Git", desc: t('settings.sourcesTab.types.git.desc') || "Git-Repository mit Source-Code anbinden", typeKey: "git", icon: <GitBranch className="w-5 h-5 text-ds-indigo-400" />, featureKey: 'git' as any },
    { name: t('settings.sourcesTab.types.confluence.name'), desc: t('settings.sourcesTab.types.confluence.desc'), typeKey: "confluence", icon: <Database className="w-5 h-5 text-ds-blue-400" />, featureKey: 'confluence' as const },
    { name: t('settings.sourcesTab.types.jira.name'), desc: t('settings.sourcesTab.types.jira.desc'), typeKey: "jira", icon: <Layers className="w-5 h-5 text-ds-violet-400" />, featureKey: 'jira' as const },
    { name: t('settings.sourcesTab.types.local.name'), desc: t('settings.sourcesTab.types.local.desc'), typeKey: "local", icon: <Code className="w-5 h-5 text-ds-amber-400" />, featureKey: 'local' as const },
    { name: t('settings.sourcesTab.types.folderwatch.name'), desc: t('settings.sourcesTab.types.folderwatch.desc'), typeKey: "folderwatch", icon: <Folder className="w-5 h-5 text-ds-emerald-400" />, featureKey: 'folderwatch' as const },
  ];

  // Fitering connected sources based on the active selection.
  // "all" (Allgemein) zeigt nur echte projektübergreifende Quellen
  // (project_id === null, siehe GitSetupTab-Kommentar zu project_id=null als
  // "allgemeine Wissensquelle") — projektgebundene Quellen gehören
  // ausschließlich unter ihr jeweiliges Projekt, nicht zusätzlich hierhin.
  const filteredSources = connectedSources.filter(cs => {
    if (selectedSourceRepoId === "all") return cs.project_id == null;
    return cs.project_id?.toString() === selectedSourceRepoId || cs.repoId === selectedSourceRepoId;
  });

  // Sort pinned sources first
  const sortedSources = [...filteredSources].sort((a, b) => {
    const aPinned = pinnedSourceIds.includes(a.id) ? 1 : 0;
    const bPinned = pinnedSourceIds.includes(b.id) ? 1 : 0;
    return bPinned - aPinned;
  });

  // Der Netzwerk-Graph folgt demselben Projekt-Filter wie die Kartenliste —
  // "allgemein" (alle Projekte) vs. ein einzelnes Projekt ist so ohne
  // zusätzlichen Auswahl-Kontrollpunkt bereits abgedeckt.
  const networkScopeLabel = selectedSourceRepoId === "all"
    ? t('settings.sourcesTab.allProjects')
    : projects.find((p: any) => p.id.toString() === selectedSourceRepoId)?.name || t('settings.sourcesTab.selectProjectPlaceholder');

  return (
    <div className="space-y-8 animate-in fade-in duration-300 w-full min-w-0">
      {/* Header Info */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-ds-zinc-800/40 pb-5">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <h4 className={cn("text-sm font-bold uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-850")}>
              {t('settings.sourcesTab.title')}
            </h4>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-sm bg-ds-indigo-500/10 text-ds-indigo-400 border border-ds-indigo-500/20">
              {connectedSources.length} {connectedSources.length === 1 ? t('settings.sourcesTab.sourceBadgeSingular') : t('settings.sourcesTab.sourceBadgePlural')}
            </span>
          </div>
          <p className={cn("text-xs leading-relaxed max-w-2xl", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-650")}>
            {t('settings.sourcesTab.description')}
          </p>
        </div>

        {/* Project Selector */}
        <div className="p-2.5 rounded-lg flex items-center gap-3 transition-all duration-300">
          <span className={cn("text-[10px] font-bold uppercase tracking-wider shrink-0", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>
            Filter:
          </span>
          <Select
            value={selectedSourceRepoId}
            onValueChange={(val) => setSelectedSourceRepoId(val)}
          >
            <SelectTrigger className={cn(
              "h-8 text-xs border focus:ring-0 w-[180px] rounded-lg font-medium shadow-none transition-all flex items-center justify-between gap-1.5",
              theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-300 hover:bg-ds-zinc-800/60" : "bg-ds-white border-ds-zinc-250 text-ds-zinc-700 hover:bg-ds-zinc-50"
            )}>
              <div className="flex items-center gap-1.5 truncate">
                <GitBranch className="w-3 h-3 text-ds-indigo-400 shrink-0" />
                <span className="truncate">
                  {selectedSourceRepoId === "all"
                    ? t('settings.sourcesTab.allProjects')
                    : projects.find((p: any) => p.id.toString() === selectedSourceRepoId)?.name || t('settings.sourcesTab.selectProjectPlaceholder')}
                </span>
              </div>
            </SelectTrigger>
            <SelectContent className={theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-850 text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800"}>
              <SelectItem value="all" className="text-xs">
                {t('settings.sourcesTab.allProjects')}
              </SelectItem>
              {projects.map((project: any) => (
                <SelectItem key={project.id} value={project.id.toString()} disabled={!!project.url && project.status !== 'completed'} className="text-xs">
                  {project.name} {project.url && project.status !== 'completed' ? `(${project.status === 'parsing' ? (project.progress_message || t('settings.sourcesTab.analyzingShort', { percent: project.progress || 0 })) : t('settings.sourcesTab.projectPendingStatus')})` : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Netzwerk-Visualisierung: zeigt den Informationsfluss aller (gefilterten) Quellen in Doctus */}
      <SourceNetworkGraph sources={filteredSources} theme={theme} scopeLabel={networkScopeLabel} />

      {/* SECTION 1: Active Connected Sources */}
      <div className="space-y-4">
        <h5 className={cn("text-sm font-bold uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-450" : "text-ds-zinc-550")}>
          {t('settings.sourcesTab.connectedSourcesHeading', { count: filteredSources.length })}
        </h5>

        {sortedSources.length === 0 ? (
          /* Empty State */
          <div className={cn(
            "flex flex-col items-center justify-center p-8 text-center rounded-lg border border-dashed transition-all duration-300",
            theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-zinc-50/50 border-ds-zinc-200"
          )}>
            <div className="h-14 w-14 rounded-full bg-ds-indigo-500/10 flex items-center justify-center mb-3">
              <Info className="w-6 h-6 text-ds-indigo-400" />
            </div>
            <p className={cn("text-sm font-bold", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-800")}>
              {t('settings.sourcesTab.emptyStateHeading')}
            </p>
            <p className={cn("text-sm mt-1 max-w-sm leading-relaxed", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-450")}>
              {selectedSourceRepoId === "all"
                ? t('settings.sourcesTab.emptyStateHintAll')
                : t('settings.sourcesTab.emptyStateHintProject')}
            </p>
          </div>
        ) : (
          /* Premium Cards Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {sortedSources.map((inst) => {
              const meta = getConnectorMetadata(inst.type);
              const isPinned = pinnedSourceIds.includes(inst.id);
              const project = projects.find((p: any) => p.id === inst.project_id);

              return (
                <div
                  key={inst.id}
                  className={cn(
                    "group relative p-5 rounded-lg border transition-all duration-300 flex flex-col justify-between overflow-hidden shadow-sm hover:shadow-md hover:-translate-y-0.5",
                    theme === 'dark'
                      ? "bg-ds-zinc-900/40 border-ds-zinc-800/80 hover:border-ds-zinc-700/50"
                      : "bg-ds-white/80 border-ds-zinc-200 hover:border-ds-zinc-300",
                    isPinned && (theme === 'dark' ? "border-ds-amber-500/40 bg-gradient-to-b from-ds-amber-500/5 to-transparent" : "border-ds-amber-400 bg-ds-amber-50/30")
                  )}
                  style={{
                    boxShadow: isPinned ? `0 4px 20px ${theme === 'dark' ? 'rgba(245, 158, 11, 0.03)' : 'rgba(245, 158, 11, 0.05)'}` : undefined
                  }}
                >
                  {/* Neon Glow backdrop */}
                  <div
                    className="absolute top-0 right-0 w-28 h-28 blur-2xl rounded-full opacity-30 z-0 pointer-events-none transition-all duration-500 group-hover:scale-110"
                    style={{ backgroundColor: meta.glowColor }}
                  />

                  {/* Header info row */}
                  <div className="relative z-10 w-full space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        {/* Glowing icon wrapper */}
                        <div className={cn(
                          "h-10 w-10 rounded-lg flex items-center justify-center border shadow-inner transition-transform duration-300 group-hover:scale-105",
                          theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-zinc-50 border-ds-zinc-200 text-ds-zinc-800"
                        )}>
                          <span className={meta.iconColor}>{meta.icon}</span>
                        </div>

                        {/* Title & Badge */}
                        <div className="flex flex-col min-w-0">
                          <span className={cn("text-sm font-bold truncate max-w-[220px] leading-tight", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")} title={inst.name}>
                            {inst.name}
                          </span>
                          <span className={cn("inline-self-start text-[11px] uppercase tracking-widest font-extrabold px-1.5 py-1 rounded border mt-1 w-max", meta.badgeColor)}>
                            {inst.type}
                          </span>
                        </div>
                      </div>

                      {/* Status badge */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {inst.sync_status === 'syncing' ? (
                          <span className="flex items-center gap-1 text-sm font-bold text-ds-blue-400 bg-ds-blue-500/10 border border-ds-blue-500/20 px-2 py-1 rounded-sm">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('settings.logsTab.statusSyncingDefault')}
                          </span>
                        ) : inst.sync_status === 'error' ? (
                          <span className="flex items-center gap-1 text-sm font-bold text-ds-red-400 bg-ds-red-500/10 border border-ds-red-500/20 px-2 py-1 rounded-sm">
                            <AlertCircle className="w-3.5 h-3.5" /> {t('settings.logsTab.statusErrorLabel')}
                          </span>
                        ) : inst.last_synced_at ? (
                          <span className="flex items-center gap-1 text-sm font-bold text-ds-emerald-400 bg-ds-emerald-500/10 border border-ds-emerald-500/20 px-2 py-1 rounded-sm">
                            <CheckCircle2 className="w-3.5 h-3.5" /> {t('settings.logsTab.statusSuccess')}
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-sm font-bold text-ds-amber-400 bg-ds-amber-500/10 border border-ds-amber-500/20 px-2 py-1 rounded-sm">
                            <Info className="w-3.5 h-3.5" /> {t('settings.logsTab.statusReady')}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Metadata lines */}
                    <div className={cn(
                      "text-[11px] space-y-2 p-3 rounded-lg border font-medium",
                      theme === 'dark' ? "bg-ds-zinc-950/30 border-ds-zinc-850/60 text-ds-zinc-400" : "bg-ds-zinc-50 border-ds-zinc-200 text-ds-zinc-650"
                    )}>
                      {project && (
                        <div className="flex items-center gap-1.5">
                          <span className="opacity-50">{t('settings.sourcesTab.projectLabelColon')}</span>
                          <span className={cn("font-bold", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-800")}>{project.name}</span>
                        </div>
                      )}
                      {inst.type?.toLowerCase() === 'git' && (inst.branch || inst.spaces?.branch) && (
                        <div className="flex items-center gap-1.5">
                          <GitBranch className="w-3.5 h-3.5 opacity-60" />
                          <span className="opacity-50">{t('settings.sourcesTab.branchLabelColon')}</span>
                          <span className="font-mono text-sm font-bold">{inst.branch || inst.spaces.branch}</span>
                        </div>
                      )}

                      {/* Sync details */}
                      <div className="flex items-center gap-1.5 mt-1 border-t pt-1 border-ds-zinc-800/20">
                        <Calendar className="w-3.5 h-3.5 opacity-60" />
                        {inst.sync_status === 'error' ? (
                          <span className="text-ds-red-400 font-bold">{t('settings.sourcesTab.syncErrorShort')}</span>
                        ) : inst.last_synced_at ? (
                          <span>
                            {t('settings.sourcesTab.activeLastSync', {
                              date: new Date(inst.last_synced_at).toLocaleString(language === 'de' ? 'de-DE' : 'en-US', {
                                hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'
                              })
                            })}
                          </span>
                        ) : (
                          <span className="text-ds-amber-500 font-bold">{t('settings.sourcesTab.readyNeverSynced')}</span>
                        )}
                      </div>
                    </div>

                    {/* Syncing Progress Bar (if active) */}
                    {inst.sync_status === 'syncing' && (
                      <div className="space-y-2 mt-2 animate-in fade-in duration-300">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-ds-blue-400 font-bold truncate max-w-[80%]">
                            {inst.progress_message || t('settings.sourcesTab.processingFallback')}
                          </span>
                          {inst.progress > 0 && (
                            <span className="text-ds-blue-400 font-extrabold">{inst.progress}%</span>
                          )}
                        </div>
                        <div className={cn(
                          "w-full h-1.5 rounded-full overflow-hidden shadow-inner",
                          theme === 'dark' ? "bg-ds-zinc-950" : "bg-ds-zinc-200"
                        )}>
                          <div
                            className="h-full bg-gradient-to-r from-ds-blue-500 to-ds-indigo-500 transition-all duration-500 ease-out rounded-full shadow-[0_0_8px_rgba(59,130,246,0.4)] animate-pulse"
                            style={{ width: `${Math.max(inst.progress || 0, 8)}%` }}
                          />
                        </div>
                      </div>
                    )}

                    {/* Kontext-Notiz: Fachwissen/Kunden-Jargon zu dieser Quelle, fließt in den System-Prompt ein */}
                    <div className="mt-2.5" onClick={(e) => e.stopPropagation()}>
                      <label className="text-[11px] uppercase tracking-wider font-extrabold opacity-45 block mb-1">
                        {t('settings.sourcesTab.contextNoteLabel')}
                      </label>
                      <textarea
                        key={inst.id}
                        defaultValue={inst.context_note || ""}
                        onBlur={(e) => handleContextNoteBlur(inst.id, e.target.value)}
                        placeholder={t('settings.sourcesTab.contextNotePlaceholder')}
                        title={t('settings.sourcesTab.contextNoteTitle')}
                        maxLength={2000}
                        rows={2}
                        className={cn(
                          "w-full text-sm rounded-lg border px-2 py-1.5 outline-none transition-colors resize-y",
                          theme === 'dark'
                            ? "bg-ds-zinc-950 border-ds-zinc-850 text-ds-zinc-300 placeholder:text-ds-zinc-700 hover:border-ds-zinc-700 focus:border-ds-blue-600"
                            : "bg-ds-white border-ds-zinc-200 text-ds-zinc-650 placeholder:text-ds-zinc-400 hover:border-ds-zinc-300 focus:border-ds-blue-400"
                        )}
                      />
                    </div>
                  </div>

                  {/* Actions footer */}
                  <div className="relative z-10 flex items-center justify-between mt-5 border-t border-ds-zinc-800/30 pt-3 w-full">
                    {/* Interval selector */}
                    <div>
                      {inst.type?.toLowerCase() !== 'local' ? (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] uppercase tracking-wider font-extrabold opacity-45">{t('settings.sourcesTab.intervalLabelColon')}</span>
                          <select
                            value={inst.sync_interval_minutes ?? 0}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => handleIntervalChange(inst.id, parseInt(e.target.value))}
                            title={t('settings.sourcesTab.syncIntervalTitle')}
                            className={cn(
                              "text-sm font-bold rounded-lg border px-2 py-1 cursor-pointer outline-none transition-colors",
                              theme === 'dark'
                                ? "bg-ds-zinc-950 border-ds-zinc-850 text-ds-zinc-300 hover:border-ds-zinc-700"
                                : "bg-ds-white border-ds-zinc-200 text-ds-zinc-650 hover:border-ds-zinc-300"
                            )}
                          >
                            <option value={60}>{t('settings.sourcesTab.interval1h')}</option>
                            <option value={360}>{t('settings.sourcesTab.interval6h')}</option>
                            <option value={1440}>{t('settings.sourcesTab.interval24h')}</option>
                            <option value={0}>{t('settings.sourcesTab.intervalManual')}</option>
                          </select>
                        </div>
                      ) : (
                        <div className="text-[11px] uppercase tracking-wider font-extrabold opacity-45">{t('settings.sourcesTab.manualDocumentLabel')}</div>
                      )}
                    </div>

                    {/* Button group */}
                    <div className="flex items-center gap-1">
                      {inst.type?.toLowerCase() === 'local' && (
                        <a
                          href={`${API_URL}/knowledge-sources/${inst.id}/raw?download=true`}
                          download={inst.name}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className={cn(
                            "h-7 w-7 rounded-lg flex items-center justify-center transition-colors border",
                            theme === 'dark'
                              ? "bg-ds-zinc-950/80 border-ds-zinc-850 text-ds-indigo-400 hover:bg-ds-indigo-500/10 hover:text-ds-indigo-300"
                              : "bg-ds-white border-ds-zinc-200 text-ds-indigo-650 hover:bg-ds-indigo-50 hover:text-ds-indigo-800"
                          )}
                          title={t('settings.sourcesTab.downloadTitle')}
                        >
                          <Download className="w-3.5 h-3.5" />
                        </a>
                      )}

                      {(inst.type?.toLowerCase() === 'confluence' || inst.type?.toLowerCase() === 'jira' || inst.type?.toLowerCase() === 'git') && (
                        <>
                          <button
                            type="button"
                            disabled={inst.sync_status === 'syncing'}
                            onClick={(e) => handleSyncSource(inst.id, inst.name, e)}
                            className={cn(
                              "h-7 w-7 rounded-lg flex items-center justify-center transition-colors border",
                              theme === 'dark'
                                ? "bg-ds-zinc-950/80 border-ds-zinc-850 text-ds-zinc-400 hover:bg-ds-zinc-800 hover:text-ds-zinc-200"
                                : "bg-ds-white border-ds-zinc-200 text-ds-zinc-600 hover:bg-ds-zinc-50 hover:text-ds-zinc-800",
                              inst.sync_status === 'syncing' && "opacity-50 cursor-not-allowed"
                            )}
                            title={t('settings.sourcesTab.syncSourceTitle')}
                          >
                            <RefreshCw className={cn("w-3.5 h-3.5", inst.sync_status === 'syncing' && "animate-spin")} />
                          </button>
                          {currentUser?.is_admin && inst.type?.toLowerCase() === 'git' && (
                            <button
                              type="button"
                              disabled={inst.sync_status === 'syncing' || inst.sync_status === 'pending' || reindexingSourceId === inst.id}
                              onClick={(e) => handleFullReindex(inst.id, inst.name, e)}
                              className={cn(
                                "h-7 w-7 rounded-lg flex items-center justify-center transition-colors border",
                                theme === 'dark'
                                  ? "bg-ds-amber-500/5 border-ds-amber-500/20 text-ds-amber-400 hover:bg-ds-amber-500/10 hover:text-ds-amber-300"
                                  : "bg-ds-amber-50 border-ds-amber-200 text-ds-amber-600 hover:bg-ds-amber-100 hover:text-ds-amber-700",
                                (inst.sync_status === 'syncing' || inst.sync_status === 'pending' || reindexingSourceId === inst.id) && "opacity-50 cursor-not-allowed"
                              )}
                              title={t('settings.sourcesTab.fullReindexTitle')}
                            >
                              <RefreshCcw className={cn("w-3.5 h-3.5", reindexingSourceId === inst.id && "animate-spin")} />
                            </button>
                          )}
                        </>
                      )}

                      {/* Pin button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          togglePinSource(inst.id);
                        }}
                        className={cn(
                          "h-7 w-7 rounded-lg flex items-center justify-center transition-colors border",
                          isPinned
                            ? (theme === 'dark' ? "bg-ds-amber-500/10 border-ds-amber-500/30 text-ds-amber-500 hover:bg-ds-amber-500/20" : "bg-ds-amber-50 border-ds-amber-300 text-ds-amber-500 hover:bg-ds-amber-100")
                            : (theme === 'dark' ? "bg-ds-zinc-950/80 border-ds-zinc-850 text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-500 hover:text-ds-zinc-800 hover:bg-ds-zinc-50")
                        )}
                        title={isPinned ? t('settings.sourcesTab.unpinSource') || 'Entpinnen' : t('settings.sourcesTab.pinSource') || 'Anpinnen'}
                      >
                        <Pin className="w-3.5 h-3.5" />
                      </button>

                      {/* Delete button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteSource(inst.id);
                        }}
                        className={cn(
                          "h-7 w-7 rounded-lg flex items-center justify-center transition-colors border",
                          theme === 'dark'
                            ? "bg-ds-zinc-950/80 border-ds-zinc-850 text-ds-red-500 hover:bg-ds-red-500/10 hover:text-ds-red-400"
                            : "bg-ds-white border-ds-zinc-200 text-ds-red-650 hover:bg-ds-red-50 hover:text-ds-red-800"
                        )}
                        title={t('settings.sourcesTab.deleteInstanceTitle')}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* SECTION 2: Add New Source / Integration Hub */}
      <div className="space-y-4 pt-3 border-t border-ds-zinc-800/30">
        <div className="flex items-center justify-between">
          <h5 className={cn("text-xs font-bold uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-450" : "text-ds-zinc-550")}>
            {t('settings.sourcesTab.addNewSourceHeading')}
          </h5>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {availableConnectors.filter(src => src.featureKey === 'git' || features.connectors[src.featureKey]).map((src) => {
            return (
              <button
                key={src.typeKey}
                onClick={() => onSetupSource(src.name)}
                className={cn(
                  "group relative text-left p-4 border rounded-lg transition-all duration-300 flex flex-col justify-between min-h-[110px] h-auto shadow-sm hover:shadow-md hover:-translate-y-0.5",
                  theme === 'dark'
                    ? "bg-ds-zinc-900/20 border-ds-zinc-800/80 hover:border-ds-zinc-700/60 hover:bg-ds-zinc-900/40"
                    : "bg-ds-zinc-50 border-ds-zinc-200 hover:border-ds-zinc-300 hover:bg-ds-zinc-50/20"
                )}
              >
                <div className="space-y-2 relative z-10 w-full">
                  <div className="flex items-center justify-between w-full">
                    {/* Glowing icon container */}
                    <div className={cn(
                      "h-8 w-8 rounded-lg flex items-center justify-center border shadow-inner transition-colors duration-300",
                      theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-850 text-ds-zinc-200 group-hover:border-ds-zinc-700" : "bg-ds-white border-ds-zinc-250 text-ds-zinc-800 group-hover:border-ds-zinc-350"
                    )}>
                      {src.icon}
                    </div>

                    {/* Hover Link indicator */}
                    <div className={cn(
                      "h-6 w-6 rounded-lg border flex items-center justify-center transition-all duration-300 opacity-60 group-hover:opacity-100 group-hover:scale-105",
                      theme === 'dark'
                        ? "bg-ds-zinc-950/80 border-ds-zinc-850 text-ds-indigo-400 group-hover:bg-ds-indigo-500/10 group-hover:text-ds-indigo-300"
                        : "bg-ds-white border-ds-zinc-200 text-ds-indigo-600 group-hover:bg-ds-indigo-50 group-hover:text-ds-indigo-700"
                    )}>
                      <Plus className="w-3.5 h-3.5" />
                    </div>
                  </div>

                  <div className="space-y-0.5">
                    <span className={cn("text-xs font-bold tracking-wide", theme === 'dark' ? "text-ds-zinc-250" : "text-ds-zinc-800")}>
                      {src.name}
                    </span>
                    <p className={cn("text-[9px] leading-relaxed line-clamp-2 font-medium opacity-80", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-450")}>
                      {src.desc}
                    </p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
