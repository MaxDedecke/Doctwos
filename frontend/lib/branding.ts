"use client";
import { useSyncExternalStore } from 'react';
import { BRANDING_STYLE_ID, DEFAULT_BRANDING, brandingCss, brandingTitle, normalizeBranding, type Branding } from './brandingTheme';

export * from './brandingTheme';

// Ein kleiner Speicher statt Context: Login (vor dem App-Zustand) und Arbeitsbereich lesen
// dasselbe, und der Corporate-Tab aktualisiert beide sofort nach dem Speichern.
let current: Branding = normalizeBranding(typeof window !== 'undefined' ? window.__CODENA_BRANDING__ : null);
const listeners = new Set<() => void>();

export function getBranding(): Branding {
  return current;
}

export function setBranding(next: Partial<Branding> | null): void {
  current = normalizeBranding(next);
  if (typeof document !== 'undefined') {
    let style = document.getElementById(BRANDING_STYLE_ID);
    if (!style) {
      style = document.createElement('style');
      style.id = BRANDING_STYLE_ID;
      document.head.appendChild(style);
    }
    style.textContent = brandingCss(current);
    document.title = brandingTitle(current);
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useBranding(): Branding {
  return useSyncExternalStore(subscribe, getBranding, () => DEFAULT_BRANDING);
}
