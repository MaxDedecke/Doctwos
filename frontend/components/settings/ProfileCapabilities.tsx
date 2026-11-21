"use client";
import { api } from '@/app/services/api';
import type { ShowToast } from '@/components/Toast';
import { badgeClass } from '@/components/settings/settingsStyles';
import { Button } from '@/components/ui/button';
import { profileFromApi, type LlmProfile, type ProfileCapabilities as Capabilities } from '@/hooks/useAiSettings';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Check, Loader2, ScanSearch, X } from 'lucide-react';
import { useState } from 'react';

const SHOWN: Array<keyof Capabilities> = ['tools', 'tool_arguments', 'tool_roundtrip', 'streaming', 'reasoning', 'reasoning_summary'];

/** Geprüfte Fähigkeiten eines KI-Profils und die Prüfung selbst (nur Admins sehen die KI-Einstellungen). */
export function ProfileCapabilities({ profile, onChecked, showToast }: {
  profile: LlmProfile;
  onChecked: (profile: LlmProfile) => void;
  showToast: ShowToast;
}) {
  const { t, language } = useLanguage();
  const [checking, setChecking] = useState(false);
  const capabilities = profile.capabilities;

  const check = async () => {
    setChecking(true);
    try {
      const response = await api.checkAiProfileCapabilities(Number(profile.id));
      const checked = profileFromApi(response.data);
      onChecked(checked);
      if (checked.capabilities?.error) showToast(t('settings.profilesTab.capabilities.checkFailedToast'), 'error');
      else showToast(t('settings.profilesTab.capabilities.checkedToast'), 'success');
    } catch (error) {
      showToast(t('settings.profilesTab.capabilities.checkFailedToast'), 'error', error);
    } finally {
      setChecking(false);
    }
  };

  const checkedAt = capabilities?.checked_at ? new Date(capabilities.checked_at).toLocaleString(language) : null;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[0.6875rem]" aria-label={t('settings.profilesTab.capabilities.title')}>
      {!capabilities && <span className="text-ds-zinc-500">{t('settings.profilesTab.capabilities.unchecked')}</span>}
      {capabilities?.error && <span className="text-ds-amber-600">{t('settings.profilesTab.capabilities.failed', { error: capabilities.error })}</span>}
      {capabilities && !capabilities.error && SHOWN.filter(key => typeof capabilities[key] === 'boolean').map(key => (
        <span key={key} className={cn(badgeClass(capabilities[key] ? 'success' : 'neutral'), 'inline-flex items-center gap-1')}>
          {capabilities[key] ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
          {t(`settings.profilesTab.capabilities.${key}`)}
        </span>
      ))}
      {capabilities?.tools === false && <span className="w-full text-ds-amber-600">{t('settings.profilesTab.capabilities.noTools')}</span>}
      {checkedAt && <span className="text-ds-zinc-500">{t('settings.profilesTab.capabilities.checked', { date: checkedAt })}</span>}
      <Button variant="ghost" size="sm" onClick={check} disabled={checking} className="h-6 px-2 text-[0.6875rem]">
        {checking ? <Loader2 className="w-3 h-3 animate-spin" /> : <ScanSearch className="w-3 h-3" />}
        {t(checking ? 'settings.profilesTab.capabilities.checking' : 'settings.profilesTab.capabilities.check')}
      </Button>
    </div>
  );
}
