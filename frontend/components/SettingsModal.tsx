import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Database, Cpu, Terminal, Code, Sliders, Layers, Users, UserCog } from 'lucide-react';

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useFeatures } from '@/lib/FeaturesContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { EditorSettingsTab } from '@/components/settings/tabs/EditorSettingsTab';
import { LayoutSettingsTab } from '@/components/settings/tabs/LayoutSettingsTab';
import { AiSettingsTab } from '@/components/settings/tabs/AiSettingsTab';
import { ProjectSetupTab } from '@/components/settings/tabs/ProjectSetupTab';
import { LogsSettingsTab } from '@/components/settings/tabs/LogsSettingsTab';
import { TeamsSettingsTab } from '@/components/settings/tabs/TeamsSettingsTab';
import { UsersSettingsTab } from '@/components/settings/tabs/UsersSettingsTab';
import { GitSetupTab } from '@/components/settings/tabs/GitSetupTab';
import { SourcesSetupTab } from '@/components/settings/tabs/SourcesSetupTab';
import { SourcesTab } from '@/components/settings/tabs/SourcesTab';
import { ProjectsTab } from '@/components/settings/tabs/ProjectsTab';

interface SettingsModalProps {
  // Modal-Lebenszyklus bleibt Prop (gehört dem Parent). Der restliche Settings-
  // Zustand kommt über useSettings() aus dem SettingsContext, den page.tsx
  // bereitstellt — siehe docs/TECH_DEBT_CLEANUP_PLAN.md §5, Schritt 1.
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
}) => {
  // Der Modal-Shell nutzt nach der Tab-Zerlegung (§5 Schritt 2) nur noch wenige
  // Werte direkt: Theme fürs Shell-Styling, currentUser für die Admin-Sichtbarkeit
  // des Teams-Tabs, sowie selectedProject/connectedSources für die beiden hier
  // verbliebenen Effekte (selectedSourceRepoId-Sync, sources-Poll). Alles Übrige
  // konsumieren die Tab-Komponenten selbst via useSettings().
  const {
    theme,
    selectedProject,
    connectedSources,
    setConnectedSources,
    currentUser,
  } = useSettings();

  const { language, t } = useLanguage();
  const features = useFeatures();
  const [settingsTab, setSettingsTab] = useState<'projects' | 'sources' | 'ai' | 'logs' | 'editor' | 'layout' | 'git-setup' | 'sources-setup' | 'project-setup' | 'teams' | 'users'>('sources');



  // Wissensquellen local states
  const [selectedSourceRepoId, setSelectedSourceRepoId] = useState<string>("all");
  const [sourcesWizardStep, setSourcesWizardStep] = useState(1);
  const [activeSourceType, setActiveSourceType] = useState<string | null>(null);
  const [targetProjectIdForGitSetup, setTargetProjectIdForGitSetup] = useState<number | null>(null);

  // Synchronize local selectedSourceRepoId with current project focus.
  // selectedSourceRepoId is otherwise user-controlled (see SourcesTab's
  // setSelectedSourceRepoId), so this can't just be computed from
  // selectedProject during render — it's the "adjusting state when a prop
  // changes" pattern (https://react.dev/learn/you-might-not-need-an-effect),
  // done during render instead of in an effect to avoid an extra commit.
  const [prevSelectedProjectId, setPrevSelectedProjectId] = useState<number | null>(selectedProject?.id ?? null);
  if ((selectedProject?.id ?? null) !== prevSelectedProjectId) {
    setPrevSelectedProjectId(selectedProject?.id ?? null);
    setSelectedSourceRepoId(selectedProject ? selectedProject.id.toString() : "all");
  }

  // Der sources-Tab pollt connectedSources selbst, solange etwas synchronisiert.
  // (Das logs-seitige Refresh inkl. activeLogSource-Update lebt jetzt in
  // LogsSettingsTab; hier genügt der reine Neu-Fetch der geteilten Liste.)
  useEffect(() => {
    if (!isOpen || settingsTab !== 'sources') return;
    const hasSyncing = connectedSources.some(s => s.sync_status === 'syncing');
    if (!hasSyncing) return;
    const refetch = async () => {
      try {
        const res = await api.getKnowledgeSources();
        setConnectedSources(res.data);
      } catch (err) {
        console.error("Failed to reload knowledge sources", err);
      }
    };
    const interval = setInterval(refetch, 4000);
    return () => clearInterval(interval);
  }, [isOpen, settingsTab, connectedSources, setConnectedSources]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 bg-ds-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-3 md:p-4">
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className={cn(
              "border rounded-lg w-[95vw] md:w-[96vw] h-[90vh] md:h-[96vh] overflow-hidden shadow-2xl flex flex-col md:flex-row transition-all duration-200",
              theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800/80 shadow-ds-black/80" : "bg-ds-white border-ds-zinc-200 shadow-ds-zinc-300/80"
            )}
          >
            {/* Left tab selectors list */}
            <div className={cn(
              "w-full md:w-[252px] border-b md:border-b-0 md:border-r p-3 md:p-4 flex flex-row md:flex-col justify-between transition-colors duration-200 shrink-0",
              theme === 'dark' ? "bg-ds-zinc-950/40 border-ds-zinc-800/60" : "bg-ds-zinc-50 border-ds-zinc-200"
            )}>
              <div className="space-y-0 md:space-y-5 flex flex-col md:block w-full">
                <div className="px-3 hidden md:block">
                  <h3 className="text-[10px] font-bold text-ds-zinc-500 uppercase tracking-widest">
                    {t('settings.nav.config')}
                  </h3>
                </div>

                <nav className="flex flex-row md:flex-col gap-1 overflow-x-auto no-scrollbar w-full py-1 md:py-0 md:space-y-1">
                  {[
                    { id: 'projects', label: t('settings.nav.projects'), icon: <Layers className="w-3.5 h-3.5 shrink-0" />, enabled: true },
                    { id: 'sources', label: t('settings.nav.sources'), icon: <Database className="w-3.5 h-3.5 shrink-0" />, enabled: true },
                    { id: 'teams', label: t('settings.nav.teams'), icon: <Users className="w-3.5 h-3.5 shrink-0" />, enabled: !!currentUser?.is_admin },
                    { id: 'users', label: t('settings.nav.users'), icon: <UserCog className="w-3.5 h-3.5 shrink-0" />, enabled: !!currentUser?.is_admin },
                    { id: 'ai', label: t('settings.nav.ai'), icon: <Cpu className="w-3.5 h-3.5 shrink-0" />, enabled: features.settings.ai },
                    { id: 'logs', label: t('settings.nav.logs'), icon: <Terminal className="w-3.5 h-3.5 shrink-0" />, enabled: features.settings.logs },
                    { id: 'editor', label: t('settings.nav.editor'), icon: <Code className="w-3.5 h-3.5 shrink-0" />, enabled: features.settings.editor },
                    { id: 'layout', label: t('settings.nav.layout'), icon: <Sliders className="w-3.5 h-3.5 shrink-0" />, enabled: features.settings.layout }
                  ].filter(tab => tab.enabled).map(tab => (
                    <button
                      key={tab.id}
                      type="button"
                      id={`settings-tab-btn-${tab.id}`}
                      onClick={() => setSettingsTab(tab.id as any)}
                      className={cn(
                        "flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all text-left whitespace-nowrap shrink-0",
                        settingsTab === tab.id
                          ? (theme === 'dark'
                              ? "bg-ds-indigo-500/10 text-ds-indigo-400 border border-ds-indigo-500/20 shadow-sm"
                              : "bg-ds-indigo-50 text-ds-indigo-700 border border-ds-indigo-200/50 shadow-sm")
                          : (theme === 'dark'
                              ? "text-ds-zinc-400 hover:bg-ds-zinc-800/40 hover:text-ds-zinc-200"
                              : "text-ds-zinc-650 hover:bg-ds-zinc-200/55 hover:text-ds-zinc-900")
                      )}
                    >
                      {tab.icon}
                      <span>{tab.label}</span>
                    </button>
                  ))}
                </nav>
              </div>

              <div className="hidden md:block px-3 py-2 border-t border-ds-zinc-800/50 text-[9px] text-ds-zinc-500 font-medium">
                IP Context: 82.165.216.180
              </div>
            </div>

            {/* Right tab contents panel */}
            <div className={cn("flex-1 flex flex-col h-full overflow-hidden transition-colors duration-200", theme === 'dark' ? "bg-ds-zinc-900" : "bg-ds-white")}>
              {/* Header */}
              <div className={cn("px-6 py-4 border-b flex items-center justify-between transition-colors", theme === 'dark' ? "border-ds-zinc-800/60" : "border-ds-zinc-200")}>
                <h3 className={cn("font-extrabold text-xs uppercase tracking-wider", theme === 'dark' ? "text-ds-zinc-100" : "text-ds-zinc-800")}>
                  {settingsTab === 'projects' ? t('settings.nav.projects') :
                   settingsTab === 'project-setup' ? t('settings.header.projectSetup') :
                   settingsTab === 'git-setup' ? t('settings.header.gitSetupWizard') :
                   settingsTab === 'sources' ? t('settings.nav.sources') :
                   settingsTab === 'sources-setup' ? t('settings.header.sourcesSetup') :
                   settingsTab === 'teams' ? t('settings.nav.teams') :
                   settingsTab === 'users' ? t('settings.nav.users') :
                   settingsTab === 'ai' ? t('settings.nav.ai') :
                   settingsTab === 'logs' ? t('settings.nav.logs') :
                   settingsTab === 'editor' ? t('settings.header.editorSettings') :
                   t('settings.nav.layout')}
                </h3>
              </div>

              {/* Scrollable Contents */}
              <ScrollArea className="flex-1 w-full min-w-0 p-4 sm:p-6">
                <div className="space-y-6">
                  {/* Tab 1: Projects list and management */}
                  {settingsTab === 'projects' && (
                    <ProjectsTab onNewProject={() => setSettingsTab('project-setup')} />
                  )}

                  {/* Tab 1b: New project creation (own step, not inline) */}
                  {settingsTab === 'project-setup' && <ProjectSetupTab onDone={() => setSettingsTab('projects')} />}

                  {settingsTab === 'git-setup' && <GitSetupTab targetProjectId={targetProjectIdForGitSetup} onDone={() => setSettingsTab('projects')} />}

                  {/* Tab 2: Wissensquellen */}
                  {settingsTab === 'sources' && (
                    <SourcesTab
                      selectedSourceRepoId={selectedSourceRepoId}
                      setSelectedSourceRepoId={setSelectedSourceRepoId}
                      onSetupSource={(typeName) => {
                        setActiveSourceType(typeName);
                        setSourcesWizardStep(1);
                        setSettingsTab('sources-setup');
                      }}
                      onAttachGit={(projectId) => {
                        setTargetProjectIdForGitSetup(projectId);
                        setSettingsTab('git-setup');
                      }}
                    />
                  )}

                  {settingsTab === 'sources-setup' && activeSourceType && <SourcesSetupTab activeSourceType={activeSourceType} selectedSourceRepoId={selectedSourceRepoId} onDone={() => { setActiveSourceType(null); setSettingsTab('sources'); }} />}

                  {/* Tab: Teams (Admin-only) */}
                  {settingsTab === 'teams' && <TeamsSettingsTab />}

                  {/* Tab: Nutzerverwaltung (Admin-only, F-004) */}
                  {settingsTab === 'users' && <UsersSettingsTab />}

                  {/* Tab 3: AI-Parameter */}
                  {settingsTab === 'ai' && <AiSettingsTab />}

                  {/* Tab 4: Logs & Status */}
                  {settingsTab === 'logs' && <LogsSettingsTab />}

                  {/* Tab 5: Editor Preferences */}
                  {settingsTab === 'editor' && <EditorSettingsTab />}

                  {/* Tab 6: Layout & Design */}
                  {settingsTab === 'layout' && <LayoutSettingsTab />}
                </div>
              </ScrollArea>

              {/* Footer */}
              <div className={cn("px-6 py-4 border-t flex justify-end", theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800/60" : "bg-ds-zinc-50 border-ds-zinc-200")}>
                <Button
                  type="button"
                  onClick={onClose}
                  className={cn(
                    "rounded-lg px-4 text-xs font-semibold h-8 transition-colors duration-200",
                    theme === 'dark' ? "bg-ds-zinc-800 hover:bg-ds-zinc-700 text-ds-zinc-200" : "bg-ds-zinc-100 hover:bg-ds-zinc-200 text-ds-zinc-800"
                  )}
                >
                  {t('common.close')}
                </Button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
