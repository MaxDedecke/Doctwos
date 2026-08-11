export interface FeaturesConfig {
  connectors: {
    confluence: boolean;
    jira: boolean;
    local: boolean;
    folderwatch: boolean;
    webdav: boolean;
  };
  git: {
    github: boolean;
    gitlab: boolean;
    bitbucket: boolean;
    public: boolean;
  };
  views: {
    linkManager: boolean;
    knowledgeGraph: boolean;
    globalSearch: boolean;
  };
  settings: {
    ai: boolean;
    logs: boolean;
    layout: boolean;
  };
  llm: {
    // Doctus's core pitch is on-prem, local-only inference.
    // Cloud LLM profiles (OpenAI/Gemini/Anthropic) are opt-in per deployment, not default —
    // flipping this on breaks the "no data leaves the network" guarantee for that customer.
    allowCloudProviders: boolean;
  };
}

export const DEFAULT_FEATURES: FeaturesConfig = {
  connectors: {
    confluence: false,
    jira: false,
    local: true,
    folderwatch: true,
    webdav: false,
  },
  git: {
    github: false,
    gitlab: false,
    bitbucket: false,
    public: false,
  },
  views: {
    linkManager: true,
    knowledgeGraph: true,
    globalSearch: true,
  },
  settings: {
    ai: true,
    logs: true,
    layout: true,
  },
  llm: {
    allowCloudProviders: false,
  },
};

declare global {
  interface Window {
    __DOCTUS_FEATURES__?: Partial<FeaturesConfig> | null;
  }
}

export function getFeatures(): FeaturesConfig {
  const injected = typeof window !== 'undefined' ? window.__DOCTUS_FEATURES__ : null;
  if (!injected) return DEFAULT_FEATURES;

  return {
    connectors: { ...DEFAULT_FEATURES.connectors, ...injected.connectors },
    git: { ...DEFAULT_FEATURES.git, ...injected.git },
    views: { ...DEFAULT_FEATURES.views, ...injected.views },
    settings: { ...DEFAULT_FEATURES.settings, ...injected.settings },
    llm: { ...DEFAULT_FEATURES.llm, ...injected.llm },
  };
}
