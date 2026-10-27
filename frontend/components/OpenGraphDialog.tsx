"use client";

import * as Dialog from '@radix-ui/react-dialog';
import { useRef } from 'react';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';

interface OpenGraphDialogProps {
  isOpen: boolean;
  theme: string;
  onClose: () => void;
  onNewSession: () => void;
  onStayInSession: () => void;
}

export function OpenGraphDialog({ isOpen, theme, onClose, onNewSession, onStayInSession }: OpenGraphDialogProps) {
  const { t } = useLanguage();
  const cancelRef = useRef<HTMLButtonElement>(null);

  return (
    <Dialog.Root open={isOpen} onOpenChange={open => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/80 backdrop-blur-sm" />
        <Dialog.Content onOpenAutoFocus={event => {
          event.preventDefault();
          cancelRef.current?.focus();
        }} className={cn(
          'fixed left-1/2 top-1/2 z-[111] w-[calc(100%_-_2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-2xl',
          theme === 'dark'
            ? 'bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-100'
            : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-950'
        )}>
          <Dialog.Title className="text-sm font-bold">{t('openGraphDialog.title')}</Dialog.Title>
          <Dialog.Description className={cn('mt-2 text-sm leading-relaxed', theme === 'dark' ? 'text-ds-zinc-400' : 'text-ds-zinc-600')}>
            {t('openGraphDialog.description')}
          </Dialog.Description>
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onNewSession}>{t('openGraphDialog.newSession')}</Button>
            <Dialog.Close asChild>
              <Button ref={cancelRef} variant="ghost" size="sm">{t('openGraphDialog.cancel')}</Button>
            </Dialog.Close>
            <Button size="sm" onClick={onStayInSession} className="bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-550">{t('openGraphDialog.stayInSession')}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
