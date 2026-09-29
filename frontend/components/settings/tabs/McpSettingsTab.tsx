"use client";

import React, { useEffect, useState } from 'react';
import { Copy, KeyRound, Loader2, Plus, Trash2 } from 'lucide-react';

import { api, API_URL } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cardClass, dangerIconButtonClass, emptyStateClass, helpTextClass, inputClass, primaryButtonClass, sectionTitleClass, secondaryButtonClass, settingsRoot, strongTextClass } from '@/components/settings/settingsStyles';
import { cn, copyToClipboard } from '@/lib/utils';

import { McpAuditLog } from './McpAuditLog';

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
  const [rows, setRows] = useState<TokenRow[]>([]);
  const [name, setName] = useState('Meine IDE');
  const [days, setDays] = useState(30);
  const [issued, setIssued] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  // Einmal pro Laden gesetzt, damit das Ablaufdatum beim Rendern keinen impuren Aufruf braucht.
  const [now, setNow] = useState(0);

  useEffect(() => {
    let active = true;
    api.getMcpTokens()
      .then((response) => { if (active) { setRows(response.data); setNow(Date.now()); } })
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
    <div className={settingsRoot}>
      <section className="space-y-1.5">
        <h4 className={cn(sectionTitleClass(theme), 'flex items-center gap-1.5')}><KeyRound className="w-3.5 h-3.5 text-ds-indigo-500" /> Doctus in der IDE</h4>
        <p className={helpTextClass}>Lesender MCP-Zugang für Code- und Wissenssuche. Jeder Aufruf verwendet deine aktuellen Projektberechtigungen.</p>
        <p className={helpTextClass}>Server-Adresse: <code className={cn('font-mono break-all', strongTextClass(theme))}>{API_URL}/mcp</code></p>
      </section>

      <form onSubmit={create} className={cn(cardClass(theme), 'p-4 space-y-3')}>
        <h4 className={sectionTitleClass(theme)}>Persönliches Token erstellen</h4>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1.5 flex-1 min-w-[12rem]">
            <span className={sectionTitleClass(theme)}>Name</span>
            <input className={inputClass(theme)} value={name} maxLength={100} onChange={(event) => setName(event.target.value)} required />
          </label>
          <div className="space-y-1.5">
            <span className={sectionTitleClass(theme)}>Gültigkeit</span>
            <Select value={String(days)} onValueChange={(value) => setDays(Number(value))}>
              <SelectTrigger aria-label="Gültigkeit" className="h-9 w-32 text-xs font-semibold"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="7">7 Tage</SelectItem><SelectItem value="30">30 Tage</SelectItem><SelectItem value="90">90 Tage</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={busy || !name.trim()} className={primaryButtonClass}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            <span>{busy ? 'Erstelle…' : 'Token erstellen'}</span>
          </Button>
        </div>
      </form>

      {issued && (
        <div className={cn('rounded-lg border p-4 space-y-2', dark ? 'border-ds-amber-700/60 bg-ds-amber-950/20' : 'border-ds-amber-400 bg-ds-amber-50')}>
          <div className={cn('text-xs font-bold', dark ? 'text-ds-amber-300' : 'text-ds-amber-900')}>Token jetzt kopieren – danach wird es nicht erneut angezeigt.</div>
          <code className={cn('block break-all rounded-lg border p-3 font-mono text-xs select-all', dark ? 'bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-200' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-900')}>{issued}</code>
          <Button type="button" variant="outline" size="sm" className={secondaryButtonClass(theme)} onClick={async () => { if (await copyToClipboard(issued)) showToast('Token kopiert', 'success'); }}><Copy className="h-3.5 w-3.5" /> Kopieren</Button>
        </div>
      )}

      <section className="space-y-2">
        <h4 className={sectionTitleClass(theme)}>Meine Tokens</h4>
        {loading ? (
          <div className="flex items-center justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-ds-zinc-500" /></div>
        ) : rows.length === 0 ? (
          <div className={emptyStateClass(theme)}>Noch keine Tokens vorhanden.</div>
        ) : (
          <div className="space-y-2">
            {rows.map((row) => {
              const expired = new Date(row.expires_at).getTime() <= now;
              return (
                <div key={row.id} className={cn(cardClass(theme), 'flex items-center justify-between gap-3 p-3')}>
                  <div className="min-w-0">
                    <div className={cn('text-xs truncate', strongTextClass(theme))}>{row.name} <span className="font-mono font-normal text-ds-zinc-500">{row.prefix}…</span></div>
                    <div className={cn(helpTextClass, 'mt-0.5')}>{row.revoked_at ? 'Widerrufen' : expired ? 'Abgelaufen' : `Gültig bis ${new Date(row.expires_at).toLocaleDateString()}`}</div>
                  </div>
                  {!row.revoked_at && !expired && (
                    <Button type="button" variant="ghost" size="icon" aria-label={`${row.name} widerrufen`} title="Token widerrufen" onClick={() => revoke(row.id)} className={dangerIconButtonClass}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className={cn(cardClass(theme), 'p-4 space-y-2')}>
        <h4 className={sectionTitleClass(theme)}>IDE verbinden</h4>
        <p className={helpTextClass}>In VS Code, Continue oder Cursor einen Streamable-HTTP-MCP-Server mit der Adresse oben einrichten. Als HTTP-Header <code className="font-mono">Authorization: Bearer &lt;Token&gt;</code> verwenden und das Token nur in der persönlichen IDE-Konfiguration speichern.</p>
        <p className={helpTextClass}>Diese Anmeldung verwendet ein persönliches Bearer-Token. Ein automatischer MCP-OAuth-Login ist derzeit nicht eingerichtet.</p>
      </section>

      <McpAuditLog />
    </div>
  );
};
