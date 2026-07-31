"use client";

import React, { useState, useEffect } from 'react';
import { Loader2, Plus, KeyRound, Lock, Unlock, UserX, UserCheck, Copy, ShieldCheck } from 'lucide-react';
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

// Nutzerverwaltung (F-004), Admin-only — Gegenstück zu backend/api/users.py.
// Ein neu vergebenes Passwort kommt genau einmal aus dem Backend zurück und lebt
// danach nur noch in diesem State, bis der Administrator den Hinweis schließt.
// Deshalb kein Auto-Refresh, der ihn wegräumt (F-005).

interface ManagedUser {
  id: number;
  username: string;
  name: string | null;
  email: string | null;
  role: 'superuser' | 'user';
  is_active: boolean;
  is_locked: boolean;
  must_change_password: boolean;
  failed_login_count: number;
  last_login_at: string | null;
}

export const UsersSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const { theme, showToast, currentUser } = useSettings();

  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [newUsername, setNewUsername] = useState("");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<'superuser' | 'user'>('user');
  const [issuedPassword, setIssuedPassword] = useState<{ username: string; password: string } | null>(null);

  const refresh = async () => {
    setIsLoading(true);
    try {
      const res = await api.getUsers();
      setUsers(res.data);
    } catch (err) {
      console.error("Failed to load users", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim()) return;
    setIsCreating(true);
    try {
      const res = await api.createUser({
        username: newUsername.trim(),
        name: newName.trim() || undefined,
        role: newRole,
      });
      setIssuedPassword({ username: res.data.username, password: res.data.initial_password });
      setNewUsername("");
      setNewName("");
      setNewRole('user');
      showToast(t('settings.toast.userCreated'), "success");
      await refresh();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.userCreateFailed'), "error");
    } finally {
      setIsCreating(false);
    }
  };

  const handleResetPassword = async (user: ManagedUser) => {
    if (!confirm(t('settings.confirm.resetPassword', { name: user.username }))) return;
    setBusyUserId(user.id);
    try {
      const res = await api.resetUserPassword(user.id);
      setIssuedPassword({ username: user.username, password: res.data.initial_password });
      showToast(t('settings.toast.passwordReset'), "success");
      await refresh();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.passwordResetFailed'), "error");
    } finally {
      setBusyUserId(null);
    }
  };

  const handleToggleActive = async (user: ManagedUser) => {
    if (user.is_active && !confirm(t('settings.confirm.deactivateUser', { name: user.username }))) return;
    setBusyUserId(user.id);
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      showToast(user.is_active ? t('settings.toast.userDeactivated') : t('settings.toast.userActivated'), "success");
      await refresh();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.userUpdateFailed'), "error");
    } finally {
      setBusyUserId(null);
    }
  };

  const handleUnlock = async (user: ManagedUser) => {
    setBusyUserId(user.id);
    try {
      await api.unlockUser(user.id);
      showToast(t('settings.toast.userUnlocked'), "success");
      await refresh();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.userUpdateFailed'), "error");
    } finally {
      setBusyUserId(null);
    }
  };

  const handleRoleChange = async (user: ManagedUser, role: 'superuser' | 'user') => {
    if (role === user.role) return;
    setBusyUserId(user.id);
    try {
      await api.updateUser(user.id, { role });
      showToast(t('settings.toast.userRoleChanged'), "success");
      await refresh();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.userUpdateFailed'), "error");
    } finally {
      setBusyUserId(null);
    }
  };

  const copyPassword = async () => {
    if (!issuedPassword) return;
    try {
      await navigator.clipboard.writeText(issuedPassword.password);
      showToast(t('settings.toast.passwordCopied'), "success");
    } catch {
      showToast(t('settings.toast.passwordCopyFailed'), "error");
    }
  };

  const inputClass = cn(
    "w-full h-9 rounded-lg text-xs font-semibold px-3 border transition-colors outline-none",
    theme === 'dark'
      ? "bg-zinc-950 border-zinc-800 text-zinc-100 focus:border-zinc-700"
      : "bg-white border-zinc-200 text-zinc-800 focus:border-zinc-300"
  );

  return (
    <div className="space-y-6 w-full min-w-0 animate-in fade-in duration-200">
      <form onSubmit={handleCreate} className="space-y-2">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-end gap-2">
          <div className="space-y-1.5 flex-1 min-w-0">
            <label className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
              {t('settings.users.usernameLabel')}
            </label>
            <input
              type="text"
              required
              autoComplete="off"
              placeholder={t('settings.users.usernamePlaceholder')}
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              className={inputClass}
            />
          </div>
          <div className="space-y-1.5 flex-1 min-w-0">
            <label className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
              {t('settings.users.nameLabel')}
            </label>
            <input
              type="text"
              autoComplete="off"
              placeholder={t('settings.users.namePlaceholder')}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className={inputClass}
            />
          </div>
          <div className="space-y-1.5 w-full sm:w-40 shrink-0">
            <label className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>
              {t('settings.users.roleLabel')}
            </label>
            <Select value={newRole} onValueChange={(v) => setNewRole(v as 'superuser' | 'user')}>
              <SelectTrigger className="h-9 text-xs font-semibold">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="user">{t('settings.users.roleUser')}</SelectItem>
                <SelectItem value="superuser">{t('settings.users.roleSuperuser')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button
            type="submit"
            disabled={isCreating || !newUsername.trim()}
            className="bg-indigo-650 hover:bg-indigo-700 text-white rounded-lg px-3.5 h-9 text-xs font-bold shadow-md shadow-indigo-600/15 flex items-center gap-1.5 transition-all shrink-0"
          >
            {isCreating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            <span>{t('settings.users.createButton')}</span>
          </Button>
        </div>
        <p className={cn("text-[11px]", theme === 'dark' ? "text-zinc-500" : "text-zinc-500")}>
          {t('settings.users.createHint')}
        </p>
      </form>

      {issuedPassword && (
        <div className={cn(
          "rounded-lg border p-3.5 space-y-2",
          theme === 'dark' ? "bg-amber-500/5 border-amber-500/30" : "bg-amber-50 border-amber-200"
        )}>
          <div className={cn("text-xs font-bold", theme === 'dark' ? "text-amber-400" : "text-amber-700")}>
            {t('settings.users.passwordTitle', { name: issuedPassword.username })}
          </div>
          <div className="flex items-center gap-2">
            <code className={cn(
              "flex-1 min-w-0 px-2.5 py-1.5 rounded-lg text-xs font-mono break-all",
              theme === 'dark' ? "bg-zinc-950 text-zinc-100" : "bg-white text-zinc-800 border border-zinc-200"
            )}>
              {issuedPassword.password}
            </code>
            <Button type="button" variant="ghost" size="icon" onClick={copyPassword} className="h-8 w-8 rounded-lg shrink-0">
              <Copy className="w-3.5 h-3.5" />
            </Button>
          </div>
          <div className="flex items-center justify-between gap-2">
            <p className={cn("text-[11px]", theme === 'dark' ? "text-amber-400/80" : "text-amber-700/90")}>
              {t('settings.users.passwordHint')}
            </p>
            <Button type="button" variant="ghost" size="sm" onClick={() => setIssuedPassword(null)} className="h-7 text-[11px] font-bold shrink-0">
              {t('common.close')}
            </Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {isLoading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="w-4 h-4 animate-spin text-zinc-500" />
          </div>
        ) : (
          users.map((user) => {
            const isSelf = currentUser?.id === user.id;
            const isBusy = busyUserId === user.id;
            return (
              <div
                key={user.id}
                className={cn(
                  "rounded-lg border p-3.5 flex flex-col sm:flex-row sm:items-center gap-3 w-full min-w-0 transition-all",
                  theme === 'dark' ? "bg-zinc-950/20 border-zinc-800/80" : "bg-zinc-50 border-zinc-200",
                  !user.is_active && "opacity-60"
                )}
              >
                <div className="flex-1 min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={cn("font-semibold text-xs truncate", theme === 'dark' ? "text-zinc-100" : "text-zinc-800")}>
                      {user.username}
                    </span>
                    {user.role === 'superuser' && (
                      <ShieldCheck className="w-3.5 h-3.5 shrink-0 text-indigo-500" aria-label={t('settings.users.roleSuperuser')} />
                    )}
                    {user.is_locked && (
                      <span className="flex items-center gap-1 text-[10px] font-bold text-red-500 shrink-0">
                        <Lock className="w-3 h-3" />
                        {t('settings.users.statusLocked')}
                      </span>
                    )}
                    {!user.is_active && (
                      <span className="text-[10px] font-bold text-zinc-500 shrink-0">{t('settings.users.statusInactive')}</span>
                    )}
                  </div>
                  <div className={cn("text-[11px] truncate", theme === 'dark' ? "text-zinc-500" : "text-zinc-500")}>
                    {user.name || user.email || '—'}
                    {user.last_login_at
                      ? ` · ${t('settings.users.lastLogin', { date: new Date(user.last_login_at).toLocaleString() })}`
                      : ` · ${t('settings.users.neverLoggedIn')}`}
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <Select
                    value={user.role}
                    onValueChange={(v) => handleRoleChange(user, v as 'superuser' | 'user')}
                    disabled={isSelf || isBusy}
                  >
                    <SelectTrigger className="h-8 w-32 text-[11px] font-semibold">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="user">{t('settings.users.roleUser')}</SelectItem>
                      <SelectItem value="superuser">{t('settings.users.roleSuperuser')}</SelectItem>
                    </SelectContent>
                  </Select>

                  {user.is_locked && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      disabled={isBusy}
                      onClick={() => handleUnlock(user)}
                      title={t('settings.users.unlockTitle')}
                      className="h-8 w-8 rounded-lg text-amber-500 hover:bg-amber-500/10"
                    >
                      <Unlock className="w-3.5 h-3.5" />
                    </Button>
                  )}

                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    disabled={isBusy}
                    onClick={() => handleResetPassword(user)}
                    title={t('settings.users.resetPasswordTitle')}
                    className="h-8 w-8 rounded-lg text-zinc-500 hover:bg-zinc-500/10"
                  >
                    {isBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <KeyRound className="w-3.5 h-3.5" />}
                  </Button>

                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    disabled={isSelf || isBusy}
                    onClick={() => handleToggleActive(user)}
                    title={user.is_active ? t('settings.users.deactivateTitle') : t('settings.users.activateTitle')}
                    className={cn(
                      "h-8 w-8 rounded-lg",
                      user.is_active
                        ? "text-red-500 border border-red-500/20 hover:border-red-500/40 hover:bg-red-500/10"
                        : "text-emerald-500 hover:bg-emerald-500/10"
                    )}
                  >
                    {user.is_active ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                  </Button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
