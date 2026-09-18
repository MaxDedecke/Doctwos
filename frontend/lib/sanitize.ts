import DOMPurify from 'dompurify';

// Zentrale Stelle für das Rendern von untrusted HTML/SVG per dangerouslySetInnerHTML.
// Quellen sind grundsätzlich nicht vertrauenswürdig: ingestierte Dokumente
// (Confluence/Jira/HTML-Uploads) und LLM-Antworten. Ohne Sanitizing wäre jede
// dieser Stellen ein Stored-XSS-Vektor.

// SSR: DOMPurify braucht ein DOM (window). Alle Aufrufer sind Client-Komponenten,
// deren Inhalte ohnehin erst nach dem Mount per Fetch geladen werden — server-
// seitig gibt es also nichts zu rendern. Wir geben "" zurück, statt unsanitisiert
// durchzureichen; der Client rendert nach der Hydration mit dem echten Inhalt.
const isBrowser = typeof window !== 'undefined';

export function sanitizeHtml(dirty: string | null | undefined): string {
  if (!isBrowser || !dirty) return '';
  return DOMPurify.sanitize(dirty, { USE_PROFILES: { html: true } });
}

export function sanitizeSvg(dirty: string | null | undefined): string {
  if (!isBrowser || !dirty) return '';
  // Mermaid 11 legt Beschriftungen (insbesondere bei Sequence-Diagrammen) in
  // SVG-foreignObject-Containern ab. Das reine SVG-Profil entfernt diese
  // Container komplett: Linien und Knoten bleiben dann sichtbar, aber jeder
  // Text verschwindet. HTML bleibt innerhalb von foreignObject weiterhin
  // durch DOMPurify bereinigt; Skripte, Event-Handler und gefährliche URLs
  // werden also nicht in die Chat-Antwort übernommen.
  return DOMPurify.sanitize(dirty, {
    USE_PROFILES: { html: true, svg: true, svgFilters: true },
    ADD_TAGS: ['foreignObject'],
    ADD_ATTR: ['xmlns'],
    HTML_INTEGRATION_POINTS: { foreignobject: true },
    // DOMPurify forbids the *contents* of foreignObject by default even if
    // the element itself is added to the allow-list. Mermaid has already
    // produced this SVG in strict mode; DOMPurify still sanitizes every HTML
    // child and strips executable tags/attributes below.
    FORBID_CONTENTS: ['script', 'iframe', 'object', 'embed', 'noscript', 'template'],
  });
}

// Für Text, der anschließend selbst zu (kontrolliertem) HTML zusammengesetzt wird
// — z. B. die Regex-"Markdown"-Wiedergabe im Link-Chat: erst escapen, dann dürfen
// nur die selbst erzeugten Tags (<strong>/<em>/<code>) HTML sein.
const HTML_ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}
