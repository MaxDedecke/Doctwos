/**
 * Embedding-Modell einer Wissensquelle für die Anzeige. Hat die Quelle kein Modell gespeichert, gilt der
 * Deployment-Standard; dann ist weder ein Name noch ein Abgleich mit dem aktiven Profil belegbar. Ein fest
 * eingetragener Standardname würde hier einen falschen Reindex-Alarm auslösen.
 */
export function sourceEmbeddingState(sourceModel: string | null | undefined, activeModel: string): {
  label: string;
  mismatch: boolean;
} {
  const explicit = (sourceModel ?? '').trim();
  if (!explicit) return { label: activeModel, mismatch: false };
  return { label: explicit, mismatch: explicit !== activeModel };
}
