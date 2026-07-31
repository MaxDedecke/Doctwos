"use client";

import React from 'react';
import { cn } from "@/lib/utils";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Erster aus SettingsModal herausgelöster Tab (docs/TECH_DEBT_CLEANUP_PLAN.md §5,
// Schritt 2). Konsumiert seinen Zustand direkt über useSettings() — dank Schritt 1
// müssen dafür keine Props durch SettingsModal weitergereicht werden. Muster für
// die übrigen Tabs.
export const EditorSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const {
    theme,
    editorFontSize,
    setEditorFontSize,
    editorFontFamily,
    setEditorFontFamily,
    editorMinimap,
    setEditorMinimap,
  } = useSettings();

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      <div className="space-y-3">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>{t('settings.editorTab.title')}</h4>
        <div className={cn(
          "space-y-4 border rounded-lg p-4 transition-colors",
          theme === 'dark' ? "bg-zinc-950/40 border-zinc-800" : "bg-zinc-50 border-zinc-200"
        )}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.editorTab.fontSizeLabel')}</label>
              <Select
                value={editorFontSize.toString()}
                onValueChange={val => setEditorFontSize(parseInt(val))}
              >
                <SelectTrigger className={cn(
                  "w-full h-8 text-xs focus:ring-0",
                  theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-350" : "bg-white border-zinc-200 text-zinc-800"
                )}>
                  <SelectValue placeholder={t('settings.editorTab.fontSizePlaceholder')} />
                </SelectTrigger>
                <SelectContent className={theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-200" : "bg-white border-zinc-200 text-zinc-800"}>
                  {['12', '13', '14', '15', '16', '18'].map(size => (
                    <SelectItem key={size} value={size}>{size}px</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.editorTab.fontFamilyLabel')}</label>
              <Select value={editorFontFamily} onValueChange={setEditorFontFamily}>
                <SelectTrigger className={cn(
                  "w-full h-8 text-xs focus:ring-0",
                  theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-350" : "bg-white border-zinc-200 text-zinc-800"
                )}>
                  <SelectValue placeholder={t('settings.editorTab.fontFamilyPlaceholder')} />
                </SelectTrigger>
                <SelectContent className={theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-200" : "bg-white border-zinc-200 text-zinc-800"}>
                  <SelectItem value="'JetBrains Mono', monospace">JetBrains Mono</SelectItem>
                  <SelectItem value="'Fira Code', monospace">Fira Code</SelectItem>
                  <SelectItem value="monospace">Courier New</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center justify-between p-1 pt-2 border-t border-zinc-800/40">
            <div className="space-y-0.5">
              <span className={cn("block text-xs font-semibold", theme === 'dark' ? "text-zinc-200" : "text-zinc-850")}>{t('settings.editorTab.minimapLabel')}</span>
              <span className="block text-[10px] text-zinc-500">{t('settings.editorTab.minimapDesc')}</span>
            </div>
            <button
              type="button"
              onClick={() => setEditorMinimap(!editorMinimap)}
              className={cn(
                "w-9 h-5 rounded-full p-0.5 transition-colors duration-250 focus:outline-none relative",
                editorMinimap ? "bg-indigo-650" : "bg-zinc-800"
              )}
            >
              <div className={cn(
                "w-4 h-4 rounded-full bg-white transition-transform duration-250 shadow-md",
                editorMinimap ? "translate-x-4" : "translate-x-0"
              )} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
