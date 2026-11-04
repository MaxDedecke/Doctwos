# Webansicht: Einträge fremder Systeme

Tickets, Wikiseiten und Ähnliches werden in Doctus einheitlich dargestellt. Ein System liefert Daten, die Darstellung
ist für alle gleich. Code: `backend/services/web_documents/`, `frontend/components/WebDocumentView.tsx`.

## Ein neues System anbinden

1. **Konnektor** in `parser/connectors/` schreiben und in `registry.py` eintragen. Jedes Dokument trägt `storage_key`
   (stabiler Schlüssel), `url` und `title`. **Damit funktioniert die Webansicht bereits:** Sie zeigt den indexierten Text.
   Nur Quellen, die Dateien liefern, müssen in `FILE_SOURCE_TYPES` stehen (Backend und `frontend/lib/webSources.ts`).
2. **Adapter** für die volle Darstellung: Unterklasse von `WebAdapter` in `backend/services/web_documents/<system>.py`,
   Eintrag in `ADAPTERS`.
   - `index_key(url)`: Index-Schlüssel aus einer URL, ohne Netzzugriff. Führendes `*` heißt: Nur das Ende zählt.
     Davon hängt ab, ob Links auf diesen Eintrag in Doctus öffnen. Verrät die URL den Schlüssel nicht (`None`, etwa
     GitLab: Schlüssel mit Projekt-ID, URL mit Pfad), gilt die beim Import gespeicherte URL des Eintrags.
   - `fetch(ctx, key, meta)`: das `WebDocument` live abrufen, über `ctx.get_json`. Nicht darstellbar: `NotRenderable`.
3. **Übersetzungen** nur, wenn neue `Fact.key` übersetzt erscheinen sollen (`webDocument.facts`, `TRANSLATED_FACTS`).
   Ohne Eintrag erscheint `Fact.label`.

## Was der Adapter nicht tun muss

Links absolut machen, Bilder und Anhänge über den signierten `web-asset`-Pfad leiten, bekannte Links markieren, HTML
bereinigen, auf den Index zurückfallen, wenn die Quelle nicht antwortet, im Text genannten Code finden
(`mentions.py`): Das geschieht für alle Systeme gemeinsam.
`extra_css` ergänzt feste Regeln für die Klassen des Systems; Farben kommen aus den Variablen `--wd-*`.

## Regeln

- **Nur Indexiertes wird geöffnet.** Zugangsdaten einer Quelle lesen oft mehr, als freigegeben ist (andere Bereiche,
  gesperrte Seiten). Eine frei übergebene URL darf das nicht erreichen.
- **Zugangsdaten gehen nur an die eigene Adresse der Quelle**, auch bei Weiterleitungen.
- **Inhalte der Quelle sind nicht vertrauenswürdig.** Sie laufen durch DOMPurify und in ein iframe ohne `allow-same-origin`.
  Metadaten stellt React dar. Das iframe sendet kein Sitzungs-Cookie, deshalb die signierten Verweise (1 Stunde gültig).
