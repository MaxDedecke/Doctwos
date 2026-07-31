"use client";

import React, { useState } from 'react';
import { ChevronLeft, Loader2, Plus } from 'lucide-react';
import { cn } from "@/lib/utils";
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Aus SettingsModal herausgelöster 'project-setup'-Tab (docs/TECH_DEBT_CLEANUP_PLAN.md
// §5, Schritt 2). Die new-project-Formularzustände und handleCreateProject lagen zuvor
// auf Modal-Ebene, wurden aber nur von diesem Tab genutzt und sind jetzt hier gekapselt.
// Die Tab-Navigation gehört dem Modal, daher meldet der Tab per onDone-Callback zurück,
// dass er fertig ist (statt den settingsTab-Setter durchzureichen).
interface ProjectSetupTabProps {
  onDone: () => void;
}

export const ProjectSetupTab: React.FC<ProjectSetupTabProps> = ({ onDone }) => {
  const { t } = useLanguage();
  const {
    theme,
    currentUser,
    setProjects,
    setSelectedProject,
    showToast,
  } = useSettings();

  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");
  const [newProjectTeamId, setNewProjectTeamId] = useState<string>("");
  const [newProjectColor, setNewProjectColor] = useState("#4d7fff");
  const [isCreatingProject, setIsCreatingProject] = useState(false);

  const handleCreateProject = async (e: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!newProjectName.trim()) return;
    setIsCreatingProject(true);
    try {
      const res = await api.createProject({
        name: newProjectName.trim(),
        description: newProjectDescription.trim() || undefined,
        team_id: newProjectTeamId ? Number(newProjectTeamId) : undefined,
        color: newProjectColor
      });
      const projectsRes = await api.getProjects();
      setProjects(projectsRes.data);
      const created = projectsRes.data.find((p: any) => p.id === res.data.id);
      if (created) setSelectedProject(created);
      setNewProjectName("");
      setNewProjectDescription("");
      setNewProjectTeamId("");
      setNewProjectColor("#4d7fff");
      showToast(t('settings.toast.projectCreated'), "success");
      onDone();
    } catch (err) {
      console.error(err);
      showToast(t('settings.toast.projectCreateFailed'), "error");
    } finally {
      setIsCreatingProject(false);
    }
  };

  return (
    <div className="space-y-6 w-full min-w-0 max-w-md">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onDone}
        className="h-7 px-2 text-xs font-semibold flex items-center gap-1 text-zinc-500 hover:text-zinc-300"
      >
        <ChevronLeft className="w-3.5 h-3.5" />
        <span>{t('settings.projects.backToList')}</span>
      </Button>

      <form onSubmit={handleCreateProject} className="space-y-4">
        <div className="space-y-1.5">
          <label className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
            {t('settings.projects.nameLabel')}
          </label>
          <input
            type="text"
            required
            placeholder={t('settings.projects.namePlaceholder')}
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            className={cn(
              "w-full h-9 rounded-lg text-xs font-semibold px-3 border transition-colors outline-none",
              theme === 'dark'
                ? "bg-zinc-950 border-zinc-800 text-zinc-100 focus:border-zinc-700"
                : "bg-white border-zinc-200 text-zinc-800 focus:border-zinc-300"
            )}
          />
        </div>

        <div className="space-y-1.5">
          <label className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
            {t('settings.projects.descriptionLabel')}
          </label>
          <Textarea
            placeholder={t('settings.projects.descriptionPlaceholder')}
            value={newProjectDescription}
            onChange={(e) => setNewProjectDescription(e.target.value)}
            className={cn(
              "w-full text-xs font-medium px-3 py-2 border transition-colors outline-none min-h-[80px]",
              theme === 'dark'
                ? "bg-zinc-950 border-zinc-800 text-zinc-100 focus:border-zinc-700"
                : "bg-white border-zinc-200 text-zinc-800 focus:border-zinc-300"
            )}
          />
        </div>

        <div className="space-y-1.5">
          <label className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
            Projekt-Farbe
          </label>
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={newProjectColor}
              onChange={(e) => setNewProjectColor(e.target.value)}
              className="w-10 h-9 p-0.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-transparent cursor-pointer"
            />
            <span className="text-xs font-semibold text-zinc-500">{newProjectColor}</span>
          </div>
        </div>

        {(currentUser?.teams?.length ?? 0) > 1 && (
          <div className="space-y-1.5">
            <label className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
              {t('settings.projects.teamLabel')}
            </label>
            <Select value={newProjectTeamId} onValueChange={setNewProjectTeamId}>
              <SelectTrigger className="h-9 text-xs font-semibold">
                <SelectValue placeholder={t('settings.projects.teamPlaceholderDefault')} />
              </SelectTrigger>
              <SelectContent>
                {currentUser.teams.map((team: any) => (
                  <SelectItem key={team.id} value={String(team.id)}>{team.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <Button
          type="submit"
          disabled={isCreatingProject || !newProjectName.trim()}
          className="bg-indigo-650 hover:bg-indigo-700 text-white rounded-lg px-4 h-9 text-xs font-bold shadow-md shadow-indigo-600/15 flex items-center gap-1.5 transition-all"
        >
          {isCreatingProject ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Plus className="w-3.5 h-3.5" />
          )}
          <span>{t('settings.projects.createButton')}</span>
        </Button>
      </form>
    </div>
  );
};
