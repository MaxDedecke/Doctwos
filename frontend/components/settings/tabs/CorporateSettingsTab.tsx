"use client";

import { AlertTriangle, ImageUp, Loader2, RotateCcw, Save, Trash2 } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';

import { api, type BrandingSettings } from '@/app/services/api';
import { CustomerLogo, hasCustomerIdentity } from '@/components/CustomerLogo';
import { CodenaLogo } from '@/components/Logo';
import { useSettings } from '@/components/settings/SettingsContext';
import {
  cardClass,
  helpTextClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
  sectionTitleClass,
  settingsRoot,
} from '@/components/settings/settingsStyles';
import { apiErrorDetail } from '@/lib/apiError';
import { DEFAULT_BRANDING, deriveAccentTokens, hexToRgb, setBranding, statusColorConflict, type Branding } from '@/lib/branding';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';

const CODENA_ACCENT = '#0064d2';
const EMPTY_FORM: Required<{ [K in keyof BrandingSettings]: string }> = {
  customer_name: '',
  accent_color: '',
  login_notice: '',
  imprint_url: '',
  privacy_url: '',
  support_url: '',
};

const toForm = (b: Branding) => ({
  customer_name: b.customer_name ?? '',
  accent_color: b.accent_color ?? '',
  login_notice: b.login_notice ?? '',
  imprint_url: b.imprint_url ?? '',
  privacy_url: b.privacy_url ?? '',
  support_url: b.support_url ?? '',
});

const rgb = (channels: string) => `rgb(${channels})`;

/** Akzentfarbe als Muster in beiden Themes, so wie Codena sie nach der Kontrastprüfung verwendet. */
function AccentPreview({ color }: { color: string }) {
  const { t } = useLanguage();
  const tokens = deriveAccentTokens(color);
  if (!tokens) return null;
  const surfaces = [
    { key: 'light', bg: '#fafbf7', text: '#102220', vars: tokens.light },
    { key: 'dark', bg: '#0e1e1e', text: '#eceee8', vars: { ...tokens.light, ...tokens.dark } },
  ];
  return (
    <div className="grid grid-cols-2 gap-2">
      {surfaces.map((s) => (
        <div key={s.key} className="rounded-lg border border-ds-zinc-500/20 p-3 space-y-2" style={{ background: s.bg, color: s.text }}>
          <span className="codena-kicker opacity-70">{t(`settings.corporateTab.preview.${s.key}`)}</span>
          <div className="flex items-center gap-2">
            <span className="h-7 px-3 rounded-md text-[0.6875rem] font-bold flex items-center" style={{ background: rgb(s.vars['--ds-accent']), color: rgb(s.vars['--ds-on-accent']) }}>
              {t('settings.corporateTab.preview.button')}
            </span>
            <span className="text-[0.6875rem] font-semibold underline underline-offset-2" style={{ color: rgb(s.vars['--ds-accent']) }}>
              {t('settings.corporateTab.preview.link')}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function LogoSlot({
  variant,
  url,
  draft,
  busy,
  onUpload,
  onRemove,
}: {
  variant: 'light' | 'dark';
  url: string | null;
  draft: Branding;
  busy: boolean;
  onUpload: (file: File) => void;
  onRemove: () => void;
}) {
  const { t } = useLanguage();
  const { theme } = useSettings();
  const input = useRef<HTMLInputElement | null>(null);
  return (
    <div className="space-y-2">
      <span className={sectionTitleClass(theme)}>{t(`settings.corporateTab.logo.${variant}`)}</span>
      <div className={cn('h-16 rounded-lg border flex items-center px-4', variant === 'dark' ? 'bg-[#0b1210] border-ds-zinc-800' : 'bg-ds-white border-ds-zinc-200')}>
        {url ? (
          <CustomerLogo surface={variant} branding={{ ...draft, customer_name: null }} boxClassName="h-9 max-w-[200px]" />
        ) : (
          <span className={cn(helpTextClass, 'italic')}>{t('settings.corporateTab.logo.none')}</span>
        )}
      </div>
      <div className="flex gap-2">
        <input
          ref={input}
          type="file"
          accept="image/png"
          className="hidden"
          data-testid={`branding-logo-input-${variant}`}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onUpload(file);
            e.target.value = '';
          }}
        />
        <button type="button" disabled={busy} onClick={() => input.current?.click()} className={cn(secondaryButtonClass(theme), 'border')}>
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <ImageUp className="w-3 h-3" />}
          {t('settings.corporateTab.logo.upload')}
        </button>
        {url && (
          <button type="button" disabled={busy} onClick={onRemove} className={cn(secondaryButtonClass(theme), 'border')}>
            <Trash2 className="w-3 h-3" />
            {t('settings.corporateTab.logo.remove')}
          </button>
        )}
      </div>
    </div>
  );
}

export const CorporateSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const { theme, showToast } = useSettings();
  const [saved, setSaved] = useState<Branding | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [logoBusy, setLogoBusy] = useState<'light' | 'dark' | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getBranding()
      .then((res) => {
        if (cancelled) return;
        setSaved(res.data);
        setForm(toForm(res.data));
      })
      .catch((err) => {
        if (cancelled) return;
        setSaved(DEFAULT_BRANDING);
        showToast(apiErrorDetail(err) || t('settings.corporateTab.loadError'), 'error', err);
      });
    return () => { cancelled = true; };
    // Nur beim Öffnen des Tabs laden; ein späteres Neuladen würde ungespeicherte Eingaben überschreiben.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const apply = (next: Branding, message: string) => {
    setSaved(next);
    setBranding(next);
    showToast(message, 'success');
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.saveBranding(form);
      setForm(toForm(res.data));
      apply(res.data, t('settings.corporateTab.saved'));
    } catch (err) {
      showToast(apiErrorDetail(err) || t('settings.corporateTab.saveError'), 'error', err);
    } finally {
      setSaving(false);
    }
  };

  const uploadLogo = async (variant: 'light' | 'dark', file: File) => {
    setLogoBusy(variant);
    try {
      apply((await api.uploadBrandingLogo(variant, file)).data, t('settings.corporateTab.logo.uploaded'));
    } catch (err) {
      showToast(apiErrorDetail(err) || t('settings.corporateTab.saveError'), 'error', err);
    } finally {
      setLogoBusy(null);
    }
  };

  const removeLogo = async (variant: 'light' | 'dark') => {
    setLogoBusy(variant);
    try {
      apply((await api.deleteBrandingLogo(variant)).data, t('settings.corporateTab.logo.removed'));
    } catch (err) {
      showToast(apiErrorDetail(err) || t('settings.corporateTab.saveError'), 'error', err);
    } finally {
      setLogoBusy(null);
    }
  };

  const resetAll = async () => {
    if (!window.confirm(t('settings.corporateTab.resetConfirm'))) return;
    try {
      const res = await api.resetBranding();
      setForm(toForm(res.data));
      apply(res.data, t('settings.corporateTab.resetDone'));
    } catch (err) {
      showToast(apiErrorDetail(err) || t('settings.corporateTab.saveError'), 'error', err);
    }
  };

  if (!saved) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-5 h-5 animate-spin text-ds-zinc-500" />
      </div>
    );
  }

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const draft: Branding = { ...saved, customer_name: form.customer_name.trim() || null };
  const validColor = /^#[0-9a-f]{6}$/i.test(form.accent_color);
  const conflict = validColor ? statusColorConflict(form.accent_color) : null;
  const tokens = validColor ? deriveAccentTokens(form.accent_color) : null;
  const adjusted = tokens !== null && tokens.light['--ds-accent'] !== hexToRgb(form.accent_color)?.join(' ');
  const card = cn(cardClass(theme), 'p-4 space-y-4');
  const label = (key: string) => <span className={sectionTitleClass(theme)}>{t(key)}</span>;

  return (
    <form onSubmit={save} className={settingsRoot}>
      <p className={helpTextClass}>{t('settings.corporateTab.intro')}</p>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="space-y-4 min-w-0">
          <section className={card}>
            <h4 className={sectionTitleClass(theme)}>{t('settings.corporateTab.identity')}</h4>
            <label className="block space-y-1.5">
              {label('settings.corporateTab.customerName')}
              <input className={inputClass(theme)} maxLength={60} value={form.customer_name} onChange={set('customer_name')} />
              <span className={helpTextClass}>{t('settings.corporateTab.customerNameHelp')}</span>
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              {(['light', 'dark'] as const).map((variant) => (
                <LogoSlot
                  key={variant}
                  variant={variant}
                  url={variant === 'light' ? saved.logo_light_url : saved.logo_dark_url}
                  draft={draft}
                  busy={logoBusy === variant}
                  onUpload={(file) => uploadLogo(variant, file)}
                  onRemove={() => removeLogo(variant)}
                />
              ))}
            </div>
            <p className={helpTextClass}>{t('settings.corporateTab.logo.help')}</p>
          </section>

          <section className={card}>
            <h4 className={sectionTitleClass(theme)}>{t('settings.corporateTab.accent')}</h4>
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="color"
                aria-label={t('settings.corporateTab.accent')}
                value={validColor ? form.accent_color : CODENA_ACCENT}
                onChange={set('accent_color')}
                className="h-9 w-12 rounded-lg border border-ds-zinc-500/30 bg-transparent cursor-pointer"
              />
              <input
                className={cn(inputClass(theme), 'w-32 font-mono')}
                placeholder={CODENA_ACCENT}
                maxLength={7}
                value={form.accent_color}
                onChange={set('accent_color')}
              />
              {form.accent_color && (
                <button type="button" onClick={() => setForm((f) => ({ ...f, accent_color: '' }))} className={cn(secondaryButtonClass(theme), 'border')}>
                  <RotateCcw className="w-3 h-3" />
                  {t('settings.corporateTab.accentReset')}
                </button>
              )}
            </div>
            <AccentPreview color={validColor ? form.accent_color : CODENA_ACCENT} />
            <p className={helpTextClass}>
              {t('settings.corporateTab.accentHelp')}
              {adjusted && ` ${t('settings.corporateTab.accentAdjusted')}`}
            </p>
            {conflict && (
              <p className="flex items-start gap-1.5 text-[0.6875rem] text-ds-amber-600 dark:text-ds-amber-400">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
                {t(`settings.corporateTab.accentConflict.${conflict}`)}
              </p>
            )}
          </section>

          <section className={card}>
            <h4 className={sectionTitleClass(theme)}>{t('settings.corporateTab.loginPage')}</h4>
            <label className="block space-y-1.5">
              {label('settings.corporateTab.notice')}
              <textarea
                className={cn(inputClass(theme), 'h-20 py-2 resize-none font-normal')}
                maxLength={280}
                value={form.login_notice}
                onChange={set('login_notice')}
                placeholder={t('settings.corporateTab.noticePlaceholder')}
              />
              <span className={helpTextClass}>{form.login_notice.length} / 280</span>
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              {(['imprint_url', 'privacy_url', 'support_url'] as const).map((key) => (
                <label key={key} className="block space-y-1.5">
                  {label(`settings.corporateTab.links.${key}`)}
                  <input className={inputClass(theme)} maxLength={500} value={form[key]} onChange={set(key)} placeholder={key === 'support_url' ? 'https:// · mailto:' : 'https://'} />
                </label>
              ))}
            </div>
          </section>
        </div>

        <aside className="space-y-3 min-w-0">
          <span className={sectionTitleClass(theme)}>{t('settings.corporateTab.preview.title')}</span>
          <div className="codena-brand-panel rounded-lg px-5 py-6 flex items-center gap-4 overflow-hidden">
            <CodenaLogo className="text-[1.4rem]" />
            {hasCustomerIdentity(draft) && (
              <>
                <span className="h-6 w-px bg-[rgb(236_238_232/0.2)]" />
                <CustomerLogo surface="dark" branding={draft} boxClassName="h-6 max-w-[120px]" className="text-[rgb(236_238_232/0.8)]" />
              </>
            )}
          </div>
          <p className={helpTextClass}>{t('settings.corporateTab.preview.help')}</p>
        </aside>
      </div>

      <div className="flex flex-wrap justify-between gap-2">
        <button type="button" onClick={resetAll} className={cn(secondaryButtonClass(theme), 'border h-9')}>
          <RotateCcw className="w-3 h-3" />
          {t('settings.corporateTab.resetAll')}
        </button>
        <button type="submit" disabled={saving} className={primaryButtonClass}>
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          {t('settings.corporateTab.save')}
        </button>
      </div>
    </form>
  );
};
