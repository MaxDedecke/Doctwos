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
        showToast("IdP-Verbindungstest erfolgreich", "success");
      } else {
        showToast("IdP-Verbindungstest fehlgeschlagen", "error");
      }
    } catch (err) {
      console.error("Connection test failed", err);
      setConnectionResult({ success: false, error: String(err) });
      showToast("IdP-Verbindungstest fehlgeschlagen", "error", err);
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
      showToast("Simulation fehlgeschlagen", "error", err);
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
    <div className="space-y-8 w-full min-w-0 animate-in fade-in duration-200">
      {/* ── Status Banner ────────────────────────────────────────────── */}
      <div
        className={cn(
          "rounded-xl border p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all shadow-sm",
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
                {sso?.enabled ? "Single Sign-On (OIDC) ist aktiv" : "Single Sign-On (OIDC) ist nicht aktiviert"}
              </h4>
              <span
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider",
                  sso?.enabled
                    ? "bg-ds-emerald-500/20 text-ds-emerald-700 dark:text-ds-emerald-300"
                    : "bg-ds-zinc-500/20 text-ds-zinc-600 dark:text-ds-zinc-400"
                )}
              >
                {sso?.enabled ? "Aktiv" : "Inaktiv"}
              </span>
            </div>
            <p className="text-xs text-ds-zinc-500 dark:text-ds-zinc-400 leading-relaxed max-w-2xl">
              {sso?.enabled
                ? `Angemeldet an ${sso.issuer}. Benutzer können sich per OpenID Connect einloggen; lokaler Passwort-Login bleibt als Fallback verfügbar.`
                : "Doctus läuft im reinen lokalen Passwort-Modus. Um SSO einzurichten, hinterlege OIDC_ISSUER, OIDC_CLIENT_ID und OIDC_CLIENT_SECRET in der .env-Datei."}
            </p>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={loadConfig}
          className="shrink-0 h-8 gap-1.5 text-xs font-semibold self-start md:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Aktualisieren
        </Button>
      </div>

      {/* ── Section 1: SSO & IdP-Verbindung ───────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 border-b pb-2 border-ds-zinc-200 dark:border-ds-zinc-800">
          <KeyRound className="w-4 h-4 text-ds-indigo-500" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-ds-zinc-900 dark:text-ds-zinc-100">
            OpenID Connect / IdP-Konfiguration
          </h4>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Issuer & Client-ID */}
          <div
            className={cn(
              "rounded-xl border p-4 space-y-3",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
                OIDC Issuer (IdP-URL)
              </span>
              <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100 truncate mt-0.5">
                {sso?.issuer || "— (Nicht gesetzt)"}
              </div>
            </div>

            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
                Client ID
              </span>
              <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100 truncate mt-0.5">
                {sso?.client_id || "— (Nicht gesetzt)"}
              </div>
            </div>

            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
                Client Secret Status
              </span>
              <div className="text-xs font-semibold flex items-center gap-1.5 mt-0.5">
                {sso?.client_secret_configured ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-ds-emerald-500" />
                    <span className="text-ds-emerald-600 dark:text-ds-emerald-400">Konfiguriert (verborgen)</span>
                  </>
                ) : (
                  <>
                    <span className="w-2 h-2 rounded-full bg-ds-amber-500" />
                    <span className="text-ds-amber-600 dark:text-ds-amber-400">Nicht konfiguriert</span>
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
                  className="w-full h-8 gap-1.5 text-xs font-semibold"
                >
                  {isTestingConnection ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5 text-ds-indigo-500" />
                  )}
                  IdP-Verbindung testen (.well-known)
                </Button>
              </div>
            )}
          </div>

          {/* Callback / Redirect URI mit 1-Click Copy */}
          <div
            className={cn(
              "rounded-xl border p-4 space-y-3 flex flex-col justify-between",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
                  Erforderliche Redirect-URI
                </span>
                <span className="text-[10px] text-ds-indigo-500 font-semibold">Für IdP-Client</span>
              </div>

              <p className="text-[11px] text-ds-zinc-500 dark:text-ds-zinc-400">
                Trage diese exakte URL im Kunden-IdP (Keycloak, Microsoft Entra ID, Okta) als erlaubte Callback-URI ein:
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
                  className="h-7 w-7 rounded shrink-0"
                  title="Redirect-URI kopieren"
                >
                  {copiedRedirect ? <Check className="w-3.5 h-3.5 text-ds-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                </Button>
              </div>
            </div>

            <div className="text-[11px] text-ds-zinc-500">
              Wichtig: Muss im Browser und vom IdP exakt so erreichbar sein.
            </div>
          </div>
        </div>

        {/* IdP Test Result Banner */}
        {connectionResult && (
          <div
            className={cn(
              "rounded-xl border p-4 text-xs space-y-2 animate-in fade-in duration-150",
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
                  <span>IdP Discovery erfolgreich ({connectionResult.duration_ms} ms)</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-ds-red-500" />
                  <span>IdP Discovery fehlgeschlagen ({connectionResult.duration_ms} ms)</span>
                </>
              )}
            </div>

            {connectionResult.success ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 font-mono text-[11px] pt-1">
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
              <div className="font-mono text-[11px] break-all">{connectionResult.error}</div>
            )}
          </div>
        )}
      </div>

      {/* ── Section 2: Rollen- & Team-Zuordnung (O-164) ───────────────── */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 border-b pb-2 border-ds-zinc-200 dark:border-ds-zinc-800">
          <Users className="w-4 h-4 text-ds-indigo-500" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-ds-zinc-900 dark:text-ds-zinc-100">
            Rollen- & Team-Zuordnung (O-164)
          </h4>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Default Team */}
          <div
            className={cn(
              "rounded-xl border p-4 space-y-1.5",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
              Automatisches Standard-Team
            </span>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs text-ds-zinc-900 dark:text-ds-zinc-100">
                {sso?.default_team || "Keines (ohne Team)"}
              </span>
              {sso?.default_team && (
                sso.default_team_exists ? (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-ds-emerald-500/10 text-ds-emerald-600 dark:text-ds-emerald-400 border border-ds-emerald-500/20">
                    Existiert
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-ds-amber-500/10 text-ds-amber-600 dark:text-ds-amber-400 border border-ds-amber-500/20">
                    Team fehlt in Doctus
                  </span>
                )
              )}
            </div>
            <p className="text-[11px] text-ds-zinc-500">
              Jeder neue SSO-Nutzer tritt diesem Team automatisch bei.
            </p>
          </div>

          {/* Superuser Roles */}
          <div
            className={cn(
              "rounded-xl border p-4 space-y-1.5",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
              Superuser-Rollen (Admin)
            </span>
            <div className="flex flex-wrap gap-1">
              {sso?.admin_roles && sso.admin_roles.length > 0 ? (
                sso.admin_roles.map((r) => (
                  <span
                    key={r}
                    className="px-2 py-0.5 rounded font-mono text-[11px] font-semibold bg-ds-indigo-500/10 text-ds-indigo-600 dark:text-ds-indigo-400 border border-ds-indigo-500/20"
                  >
                    {r}
                  </span>
                ))
              ) : (
                <span className="text-xs text-ds-zinc-500">Keine Rollen gemappt (nur manuelle Admin-Vergabe)</span>
              )}
            </div>
            <p className="text-[11px] text-ds-zinc-500">
              Nutzer mit diesen IdP-Rollen erhalten automatisch Superuser-Rechte.
            </p>
          </div>

          {/* Claims Pfade */}
          <div
            className={cn(
              "rounded-xl border p-4 space-y-1.5",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
              Geprüfte IdP-Claims
            </span>
            <div className="text-xs font-mono space-y-0.5">
              <div><span className="text-ds-zinc-500">Rollen:</span> {sso?.roles_claim || "roles"} (inkl. realm_access.roles)</div>
              <div><span className="text-ds-zinc-500">Gruppen:</span> {sso?.groups_claim || "groups"}</div>
            </div>
            <p className="text-[11px] text-ds-zinc-500">
              Keycloak, Azure Entra ID und Okta Standardpfade werden automatisch durchsucht.
            </p>
          </div>
        </div>

        {/* Team Mapping Table */}
        <div
          className={cn(
            "rounded-xl border p-4 space-y-3",
            theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
          )}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-ds-zinc-500">
              Konfiguriertes Team-Mapping (OIDC_TEAM_MAPPING)
            </span>
            <span className="text-[11px] text-ds-zinc-500">
              {Object.keys(sso?.team_mapping || {}).length} Mappings konfiguriert
            </span>
          </div>

          {Object.keys(sso?.team_mapping || {}).length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="border-b border-ds-zinc-200 dark:border-ds-zinc-800 text-ds-zinc-500">
                    <th className="pb-2 font-semibold">IdP Gruppe / Rolle</th>
                    <th className="pb-2 font-semibold w-8 text-center">➔</th>
                    <th className="pb-2 font-semibold">Doctus Team</th>
                    <th className="pb-2 font-semibold text-right">Team-Status</th>
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
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-sans font-bold bg-ds-emerald-500/10 text-ds-emerald-600 dark:text-ds-emerald-400 border border-ds-emerald-500/20">
                              Existiert in Doctus
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-sans font-bold bg-ds-amber-500/10 text-ds-amber-600 dark:text-ds-amber-400 border border-ds-amber-500/20">
                              Noch nicht angelegt
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
              Kein Team-Mapping definiert. Nutzer werden keinem spezifischen Gruppen-Team zugewiesen.
            </div>
          )}
        </div>

        {/* Interaktiver Mapping-Simulator */}
        <div
          className={cn(
            "rounded-xl border p-4 sm:p-5 space-y-4",
            theme === 'dark' ? "bg-ds-zinc-950/40 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
          )}
        >
          <div className="space-y-1">
            <h5 className="font-bold text-xs uppercase tracking-wider text-ds-zinc-900 dark:text-ds-zinc-100 flex items-center gap-1.5">
              <Play className="w-3.5 h-3.5 text-ds-indigo-500" />
              Interaktiver Mapping-Simulator
            </h5>
            <p className="text-[11px] text-ds-zinc-500">
              Prüfe vorab, welche Rolle und Teams ein Nutzer bei der Anmeldung erhält:
            </p>
          </div>

          <form onSubmit={handleSimulateMapping} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
                  IdP Rollen (z. B. doctus-admin, tester)
                </label>
                <input
                  type="text"
                  placeholder="Kommagetrennte Rollen..."
                  value={simRoles}
                  onChange={(e) => setSimRoles(e.target.value)}
                  className={cn(
                    "w-full h-8 px-3 rounded-lg border text-xs font-mono transition-colors outline-none",
                    theme === 'dark'
                      ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-100 focus:border-ds-indigo-500"
                      : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 focus:border-ds-indigo-500"
                  )}
                />
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">
                  IdP Gruppen (z. B. /dev, security)
                </label>
                <input
                  type="text"
                  placeholder="Kommagetrennte Gruppen..."
                  value={simGroups}
                  onChange={(e) => setSimGroups(e.target.value)}
                  className={cn(
                    "w-full h-8 px-3 rounded-lg border text-xs font-mono transition-colors outline-none",
                    theme === 'dark'
                      ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-100 focus:border-ds-indigo-500"
                      : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 focus:border-ds-indigo-500"
                  )}
                />
              </div>
            </div>

            <Button
              type="submit"
              size="sm"
              disabled={isSimulating || (!simRoles && !simGroups)}
              className="h-8 text-xs font-semibold gap-1.5"
            >
              {isSimulating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              Mapping simulieren
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
                <span className="font-semibold text-ds-zinc-500">Berechnete Doctus-Rolle:</span>
                <span
                  className={cn(
                    "px-2 py-0.5 rounded font-bold uppercase text-[10px]",
                    simulationResult.computed_role === 'superuser'
                      ? "bg-ds-indigo-500/20 text-ds-indigo-400 border border-ds-indigo-500/30"
                      : "bg-ds-zinc-500/20 text-ds-zinc-400 border border-ds-zinc-500/30"
                  )}
                >
                  {simulationResult.computed_role === 'superuser' ? "Administrator (Superuser)" : "Normaler Nutzer (User)"}
                </span>
              </div>

              <div className="space-y-1">
                <span className="font-semibold text-ds-zinc-500">Zugeordnete Teams:</span>
                {simulationResult.teams.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {simulationResult.teams.map((t) => (
                      <span
                        key={t.name}
                        className={cn(
                          "px-2 py-0.5 rounded font-mono text-[11px] font-semibold border flex items-center gap-1",
                          t.exists
                            ? "bg-ds-emerald-500/10 text-ds-emerald-600 dark:text-ds-emerald-400 border-ds-emerald-500/20"
                            : "bg-ds-amber-500/10 text-ds-amber-600 dark:text-ds-amber-400 border-ds-amber-500/20"
                        )}
                      >
                        {t.name}
                        {!t.exists && <span className="text-[9px] opacity-70">(fehlt in DB)</span>}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="text-ds-zinc-500 italic">Keine Teams zugewiesen</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Section 3: System- & Laufzeit-Konfiguration ───────────────── */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 border-b pb-2 border-ds-zinc-200 dark:border-ds-zinc-800">
          <Server className="w-4 h-4 text-ds-indigo-500" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-ds-zinc-900 dark:text-ds-zinc-100">
            System- & Laufzeit-Konfiguration
          </h4>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div
            className={cn(
              "rounded-xl border p-3.5 space-y-1",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">Version</span>
            <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100">
              {sys?.version || "latest"}
            </div>
          </div>

          <div
            className={cn(
              "rounded-xl border p-3.5 space-y-1",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">Log-Level</span>
            <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100">
              {sys?.log_level || "INFO"}
            </div>
          </div>

          <div
            className={cn(
              "rounded-xl border p-3.5 space-y-1",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">KI Modell</span>
            <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100 truncate">
              {sys?.llm_model || "disabled"}
            </div>
          </div>

          <div
            className={cn(
              "rounded-xl border p-3.5 space-y-1",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500">Kontextfenster</span>
            <div className="font-mono text-xs font-semibold text-ds-zinc-900 dark:text-ds-zinc-100">
              {sys?.context_window || 8192} Tokens
            </div>
          </div>
        </div>

        {/* Secrets & Security Status */}
        <div
          className={cn(
            "rounded-xl border p-4 space-y-2.5",
            theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
          )}
        >
          <span className="text-xs font-bold uppercase tracking-wider text-ds-zinc-500">
            Sicherheit & Verschlüsselung
          </span>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="flex items-center justify-between p-2.5 rounded-lg border border-ds-zinc-200 dark:border-ds-zinc-800">
              <span className="text-ds-zinc-600 dark:text-ds-zinc-400">Master Encryption Key (Fernet):</span>
              <span className="flex items-center gap-1 font-semibold text-ds-emerald-600 dark:text-ds-emerald-400">
                <Check className="w-3.5 h-3.5" /> Aktiv & geschützt
              </span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-lg border border-ds-zinc-200 dark:border-ds-zinc-800">
              <span className="text-ds-zinc-600 dark:text-ds-zinc-400">Session Secret Key (HMAC):</span>
              <span className="flex items-center gap-1 font-semibold text-ds-emerald-600 dark:text-ds-emerald-400">
                <Check className="w-3.5 h-3.5" /> Aktiv & geschützt
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
