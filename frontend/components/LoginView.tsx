import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Loader2 } from 'lucide-react';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { DoctusIcon, DoctusWordmark } from './Logo';
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';

const MIN_PASSWORD_LENGTH = 12;

interface LoginViewProps {
  /** Wird nach erfolgreicher Anmeldung (inkl. ggf. erzwungenem Wechsel) aufgerufen. */
  onAuthenticated?: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onAuthenticated }) => {
  const { t } = useLanguage();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newPasswordRepeat, setNewPasswordRepeat] = useState('');
  // Nach einem Login mit must_change_password ist die Session bereits gültig — der
  // Wechsel ist deshalb ein zweiter Schritt in derselben Ansicht, kein eigener Screen.
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const res = await api.login(username, password);
      if (res.data?.must_change_password) {
        setMustChangePassword(true);
      } else if (onAuthenticated) {
        onAuthenticated();
      } else {
        window.location.reload();
      }
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 401) setError(t('loginView.invalidCredentials'));
      else if (status === 423) {
        // Restzeit steht im Retry-After-Header (Sekunden). Sie kommt bewusst von
        // dort und nicht aus dem detail-Text: der ist serverseitig deutsch, die
        // Oberfläche kann englisch sein.
        const retryAfter = Number(err?.response?.headers?.['retry-after']);
        setError(retryAfter > 0
          ? t('loginView.lockedFor', { minutes: String(Math.max(1, Math.ceil(retryAfter / 60))) })
          : t('loginView.locked'));
      }
      else setError(t('loginView.genericError'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(t('loginView.passwordTooShort'));
      return;
    }
    if (newPassword !== newPasswordRepeat) {
      setError(t('loginView.passwordsDoNotMatch'));
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await api.changePassword(password, newPassword);
      if (onAuthenticated) onAuthenticated();
      else window.location.reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('loginView.genericError'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const inputClass = "w-full h-11 rounded-md bg-ds-zinc-950 border-ds-zinc-700 text-ds-zinc-100 placeholder:text-ds-zinc-600 focus-visible:ring-2 focus-visible:ring-ds-zinc-400 focus-visible:border-ds-zinc-400";

  return (
    <div className="min-h-screen w-screen grid lg:grid-cols-[1.15fr_0.85fr] bg-ds-zinc-950 text-ds-zinc-200 font-sans overflow-hidden">
      <section className="hidden lg:flex relative flex-col justify-between border-r border-ds-zinc-800 p-12 doctus-canvas overflow-hidden">
        <div className="absolute left-0 top-0 h-full w-2 doctus-brand-gradient" />
        <div className="flex items-center gap-3">
          <DoctusIcon className="h-10 w-10" />
          <DoctusWordmark className="h-9 w-32" theme="dark" />
        </div>
        <div className="max-w-2xl">
          <p className="doctus-kicker text-ds-zinc-400 mb-5">{t('loginView.heroKicker')}</p>
          <h1 className="font-heading text-6xl xl:text-7xl font-semibold leading-[0.95] tracking-[-0.055em] text-ds-zinc-100">
            {t('loginView.heroHeadline')}
          </h1>
          <div className="mt-10 grid grid-cols-3 border-y border-ds-zinc-800 py-5 text-ds-zinc-400">
            <span className="doctus-kicker">{t('loginView.heroTraceWord')}</span>
            <span className="doctus-kicker">{t('loginView.heroExplainWord')}</span>
            <span className="doctus-kicker">{t('loginView.heroModernizeWord')}</span>
          </div>
        </div>
        <div aria-hidden="true" />
      </section>

      <section className="relative flex items-center justify-center p-6 sm:p-12 bg-ds-zinc-900">
      <div className="absolute inset-x-0 top-0 h-1 doctus-brand-gradient lg:hidden" />
      <div className="w-full max-w-[420px] z-10">

        {/* Login Card */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.05, ease: "easeOut" }}
          className="relative border-t-2 border-ds-zinc-700 bg-ds-zinc-950 p-7 sm:p-9 space-y-7 shadow-[10px_10px_0_rgb(var(--ds-neutral-800))]"
        >
          <div className="flex items-center justify-between lg:hidden select-none">
            <div className="flex items-center gap-3">
              <DoctusIcon className="h-9 w-9" />
              <DoctusWordmark className="h-8 w-28" theme="dark" />
            </div>
          </div>

          <div className="space-y-2 border-b border-ds-zinc-800 pb-6">
            <h2 className="text-3xl font-heading font-semibold text-ds-zinc-100 tracking-[-0.035em]">
              {mustChangePassword ? t('loginView.changeTitle') : t('loginView.title')}
            </h2>
            <p className="text-sm text-ds-zinc-500">
              {mustChangePassword ? t('loginView.changeHint') : t('loginView.description')}
            </p>
          </div>

          {mustChangePassword ? (
            <form className="space-y-3" onSubmit={handleChangePassword}>
              <div className="space-y-1.5">
                <label htmlFor="new-password" className="text-[11px] text-ds-zinc-400">{t('loginView.newPasswordLabel')}</label>
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className={inputClass}
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="new-password-repeat" className="text-[11px] text-ds-zinc-400">{t('loginView.newPasswordRepeatLabel')}</label>
                <Input
                  id="new-password-repeat"
                  type="password"
                  autoComplete="new-password"
                  value={newPasswordRepeat}
                  onChange={(e) => setNewPasswordRepeat(e.target.value)}
                  className={inputClass}
                />
              </div>

              {error && <p role="alert" className="text-[11px] text-ds-red-400">{error}</p>}

              <Button
                type="submit"
                disabled={isSubmitting}
                className={cn(
                  "w-full h-11 rounded-md doctus-brand-gradient text-ds-white font-bold border-0 transition-colors duration-150 flex items-center justify-center gap-2 cursor-pointer",
                  "active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
                )}
              >
                {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                <span>{t('loginView.changeSubmit')}</span>
              </Button>
            </form>
          ) : (
            <form className="space-y-3" onSubmit={handleLogin}>
              <div className="space-y-1.5">
                <label htmlFor="username" className="text-[11px] text-ds-zinc-400">{t('loginView.usernameLabel')}</label>
                <Input
                  id="username"
                  type="text"
                  autoComplete="username"
                  autoFocus
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className={inputClass}
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="password" className="text-[11px] text-ds-zinc-400">{t('loginView.passwordLabel')}</label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputClass}
                />
              </div>

              {error && <p role="alert" className="text-[11px] text-ds-red-400">{error}</p>}

              <Button
                type="submit"
                disabled={isSubmitting || !username || !password}
                className={cn(
                  "w-full h-11 rounded-md doctus-brand-gradient text-ds-white font-bold border-0 transition-colors duration-150 flex items-center justify-center gap-2 cursor-pointer",
                  "active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
                )}
              >
                {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                <span>{isSubmitting ? t('loginView.submitting') : t('loginView.submit')}</span>
                {!isSubmitting && <ArrowRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-1" />}
              </Button>
            </form>
          )}
        </motion.div>

      </div>
      </section>
    </div>
  );
};
