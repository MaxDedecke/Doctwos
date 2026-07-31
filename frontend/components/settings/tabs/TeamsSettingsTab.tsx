"use client";

import React, { useState, useEffect } from 'react';
import { Loader2, Plus, Check, X, ChevronRight, Users, Edit, Trash2, UserPlus } from 'lucide-react';
import { cn } from "@/lib/utils";
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Aus SettingsModal herausgelöster 'teams'-Tab (Admin-only; docs/TECH_DEBT_CLEANUP_PLAN.md
// §5, Schritt 2). Vollständig eigenständig: teams-Zustand, refreshTeams (inkl. der
// Users-Liste), Member-Handling und das Laden beim Betreten wandern mit hierher.
// allUsers ist jetzt tab-lokal — der projects-Tab lädt seine eigene Users-Liste
// separat (im Modal), statt wie bisher darauf angewiesen zu sein, dass vorher der
// teams-Tab geöffnet wurde (das war ein latenter Bug für Nicht-Global-Admins).
export const TeamsSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const { theme, showToast } = useSettings();

  const [teams, setTeams] = useState<any[]>([]);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [isLoadingTeams, setIsLoadingTeams] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");
  const [isCreatingTeam, setIsCreatingTeam] = useState(false);
  const [expandedTeamId, setExpandedTeamId] = useState<number | null>(null);
  const [addMemberUserId, setAddMemberUserId] = useState<string>("");
  const [editingTeamId, setEditingTeamId] = useState<number | null>(null);
  const [editTeamNameInput, setEditTeamNameInput] = useState("");
  const [teamMembers, setTeamMembers] = useState<Record<number, any[]>>({});

  const refreshTeams = async () => {
    setIsLoadingTeams(true);
    try {
      const [teamsRes, usersRes] = await Promise.all([api.getTeams(), api.getUsers()]);
      setTeams(teamsRes.data);
      setAllUsers(usersRes.data);
    } catch (err) {
      console.error("Failed to load teams", err);
    } finally {
      setIsLoadingTeams(false);
    }
  };

  // Dieser Tab wird nur gerendert, wenn das Modal offen und teams aktiv ist.
  useEffect(() => {
    (async () => {
      await refreshTeams();
    })();
  }, []);

  const refreshTeamMembers = async (teamId: number) => {
    try {
      const res = await api.getTeamMembers(teamId);
      setTeamMembers(prev => ({ ...prev, [teamId]: res.data }));
    } catch (err) {
      console.error("Failed to load team members", err);
    }
  };

  const handleToggleTeamExpand = (teamId: number) => {
    if (expandedTeamId === teamId) {
      setExpandedTeamId(null);
      return;
    }
    setExpandedTeamId(teamId);
    setAddMemberUserId("");
    if (!teamMembers[teamId]) {
      refreshTeamMembers(teamId);
    }
  };

  const handleCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTeamName.trim()) return;
    setIsCreatingTeam(true);
    try {
      await api.createTeam(newTeamName.trim());
      setNewTeamName("");
      showToast(t('settings.toast.teamCreated'), "success");
      await refreshTeams();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.teamCreateFailed'), "error");
    } finally {
      setIsCreatingTeam(false);
    }
  };

  const handleStartRenameTeam = (team: any) => {
    setEditingTeamId(team.id);
    setEditTeamNameInput(team.name);
  };

  const handleRenameTeam = async (teamId: number) => {
    if (!editTeamNameInput.trim()) return;
    try {
      await api.updateTeam(teamId, editTeamNameInput.trim());
      setEditingTeamId(null);
      showToast(t('settings.toast.teamRenamed'), "success");
      await refreshTeams();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.teamRenameFailed'), "error");
    }
  };

  const handleDeleteTeam = async (teamId: number, teamName: string) => {
    if (!confirm(t('settings.confirm.deleteTeam', { name: teamName }))) return;
    try {
      await api.deleteTeam(teamId);
      showToast(t('settings.toast.teamDeleted', { name: teamName }), "success");
      if (expandedTeamId === teamId) setExpandedTeamId(null);
      await refreshTeams();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.teamDeleteFailed'), "error");
    }
  };

  const handleAddMember = async (teamId: number) => {
    if (!addMemberUserId) return;
    try {
      await api.addTeamMember(teamId, Number(addMemberUserId));
      setAddMemberUserId("");
      showToast(t('settings.toast.memberAdded'), "success");
      await refreshTeamMembers(teamId);
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.memberAddFailed'), "error");
    }
  };

  const handleRemoveMember = async (teamId: number, userId: number) => {
    try {
      await api.removeTeamMember(teamId, userId);
      showToast(t('settings.toast.memberRemoved'), "success");
      await refreshTeamMembers(teamId);
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.memberRemoveFailed'), "error");
    }
  };

  return (
    <div className="space-y-6 w-full min-w-0 animate-in fade-in duration-200">
      <form onSubmit={handleCreateTeam} className="flex items-end gap-2">
        <div className="space-y-1.5 flex-1 min-w-0">
          <label className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
            {t('settings.teams.newTeamLabel')}
          </label>
          <input
            type="text"
            required
            placeholder={t('settings.teams.newTeamPlaceholder')}
            value={newTeamName}
            onChange={(e) => setNewTeamName(e.target.value)}
            className={cn(
              "w-full h-9 rounded-lg text-xs font-semibold px-3 border transition-colors outline-none",
              theme === 'dark'
                ? "bg-zinc-950 border-zinc-800 text-zinc-100 focus:border-zinc-700"
                : "bg-white border-zinc-200 text-zinc-800 focus:border-zinc-300"
            )}
          />
        </div>
        <Button
          type="submit"
          disabled={isCreatingTeam || !newTeamName.trim()}
          className="bg-indigo-650 hover:bg-indigo-700 text-white rounded-lg px-3.5 h-9 text-xs font-bold shadow-md shadow-indigo-600/15 flex items-center gap-1.5 transition-all shrink-0"
        >
          {isCreatingTeam ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
          <span>{t('settings.teams.createButton')}</span>
        </Button>
      </form>

      <div className="space-y-2">
        {isLoadingTeams ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="w-4 h-4 animate-spin text-zinc-500" />
          </div>
        ) : teams.length === 0 ? (
          <div className={cn(
            "text-xs italic p-3.5 border rounded-lg transition-colors",
            theme === 'dark' ? "text-zinc-500 bg-zinc-950/40 border-zinc-800/60" : "text-zinc-500 bg-zinc-50 border-zinc-200"
          )}>
            {t('settings.teams.empty')}
          </div>
        ) : (
          teams.map((team: any) => {
            const isExpanded = expandedTeamId === team.id;
            const members = teamMembers[team.id] || [];
            const memberIds = new Set(members.map((m: any) => m.id));
            const availableUsers = allUsers.filter((u: any) => !memberIds.has(u.id));
            return (
              <div
                key={team.id}
                className={cn(
                  "rounded-lg border transition-all w-full min-w-0 overflow-hidden",
                  theme === 'dark' ? "bg-zinc-950/20 border-zinc-800/80" : "bg-zinc-50 border-zinc-200"
                )}
              >
                <div className="p-4 flex items-center justify-between gap-3">
                  {editingTeamId === team.id ? (
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <input
                        type="text"
                        autoFocus
                        value={editTeamNameInput}
                        onChange={(e) => setEditTeamNameInput(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleRenameTeam(team.id); } if (e.key === 'Escape') setEditingTeamId(null); }}
                        className={cn(
                          "flex-1 min-w-0 h-8 rounded-lg text-xs font-semibold px-2.5 border transition-colors outline-none",
                          theme === 'dark'
                            ? "bg-zinc-950 border-zinc-700 text-zinc-100 focus:border-zinc-600"
                            : "bg-white border-zinc-300 text-zinc-800 focus:border-zinc-400"
                        )}
                      />
                      <Button type="button" variant="ghost" size="icon" onClick={() => handleRenameTeam(team.id)} className="h-8 w-8 rounded-lg text-emerald-500 hover:bg-emerald-500/10 shrink-0">
                        <Check className="w-4 h-4" />
                      </Button>
                      <Button type="button" variant="ghost" size="icon" onClick={() => setEditingTeamId(null)} className="h-8 w-8 rounded-lg text-zinc-500 hover:bg-zinc-500/10 shrink-0">
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleToggleTeamExpand(team.id)}
                      className="flex items-center gap-2 flex-1 min-w-0 text-left"
                    >
                      <ChevronRight className={cn("w-3.5 h-3.5 shrink-0 transition-transform text-zinc-500", isExpanded && "rotate-90")} />
                      <Users className="w-3.5 h-3.5 shrink-0 text-zinc-500" />
                      <span className={cn("font-semibold text-xs truncate", theme === 'dark' ? "text-zinc-100" : "text-zinc-800")}>{team.name}</span>
                    </button>
                  )}

                  {editingTeamId !== team.id && (
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleStartRenameTeam(team)}
                        title={t('settings.teams.renameTitle')}
                        className="h-8 w-8 rounded-lg text-zinc-500 hover:bg-zinc-500/10"
                      >
                        <Edit className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteTeam(team.id, team.name)}
                        title={t('settings.teams.deleteTitle')}
                        className="h-8 w-8 rounded-lg text-red-500 border border-red-500/20 hover:border-red-500/40 hover:bg-red-500/10"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  )}
                </div>

                {isExpanded && (
                  <div className={cn(
                    "px-4 pb-4 pt-1 border-t space-y-3",
                    theme === 'dark' ? "border-zinc-800/60" : "border-zinc-200/80"
                  )}>
                    <div className="space-y-1.5">
                      {members.length === 0 ? (
                        <div className={cn("text-[11px] italic py-1.5", theme === 'dark' ? "text-zinc-500" : "text-zinc-500")}>
                          {t('settings.teams.noMembers')}
                        </div>
                      ) : (
                        members.map((member: any) => (
                          <div
                            key={member.id}
                            className={cn(
                              "flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-xs",
                              theme === 'dark' ? "bg-zinc-900/60" : "bg-white border border-zinc-200"
                            )}
                          >
                            <span className={cn("truncate font-medium", theme === 'dark' ? "text-zinc-300" : "text-zinc-700")}>
                              {member.name || member.email}
                            </span>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => handleRemoveMember(team.id, member.id)}
                              title={t('settings.teams.removeMemberTitle')}
                              className="h-6 w-6 rounded text-red-500 hover:bg-red-500/10 shrink-0"
                            >
                              <X className="w-3 h-3" />
                            </Button>
                          </div>
                        ))
                      )}
                    </div>

                    {availableUsers.length > 0 && (
                      <div className="flex items-center gap-2">
                        <Select value={addMemberUserId} onValueChange={setAddMemberUserId}>
                          <SelectTrigger className="h-8 text-xs font-semibold flex-1 min-w-0">
                            <SelectValue placeholder={t('settings.teams.addMemberPlaceholder')} />
                          </SelectTrigger>
                          <SelectContent>
                            {availableUsers.map((u: any) => (
                              <SelectItem key={u.id} value={String(u.id)}>{u.name || u.email}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button
                          type="button"
                          size="sm"
                          disabled={!addMemberUserId}
                          onClick={() => handleAddMember(team.id)}
                          className="h-8 px-2.5 rounded-lg bg-indigo-650 hover:bg-indigo-700 text-white shrink-0"
                        >
                          <UserPlus className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
