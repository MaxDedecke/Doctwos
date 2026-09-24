"use client";

import React, { useEffect, useState } from 'react';
import { Copy, KeyRound, Loader2, Trash2 } from 'lucide-react';

import { api, API_URL } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { copyToClipboard } from '@/lib/utils';

type TokenRow = {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
};

export const McpSettingsTab: React.FC = () => {
  const { showToast, theme } = useSettings();
  const dark = theme === 'dark';
  const muted = dark ? 'text-ds-zinc-400' : 'text-ds-zinc-600';
  const panel = dark ? 'border-ds-zinc-700' : 'border-ds-zinc-300';
  const field = dark ? 'border-ds-zinc-600 bg-ds-zinc-900 text-ds-zinc-100' : 'border-ds-zinc-300 bg-ds-white text-ds-zinc-900';
  const [rows, setRows] = useState<TokenRow[]>([]);
  const [name, setName] = useState('Meine IDE');
  const [days, setDays] = useState(30);
  const [issued, setIssued] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api.getMcpTokens()
      .then((response) => { if (active) setRows(response.data); })
      .catch(() => { if (active) showToast('MCP-Tokens konnten nicht geladen werden', 'error'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [showToast]);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setIssued(null);
    try {
      const response = await api.createMcpToken(name.trim(), days);
      const { token, ...row } = response.data;
      setIssued(token);
      setRows((previous) => [row, ...previous]);
    } catch {
      showToast('MCP-Token konnte nicht erstellt werden', 'error');
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: number) => {
    try {
      await api.revokeMcpToken(id);
      setRows((previous) => previous.map((row) => row.id === id ? { ...row, revoked_at: new Date().toISOString() } : row));
      showToast('MCP-Token widerrufen', 'success');
    } catch {
      showToast('MCP-Token konnte nicht widerrufen werden', 'error');
    }
  };

  return (
    <div className={`max-w-3xl space-y-6 text-sm ${dark ? 'text-ds-zinc-200' : 'text-ds-zinc-900'}`}>
      <div className="space-y-2">
        <div className="flex items-center gap-2 font-semibold"><KeyRound className="h-4 w-4" /> Doctus in der IDE</div>
        <p className={muted}>Lesender MCP-Zugang für Code- und Wissenssuche. Jeder Aufruf verwendet deine aktuellen Projektberechtigungen.</p>
        <p className={muted}>Server-Adresse: <code className="break-all">{API_URL}/mcp</code></p>
      </div>

      <form onSubmit={create} className={`rounded-lg border p-4 space-y-3 ${panel}`}>
        <div className="font-medium">Persönliches Token erstellen</div>
        <div className="flex flex-wrap gap-3">
          <label className={`flex flex-col gap-1 ${muted}`}>Name
            <input className={`rounded border px-3 py-2 ${field}`} value={name} maxLength={100} onChange={(event) => setName(event.target.value)} required />
          </label>
          <label className={`flex flex-col gap-1 ${muted}`}>Gültigkeit
            <select className={`rounded border px-3 py-2 ${field}`} value={days} onChange={(event) => setDays(Number(event.target.value))}>
              <option value={7}>7 Tage</option><option value={30}>30 Tage</option><option value={90}>90 Tage</option>
            </select>
          </label>
        </div>
        <button type="submit" disabled={busy} className="rounded bg-ds-indigo-600 px-3 py-2 font-medium text-white disabled:opacity-50">{busy ? 'Erstelle…' : 'Token erstellen'}</button>
      </form>

      {issued && (
        <div className={`rounded-lg border p-4 space-y-2 ${dark ? 'border-ds-amber-700 bg-ds-amber-950/20' : 'border-ds-amber-400 bg-ds-amber-50'}`}>
          <div className="font-semibold">Token jetzt kopieren – danach wird es nicht erneut angezeigt.</div>
          <code className={`block break-all rounded p-3 select-all ${dark ? 'bg-ds-zinc-950' : 'bg-ds-white'}`}>{issued}</code>
          <button type="button" className={`flex items-center gap-2 rounded border px-3 py-2 ${panel}`} onClick={async () => { if (await copyToClipboard(issued)) showToast('Token kopiert', 'success'); }}><Copy className="h-4 w-4" /> Kopieren</button>
        </div>
      )}

      <div className="space-y-2">
        <div className="font-medium">Meine Tokens</div>
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : rows.length === 0 ? <p className={muted}>Noch keine Tokens vorhanden.</p> : (
          <div className="space-y-2">
            {rows.map((row) => {
              const expired = new Date(row.expires_at).getTime() <= Date.now();
              return <div key={row.id} className={`flex items-center justify-between gap-3 rounded border p-3 ${panel}`}>
                <div><div className="font-medium">{row.name} <span className={`font-normal ${muted}`}>{row.prefix}…</span></div>
                  <div className={`text-xs ${muted}`}>{row.revoked_at ? 'Widerrufen' : expired ? 'Abgelaufen' : `Gültig bis ${new Date(row.expires_at).toLocaleDateString()}`}</div>
                </div>
                {!row.revoked_at && !expired && <button type="button" aria-label={`${row.name} widerrufen`} onClick={() => revoke(row.id)} className={`rounded border p-2 ${panel}`}><Trash2 className="h-4 w-4" /></button>}
              </div>;
            })}
          </div>
        )}
      </div>

      <div className={`rounded-lg border p-4 space-y-2 ${panel} ${muted}`}>
        <div className={`font-medium ${dark ? 'text-ds-zinc-200' : 'text-ds-zinc-900'}`}>IDE verbinden</div>
        <p>In VS Code, Continue oder Cursor einen Streamable-HTTP-MCP-Server mit der Adresse oben einrichten. Als HTTP-Header <code>Authorization: Bearer &lt;Token&gt;</code> verwenden und das Token nur in der persönlichen IDE-Konfiguration speichern.</p>
        <p>Diese Anmeldung verwendet ein persönliches Bearer-Token. Ein automatischer MCP-OAuth-Login ist derzeit nicht eingerichtet.</p>
      </div>
    </div>
  );
};
