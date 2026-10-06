"use client";
import { apiErrorDetail } from '@/lib/apiError';
import type { Team, User } from '@/types/domain';

import { api } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from "@/lib/utils";
import { InitialsAvatar } from '@/components/settings/InitialsAvatar';
import { badgeClass, cardClass, dividerClass, emptyStateClass, inputClass as fieldClass, primaryButtonClass, secondaryButtonClass, sectionTitleClass } from '@/components/settings/settingsStyles';
import { Check, ChevronRight, Edit, Loader2, Plus, Trash2, UserPlus, Users, X } from 'lucide-react';
import React, { useEffect, useState } from 'react';

// Aus SettingsModal herausgelöster 'teams'-Tab (Admin-only). Vollständig eigenständig: teams-Zustand, refreshTeams (inkl. der
// Users-Liste), Member-Handling und das Laden beim Betreten wandern mit hierher.
// allUsers ist jetzt tab-lokal — der projects-Tab lädt seine eigene Users-Liste
// separat (im Modal), statt wie bisher darauf angewiesen zu sein, dass vorher der
// teams-Tab geöffnet wurde (das war ein latenter Bug für Nicht-Global-Admins).
export const TeamsSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const { theme, showToast } = useSettings();

  const [teams, setTeams] = useState<Team[]>([]);
  const [allUsers, setAllUsers] = useState<User[]>([]);
  const [isLoadingTeams, setIsLoadingTeams] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");
  const [isCreatingTeam, setIsCreatingTeam] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [expandedTeamId, setExpandedTeamId] = useState<number | null>(null);
  const [addMemberUserId, setAddMemberUserId] = useState<string>("");
  const [editingTeamId, setEditingTeamId] = useState<number | null>(null);
  const [editTeamNameInput, setEditTeamNameInput] = useState("");
  const [teamMembers, setTeamMembers] = useState<Record<number, User[]>>({});

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
      setShowForm(false);
      showToast(t('settings.toast.teamCreated'), "success");
      await refreshTeams();
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.teamCreateFailed'), "error", err);
    } finally {
      setIsCreatingTeam(false);
    }
  };

  const handleStartRenameTeam = (team: Team) => {
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
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.teamRenameFailed'), "error", err);
    }
  };

  const handleDeleteTeam = async (teamId: number, teamName: string) => {
    if (!confirm(t('settings.confirm.deleteTeam', { name: teamName }))) return;
    try {
      await api.deleteTeam(teamId);
      showToast(t('settings.toast.teamDeleted', { name: teamName }), "success");
      if (expandedTeamId === teamId) setExpandedTeamId(null);
      await refreshTeams();
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.teamDeleteFailed'), "error", err);
    }
  };

  const handleAddMember = async (teamId: number) => {
    if (!addMemberUserId) return;
    try {
      await api.addTeamMember(teamId, Number(addMemberUserId));
      setAddMemberUserId("");
      showToast(t('settings.toast.memberAdded'), "success");
      await refreshTeamMembers(teamId);
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.memberAddFailed'), "error", err);
    }
  };

  const handleRemoveMember = async (teamId: number, userId: number) => {
    try {
      await api.removeTeamMember(teamId, userId);
      showToast(t('settings.toast.memberRemoved'), "success");
      await refreshTeamMembers(teamId);
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.memberRemoveFailed'), "error", err);
    }
  };

  const dark = theme === 'dark';

  return (
    <div className="space-y-5 w-full min-w-0 animate-in fade-in duration-200">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h4 className={sectionTitleClass(theme)}>{t('settings.teams.title')}</h4>
          {teams.length > 0 && <span className={badgeClass('neutral')}>{teams.length}</span>}
        </div>
        {showForm ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => { setShowForm(false); setNewTeamName(""); }}
            className={secondaryButtonClass(theme)}
          >
            <X className="w-3.5 h-3.5" />
            <span>{t('common.cancel')}</span>
          </Button>
        ) : (
          <Button type="button" onClick={() => setShowForm(true)} className={primaryButtonClass}>
            <Plus className="w-3.5 h-3.5" />
            <span>{t('settings.teams.addButton')}</span>
          </Button>
        )}
      </div>

      {showForm && (
        <form
          onSubmit={handleCreateTeam}
          className={cn(cardClass(theme), 'p-4 flex items-end gap-3 animate-in fade-in slide-in-from-top-1 duration-200 motion-reduce:animate-none')}
        >
          <div className="space-y-1.5 flex-1 min-w-0">
            <label className={sectionTitleClass(theme)}>{t('settings.teams.newTeamLabel')}</label>
            <input
              type="text"
              required
              autoFocus
              placeholder={t('settings.teams.newTeamPlaceholder')}
              value={newTeamName}
              onChange={(e) => setNewTeamName(e.target.value)}
              className={fieldClass(theme)}
            />
          </div>
          <Button type="submit" disabled={isCreatingTeam || !newTeamName.trim()} className={primaryButtonClass}>
            {isCreatingTeam ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            <span>{t('settings.teams.createButton')}</span>
          </Button>
        </form>
      )}

      <div className="space-y-2">
        {isLoadingTeams ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="w-4 h-4 animate-spin text-ds-zinc-500" />
          </div>
        ) : teams.length === 0 ? (
          <div className={emptyStateClass(theme)}>{t('settings.teams.empty')}</div>
        ) : (
          teams.map((team: Team) => {
            const isExpanded = expandedTeamId === team.id;
            const members = teamMembers[team.id] || [];
            const memberIds = new Set(members.map((m) => m.id));
            const availableUsers = allUsers.filter((u) => !memberIds.has(u.id));
            return (
              <div
                key={team.id}
                className={cn(
                  cardClass(theme),
                  "w-full min-w-0 overflow-hidden",
                  isExpanded ? (dark ? "border-ds-zinc-700" : "border-ds-zinc-300") : (dark ? "hover:border-ds-zinc-700" : "hover:border-ds-zinc-300")
                )}
              >
                <div className="p-3.5 flex items-center justify-between gap-3">
                  {editingTeamId === team.id ? (
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <input
                        type="text"
                        autoFocus
                        value={editTeamNameInput}
                        onChange={(e) => setEditTeamNameInput(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleRenameTeam(team.id); } if (e.key === 'Escape') setEditingTeamId(null); }}
                        className={cn(fieldClass(theme), 'flex-1 min-w-0 h-8 px-2.5')}
                      />
                      <Button type="button" variant="ghost" size="icon" onClick={() => handleRenameTeam(team.id)} className="h-8 w-8 rounded-lg text-ds-emerald-500 hover:bg-ds-emerald-500/10 shrink-0">
                        <Check className="w-4 h-4" />
                      </Button>
                      <Button type="button" variant="ghost" size="icon" onClick={() => setEditingTeamId(null)} className="h-8 w-8 rounded-lg text-ds-zinc-500 hover:bg-ds-zinc-500/10 shrink-0">
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleToggleTeamExpand(team.id)}
                      className="flex items-center gap-3 flex-1 min-w-0 text-left"
                    >
                      <InitialsAvatar label={team.name} className="rounded-lg" />
                      <span className="flex-1 min-w-0 flex items-center gap-2">
                        <span className={cn("font-semibold text-xs truncate", dark ? "text-ds-zinc-100" : "text-ds-zinc-800")}>{team.name}</span>
                        {teamMembers[team.id] && (
                          <span className={cn(badgeClass('neutral'), 'inline-flex items-center gap-1')}>
                            <Users className="w-2.5 h-2.5" />
                            {members.length}
                          </span>
                        )}
                      </span>
                      <ChevronRight className={cn("w-3.5 h-3.5 shrink-0 transition-transform text-ds-zinc-500", isExpanded && "rotate-90")} />
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
                        className="h-8 w-8 rounded-lg text-ds-zinc-500 hover:bg-ds-zinc-500/10"
                      >
                        <Edit className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteTeam(team.id, team.name)}
                        title={t('settings.teams.deleteTitle')}
                        className="h-8 w-8 rounded-lg text-ds-red-500 border border-ds-red-500/20 hover:border-ds-red-500/40 hover:bg-ds-red-500/10"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  )}
                </div>

                {isExpanded && (
                  <div className={cn("px-3.5 pb-3.5 pt-3 space-y-3 animate-in fade-in duration-150 motion-reduce:animate-none", dividerClass(theme))}>
                    <div className="space-y-1.5">
                      {members.length === 0 ? (
                        <div className="text-[0.6875rem] italic py-1.5 text-ds-zinc-500">
                          {t('settings.teams.noMembers')}
                        </div>
                      ) : (
                        members.map((member) => (
                          <div
                            key={member.id}
                            className={cn(
                              "flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-xs",
                              dark ? "bg-ds-zinc-900/60" : "bg-ds-white border border-ds-zinc-200"
                            )}
                          >
                            <span className="flex items-center gap-2.5 min-w-0">
                              <InitialsAvatar label={member.name || member.email || '?'} className="h-6 w-6 text-[0.5625rem]" />
                              <span className={cn("truncate font-medium", dark ? "text-ds-zinc-300" : "text-ds-zinc-700")}>
                                {member.name || member.email}
                              </span>
                            </span>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => handleRemoveMember(team.id, member.id)}
                              title={t('settings.teams.removeMemberTitle')}
                              className="h-6 w-6 rounded text-ds-red-500 hover:bg-ds-red-500/10 shrink-0"
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
                            {availableUsers.map((u) => (
                              <SelectItem key={u.id} value={String(u.id)}>{u.name || u.email}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button
                          type="button"
                          size="sm"
                          disabled={!addMemberUserId}
                          onClick={() => handleAddMember(team.id)}
                          className="h-8 px-2.5 rounded-lg bg-transparent border border-ds-zinc-300 dark:border-ds-zinc-700 text-ds-zinc-800 dark:text-ds-zinc-100 hover:bg-ds-zinc-500/10 shrink-0"
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
