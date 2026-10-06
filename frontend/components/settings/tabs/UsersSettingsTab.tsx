"use client";
import { apiErrorDetail } from '@/lib/apiError';

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
import { cn, copyToClipboard } from "@/lib/utils";
import { InitialsAvatar } from '@/components/settings/InitialsAvatar';
import { badgeClass, cardClass, emptyStateClass, inputClass as fieldClass, primaryButtonClass, secondaryButtonClass, sectionTitleClass } from '@/components/settings/settingsStyles';
import { Copy, KeyRound, Loader2, Lock, Plus, Unlock, UserCheck, UserX, X } from 'lucide-react';
import React, { useEffect, useState } from 'react';

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
  auth_provider?: 'oidc' | 'local';
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
  const [showForm, setShowForm] = useState(false);
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
    // queueMicrotask: refresh() only sets state after its own await, but
    // calling it straight from the effect body still reads as a
    // synchronous setState-in-effect to the compiler's analysis.
    queueMicrotask(refresh);
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
      setShowForm(false);
      showToast(t('settings.toast.userCreated'), "success");
      await refresh();
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.userCreateFailed'), "error", err);
    } finally {
      setIsCreating(false);
    }
  };

  const closeForm = () => {
    setShowForm(false);
    setNewUsername("");
    setNewName("");
    setNewRole('user');
  };

  const handleResetPassword = async (user: ManagedUser) => {
    if (!confirm(t('settings.confirm.resetPassword', { name: user.username }))) return;
    setBusyUserId(user.id);
    try {
      const res = await api.resetUserPassword(user.id);
      setIssuedPassword({ username: user.username, password: res.data.initial_password });
      showToast(t('settings.toast.passwordReset'), "success");
      await refresh();
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.passwordResetFailed'), "error", err);
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
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.userUpdateFailed'), "error", err);
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
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.userUpdateFailed'), "error", err);
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
    } catch (err) {
      console.error(err);
      showToast(apiErrorDetail(err) || t('settings.toast.userUpdateFailed'), "error", err);
    } finally {
      setBusyUserId(null);
    }
  };

  const copyPassword = async () => {
    if (!issuedPassword) return;
    const ok = await copyToClipboard(issuedPassword.password);
    showToast(t(ok ? 'settings.toast.passwordCopied' : 'settings.toast.passwordCopyFailed'), ok ? "success" : "error");
  };

  const dark = theme === 'dark';
  const labelClass = sectionTitleClass(theme);

  return (
    <div className="space-y-5 w-full min-w-0 animate-in fade-in duration-200">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h4 className={labelClass}>{t('settings.users.title')}</h4>
          {users.length > 0 && <span className={badgeClass('neutral')}>{users.length}</span>}
        </div>
        {showForm ? (
          <Button type="button" variant="outline" onClick={closeForm} className={secondaryButtonClass(theme)}>
            <X className="w-3.5 h-3.5" />
            <span>{t('common.cancel')}</span>
          </Button>
        ) : (
          <Button type="button" onClick={() => setShowForm(true)} className={primaryButtonClass}>
            <Plus className="w-3.5 h-3.5" />
            <span>{t('settings.users.addButton')}</span>
          </Button>
        )}
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className={cn(cardClass(theme), 'p-4 space-y-3 animate-in fade-in slide-in-from-top-1 duration-200 motion-reduce:animate-none')}
        >
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_10rem] gap-3">
            <div className="space-y-1.5 min-w-0">
              <label className={labelClass}>{t('settings.users.usernameLabel')}</label>
              <input
                type="text"
                required
                autoFocus
                autoComplete="off"
                placeholder={t('settings.users.usernamePlaceholder')}
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                className={fieldClass(theme)}
              />
            </div>
            <div className="space-y-1.5 min-w-0">
              <label className={labelClass}>{t('settings.users.nameLabel')}</label>
              <input
                type="text"
                autoComplete="off"
                placeholder={t('settings.users.namePlaceholder')}
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className={fieldClass(theme)}
              />
            </div>
            <div className="space-y-1.5 min-w-0">
              <label className={labelClass}>{t('settings.users.roleLabel')}</label>
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
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p className="text-[0.6875rem] leading-relaxed text-ds-zinc-500">{t('settings.users.createHint')}</p>
            <Button type="submit" disabled={isCreating || !newUsername.trim()} className={primaryButtonClass}>
              {isCreating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              <span>{t('settings.users.createButton')}</span>
            </Button>
          </div>
        </form>
      )}

      {issuedPassword && (
        <div className={cn(
          "rounded-lg border p-3.5 space-y-2 animate-in fade-in slide-in-from-top-1 duration-200 motion-reduce:animate-none",
          dark ? "bg-ds-amber-500/5 border-ds-amber-500/30" : "bg-ds-amber-50 border-ds-amber-200"
        )}>
          <div className={cn("text-xs font-bold", dark ? "text-ds-amber-400" : "text-ds-amber-700")}>
            {t('settings.users.passwordTitle', { name: issuedPassword.username })}
          </div>
          <div className="flex items-center gap-2">
            <code className={cn(
              "flex-1 min-w-0 px-2.5 py-1.5 rounded-lg text-xs font-mono break-all",
              dark ? "bg-ds-zinc-950 text-ds-zinc-100" : "bg-ds-white text-ds-zinc-800 border border-ds-zinc-200"
            )}>
              {issuedPassword.password}
            </code>
            <Button type="button" variant="ghost" size="icon" onClick={copyPassword} className="h-8 w-8 rounded-lg shrink-0">
              <Copy className="w-3.5 h-3.5" />
            </Button>
          </div>
          <div className="flex items-center justify-between gap-2">
            <p className={cn("text-[0.6875rem]", dark ? "text-ds-amber-400/80" : "text-ds-amber-700/90")}>
              {t('settings.users.passwordHint')}
            </p>
            <Button type="button" variant="ghost" size="sm" onClick={() => setIssuedPassword(null)} className="h-7 text-[0.6875rem] font-bold shrink-0">
              {t('common.close')}
            </Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {isLoading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="w-4 h-4 animate-spin text-ds-zinc-500" />
          </div>
        ) : users.length === 0 ? (
          <div className={emptyStateClass(theme)}>{t('settings.users.empty')}</div>
        ) : (
          users.map((user) => {
            const isSelf = currentUser?.id === user.id;
            const isBusy = busyUserId === user.id;
            return (
              <div
                key={user.id}
                className={cn(
                  cardClass(theme),
                  "p-3.5 flex flex-col sm:flex-row sm:items-center gap-3 w-full min-w-0",
                  dark ? "hover:border-ds-zinc-700" : "hover:border-ds-zinc-300",
                  !user.is_active && "opacity-60"
                )}
              >
                <div className="flex flex-1 items-center gap-3 min-w-0">
                  <InitialsAvatar label={user.name || user.username} />
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0">
                      <span className={cn("font-semibold text-xs truncate", dark ? "text-ds-zinc-100" : "text-ds-zinc-800")}>
                        {user.username}
                      </span>
                      {isSelf && <span className={badgeClass('neutral')}>{t('settings.users.you')}</span>}
                      {user.role === 'superuser' && <span className={badgeClass('accent')}>{t('settings.users.roleSuperuser')}</span>}
                      {user.auth_provider === 'oidc' && <span className={badgeClass('neutral')}>SSO</span>}
                      {user.is_locked && (
                        <span className={cn(badgeClass('warning'), 'inline-flex items-center gap-1')}>
                          <Lock className="w-2.5 h-2.5" />
                          {t('settings.users.statusLocked')}
                        </span>
                      )}
                      {!user.is_active && <span className={badgeClass('neutral')}>{t('settings.users.statusInactive')}</span>}
                    </div>
                    <div className="text-[0.6875rem] truncate text-ds-zinc-500">
                      {user.name || user.email || '—'}
                      {user.last_login_at
                        ? ` · ${t('settings.users.lastLogin', { date: new Date(user.last_login_at).toLocaleString() })}`
                        : ` · ${t('settings.users.neverLoggedIn')}`}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0 sm:pl-3 sm:border-l sm:border-ds-zinc-500/15">
                  <Select
                    value={user.role}
                    onValueChange={(v) => handleRoleChange(user, v as 'superuser' | 'user')}
                    disabled={isSelf || isBusy}
                  >
                    <SelectTrigger className="h-8 w-32 text-[0.6875rem] font-semibold">
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
                      className="h-8 w-8 rounded-lg text-ds-amber-500 hover:bg-ds-amber-500/10"
                    >
                      <Unlock className="w-3.5 h-3.5" />
                    </Button>
                  )}

                  {user.auth_provider !== 'oidc' && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      disabled={isBusy}
                      onClick={() => handleResetPassword(user)}
                      title={t('settings.users.resetPasswordTitle')}
                      className="h-8 w-8 rounded-lg text-ds-zinc-500 hover:bg-ds-zinc-500/10"
                    >
                      {isBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <KeyRound className="w-3.5 h-3.5" />}
                    </Button>
                  )}

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
                        ? "text-ds-red-500 border border-ds-red-500/20 hover:border-ds-red-500/40 hover:bg-ds-red-500/10"
                        : "text-ds-emerald-500 hover:bg-ds-emerald-500/10"
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
