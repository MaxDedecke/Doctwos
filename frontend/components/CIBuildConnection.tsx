"use client";

import { useState } from 'react';
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';

type Connection = Awaited<ReturnType<typeof api.getCITokens>>['data'];

export function CIBuildConnection({ projectId, theme }: { projectId: number; theme: string }) {
  const { t } = useLanguage();
  const [data, setData] = useState<Connection | null>(null);
  const [source, setSource] = useState('');
  const [name, setName] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const response = await api.getCITokens(projectId);
      setData(response.data);
      if (response.data.sources.length === 1) setSource(String(response.data.sources[0].id));
    } catch { setError(t('ciBuild.connectionFailed')); }
  };

  const create = async () => {
    setBusy(true);
    setSecret('');
    setError('');
    try {
      const response = await api.createCIToken(projectId, { source_id: Number(source), name });
      setSecret(response.data.token);
      await load();
    } catch { setError(t('ciBuild.connectionFailed')); }
    finally { setBusy(false); }
  };

  const revoke = async (id: number) => {
    setSecret('');
    setBusy(true);
    setError('');
    try {
      await api.revokeCIToken(projectId, id);
      await load();
    } catch { setError(t('ciBuild.connectionFailed')); }
    finally { setBusy(false); }
  };

  return (
    <details className="mb-3 rounded border border-ds-zinc-500/30 p-2 text-xs" onToggle={event => {
      if (event.currentTarget.open && !data) void load();
      if (!event.currentTarget.open) setSecret('');
    }}>
      <summary className="cursor-pointer text-ds-indigo-400">{t('ciBuild.connection')}</summary>
      {error && <p role="alert" className="mt-2 text-ds-red-500">{error}</p>}
      {data && !data.can_manage && <p className="mt-2">{t('ciBuild.adminRequired')}</p>}
      {data?.can_manage && <div className="mt-3 space-y-2">
        <p>{t('ciBuild.setupHint')}</p>
        <label className="block">{t('ciBuild.source')}
          <select disabled={busy} className={`ml-2 rounded border border-ds-zinc-500 p-1 ${theme === 'dark' ? 'bg-ds-zinc-900' : 'bg-ds-white'}`} value={source} onChange={event => { setSource(event.target.value); setSecret(''); }}>
            <option value="">{t('ciBuild.selectSource')}</option>
            {data.sources.map(item => <option key={item.id} value={item.id}>{item.name} · {item.branch || '—'}</option>)}
          </select>
        </label>
        <label className="block">{t('ciBuild.tokenName')}<input className="ml-2 rounded border border-ds-zinc-500 bg-transparent p-1" value={name} disabled={busy} maxLength={100} onChange={event => setName(event.target.value)} /></label>
        <button type="button" disabled={busy || !source || !name.trim()} onClick={() => void create()} className="rounded bg-ds-indigo-600 px-2 py-1 text-ds-white disabled:opacity-50">{t('ciBuild.createToken')}</button>
        {secret && <label className="block text-ds-amber-500">{t('ciBuild.secretOnce')}<input className="mt-1 block w-full rounded border border-ds-zinc-500 bg-transparent p-2 font-mono" value={secret} readOnly onFocus={event => event.target.select()} /></label>}
        {data.tokens.map(token => <div key={token.id} className="flex flex-wrap items-center gap-2 border-t border-ds-zinc-500/30 pt-2">
          <span>{token.name} · {token.prefix} · {token.expires_at}</span>
          {token.revoked_at ? <span>{t('ciBuild.revoked')}</span> : <button type="button" disabled={busy} onClick={() => void revoke(token.id)} className="text-ds-red-500">{t('ciBuild.revoke')}</button>}
        </div>)}
      </div>}
    </details>
  );
}
