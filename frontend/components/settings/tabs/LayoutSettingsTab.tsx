"use client";

import React from 'react';
import { Download } from 'lucide-react';
import { cn } from "@/lib/utils";
import { API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Aus SettingsModal herausgelöster 'layout'-Tab (docs/TECH_DEBT_CLEANUP_PLAN.md §5,
// Schritt 2). Die zuvor auf Modal-Ebene liegenden Handler handleThemeToggle und
// exportNeo4j wurden mit hierher gezogen — beide wurden nur von diesem Tab genutzt.
// Die Monaco-Editor-Optionen (vormals eigener 'editor'-Tab) sind mit hierher
// gezogen, da sie nur eine einzelne Einstellungsgruppe waren — ein eigener Tab
// dafür war unnötig.
export const LayoutSettingsTab: React.FC = () => {
  const { language, setLanguage, t } = useLanguage();
  const {
    theme,
    setTheme,
    showToast,
    selectedProject,
    workspaceSplit,
    setWorkspaceSplit,
    editorFontSize,
    setEditorFontSize,
    editorFontFamily,
    setEditorFontFamily,
    editorMinimap,
    setEditorMinimap,
  } = useSettings();

  const handleThemeToggle = (newTheme: string) => {
    setTheme(newTheme);
    localStorage.setItem('doctus-theme', newTheme);
    showToast(newTheme === 'dark' ? t('settings.toast.darkModeEnabled') : t('settings.toast.lightModeEnabled'), "success");
  };

  const exportNeo4j = async () => {
    const params = new URLSearchParams({ status: 'approved' });
    if (selectedProject?.id) params.set('project_id', String(selectedProject.id));
    try {
      const res = await fetch(`${API_URL}/graph/export/neo4j?${params}`);
      const data = await res.json();
      const blob = new Blob([data.cypher], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `knowledge_graph_${selectedProject?.name ?? 'all'}.cypher`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      showToast(t('settings.layoutTab.exportError'), 'error');
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Whitemode / Theme Switcher */}
      <div className="space-y-3">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>{t('settings.layoutTab.colorThemeTitle')}</h4>
        <div className={cn(
          "border rounded-lg p-4 transition-colors",
          theme === 'dark' ? "bg-ds-zinc-950/40 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
        )}>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className={cn("block text-xs font-semibold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-850")}>{t('settings.layoutTab.lightModeLabel')}</span>
              <span className="block text-[10px] text-ds-zinc-500">{t('settings.layoutTab.lightModeDesc')}</span>
            </div>
            <button
              type="button"
              id="theme-toggle-switch"
              onClick={() => handleThemeToggle(theme === 'dark' ? 'light' : 'dark')}
              className={cn(
                "w-9 h-5 rounded-full p-0.5 transition-colors duration-250 focus:outline-none relative",
                theme === 'light' ? "bg-ds-indigo-650" : "bg-ds-zinc-850"
              )}
            >
              <div className={cn(
                "w-4 h-4 rounded-full bg-ds-white transition-transform duration-250 shadow-md",
                theme === 'light' ? "translate-x-4" : "translate-x-0"
              )} />
            </button>
          </div>
        </div>
      </div>

      {/* Language Switcher */}
      <div className="space-y-3">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>{t('settings.layoutTab.languageTitle')}</h4>
        <div className={cn(
          "border rounded-lg p-4 transition-colors",
          theme === 'dark' ? "bg-ds-zinc-950/40 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
        )}>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className={cn("block text-xs font-semibold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-850")}>{t('settings.layoutTab.languageTitle')}</span>
              <span className="block text-[10px] text-ds-zinc-500">{t('settings.layoutTab.languageDesc')}</span>
            </div>
            <div className={cn(
              "flex items-center rounded-lg border p-0.5 text-[10px] font-semibold",
              theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200"
            )}>
              <button
                type="button"
                id="language-toggle-de"
                onClick={() => setLanguage('de')}
                className={cn(
                  "px-3 h-7 rounded-md transition-colors",
                  language === 'de'
                    ? "bg-ds-indigo-650 text-ds-white"
                    : (theme === 'dark' ? "text-ds-zinc-400 hover:text-ds-zinc-200" : "text-ds-zinc-500 hover:text-ds-zinc-800")
                )}
              >
                {t('settings.layoutTab.languageGerman')}
              </button>
              <button
                type="button"
                id="language-toggle-en"
                onClick={() => setLanguage('en')}
                className={cn(
                  "px-3 h-7 rounded-md transition-colors",
                  language === 'en'
                    ? "bg-ds-indigo-650 text-ds-white"
                    : (theme === 'dark' ? "text-ds-zinc-400 hover:text-ds-zinc-200" : "text-ds-zinc-500 hover:text-ds-zinc-800")
                )}
              >
                {t('settings.layoutTab.languageEnglish')}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>{t('settings.layoutTab.workspaceSplitTitle')}</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          {[
            { id: '40/60', label: t('settings.layoutTab.splits.narrowChat.label'), desc: t('settings.layoutTab.splits.narrowChat.desc') },
            { id: '45/55', label: t('settings.layoutTab.splits.standard.label'), desc: t('settings.layoutTab.splits.standard.desc') },
            { id: '50/50', label: t('settings.layoutTab.splits.even.label'), desc: t('settings.layoutTab.splits.even.desc') },
            { id: '60/40', label: t('settings.layoutTab.splits.wideChat.label'), desc: t('settings.layoutTab.splits.wideChat.desc') }
          ].map(layout => (
            <button
              key={layout.id}
              type="button"
              onClick={() => setWorkspaceSplit(layout.id)}
              className={cn(
                "p-3 rounded-lg border text-left space-y-1 transition-all",
                workspaceSplit === layout.id
                  ? (theme === 'dark' ? "border-ds-indigo-500/40 bg-ds-indigo-500/5" : "border-ds-indigo-400 bg-ds-indigo-50/40")
                  : (theme === 'dark' ? "border-ds-zinc-800/85 bg-ds-zinc-950/20 hover:border-ds-zinc-700/80" : "border-ds-zinc-200 bg-ds-zinc-50 hover:border-ds-zinc-300")
              )}
            >
              <span className={cn("block text-[11px] font-bold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")}>{layout.label}</span>
              <span className="block text-[9px] text-ds-zinc-500 leading-normal">{layout.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Monaco Editor Optionen (vormals eigener Editor-Tab) */}
      <div className="space-y-3">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>{t('settings.editorTab.title')}</h4>
        <div className={cn(
          "space-y-4 border rounded-lg p-4 transition-colors",
          theme === 'dark' ? "bg-ds-zinc-950/40 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
        )}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[9px] font-bold text-ds-zinc-500 uppercase px-0.5">{t('settings.editorTab.fontSizeLabel')}</label>
              <Select
                value={editorFontSize.toString()}
                onValueChange={val => setEditorFontSize(parseInt(val))}
              >
                <SelectTrigger className={cn(
                  "w-full h-8 text-xs focus:ring-0",
                  theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-350" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800"
                )}>
                  <SelectValue placeholder={t('settings.editorTab.fontSizePlaceholder')} />
                </SelectTrigger>
                <SelectContent className={theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800"}>
                  {['12', '13', '14', '15', '16', '18'].map(size => (
                    <SelectItem key={size} value={size}>{size}px</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <label className="text-[9px] font-bold text-ds-zinc-500 uppercase px-0.5">{t('settings.editorTab.fontFamilyLabel')}</label>
              <Select value={editorFontFamily} onValueChange={setEditorFontFamily}>
                <SelectTrigger className={cn(
                  "w-full h-8 text-xs focus:ring-0",
                  theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-350" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800"
                )}>
                  <SelectValue placeholder={t('settings.editorTab.fontFamilyPlaceholder')} />
                </SelectTrigger>
                <SelectContent className={theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800"}>
                  <SelectItem value="'JetBrains Mono', monospace">JetBrains Mono</SelectItem>
                  <SelectItem value="'Fira Code', monospace">Fira Code</SelectItem>
                  <SelectItem value="monospace">Courier New</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center justify-between p-1 pt-2 border-t border-ds-zinc-800/40">
            <div className="space-y-0.5">
              <span className={cn("block text-xs font-semibold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-850")}>{t('settings.editorTab.minimapLabel')}</span>
              <span className="block text-[10px] text-ds-zinc-500">{t('settings.editorTab.minimapDesc')}</span>
            </div>
            <button
              type="button"
              onClick={() => setEditorMinimap(!editorMinimap)}
              className={cn(
                "w-9 h-5 rounded-full p-0.5 transition-colors duration-250 focus:outline-none relative",
                editorMinimap ? "bg-ds-indigo-650" : "bg-ds-zinc-800"
              )}
            >
              <div className={cn(
                "w-4 h-4 rounded-full bg-ds-white transition-transform duration-250 shadow-md",
                editorMinimap ? "translate-x-4" : "translate-x-0"
              )} />
            </button>
          </div>
        </div>
      </div>

      {/* Wissensgraph Export */}
      <div className="space-y-3">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>
          {t('settings.layoutTab.graphExportTitle')}
        </h4>
        <div className={cn(
          "border rounded-lg p-4 transition-colors",
          theme === 'dark' ? "bg-ds-zinc-950/40 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
        )}>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className={cn("block text-xs font-semibold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-850")}>
                {t('settings.layoutTab.graphExportLabel')}
              </span>
              <span className="block text-[10px] text-ds-zinc-500 leading-normal">
                {t('settings.layoutTab.graphExportDesc')}
              </span>
            </div>
            <Button
              type="button"
              onClick={exportNeo4j}
              className={cn(
                "flex items-center gap-1.5 h-8 px-4 rounded-lg border text-xs font-semibold transition-colors shrink-0",
                theme === 'dark'
                  ? "border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-200 hover:text-ds-zinc-100 hover:bg-ds-zinc-800"
                  : "border-ds-zinc-300 bg-ds-white text-ds-zinc-700 hover:text-ds-zinc-900 hover:bg-ds-zinc-100"
              )}
            >
              <Download className="w-3.5 h-3.5" />
              <span>{t('splitPane.neo4jExportButton')}</span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
