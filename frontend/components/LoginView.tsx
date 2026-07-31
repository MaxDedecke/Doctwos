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

  const inputClass = "w-full h-10 bg-ds-zinc-950/60 border-ds-zinc-800 text-ds-zinc-100 placeholder:text-ds-zinc-600 focus-visible:ring-ds-blue-500/40";

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-ds-zinc-950 text-ds-zinc-200 font-sans relative overflow-hidden">
      {/* Premium glowing background mesh gradients */}
      <div className="absolute top-[-20%] left-[-15%] w-[60%] h-[60%] rounded-full blur-[140px] bg-ds-blue-600/10 pointer-events-none z-0 animate-pulse [animation-duration:8000ms]" />
      <div className="absolute bottom-[-20%] right-[-15%] w-[60%] h-[60%] rounded-full blur-[140px] bg-ds-indigo-600/10 pointer-events-none z-0 animate-pulse [animation-duration:10000ms]" />
      <div className="absolute top-[40%] left-[35%] w-[30%] h-[30%] rounded-full blur-[160px] bg-ds-violet-600/5 pointer-events-none z-0" />

      {/* Animated subtle grid background */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:32px_32px] pointer-events-none z-0" />
      {/* Extra dot matrix pattern overlay */}
      <div className="absolute inset-0 bg-[radial-gradient(#ffffff03_1px,transparent_1px)] bg-[size:16px_16px] pointer-events-none z-0" />

      <div className="w-full max-w-[420px] z-10 px-6">

        {/* Login Card */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1, ease: "easeOut" }}
          className="relative group border border-ds-zinc-800/80 rounded-lg bg-ds-zinc-900/40 backdrop-blur-2xl shadow-2xl p-7 space-y-6 overflow-hidden"
        >
          {/* Top border ambient light beam effect */}
          <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-ds-zinc-700/50 to-transparent group-hover:via-ds-blue-500/30 transition-all duration-500" />

          <div className="flex flex-col items-center mb-2 select-none">
            <div className="relative flex items-center gap-3.5 justify-center">
              {/* Soft glowing aura behind the logo */}
              <div className="absolute inset-0 bg-ds-blue-500/20 rounded-full blur-xl scale-150 animate-pulse pointer-events-none" />
              <DoctusIcon className="h-10 w-10 relative z-10 filter drop-shadow-[0_0_15px_rgba(77,127,255,0.3)] hover:scale-105 transition-transform duration-300" />
              <DoctusWordmark className="h-8 w-24 relative z-10" theme="dark" />
            </div>
          </div>

          <div className="space-y-1 text-center">
            <h2 className="text-base font-heading font-semibold text-ds-zinc-100 tracking-tight">
              {mustChangePassword ? t('loginView.changeTitle') : t('loginView.title')}
            </h2>
            <p className="text-[11px] text-ds-zinc-500">
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
                  "w-full h-11 rounded-lg bg-gradient-to-r from-ds-blue-600 to-ds-indigo-600 hover:from-ds-blue-500 hover:to-ds-indigo-500 text-ds-white font-semibold shadow-lg shadow-ds-indigo-600/10 border-0 transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer",
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
                  "w-full h-11 rounded-lg bg-gradient-to-r from-ds-blue-600 to-ds-indigo-600 hover:from-ds-blue-500 hover:to-ds-indigo-500 text-ds-white font-semibold shadow-lg shadow-ds-indigo-600/10 border-0 transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer",
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

        {/* Footer info */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-center text-[10px] text-ds-zinc-600 mt-6 select-none"
        >
          {t('loginView.footer')}
        </motion.p>

      </div>
    </div>
  );
};
