# Confluence-Sync-Pipeline (`ConfluenceConnector`)

Ablauf von `BaseConnector.sync()` (`parser/connectors/base.py`) mit
`ConfluenceConnector.fetch_documents()` (`parser/connectors/confluence.py`) —
im Unterschied zur COBOL-Strukturanalyse bei Git (siehe
`docs/GIT_SYNC_PIPELINE.md`) rein textbasiert: Seiten kommen als gerendertes
HTML, Chunking läuft ausschließlich generisch.

```mermaid
flowchart TD
    Start(["sync gestartet"]) --> Model["Embedding-Modell sicherstellen<br/>ensure_model_pulled"]
    Model --> PageLoop["Content-API paginiert abfragen<br/>/wiki/rest/api/content bzw. /rest/api/content<br/>(Backoff bei HTTP 429)"]

    subgraph perPage ["pro Seite -- _build_document"]
        direction TB
        SpaceFilter{"Seite im gewuenschten Space?"}
        SpaceFilter -->|nein| SkipSpace["ueberspringen"]
        SpaceFilter -->|ja| PageDelta{"version.when &lt;= last_synced_at<br/>UND Chunks existieren bereits?"}
        PageDelta -->|ja, unveraendert| SkipPage["ueberspringen (Delta-Sync)"]
        PageDelta -->|nein| HtmlToText["body.view.value (HTML)<br/>-&gt; Klartext via _ConfluenceHTMLParser<br/>(Tabellen als Spalten, Code-Bloecke roh erhalten)"]
        HtmlToText --> EmptyCheck{"Text leer?"}
        EmptyCheck -->|ja| SkipEmpty["ueberspringen, geloggt"]
        EmptyCheck -->|nein| YieldPage["Document einreihen<br/>storage_key = Seitentitel"]
    end

    PageLoop --> SpaceFilter
    YieldPage --> AttLoop["Anhaenge der Seite abfragen<br/>/child/attachment"]

    subgraph perAttachment ["pro Anhang -- _fetch_attachments"]
        direction TB
        MimeCheck{"MIME unterstuetzt?<br/>text/* · PDF · DOCX/DOC"}
        MimeCheck -->|nein| SkipMime["ueberspringen<br/>(Bilder, ZIP, ... kein Textinhalt)"]
        MimeCheck -->|ja| SizeCheck{"Groesse &gt; 20 MB?"}
        SizeCheck -->|ja| SkipSize["ueberspringen, geloggt"]
        SizeCheck -->|nein| AttDelta{"version.when &lt;= last_synced_at<br/>UND Chunks existieren bereits?"}
        AttDelta -->|ja| SkipAttDelta["ueberspringen (Delta-Sync)"]
        AttDelta -->|nein| Download["Binaerinhalt herunterladen"]
        Download --> Extract["Text extrahieren<br/>PDF: pypdf · DOCX: python-docx · text/*: UTF-8-Decode"]
        Extract -->|kein Text gewonnen| SkipExtract["ueberspringen"]
        Extract -->|Text vorhanden| YieldAtt["Document einreihen<br/>storage_key = Seite/attachments/Dateiname"]
    end

    AttLoop --> MimeCheck
    YieldAtt --> PerDoc
    SkipMime --> NextItem{"Naechste Seite/Anhang?"}
    SkipSize --> NextItem
    SkipAttDelta --> NextItem
    SkipExtract --> NextItem
    SkipSpace --> NextItem
    SkipPage --> NextItem
    SkipEmpty --> NextItem

    subgraph PerDocGroup ["pro Dokument -- _process_document (sequentiell, KEINE Nebenlaeufigkeit)"]
        direction TB
        PerDoc["CodeParser.chunk_file<br/>generisches Zeilenchunking<br/>(siehe GIT_SYNC_PIPELINE.md, Punkt 2)"]
        PerDoc --> Reindex["reindex_chunks_preserving_links<br/>JEDER Chunk neu embedded (get_embedding,<br/>Einzel-Request, kein Batch, kein Skip)<br/>Content-Fingerprint ordnet alte/neue Chunks<br/>einander zu -&gt; EntityDocLink-Status/chunk_id<br/>bei Uebereinstimmung uebernommen"]
        Reindex --> LogDone["_log: 'X indexiert (N Chunks).'"]
    end

    PerDoc --> NextItem
    LogDone --> NextItem
    NextItem -->|ja| PageLoop
    NextItem -->|nein, alles durch| Complete["last_synced_at = Sync-Start<br/>sync_status = completed"]
    Complete --> ChangeCheck{"has_changes<br/>UND project_id gesetzt?"}
    ChangeCheck -->|ja| LinkJob["Celery-Task compute_entity_links<br/>anstossen (tasks/sync.py)"]
    ChangeCheck -->|nein| Done(["sync abgeschlossen"])
    LinkJob --> Done
```

## Kernpunkte

- **Keine Nebenläufigkeit:** anders als `GitConnector` (Semaphore-gesteuerte
  Parallelverarbeitung, siehe `docs/GIT_SYNC_PIPELINE.md`) verarbeitet
  `BaseConnector.sync()` — und damit Confluence, Jira, WebDAV, FolderWatch —
  Dokumente strikt **sequentiell**, eine Datei nach der anderen. Kein
  `EMBED_CONCURRENCY`/GPU-CPU-Umschalten nötig, dafür auch kein Parallelitäts-
  Speedup möglich.
- **Delta-Sync ist zeitbasiert**, nicht inhaltsbasiert: eine Seite/ein Anhang
  gilt als unverändert, wenn `version.when` nicht neuer ist als
  `source.last_synced_at` **und** dafür bereits Chunks existieren — anders als
  bei Git, wo der Blob-Content-Hash entscheidet (`SourceScanFile`). Jede
  Bearbeitung, die Confluence `version.when` weiterzählt, löst also einen
  Re-Embed aus — auch wenn der resultierende Klartext am Ende identisch wäre.
- **Kein COBOL-Zweig:** Confluence-Inhalte laufen immer über das generische
  Zeilenchunking (`CodeParser.chunk_file`, Punkt (2) in
  `docs/GIT_SYNC_PIPELINE.md`) — es gibt keine Sprache, die hier eine
  Strukturanalyse rechtfertigen würde.
- **Embedding läuft pro Chunk einzeln** (`get_embedding`, kein
  `get_embeddings_batch`) — sobald eine Seite den Delta-Check nicht besteht
  (also neu oder geändert ist), wird **jeder** ihrer Chunks frisch embedded,
  es gibt kein Chunk-Level-Skip für unveränderte Passagen innerhalb einer
  geänderten Seite. Der Content-Fingerprint-Vergleich mit den alten Chunks
  dient ausschließlich dazu, eine unveränderte Passage wiederzuerkennen und
  ihren bestehenden `EntityDocLink`-Status/`chunk_id` auf den neuen Chunk zu
  übertragen (statt den Review-Status zu verlieren) — er spart kein Embedding
  ein. Dasselbe `chunk_reindex.py`-Modul verwendet auch `GitConnector`, dort
  aber mit vorab batch-berechneten Embeddings statt Einzel-Requests.
- **Anhänge sind eigenständige Dokumente:** jeder unterstützte Anhang (PDF,
  DOCX/DOC, `text/*`) bekommt einen eigenen `storage_key`
  (`"<Seite>/attachments/<Dateiname>"`) und durchläuft dieselbe Chunk-/Embed-/
  Persistenz-Pipeline wie die Seite selbst — mit eigenem Delta-Sync-Check und
  einer harten 20-MB-Obergrenze.

Quelle: `parser/connectors/base.py` (`sync`, `_process_document`),
`parser/connectors/confluence.py` (`fetch_documents`, `_build_document`,
`_fetch_attachments`, `_html_to_text`), `parser/chunk_reindex.py`
(`reindex_chunks_preserving_links`), `parser/tasks/sync.py`
(`process_knowledge_source_async`).
