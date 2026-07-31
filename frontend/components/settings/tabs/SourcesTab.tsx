"use client";

import React from 'react';
import {
  GitBranch, RefreshCw, Link2, Loader2, Database, Layers,
  FileText, Code, Folder, Building2, Wrench, ClipboardList, Download, Pin, Trash2,
  Plus, Info, Calendar, AlertCircle, CheckCircle2
} from 'lucide-react';
import { cn } from "@/lib/utils";
import { api, API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useFeatures } from '@/lib/FeaturesContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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
  } = useSettings();

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

  // Helper mapping metadata per type for rich styling
  const getConnectorMetadata = (typeName: string) => {
    const name = typeName ? typeName.toLowerCase() : "";
    switch (name) {
      case 'git':
        return {
          glowColor: "rgba(99, 102, 241, 0.15)",
          gradientBorder: "from-indigo-500/40 to-purple-500/10",
          iconColor: "text-indigo-400",
          badgeColor: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
          icon: <GitBranch className="w-4 h-4" />
        };
      case 'confluence':
        return {
          glowColor: "rgba(59, 130, 246, 0.15)",
          gradientBorder: "from-blue-500/40 to-indigo-500/10",
          iconColor: "text-blue-400",
          badgeColor: "bg-blue-500/10 text-blue-400 border-blue-500/20",
          icon: <Database className="w-4 h-4" />
        };
      case 'jira':
        return {
          glowColor: "rgba(139, 92, 246, 0.15)",
          gradientBorder: "from-violet-500/40 to-fuchsia-500/10",
          iconColor: "text-violet-400",
          badgeColor: "bg-violet-500/10 text-violet-400 border-violet-500/20",
          icon: <Layers className="w-4 h-4" />
        };
      case 'local':
        return {
          glowColor: "rgba(245, 158, 11, 0.15)",
          gradientBorder: "from-amber-500/40 to-yellow-500/10",
          iconColor: "text-amber-400",
          badgeColor: "bg-amber-500/10 text-amber-400 border-amber-500/20",
          icon: <Code className="w-4 h-4" />
        };
      case 'folderwatch':
        return {
          glowColor: "rgba(16, 185, 129, 0.15)",
          gradientBorder: "from-emerald-500/40 to-teal-500/10",
          iconColor: "text-emerald-400",
          badgeColor: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
          icon: <Folder className="w-4 h-4" />
        };
      default:
        return {
          glowColor: "rgba(107, 114, 128, 0.15)",
          gradientBorder: "from-zinc-500/40 to-zinc-700/10",
          iconColor: "text-zinc-400",
          badgeColor: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
          icon: <Database className="w-4 h-4" />
        };
    }
  };

  const availableConnectors = [
    { name: "Git", desc: t('settings.sourcesTab.types.git.desc') || "Git-Repository mit Source-Code anbinden", typeKey: "git", icon: <GitBranch className="w-5 h-5 text-indigo-400" />, featureKey: 'git' as any },
    { name: t('settings.sourcesTab.types.confluence.name'), desc: t('settings.sourcesTab.types.confluence.desc'), typeKey: "confluence", icon: <Database className="w-5 h-5 text-blue-400" />, featureKey: 'confluence' as const },
    { name: t('settings.sourcesTab.types.jira.name'), desc: t('settings.sourcesTab.types.jira.desc'), typeKey: "jira", icon: <Layers className="w-5 h-5 text-violet-400" />, featureKey: 'jira' as const },
    { name: t('settings.sourcesTab.types.local.name'), desc: t('settings.sourcesTab.types.local.desc'), typeKey: "local", icon: <Code className="w-5 h-5 text-amber-400" />, featureKey: 'local' as const },
    { name: t('settings.sourcesTab.types.folderwatch.name'), desc: t('settings.sourcesTab.types.folderwatch.desc'), typeKey: "folderwatch", icon: <Folder className="w-5 h-5 text-emerald-400" />, featureKey: 'folderwatch' as const },
  ];

  // Fitering connected sources based on the active selection
  const filteredSources = connectedSources.filter(cs => {
    if (selectedSourceRepoId === "all") return true;
    return cs.project_id?.toString() === selectedSourceRepoId || cs.repoId === selectedSourceRepoId;
  });

  // Sort pinned sources first
  const sortedSources = [...filteredSources].sort((a, b) => {
    const aPinned = pinnedSourceIds.includes(a.id) ? 1 : 0;
    const bPinned = pinnedSourceIds.includes(b.id) ? 1 : 0;
    return bPinned - aPinned;
  });

  return (
    <div className="space-y-8 animate-in fade-in duration-300 w-full min-w-0">
      {/* Header Info */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800/40 pb-5">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <h4 className={cn("text-sm font-bold uppercase tracking-wider", theme === 'dark' ? "text-zinc-200" : "text-zinc-850")}>
              {t('settings.sourcesTab.title')}
            </h4>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-sm bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              {connectedSources.length} {connectedSources.length === 1 ? 'Quelle' : 'Quellen'}
            </span>
          </div>
          <p className={cn("text-xs leading-relaxed max-w-2xl", theme === 'dark' ? "text-zinc-400" : "text-zinc-650")}>
            {t('settings.sourcesTab.description')}
          </p>
        </div>

        {/* Project Selector */}
        <div className="p-2.5 rounded-lg flex items-center gap-3 transition-all duration-300">
          <span className={cn("text-[10px] font-bold uppercase tracking-wider shrink-0", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
            Filter:
          </span>
          <Select 
            value={selectedSourceRepoId} 
            onValueChange={(val) => setSelectedSourceRepoId(val)}
          >
            <SelectTrigger className={cn(
              "h-8 text-xs border focus:ring-0 w-[180px] rounded-lg font-medium shadow-none transition-all flex items-center justify-between gap-1.5",
              theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800/60" : "bg-white border-zinc-250 text-zinc-700 hover:bg-zinc-50"
            )}>
              <div className="flex items-center gap-1.5 truncate">
                <GitBranch className="w-3 h-3 text-indigo-400 shrink-0" />
                <span className="truncate">
                  {selectedSourceRepoId === "all"
                    ? t('settings.sourcesTab.allProjects')
                    : projects.find((p: any) => p.id.toString() === selectedSourceRepoId)?.name || t('settings.sourcesTab.selectProjectPlaceholder')}
                </span>
              </div>
            </SelectTrigger>
            <SelectContent className={theme === 'dark' ? "bg-zinc-900 border-zinc-850 text-zinc-200" : "bg-white border-zinc-200 text-zinc-800"}>
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

      {/* SECTION 1: Active Connected Sources */}
      <div className="space-y-4">
        <h5 className={cn("text-xs font-bold uppercase tracking-wider", theme === 'dark' ? "text-zinc-450" : "text-zinc-550")}>
          Verbundene Datenquellen ({filteredSources.length})
        </h5>

        {sortedSources.length === 0 ? (
          /* Empty State */
          <div className={cn(
            "flex flex-col items-center justify-center p-8 text-center rounded-lg border border-dashed transition-all duration-300",
            theme === 'dark' ? "bg-zinc-950/20 border-zinc-800" : "bg-zinc-50/50 border-zinc-200"
          )}>
            <div className="h-12 w-12 rounded-full bg-indigo-500/10 flex items-center justify-center mb-3">
              <Info className="w-6 h-6 text-indigo-400" />
            </div>
            <p className={cn("text-xs font-bold", theme === 'dark' ? "text-zinc-300" : "text-zinc-800")}>
              Keine aktiven Datenquellen gefunden
            </p>
            <p className={cn("text-[10px] mt-1 max-w-sm leading-relaxed", theme === 'dark' ? "text-zinc-500" : "text-zinc-450")}>
              {selectedSourceRepoId === "all" 
                ? "Binden Sie unten Ihre erste Datenquelle an, um Ihr Doctus AI Projekt mit Wissen zu füttern."
                : "Für dieses Projekt wurden noch keine spezifischen Datenquellen angebunden."}
            </p>
          </div>
        ) : (
          /* Premium Cards Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sortedSources.map((inst) => {
              const meta = getConnectorMetadata(inst.type);
              const isPinned = pinnedSourceIds.includes(inst.id);
              const project = projects.find((p: any) => p.id === inst.project_id);

              return (
                <div 
                  key={inst.id}
                  className={cn(
                    "group relative p-4 rounded-lg border transition-all duration-300 flex flex-col justify-between overflow-hidden shadow-sm hover:shadow-md hover:-translate-y-0.5",
                    theme === 'dark' 
                      ? "bg-zinc-900/40 border-zinc-800/80 hover:border-zinc-700/50" 
                      : "bg-white/80 border-zinc-200 hover:border-zinc-300",
                    isPinned && (theme === 'dark' ? "border-amber-500/40 bg-gradient-to-b from-amber-500/5 to-transparent" : "border-amber-400 bg-amber-50/30")
                  )}
                  style={{
                    boxShadow: isPinned ? `0 4px 20px ${theme === 'dark' ? 'rgba(245, 158, 11, 0.03)' : 'rgba(245, 158, 11, 0.05)'}` : undefined
                  }}
                >
                  {/* Neon Glow backdrop */}
                  <div 
                    className="absolute top-0 right-0 w-24 h-24 blur-2xl rounded-full opacity-30 z-0 pointer-events-none transition-all duration-500 group-hover:scale-110"
                    style={{ backgroundColor: meta.glowColor }}
                  />

                  {/* Header info row */}
                  <div className="relative z-10 w-full space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        {/* Glowing icon wrapper */}
                        <div className={cn(
                          "h-8 w-8 rounded-lg flex items-center justify-center border shadow-inner transition-transform duration-300 group-hover:scale-105",
                          theme === 'dark' ? "bg-zinc-950 border-zinc-800 text-zinc-200" : "bg-zinc-50 border-zinc-200 text-zinc-800"
                        )}>
                          <span className={meta.iconColor}>{meta.icon}</span>
                        </div>

                        {/* Title & Badge */}
                        <div className="flex flex-col min-w-0">
                          <span className={cn("text-xs font-bold truncate max-w-[180px] leading-tight", theme === 'dark' ? "text-zinc-200" : "text-zinc-800")} title={inst.name}>
                            {inst.name}
                          </span>
                          <span className={cn("inline-self-start text-[7.5px] uppercase tracking-widest font-extrabold px-1.5 py-0.5 rounded border mt-1 w-max", meta.badgeColor)}>
                            {inst.type}
                          </span>
                        </div>
                      </div>

                      {/* Status badge */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {inst.sync_status === 'syncing' ? (
                          <span className="flex items-center gap-1 text-[8px] font-bold text-blue-400 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded-sm">
                            <Loader2 className="w-2.5 h-2.5 animate-spin" /> {t('settings.logsTab.statusSyncingDefault')}
                          </span>
                        ) : inst.sync_status === 'error' ? (
                          <span className="flex items-center gap-1 text-[8px] font-bold text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-sm">
                            <AlertCircle className="w-2.5 h-2.5" /> Error
                          </span>
                        ) : inst.last_synced_at ? (
                          <span className="flex items-center gap-1 text-[8px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-sm">
                            <CheckCircle2 className="w-2.5 h-2.5" /> Synced
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-[8px] font-bold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-sm">
                            <Info className="w-2.5 h-2.5" /> Ready
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Metadata lines */}
                    <div className={cn(
                      "text-[9px] space-y-1.5 p-2.5 rounded-lg border font-medium",
                      theme === 'dark' ? "bg-zinc-950/30 border-zinc-850/60 text-zinc-400" : "bg-zinc-50 border-zinc-200 text-zinc-650"
                    )}>
                      {project && (
                        <div className="flex items-center gap-1.5">
                          <span className="opacity-50">Projekt:</span>
                          <span className={cn("font-bold", theme === 'dark' ? "text-zinc-300" : "text-zinc-800")}>{project.name}</span>
                        </div>
                      )}
                      {inst.type?.toLowerCase() === 'git' && inst.spaces?.branch && (
                        <div className="flex items-center gap-1.5">
                          <GitBranch className="w-2.5 h-2.5 opacity-60" />
                          <span className="opacity-50">Branch:</span>
                          <span className="font-mono text-[8px] font-bold">{inst.spaces.branch}</span>
                        </div>
                      )}
                      
                      {/* Sync details */}
                      <div className="flex items-center gap-1.5 mt-1 border-t pt-1 border-zinc-800/20">
                        <Calendar className="w-2.5 h-2.5 opacity-60" />
                        {inst.sync_status === 'error' ? (
                          <span className="text-red-400 font-bold">{t('settings.sourcesTab.syncErrorShort')}</span>
                        ) : inst.last_synced_at ? (
                          <span>
                            {t('settings.sourcesTab.activeLastSync', {
                              date: new Date(inst.last_synced_at).toLocaleString(language === 'de' ? 'de-DE' : 'en-US', {
                                hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'
                              })
                            })}
                          </span>
                        ) : (
                          <span className="text-amber-500 font-bold">{t('settings.sourcesTab.readyNeverSynced')}</span>
                        )}
                      </div>
                    </div>

                    {/* Syncing Progress Bar (if active) */}
                    {inst.sync_status === 'syncing' && (
                      <div className="space-y-1.5 mt-2 animate-in fade-in duration-300">
                        <div className="flex items-center justify-between text-[8px]">
                          <span className="text-blue-400 font-bold truncate max-w-[80%]">
                            {inst.progress_message || "Verarbeitung..."}
                          </span>
                          {inst.progress > 0 && (
                            <span className="text-blue-400 font-extrabold">{inst.progress}%</span>
                          )}
                        </div>
                        <div className={cn(
                          "w-full h-1.5 rounded-full overflow-hidden shadow-inner",
                          theme === 'dark' ? "bg-zinc-950" : "bg-zinc-200"
                        )}>
                          <div 
                            className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-500 ease-out rounded-full shadow-[0_0_8px_rgba(59,130,246,0.4)] animate-pulse"
                            style={{ width: `${Math.max(inst.progress || 0, 8)}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Actions footer */}
                  <div className="relative z-10 flex items-center justify-between mt-4 border-t border-zinc-800/30 pt-3 w-full">
                    {/* Interval selector */}
                    <div>
                      {inst.type?.toLowerCase() !== 'local' ? (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[7.5px] uppercase tracking-wider font-extrabold opacity-45">Intervall:</span>
                          <select
                            value={inst.sync_interval_minutes ?? 0}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => handleIntervalChange(inst.id, parseInt(e.target.value))}
                            title={t('settings.sourcesTab.syncIntervalTitle')}
                            className={cn(
                              "text-[8px] font-bold rounded-lg border px-2 py-0.5 cursor-pointer outline-none transition-colors",
                              theme === 'dark'
                                ? "bg-zinc-950 border-zinc-850 text-zinc-300 hover:border-zinc-700"
                                : "bg-white border-zinc-200 text-zinc-650 hover:border-zinc-300"
                            )}
                          >
                            <option value={60}>{t('settings.sourcesTab.interval1h')}</option>
                            <option value={360}>{t('settings.sourcesTab.interval6h')}</option>
                            <option value={1440}>{t('settings.sourcesTab.interval24h')}</option>
                            <option value={0}>{t('settings.sourcesTab.intervalManual')}</option>
                          </select>
                        </div>
                      ) : (
                        <div className="text-[7.5px] uppercase tracking-wider font-extrabold opacity-45">Manuelles Dokument</div>
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
                            "h-6 w-6 rounded-lg flex items-center justify-center transition-colors border",
                            theme === 'dark' 
                              ? "bg-zinc-950/80 border-zinc-850 text-indigo-400 hover:bg-indigo-500/10 hover:text-indigo-300" 
                              : "bg-white border-zinc-200 text-indigo-650 hover:bg-indigo-50 hover:text-indigo-800"
                          )}
                          title={t('settings.sourcesTab.downloadTitle')}
                        >
                          <Download className="w-3 h-3" />
                        </a>
                      )}
                      
                      {(inst.type?.toLowerCase() === 'confluence' || inst.type?.toLowerCase() === 'jira' || inst.type?.toLowerCase() === 'git') && (
                        <button
                          type="button"
                          disabled={inst.sync_status === 'syncing'}
                          onClick={(e) => handleSyncSource(inst.id, inst.name, e)}
                          className={cn(
                            "h-6 w-6 rounded-lg flex items-center justify-center transition-colors border",
                            theme === 'dark' 
                              ? "bg-zinc-950/80 border-zinc-850 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200" 
                              : "bg-white border-zinc-200 text-zinc-600 hover:bg-zinc-50 hover:text-zinc-800",
                            inst.sync_status === 'syncing' && "opacity-50 cursor-not-allowed"
                          )}
                          title={t('settings.sourcesTab.syncSourceTitle')}
                        >
                          <RefreshCw className={cn("w-3 h-3", inst.sync_status === 'syncing' && "animate-spin")} />
                        </button>
                      )}

                      {/* Pin button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          togglePinSource(inst.id);
                        }}
                        className={cn(
                          "h-6 w-6 rounded-lg flex items-center justify-center transition-colors border",
                          isPinned
                            ? (theme === 'dark' ? "bg-amber-500/10 border-amber-500/30 text-amber-500 hover:bg-amber-500/20" : "bg-amber-50 border-amber-300 text-amber-500 hover:bg-amber-100")
                            : (theme === 'dark' ? "bg-zinc-950/80 border-zinc-850 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800" : "bg-white border-zinc-200 text-zinc-500 hover:text-zinc-800 hover:bg-zinc-50")
                        )}
                        title={isPinned ? t('settings.sourcesTab.unpinSource') || 'Entpinnen' : t('settings.sourcesTab.pinSource') || 'Anpinnen'}
                      >
                        <Pin className="w-3 h-3" />
                      </button>

                      {/* Delete button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteSource(inst.id);
                        }}
                        className={cn(
                          "h-6 w-6 rounded-lg flex items-center justify-center transition-colors border",
                          theme === 'dark' 
                            ? "bg-zinc-950/80 border-zinc-850 text-red-500 hover:bg-red-500/10 hover:text-red-400" 
                            : "bg-white border-zinc-200 text-red-650 hover:bg-red-50 hover:text-red-800"
                        )}
                        title={t('settings.sourcesTab.deleteInstanceTitle')}
                      >
                        <Trash2 className="w-3 h-3" />
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
      <div className="space-y-4 pt-3 border-t border-zinc-800/30">
        <div className="flex items-center justify-between">
          <h5 className={cn("text-xs font-bold uppercase tracking-wider", theme === 'dark' ? "text-zinc-450" : "text-zinc-550")}>
            Neue Wissensquelle anbinden
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
                    ? "bg-zinc-900/20 border-zinc-800/80 hover:border-zinc-700/60 hover:bg-zinc-900/40" 
                    : "bg-zinc-50 border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50/20"
                )}
              >
                <div className="space-y-2 relative z-10 w-full">
                  <div className="flex items-center justify-between w-full">
                    {/* Glowing icon container */}
                    <div className={cn(
                      "h-8 w-8 rounded-lg flex items-center justify-center border shadow-inner transition-colors duration-300",
                      theme === 'dark' ? "bg-zinc-950 border-zinc-850 text-zinc-200 group-hover:border-zinc-700" : "bg-white border-zinc-250 text-zinc-800 group-hover:border-zinc-350"
                    )}>
                      {src.icon}
                    </div>

                    {/* Hover Link indicator */}
                    <div className={cn(
                      "h-6 w-6 rounded-lg border flex items-center justify-center transition-all duration-300 opacity-60 group-hover:opacity-100 group-hover:scale-105",
                      theme === 'dark' 
                        ? "bg-zinc-950/80 border-zinc-850 text-indigo-400 group-hover:bg-indigo-500/10 group-hover:text-indigo-300" 
                        : "bg-white border-zinc-200 text-indigo-600 group-hover:bg-indigo-50 group-hover:text-indigo-700"
                    )}>
                      <Plus className="w-3.5 h-3.5" />
                    </div>
                  </div>

                  <div className="space-y-0.5">
                    <span className={cn("text-xs font-bold tracking-wide", theme === 'dark' ? "text-zinc-250" : "text-zinc-800")}>
                      {src.name}
                    </span>
                    <p className={cn("text-[9px] leading-relaxed line-clamp-2 font-medium opacity-80", theme === 'dark' ? "text-zinc-500" : "text-zinc-450")}>
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
