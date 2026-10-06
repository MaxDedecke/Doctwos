"use client";

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  KeyRound,
  Loader2,
  Play,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  Users,
} from 'lucide-react';

import { api, API_URL } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { badgeClass, cardClass, ghostIconButtonClass, inputClass, primaryButtonClass, secondaryButtonClass, sectionTitleClass, settingsRoot } from '@/components/settings/settingsStyles';
import { Button } from "@/components/ui/button";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn, copyToClipboard } from "@/lib/utils";
import type { OidcConnectionTestResult, OidcMappingSimulationResult, SystemConfigResponse } from '@/types/domain';

export const ConfigSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const { theme, showToast } = useSettings();

  const [config, setConfig] = useState<SystemConfigResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState<OidcConnectionTestResult | null>(null);

  // Simulator state
  const [simRoles, setSimRoles] = useState("");
  const [simGroups, setSimGroups] = useState("");
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationResult, setSimulationResult] = useState<OidcMappingSimulationResult | null>(null);

  const [copiedRedirect, setCopiedRedirect] = useState(false);

  const loadConfig = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.getSystemConfig();
      setConfig(res.data);
    } catch (err) {
      console.error("Failed to load system config", err);
      showToast(t('settings.toast.loadConfigFailed') || "Konfiguration konnte nicht geladen werden", "error", err);
    } finally {
      setIsLoading(false);
    }
  }, [showToast, t]);

  useEffect(() => {
    queueMicrotask(loadConfig);
  }, [loadConfig]);

  const handleCopyRedirect = async () => {
    const uri = config?.sso.redirect_uri || `${API_URL}/auth/oidc/callback`;
    const ok = await copyToClipboard(uri);
    if (ok) {
      setCopiedRedirect(true);
      setTimeout(() => setCopiedRedirect(false), 2000);
      showToast(t('settings.toast.copiedRedirect') || "Redirect-URI kopiert", "success");
    }
  };

  const handleTestConnection = async () => {
    setIsTestingConnection(true);
    setConnectionResult(null);
    try {
      const res = await api.testOidcConnection();
      setConnectionResult(res.data);
      if (res.data.success) {
        showToast(t('settings.configTab.connectionTestOk'), "success");
      } else {
        showToast(t('settings.configTab.connectionTestFailed'), "error");
      }
    } catch (err) {
      console.error("Connection test failed", err);
      setConnectionResult({ success: false, error: String(err) });
      showToast(t('settings.configTab.connectionTestFailed'), "error", err);
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleSimulateMapping = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSimulating(true);
    try {
      const roles = simRoles
        .split(/[,;\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const groups = simGroups
        .split(/[,;\n]/)
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await api.simulateOidcMapping({ roles, groups });
      setSimulationResult(res.data);
    } catch (err) {
      console.error("Simulation failed", err);
      showToast(t('settings.configTab.simulationFailed'), "error", err);
    } finally {
      setIsSimulating(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-5 h-5 animate-spin text-ds-zinc-500" />
      </div>
    );
  }

  const sso = config?.sso;
  const sys = config?.system;
  const secrets = config?.secrets;
  const redirectUri = sso?.redirect_uri || `${API_URL}/auth/oidc/callback`;

  return (
    <div className={settingsRoot}>
      {/* ── Status Banner ────────────────────────────────────────────── */}
      <div
        className={cn(
          "rounded-lg border p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all shadow-sm",
          sso?.enabled
            ? theme === 'dark'
              ? "bg-ds-emerald-950/20 border-ds-emerald-800/40 text-ds-emerald-100"
              : "bg-ds-emerald-50 border-ds-emerald-200 text-ds-emerald-950"
            : theme === 'dark'
              ? "bg-ds-zinc-950/30 border-ds-zinc-800 text-ds-zinc-300"
              : "bg-ds-zinc-50 border-ds-zinc-200 text-ds-zinc-800"
        )}
      >
        <div className="flex items-start gap-3.5">
          <div
            className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
              sso?.enabled
                ? "bg-ds-emerald-500/10 text-ds-emerald-600 dark:text-ds-emerald-400 border border-ds-emerald-500/20"
                : "bg-ds-zinc-500/10 text-ds-zinc-500 border border-ds-zinc-500/20"
            )}
          >
            {sso?.enabled ? <ShieldCheck className="w-5 h-5" /> : <ShieldAlert className="w-5 h-5" />}
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h4 className="font-bold text-sm tracking-tight">
                {sso?.enabled ? t('settings.configTab.ssoActiveTitle') : t('settings.configTab.ssoInactiveTitle')}
              </h4>
              <span
                className={cn(
                  "px-2 py-0.5 rounded text-[0.625rem] font-bold uppercase tracking-wider",
                  sso?.enabled
                    ? "bg-ds-emerald-500/20 text-ds-emerald-700 dark:text-ds-emerald-300"
                    : "bg-ds-zinc-500/20 text-ds-zinc-600 dark:text-ds-zinc-400"
                )}
              >
                {sso?.enabled ? t('settings.configTab.badgeActive') : t('settings.configTab.badgeInactive')}
              </span>
            </div>
            <p className="text-xs text-ds-zinc-500 dark:text-ds-zinc-400 leading-relaxed max-w-2xl">
              {sso?.enabled
                ? t('settings.configTab.ssoActiveDesc', { issuer: sso.issuer ?? '' })
                : t('settings.configTab.ssoInactiveDesc')}
            </p>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={loadConfig}
          className={cn(secondaryButtonClass(theme), "self-start md:self-auto")}
        >
          <RefreshCw className="w-3.5 h-3.5" />
          {t('settings.configTab.refresh')}
        </Button>
      </div>

      {/* ── Section 1: SSO & IdP-Verbindung ───────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center gap-1.5">
          <KeyRound className="w-3.5 h-3.5 text-ds-indigo-500" />
          <h4 className={sectionTitleClass(theme)}>
            {t('settings.configTab.idpSection')}
          </h4>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Issuer & Client-ID */}
          <div
            className={cn(cardClass(theme), "p-4 space-y-3")}
          >
            <div>
              <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">
                {t('settings.configTab.issuerLabel')}
              </span>
              <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100 truncate mt-0.5">
                {sso?.issuer || t('settings.configTab.notSet')}
              </div>
            </div>

            <div>
              <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">
                {t('settings.configTab.clientId')}
              </span>
              <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100 truncate mt-0.5">
                {sso?.client_id || t('settings.configTab.notSet')}
              </div>
            </div>

            <div>
              <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">
                {t('settings.configTab.clientSecretStatus')}
              </span>
              <div className="text-xs font-semibold flex items-center gap-1.5 mt-0.5">
                {sso?.client_secret_configured ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-ds-emerald-500" />
                    <span className="text-ds-emerald-600 dark:text-ds-emerald-400">{t('settings.configTab.secretConfigured')}</span>
                  </>
                ) : (
                  <>
                    <span className="w-2 h-2 rounded-full bg-ds-amber-500" />
                    <span className="text-ds-amber-600 dark:text-ds-amber-400">{t('settings.configTab.secretMissing')}</span>
                  </>
                )}
              </div>
            </div>

            {sso?.issuer && (
              <div className="pt-2 border-t border-ds-zinc-200 dark:border-ds-zinc-800/60">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={handleTestConnection}
                  disabled={isTestingConnection}
                  className={cn(secondaryButtonClass(theme), "w-full justify-center")}
                >
                  {isTestingConnection ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5 text-ds-indigo-500" />
                  )}
                  {t('settings.configTab.testConnection')}
                </Button>
              </div>
            )}
          </div>

          {/* Callback / Redirect URI mit 1-Click Copy */}
          <div
            className={cn(cardClass(theme), "p-4 space-y-3 flex flex-col justify-between")}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">
                  {t('settings.configTab.requiredRedirect')}
                </span>
                <span className="text-[0.625rem] text-ds-indigo-500 font-semibold">{t('settings.configTab.forIdpClient')}</span>
              </div>

              <p className="text-[0.6875rem] text-ds-zinc-500 dark:text-ds-zinc-400">
                {t('settings.configTab.redirectHint')}
              </p>

              <div
                className={cn(
                  "p-2.5 rounded-lg border font-mono text-xs flex items-center justify-between gap-2 select-all break-all",
                  theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-zinc-50 border-ds-zinc-200 text-ds-zinc-900"
                )}
              >
                <span>{redirectUri}</span>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={handleCopyRedirect}
                  className={cn(ghostIconButtonClass, "h-7 w-7 shrink-0")}
                  title={t('settings.configTab.copyRedirectTitle')}
                >
                  {copiedRedirect ? <Check className="w-3.5 h-3.5 text-ds-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                </Button>
              </div>
            </div>

            <div className="text-[0.6875rem] text-ds-zinc-500">
              {t('settings.configTab.redirectImportant')}
            </div>
          </div>
        </div>

        {/* IdP Test Result Banner */}
        {connectionResult && (
          <div
            className={cn(
              "rounded-lg border p-4 text-xs space-y-2 animate-in fade-in duration-150",
              connectionResult.success
                ? theme === 'dark'
                  ? "bg-ds-emerald-950/20 border-ds-emerald-800 text-ds-emerald-200"
                  : "bg-ds-emerald-50 border-ds-emerald-200 text-ds-emerald-900"
                : theme === 'dark'
                  ? "bg-ds-red-950/20 border-ds-red-800 text-ds-red-200"
                  : "bg-ds-red-50 border-ds-red-200 text-ds-red-900"
            )}
          >
            <div className="flex items-center gap-2 font-bold">
              {connectionResult.success ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-ds-emerald-500" />
                  <span>{t('settings.configTab.discoverySuccess', { ms: connectionResult.duration_ms ?? 0 })}</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-ds-red-500" />
                  <span>{t('settings.configTab.discoveryFailed', { ms: connectionResult.duration_ms ?? 0 })}</span>
                </>
              )}
            </div>

            {connectionResult.success ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 font-mono text-[0.6875rem] pt-1">
                <div>
                  <span className="opacity-70">Auth Endpoint:</span> {connectionResult.authorization_endpoint || "—"}
                </div>
                <div>
                  <span className="opacity-70">Token Endpoint:</span> {connectionResult.token_endpoint || "—"}
                </div>
                <div>
                  <span className="opacity-70">JWKS URI:</span> {connectionResult.jwks_uri || "—"}
                </div>
                <div>
                  <span className="opacity-70">End Session:</span> {connectionResult.end_session_endpoint || "—"}
                </div>
              </div>
            ) : (
              <div className="font-mono text-[0.6875rem] break-all">{connectionResult.error}</div>
            )}
          </div>
        )}
      </div>

      {/* ── Section 2: Rollen- & Team-Zuordnung (O-164) ───────────────── */}
      <div className="space-y-4">
        <div className="flex items-center gap-1.5">
          <Users className="w-3.5 h-3.5 text-ds-indigo-500" />
          <h4 className={sectionTitleClass(theme)}>
            {t('settings.configTab.mappingSection')}
          </h4>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Default Team */}
          <div
            className={cn(cardClass(theme), "p-4 space-y-1.5")}
          >
            <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">
              {t('settings.configTab.defaultTeamLabel')}
            </span>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs text-ds-zinc-900 dark:text-ds-zinc-100">
                {sso?.default_team || t('settings.configTab.noTeam')}
              </span>
              {sso?.default_team && (
                sso.default_team_exists ? (
                  <span className={badgeClass('success')}>
                    {t('settings.configTab.teamExists')}
                  </span>
                ) : (
                  <span className={badgeClass('warning')}>
                    {t('settings.configTab.teamMissing')}
                  </span>
                )
              )}
            </div>
            <p className="text-[0.6875rem] text-ds-zinc-500">
              {t('settings.configTab.defaultTeamHint')}
            </p>
          </div>

          {/* Superuser Roles */}
          <div
            className={cn(cardClass(theme), "p-4 space-y-1.5")}
          >
            <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">
              {t('settings.configTab.adminRolesLabel')}
            </span>
            <div className="flex flex-wrap gap-1">
              {sso?.admin_roles && sso.admin_roles.length > 0 ? (
                sso.admin_roles.map((r) => (
                  <span
                    key={r}
                    className="px-2 py-0.5 rounded font-mono text-[0.6875rem] font-semibold bg-ds-indigo-500/10 text-ds-indigo-600 dark:text-ds-indigo-400 border border-ds-indigo-500/20"
                  >
                    {r}
                  </span>
                ))
              ) : (
                <span className="text-xs text-ds-zinc-500">{t('settings.configTab.noRolesMapped')}</span>
              )}
            </div>
            <p className="text-[0.6875rem] text-ds-zinc-500">
              {t('settings.configTab.adminRolesHint')}
            </p>
          </div>

          {/* Claims Pfade */}
          <div
            className={cn(cardClass(theme), "p-4 space-y-1.5")}
          >
            <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">
              {t('settings.configTab.claimsLabel')}
            </span>
            <div className="text-xs font-mono space-y-0.5">
              <div><span className="text-ds-zinc-500">{t('settings.configTab.rolesLabel')}</span> {sso?.roles_claim || "roles"} {t('settings.configTab.rolesClaimSuffix')}</div>
              <div><span className="text-ds-zinc-500">{t('settings.configTab.groupsLabel')}</span> {sso?.groups_claim || "groups"}</div>
            </div>
            <p className="text-[0.6875rem] text-ds-zinc-500">
              {t('settings.configTab.claimsHint')}
            </p>
          </div>
        </div>

        {/* Team Mapping Table */}
        <div
          className={cn(cardClass(theme), "p-4 space-y-3")}
        >
          <div className="flex items-center justify-between">
            <span className={sectionTitleClass(theme)}>
              {t('settings.configTab.teamMappingTitle')}
            </span>
            <span className="text-[0.6875rem] text-ds-zinc-500">
              {t('settings.configTab.mappingsCount', { count: Object.keys(sso?.team_mapping || {}).length })}
            </span>
          </div>

          {Object.keys(sso?.team_mapping || {}).length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="border-b border-ds-zinc-200 dark:border-ds-zinc-800 text-ds-zinc-500">
                    <th className="pb-2 font-semibold">{t('settings.configTab.colIdp')}</th>
                    <th className="pb-2 font-semibold w-8 text-center">➔</th>
                    <th className="pb-2 font-semibold">{t('settings.configTab.colTeam')}</th>
                    <th className="pb-2 font-semibold text-right">{t('settings.configTab.colStatus')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ds-zinc-200/60 dark:divide-ds-zinc-800/60 font-mono">
                  {Object.entries(sso?.team_mapping || {}).map(([idpItem, doctusTeam]) => {
                    const exists = config?.existing_teams?.includes(doctusTeam);
                    return (
                      <tr key={idpItem} className="py-2">
                        <td className="py-2 text-ds-zinc-900 dark:text-ds-zinc-100 font-semibold">{idpItem}</td>
                        <td className="py-2 text-center text-ds-zinc-400">➔</td>
                        <td className="py-2 text-ds-indigo-600 dark:text-ds-indigo-400 font-semibold">{doctusTeam}</td>
                        <td className="py-2 text-right">
                          {exists ? (
                            <span className={cn(badgeClass('success'), "font-sans")}>
                              {t('settings.configTab.existsInDoctus')}
                            </span>
                          ) : (
                            <span className={cn(badgeClass('warning'), "font-sans")}>
                              {t('settings.configTab.notCreated')}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-xs text-ds-zinc-500 py-2">
              {t('settings.configTab.noMapping')}
            </div>
          )}
        </div>

        {/* Interaktiver Mapping-Simulator */}
        <div
          className={cn(cardClass(theme), "p-4 sm:p-5 space-y-4")}
        >
          <div className="space-y-1">
            <h5 className={cn(sectionTitleClass(theme), "flex items-center gap-1.5")}>
              <Play className="w-3.5 h-3.5 text-ds-indigo-500" />
              {t('settings.configTab.simTitle')}
            </h5>
            <p className="text-[0.6875rem] text-ds-zinc-500">
              {t('settings.configTab.simHint')}
            </p>
          </div>

          <form onSubmit={handleSimulateMapping} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className={sectionTitleClass(theme)}>
                  {t('settings.configTab.simRolesLabel')}
                </label>
                <input
                  type="text"
                  placeholder={t('settings.configTab.simRolesPlaceholder')}
                  value={simRoles}
                  onChange={(e) => setSimRoles(e.target.value)}
                  className={cn(inputClass(theme), "font-mono")}
                />
              </div>

              <div className="space-y-1.5">
                <label className={sectionTitleClass(theme)}>
                  {t('settings.configTab.simGroupsLabel')}
                </label>
                <input
                  type="text"
                  placeholder={t('settings.configTab.simGroupsPlaceholder')}
                  value={simGroups}
                  onChange={(e) => setSimGroups(e.target.value)}
                  className={cn(inputClass(theme), "font-mono")}
                />
              </div>
            </div>

            <Button
              type="submit"
              size="sm"
              disabled={isSimulating || (!simRoles && !simGroups)}
              className={cn(primaryButtonClass, "h-8")}
            >
              {isSimulating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              {t('settings.configTab.simSubmit')}
            </Button>
          </form>

          {simulationResult && (
            <div
              className={cn(
                "rounded-lg border p-3.5 text-xs space-y-2.5 animate-in fade-in duration-150",
                theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
              )}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ds-zinc-500">{t('settings.configTab.computedRole')}</span>
                <span
                  className={cn(
                    "px-2 py-0.5 rounded font-bold uppercase text-[0.625rem]",
                    simulationResult.computed_role === 'superuser'
                      ? "bg-ds-indigo-500/20 text-ds-indigo-400 border border-ds-indigo-500/30"
                      : "bg-ds-zinc-500/20 text-ds-zinc-400 border border-ds-zinc-500/30"
                  )}
                >
                  {simulationResult.computed_role === 'superuser' ? t('settings.configTab.roleAdmin') : t('settings.configTab.roleUser')}
                </span>
              </div>

              <div className="space-y-1">
                <span className="font-semibold text-ds-zinc-500">{t('settings.configTab.assignedTeams')}</span>
                {simulationResult.teams.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {simulationResult.teams.map((team) => (
                      <span
                        key={team.name}
                        className={cn(
                          "px-2 py-0.5 rounded font-mono text-[0.6875rem] font-semibold border flex items-center gap-1",
                          team.exists
                            ? "bg-ds-emerald-500/10 text-ds-emerald-600 dark:text-ds-emerald-400 border-ds-emerald-500/20"
                            : "bg-ds-amber-500/10 text-ds-amber-600 dark:text-ds-amber-400 border-ds-amber-500/20"
                        )}
                      >
                        {team.name}
                        {!team.exists && <span className="text-[0.5625rem] opacity-70">{t('settings.configTab.missingInDb')}</span>}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="text-ds-zinc-500 italic">{t('settings.configTab.noTeams')}</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Section 3: System- & Laufzeit-Konfiguration ───────────────── */}
      <div className="space-y-4">
        <div className="flex items-center gap-1.5">
          <Server className="w-3.5 h-3.5 text-ds-indigo-500" />
          <h4 className={sectionTitleClass(theme)}>
            {t('settings.configTab.systemSection')}
          </h4>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div
            className={cn(cardClass(theme), "p-3.5 space-y-1")}
          >
            <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">{t('settings.configTab.version')}</span>
            <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100">
              {sys?.version || "latest"}
            </div>
          </div>

          <div
            className={cn(cardClass(theme), "p-3.5 space-y-1")}
          >
            <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">{t('settings.configTab.logLevel')}</span>
            <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100">
              {sys?.log_level || "INFO"}
            </div>
          </div>

          <div
            className={cn(cardClass(theme), "p-3.5 space-y-1")}
          >
            <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">{t('settings.configTab.aiModel')}</span>
            <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100 truncate">
              {sys?.llm_model || "disabled"}
            </div>
          </div>

          <div
            className={cn(cardClass(theme), "p-3.5 space-y-1")}
          >
            <span className="text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500">{t('settings.configTab.contextWindow')}</span>
            <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100">
              {t('settings.configTab.tokens', { count: sys?.context_window || 8192 })}
            </div>
          </div>
        </div>

        {/* Secrets & Security Status */}
        <div
          className={cn(cardClass(theme), "p-4 space-y-2.5")}
        >
          <span className={sectionTitleClass(theme)}>
            {t('settings.configTab.securityTitle')}
          </span>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="flex items-center justify-between p-2.5 rounded-lg border border-ds-zinc-200 dark:border-ds-zinc-800">
              <span className="text-ds-zinc-600 dark:text-ds-zinc-400">{t('settings.configTab.masterKey')}</span>
              <span className="flex items-center gap-1 font-semibold text-ds-emerald-600 dark:text-ds-emerald-400">
                <Check className="w-3.5 h-3.5" /> {t('settings.configTab.activeProtected')}
              </span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-lg border border-ds-zinc-200 dark:border-ds-zinc-800">
              <span className="text-ds-zinc-600 dark:text-ds-zinc-400">{t('settings.configTab.sessionKey')}</span>
              <span className="flex items-center gap-1 font-semibold text-ds-emerald-600 dark:text-ds-emerald-400">
                <Check className="w-3.5 h-3.5" /> {t('settings.configTab.activeProtected')}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
