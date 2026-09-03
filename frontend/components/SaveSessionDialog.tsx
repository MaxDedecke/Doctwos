"use client";

import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/lib/i18n/LanguageContext';

interface SaveSessionDialogProps {
  isOpen: boolean;
  theme: string;
  onClose: () => void;
  onSave: (title: string) => Promise<void> | void;
}

// O-038: Namens-Dialog für "Sitzung ohne Chat-Nachricht speichern" -- der Nutzer
// vergibt hier den Titel, den POST /chat oben sonst aus der ersten Nachricht
// ableiten würde. Eigene, schlanke Modal-Struktur statt einer Dialog-Bibliothek
// (Regel 4: keine schweren SDKs), am Aufbau von SettingsModal.tsx orientiert.
export function SaveSessionDialog({ isOpen, theme, onClose, onSave }: SaveSessionDialogProps) {
  const { t } = useLanguage();
  const [title, setTitle] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset the form during render (guarded by a state comparison) rather than
  // in an effect, matching useWorkspaceLayout.ts's prevXxx idiom -- resetting
  // state is a React-to-React sync, not a side effect on an external system.
  const [prevIsOpen, setPrevIsOpen] = useState(isOpen);
  if (isOpen !== prevIsOpen) {
    setPrevIsOpen(isOpen);
    if (isOpen) {
      setTitle('');
      setIsSaving(false);
    }
  }

  useEffect(() => {
    if (isOpen) {
      // Autofocus needs a tick -- the input isn't in the DOM yet on the same
      // render that flips isOpen to true. Focusing a ref is an external-system
      // side effect, unlike the state reset above.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [isOpen]);

  const handleSave = async () => {
    const trimmed = title.trim();
    if (!trimmed || isSaving) return;
    setIsSaving(true);
    try {
      await onSave(trimmed);
      onClose();
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 bg-ds-black/80 backdrop-blur-sm z-[110] flex items-center justify-center p-4">
          <div className="absolute inset-0" onClick={onClose} />
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className={cn(
              "relative border rounded-lg w-full max-w-sm shadow-2xl p-5 space-y-4",
              theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800/80" : "bg-ds-white border-ds-zinc-200"
            )}
          >
            <div className="space-y-1">
              <h3 className={cn("text-sm font-bold flex items-center gap-2", theme === 'dark' ? "text-ds-zinc-100" : "text-ds-zinc-950")}>
                <Save className="w-4 h-4 text-ds-indigo-500" />
                {t('saveSessionDialog.title')}
              </h3>
              <p className="text-[11px] text-ds-zinc-500 leading-normal">
                {t('saveSessionDialog.description')}
              </p>
            </div>

            <input
              ref={inputRef}
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); }}
              placeholder={t('saveSessionDialog.namePlaceholder')}
              maxLength={200}
              className={cn(
                "w-full h-9 border rounded-md px-3 text-xs focus:outline-none transition-all font-sans",
                theme === 'dark'
                  ? "bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-200 placeholder-zinc-600 focus:border-ds-indigo-700"
                  : "bg-ds-zinc-50 border-ds-zinc-200 text-ds-zinc-800 placeholder-zinc-400 focus:border-ds-indigo-300"
              )}
            />

            <div className="flex items-center justify-end gap-2 pt-1">
              <Button
                type="button"
                variant="ghost"
                onClick={onClose}
                disabled={isSaving}
                className="h-8 px-3 text-xs font-semibold"
              >
                {t('saveSessionDialog.cancel')}
              </Button>
              <Button
                type="button"
                onClick={handleSave}
                disabled={!title.trim() || isSaving}
                className="h-8 px-4 text-xs font-semibold gap-1.5 bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-550"
              >
                {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {t('saveSessionDialog.save')}
              </Button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
