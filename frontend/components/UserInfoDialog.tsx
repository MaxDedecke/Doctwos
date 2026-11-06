import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import Image from 'next/image';
import type { ReactNode } from 'react';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import type { User } from '@/types/domain';

interface Props {
  user: Partial<User> | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-3 py-2 text-xs">
    <dt className="text-muted-foreground">{label}</dt>
    <dd className="min-w-0 break-words font-medium">{children}</dd>
  </div>;
}

/** Benutzerinfo aus der Sidebar: wer angemeldet ist, mit welcher Rolle, über welches Verfahren und in welchen Teams. */
export function UserInfoDialog({ user, open, onOpenChange }: Props) {
  const { t, language } = useLanguage();
  const formatDate = (value?: string | null) => {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null
      : new Intl.DateTimeFormat(language === 'en' ? 'en-GB' : 'de-DE', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  };
  const notSet = <span className="font-normal text-muted-foreground">{t('sidebar.userInfo.notSet')}</span>;
  const displayName = user?.name || user?.username || t('sidebar.defaultUser');
  const isAdmin = user?.is_admin || user?.role === 'superuser' || user?.role === 'admin';
  const teams = user?.teams ?? [];

  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/50 backdrop-blur-sm" />
      <Dialog.Content data-testid="user-info-dialog"
        className="fixed left-1/2 top-1/2 z-[111] w-[calc(100%_-_2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-background p-5 text-foreground shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="h-12 w-12 shrink-0 overflow-hidden rounded-full border border-border">
            <Image src="/avatars/demo-employee.png" alt={t('chatView.userAvatarAlt')} width={48} height={48} unoptimized className="h-full w-full object-cover" />
          </div>
          <div className="min-w-0 flex-1">
            <Dialog.Title className="truncate text-base font-semibold">{displayName}</Dialog.Title>
            <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">{t('sidebar.userInfo.description')}</Dialog.Description>
          </div>
          <Dialog.Close aria-label={t('sidebar.userInfo.close')} className="shrink-0 rounded-md p-1.5 hover:bg-muted">
            <X className="h-4 w-4" />
          </Dialog.Close>
        </div>

        <dl className="mt-4 divide-y divide-border border-y border-border">
          <Row label={t('sidebar.userInfo.username')}>{user?.username || notSet}</Row>
          <Row label={t('sidebar.userInfo.email')}>{user?.email || notSet}</Row>
          <Row label={t('sidebar.userInfo.role')}>
            <span className={isAdmin ? 'rounded bg-primary/15 px-1.5 py-0.5 text-primary' : ''}>
              {t(isAdmin ? 'sidebar.userInfo.roleAdmin' : 'sidebar.userInfo.roleUser')}
            </span>
          </Row>
          <Row label={t('sidebar.userInfo.signIn')}>
            {user?.auth_provider ? t(user.auth_provider === 'oidc' ? 'sidebar.userInfo.signInOidc' : 'sidebar.userInfo.signInLocal') : notSet}
          </Row>
          <Row label={t('sidebar.userInfo.teams')}>
            {teams.length ? <span className="flex flex-wrap gap-1">
              {teams.map(team => <span key={team.id} className="rounded-full border border-border px-2 py-0.5 font-normal">{team.name}</span>)}
            </span> : notSet}
          </Row>
          <Row label={t('sidebar.userInfo.lastLogin')}>{formatDate(user?.last_login_at) ?? notSet}</Row>
          <Row label={t('sidebar.userInfo.memberSince')}>{formatDate(user?.created_at) ?? notSet}</Row>
        </dl>

        <div className="mt-4 flex justify-end">
          <Dialog.Close className="rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90">
            {t('sidebar.userInfo.close')}
          </Dialog.Close>
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
