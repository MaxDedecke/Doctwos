'use client';

import React, { createContext, useContext, useSyncExternalStore } from 'react';
import { FeaturesConfig, DEFAULT_FEATURES, getFeatures } from './features';

const FeaturesContext = createContext<FeaturesConfig>(DEFAULT_FEATURES);

const noopSubscribe = () => () => {};

// window.__DOCTUS_FEATURES__ is injected once (inline script in layout.tsx,
// before hydration) and never mutated afterwards, so this only needs to run
// once per session rather than on every getSnapshot() call — otherwise
// useSyncExternalStore would see a new object reference each render and
// re-render forever.
let cachedClientFeatures: FeaturesConfig | undefined;
function getClientSnapshot(): FeaturesConfig {
  if (cachedClientFeatures === undefined) cachedClientFeatures = getFeatures();
  return cachedClientFeatures;
}
function getServerSnapshot(): FeaturesConfig {
  return DEFAULT_FEATURES;
}

export function FeaturesProvider({ children }: { children: React.ReactNode }) {
  const features = useSyncExternalStore(noopSubscribe, getClientSnapshot, getServerSnapshot);

  return (
    <FeaturesContext.Provider value={features}>
      {children}
    </FeaturesContext.Provider>
  );
}

export function useFeatures(): FeaturesConfig {
  return useContext(FeaturesContext);
}
