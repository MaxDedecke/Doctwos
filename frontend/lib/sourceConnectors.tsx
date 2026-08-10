import React from 'react';
import { GitBranch, Database, Layers, Code, Folder } from 'lucide-react';

/**
 * Styling-Metadaten pro Konnektor-Typ. Aus SourcesTab.tsx herausgezogen, weil
 * SourceNetworkGraph.tsx dieselbe Icon-/Farbzuordnung für die Netzwerk-Visualisierung
 * braucht — eine einzige Quelle der Wahrheit statt zweier Switch-Statements.
 */
export interface ConnectorMetadata {
  glowColor: string;
  gradientBorder: string;
  iconColor: string;
  badgeColor: string;
  icon: React.ReactNode;
}

export const getConnectorMetadata = (typeName: string | undefined | null): ConnectorMetadata => {
  const name = typeName ? typeName.toLowerCase() : "";
  switch (name) {
    case 'git':
      return {
        glowColor: "rgba(99, 102, 241, 0.15)",
        gradientBorder: "from-ds-indigo-500/40 to-ds-purple-500/10",
        iconColor: "text-ds-indigo-400",
        badgeColor: "bg-ds-indigo-500/10 text-ds-indigo-400 border-ds-indigo-500/20",
        icon: <GitBranch className="w-4 h-4" />
      };
    case 'confluence':
      return {
        glowColor: "rgba(59, 130, 246, 0.15)",
        gradientBorder: "from-ds-blue-500/40 to-ds-indigo-500/10",
        iconColor: "text-ds-blue-400",
        badgeColor: "bg-ds-blue-500/10 text-ds-blue-400 border-ds-blue-500/20",
        icon: <Database className="w-4 h-4" />
      };
    case 'jira':
      return {
        glowColor: "rgba(139, 92, 246, 0.15)",
        gradientBorder: "from-ds-violet-500/40 to-ds-fuchsia-500/10",
        iconColor: "text-ds-violet-400",
        badgeColor: "bg-ds-violet-500/10 text-ds-violet-400 border-ds-violet-500/20",
        icon: <Layers className="w-4 h-4" />
      };
    case 'local':
      return {
        glowColor: "rgba(245, 158, 11, 0.15)",
        gradientBorder: "from-ds-amber-500/40 to-ds-yellow-500/10",
        iconColor: "text-ds-amber-400",
        badgeColor: "bg-ds-amber-500/10 text-ds-amber-400 border-ds-amber-500/20",
        icon: <Code className="w-4 h-4" />
      };
    case 'folderwatch':
      return {
        glowColor: "rgba(16, 185, 129, 0.15)",
        gradientBorder: "from-ds-emerald-500/40 to-ds-teal-500/10",
        iconColor: "text-ds-emerald-400",
        badgeColor: "bg-ds-emerald-500/10 text-ds-emerald-400 border-ds-emerald-500/20",
        icon: <Folder className="w-4 h-4" />
      };
    default:
      return {
        glowColor: "rgba(107, 114, 128, 0.15)",
        gradientBorder: "from-ds-zinc-500/40 to-ds-zinc-700/10",
        iconColor: "text-ds-zinc-400",
        badgeColor: "bg-ds-zinc-500/10 text-ds-zinc-400 border-ds-zinc-500/20",
        icon: <Database className="w-4 h-4" />
      };
  }
};
