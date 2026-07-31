"use client";

import React, { createContext, useContext } from 'react';

// Gebündelter Settings-Zustand, den page.tsx bereitstellt und der SettingsModal-
// Teilbaum konsumiert — ersetzt das frühere Durchreichen von ~36 Einzel-Props
// (siehe docs/TECH_DEBT_CLEANUP_PLAN.md §5, Schritt 1). isOpen/onClose bleiben
// bewusst normale Props von SettingsModal (Modal-Lebenszyklus gehört dem Parent).
// Dieser Context ist zugleich die Grundlage für Schritt 2 (Tab-Zerlegung): künftige
// Tab-Komponenten konsumieren ihn direkt, statt erneut Props durchgereicht zu bekommen.
export interface SettingsContextValue {
  theme: string;
  setTheme: (theme: string) => void;
  projects: any[];
  setProjects: React.Dispatch<React.SetStateAction<any[]>>;
  selectedProject: any | null;
  setSelectedProject: React.Dispatch<React.SetStateAction<any | null>>;
  setFiles: React.Dispatch<React.SetStateAction<any[]>>;
  showToast: (msg: string, type: 'success' | 'error') => void;
  backendStatus: string;

  // AI parameters
  activeLlmModel: string;
  setActiveLlmModel: (model: string) => void;
  activeEmbeddingModel: string;
  setActiveEmbeddingModel: (model: string) => void;
  availableModels: string[];
  temperature: number;
  setTemperature: (temp: number) => void;
  systemPrompt: string;
  setSystemPrompt: (prompt: string) => void;
  llmProfiles: any[];
  setLlmProfiles: React.Dispatch<React.SetStateAction<any[]>>;
  activeProfileId: string;
  setActiveProfileId: (id: string) => void;

  // Editor states
  editorFontSize: number;
  setEditorFontSize: (size: number) => void;
  editorMinimap: boolean;
  setEditorMinimap: (show: boolean) => void;
  editorFontFamily: string;
  setEditorFontFamily: (family: string) => void;

  // Layout states
  workspaceSplit: string;
  setWorkspaceSplit: (split: string) => void;

  // Wissensquellen
  connectedSources: any[];
  setConnectedSources: React.Dispatch<React.SetStateAction<any[]>>;
  projectStats: Record<number, any>;
  pinnedSourceIds: number[];
  togglePinSource: (sourceId: number) => void;

  currentUser: any | null;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export const SettingsProvider = SettingsContext.Provider;

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return ctx;
}
