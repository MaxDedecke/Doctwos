"use client";

import React from 'react';
import { Download, Moon, Sun } from 'lucide-react';
import { cn } from "@/lib/utils";
import { api, API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import { activeCardClass, cardClass, dividerClass, helpTextClass, secondaryButtonClass, sectionTitleClass, strongTextClass } from '@/components/settings/settingsStyles';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Layout-&-Design-Tab: Darstellung (Theme, Sprache), Arbeitsbereich-Aufteilung, Code-Viewer und Graph-Export.
// Jede Gruppe ist eine Karte aus Zeilen "Titel + Erklärung links, Bedienelement rechts".

/** Eine Einstellungsgruppe: Überschrift und Karte. */
const Group: React.FC<{ title: string; theme: string; children: React.ReactNode }> = ({ title, theme, children }) => (
  <section className="space-y-2.5">
    <h4 className={sectionTitleClass(theme)}>{title}</h4>
    <div className={cn(cardClass(theme), 'divide-y', theme === 'dark' ? 'divide-ds-zinc-800/60' : 'divide-ds-zinc-200/80')}>{children}</div>
  </section>
);

/** Eine Zeile einer Gruppe; schmal untereinander, ab `sm` nebeneinander. */
const Row: React.FC<{ title: string; description?: string; theme: string; children: React.ReactNode }> = ({ title, description, theme, children }) => (
  <div className="flex flex-col gap-2.5 p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
    <div className="min-w-0 space-y-0.5">
      <span className={cn('block text-xs', strongTextClass(theme))}>{title}</span>
      {description && <span className={cn('block', helpTextClass)}>{description}</span>}
    </div>
    <div className="shrink-0">{children}</div>
  </div>
);

/** Umschalter mit festen Optionen (statt eines Schalters, dessen Zustand man erst deuten muss). */
function Segmented<T extends string>({ theme, options, value, onChange }: {
  theme: string;
  options: Array<{ value: T; label: string; id: string; icon?: React.ReactNode }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" className={cn('inline-flex rounded-lg border p-0.5', theme === 'dark' ? 'border-ds-zinc-800 bg-ds-zinc-900' : 'border-ds-zinc-200 bg-ds-white')}>
      {options.map(option => (
        <button key={option.value} type="button" id={option.id} aria-pressed={value === option.value} onClick={() => onChange(option.value)}
          className={cn('flex h-7 items-center gap-1.5 rounded-md px-3 text-[0.6875rem] font-semibold transition-colors',
            value === option.value
              ? 'bg-ds-indigo-650 text-ds-white'
              : theme === 'dark' ? 'text-ds-zinc-400 hover:text-ds-zinc-200' : 'text-ds-zinc-500 hover:text-ds-zinc-800')}>
          {option.icon}{option.label}
        </button>
      ))}
    </div>
  );
}

const PREVIEW_LINES = [
  '       PROCEDURE DIVISION.',
  '       0000-MAIN.',
  '           PERFORM 1000-INIT',
  '           PERFORM 2000-PROCESS UNTIL WS-EOF = "Y"',
  '           STOP RUN.',
];

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
    showToast(newTheme === 'dark' ? t('settings.toast.darkModeEnabled') : t('settings.toast.lightModeEnabled'), "success");
  };

  const exportNeo4j = async () => {
    const params = new URLSearchParams({ status: 'approved' });
    if (selectedProject?.id) params.set('project_id', String(selectedProject.id));
    try {
      const res = await api.fetch(`${API_URL}/graph/export/neo4j?${params}`);
      if (!res.ok) throw new Error(`Export fehlgeschlagen (${res.status})`);
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
      showToast(t('settings.layoutTab.exportError'), 'error', e);
    }
  };

  // Neutraler CSV-/GraphML-Export (O-034) -- anders als exportNeo4j oben (Cypher,
  // JSON-Response mit dem Skript im Body) liefert /graph/export direkt die fertige
  // Datei als Blob, analog zu CallGraphView.tsx::exportGraph.
  const exportGraph = async (format: 'csv' | 'graphml') => {
    const params = new URLSearchParams({ status: 'approved', format });
    if (selectedProject?.id) params.set('project_id', String(selectedProject.id));
    try {
      const res = await api.fetch(`${API_URL}/graph/export?${params}`);
      if (!res.ok) throw new Error(`Export fehlgeschlagen (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `knowledge_graph_${selectedProject?.name ?? 'all'}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      showToast(t('settings.layoutTab.exportError'), 'error', e);
    }
  };

  const dark = theme === 'dark';
  const splits = [
    { id: '40/60', percent: 40, label: t('settings.layoutTab.splits.narrowChat.label'), desc: t('settings.layoutTab.splits.narrowChat.desc') },
    { id: '45/55', percent: 45, label: t('settings.layoutTab.splits.standard.label'), desc: t('settings.layoutTab.splits.standard.desc') },
    { id: '50/50', percent: 50, label: t('settings.layoutTab.splits.even.label'), desc: t('settings.layoutTab.splits.even.desc') },
    { id: '60/40', percent: 60, label: t('settings.layoutTab.splits.wideChat.label'), desc: t('settings.layoutTab.splits.wideChat.desc') },
  ];
  const exports = [
    { key: 'cypher', label: t('settings.layoutTab.graphExportCypherButton'), run: exportNeo4j },
    { key: 'csv', label: t('settings.layoutTab.graphExportCsvButton'), run: () => exportGraph('csv') },
    { key: 'graphml', label: t('settings.layoutTab.graphExportGraphmlButton'), run: () => exportGraph('graphml') },
  ];
  const selectClass = cn('h-8 w-full text-xs focus:ring-0', dark ? 'bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-350' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-800');
  const selectContentClass = dark ? 'bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-800';

  return (
    <div className="w-full min-w-0 space-y-6 animate-in fade-in duration-200">
      <Group title={t('settings.layoutTab.appearanceTitle')} theme={theme}>
        <Row title={t('settings.layoutTab.colorThemeTitle')} description={t('settings.layoutTab.lightModeDesc')} theme={theme}>
          <Segmented theme={theme} value={dark ? 'dark' : 'light'} onChange={handleThemeToggle}
            options={[
              { value: 'dark', id: 'theme-dark', label: t('settings.layoutTab.themeDark'), icon: <Moon className="h-3 w-3" aria-hidden /> },
              { value: 'light', id: 'theme-light', label: t('settings.layoutTab.themeLight'), icon: <Sun className="h-3 w-3" aria-hidden /> },
            ]} />
        </Row>
        <Row title={t('settings.layoutTab.languageTitle')} description={t('settings.layoutTab.languageDesc')} theme={theme}>
          <Segmented theme={theme} value={language} onChange={setLanguage}
            options={[
              { value: 'de', id: 'language-toggle-de', label: t('settings.layoutTab.languageGerman') },
              { value: 'en', id: 'language-toggle-en', label: t('settings.layoutTab.languageEnglish') },
            ]} />
        </Row>
      </Group>

      <section className="space-y-2.5">
        <h4 className={sectionTitleClass(theme)}>{t('settings.layoutTab.workspaceSplitTitle')}</h4>
        <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
          {splits.map(split => (
            <button key={split.id} type="button" aria-pressed={workspaceSplit === split.id} onClick={() => setWorkspaceSplit(split.id)}
              className={cn('space-y-2 p-3 text-left transition-colors', workspaceSplit === split.id ? activeCardClass(theme) : cn(cardClass(theme), dark ? 'hover:border-ds-zinc-700' : 'hover:border-ds-zinc-300'))}>
              {/* Maßstäbliche Skizze: links Chat, rechts Arbeitsbereich */}
              <span aria-hidden="true" className="flex h-8 gap-1">
                <span className="rounded-sm bg-ds-indigo-500/60" style={{ width: `${split.percent}%` }} />
                <span className={cn('flex-1 rounded-sm', dark ? 'bg-ds-zinc-700' : 'bg-ds-zinc-300')} />
              </span>
              <span className="block space-y-0.5">
                <span className={cn('block text-[0.6875rem]', strongTextClass(theme))}>{split.label}</span>
                <span className="block text-[0.5625rem] leading-normal text-ds-zinc-500">{split.desc}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <Group title={t('settings.editorTab.title')} theme={theme}>
        <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label className="px-0.5 text-[0.5625rem] font-bold uppercase text-ds-zinc-500">{t('settings.editorTab.fontSizeLabel')}</label>
            <Select value={editorFontSize.toString()} onValueChange={val => setEditorFontSize(parseInt(val))}>
              <SelectTrigger className={selectClass}><SelectValue placeholder={t('settings.editorTab.fontSizePlaceholder')} /></SelectTrigger>
              <SelectContent className={selectContentClass}>
                {['12', '13', '14', '15', '16', '18'].map(size => <SelectItem key={size} value={size}>{size}px</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="px-0.5 text-[0.5625rem] font-bold uppercase text-ds-zinc-500">{t('settings.editorTab.fontFamilyLabel')}</label>
            <Select value={editorFontFamily} onValueChange={setEditorFontFamily}>
              <SelectTrigger className={selectClass}><SelectValue placeholder={t('settings.editorTab.fontFamilyPlaceholder')} /></SelectTrigger>
              <SelectContent className={selectContentClass}>
                <SelectItem value="'JetBrains Mono', monospace">JetBrains Mono</SelectItem>
                <SelectItem value="'Fira Code', monospace">Fira Code</SelectItem>
                <SelectItem value="monospace">{t('settings.editorTab.fontSystemMono')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <Row title={t('settings.editorTab.minimapLabel')} description={t('settings.editorTab.minimapDesc')} theme={theme}>
          <button type="button" role="switch" aria-checked={editorMinimap} aria-label={t('settings.editorTab.minimapLabel')} onClick={() => setEditorMinimap(!editorMinimap)}
            className={cn('relative h-5 w-9 rounded-full p-0.5 transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-ds-indigo-500', editorMinimap ? 'bg-ds-indigo-650' : dark ? 'bg-ds-zinc-800' : 'bg-ds-zinc-300')}>
            <span className={cn('block h-4 w-4 rounded-full bg-ds-white shadow-md transition-transform duration-200', editorMinimap ? 'translate-x-4' : 'translate-x-0')} />
          </button>
        </Row>
        {/* Vorschau mit den gewählten Werten (Schrift, Größe, Minimap) */}
        <div className={cn('p-4', dividerClass(theme))}>
          <div aria-hidden="true" data-testid="editor-preview" className="flex overflow-hidden rounded-lg border border-ds-zinc-800 bg-ds-zinc-950">
            <pre className="min-w-0 flex-1 overflow-x-auto p-3 text-ds-zinc-300" style={{ fontSize: `${editorFontSize}px`, fontFamily: editorFontFamily, lineHeight: 1.5 }}>
              {PREVIEW_LINES.map((line, index) => `${String(index + 1).padStart(2, ' ')}  ${line}`).join('\n')}
            </pre>
            {editorMinimap && <span className="w-12 shrink-0 space-y-1 border-l border-ds-zinc-800 p-1.5">{PREVIEW_LINES.map((line, index) => <span key={index} className="block h-0.5 rounded-full bg-ds-zinc-700" style={{ width: `${Math.min(100, line.trim().length * 2.5)}%` }} />)}</span>}
          </div>
        </div>
      </Group>

      {/* Datenexport, kein Layout: gehört thematisch zu Wissensgraph/Projekt */}
      <Group title={t('settings.layoutTab.graphExportTitle')} theme={theme}>
        <Row title={t('settings.layoutTab.graphExportLabel')} description={t('settings.layoutTab.graphExportDesc')} theme={theme}>
          <div className="flex flex-wrap items-center gap-2">
            {exports.map(item => (
              <Button key={item.key} type="button" variant="outline" onClick={item.run} className={cn(secondaryButtonClass(theme), 'h-8 px-3 text-xs font-semibold')}>
                <Download className="h-3.5 w-3.5" />
                <span>{item.label}</span>
              </Button>
            ))}
          </div>
        </Row>
      </Group>
    </div>
  );
};
