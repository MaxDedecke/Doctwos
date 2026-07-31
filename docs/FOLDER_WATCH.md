# Folder Watch — Local Folder / NAS Indexing

Doctus can index documents from a local folder or network share (NAS/fileshare) and keep them up to date automatically. This is the recommended starting point for customers who already have a shared drive with PDFs, Word documents, and text files they want to query — no API access, no cloud connector, zero IT friction.

## How it works

The `parser-beat` service (a Celery Beat scheduler) triggers a scan of every configured folder source once per hour. Each scan:

1. Walks the folder recursively.
2. Computes an MD5 hash for every supported file.
3. Compares hashes against the previous scan (stored in `folder_scan_files`).
4. Re-indexes only new or changed files — unchanged files are skipped entirely (delta sync).
5. Removes index entries for files that have been deleted from the folder.

The resulting chunks land in pgvector and are immediately available for RAG queries in the chat.

**Supported formats:** `.pdf` (text-layer, with OCR fallback for scans — see [Limitations](#limitations)), `.docx`, `.doc`, `.txt`, `.md`

A manual re-scan can be triggered at any time via the sync button in the UI (Settings → Knowledge Sources).

---

## Setup

### Step 1 — Mount the folder into the containers

Edit `.env` and set `WATCHED_FOLDER` to the **absolute path on the host** that should be made available inside the containers:

```env
WATCHED_FOLDER=/mnt/nas/Wissensbasis
```

This path is mounted read-only as `/watched` in the `backend-api`, `parser-worker`, and `parser-beat` containers. Doctus never writes to the customer's folder.

Restart the stack after changing `.env`:

```sh
docker compose down && docker compose up -d
```

### Step 2 — Register a folder source in the UI

1. Open **Settings → Knowledge Sources**.
2. Click the **"Ordner verbinden"** tile.
3. Enter a display name (e.g. `VgV-Ausschreibungen 2024`) and the container-internal path (e.g. `/watched`).
4. Click **"Ordner indizieren"**.

The first scan starts immediately in the background. Progress and logs are visible in the knowledge source card.

---

## Multiple folders / multiple NAS shares

A single `WATCHED_FOLDER` mount covers one host path. To index documents from **multiple locations**, there are two approaches depending on what the customer's infrastructure allows.

### Option A — Subdirectory structure (recommended)

If the NAS shares can be mounted on the **same host machine** under a common parent directory, set `WATCHED_FOLDER` to that parent:

```env
WATCHED_FOLDER=/mnt/doctus-watched
```

The IT team then mounts each share as a subdirectory of that parent. On Linux this is typically done with CIFS/SMB or NFS:

```sh
# /etc/fstab entries — example with CIFS
//nas.firma.local/Ausschreibungen  /mnt/doctus-watched/ausschreibungen  cifs  credentials=/etc/doctus-nas.creds,ro,uid=1000  0  0
//nas.firma.local/Projektarchiv    /mnt/doctus-watched/projekte          cifs  credentials=/etc/doctus-nas.creds,ro,uid=1000  0  0
//nas.firma.local/Normen           /mnt/doctus-watched/normen            cifs  credentials=/etc/doctus-nas.creds,ro,uid=1000  0  0
```

After mounting, the directory structure looks like:

```
/mnt/doctus-watched/
  ausschreibungen/   ← maps to /watched/ausschreibungen inside containers
  projekte/          ← maps to /watched/projekte
  normen/            ← maps to /watched/normen
```

In the Doctus UI, create one **"Ordner verbinden"** knowledge source per share, each pointing to its own container path:

| Display name        | Container path              |
|---------------------|-----------------------------|
| Ausschreibungen     | `/watched/ausschreibungen`  |
| Projektarchiv       | `/watched/projekte`         |
| Normen & Standards  | `/watched/normen`           |

Each source is scanned and indexed independently. Adding a new source doesn't re-index the others.

### Option B — All content in one root folder (simplest)

If the customer is comfortable dumping everything under a single shared folder, point `WATCHED_FOLDER` at it and create a single knowledge source at `/watched`. Doctus will walk all subdirectories recursively.

Use this when the customer doesn't need per-folder access control or separate sync visibility in the UI.

---

## Limitations

**Scanned PDFs (image-only):** `pypdf` extracts text from PDFs that have an embedded text layer first. If a PDF has no text layer (a pure scan), `parser/connectors/folder.py` falls back to rasterizing the pages and running Tesseract OCR (`parser/utils.py::extract_text_from_pdf_ocr`, German+English, `tesseract-ocr-deu` is installed in the parser image). OCR text quality depends on scan resolution and is slower than native text extraction, so expect indexing of large batches of scanned archives to take noticeably longer than born-digital PDFs — worth setting that expectation with the customer during scoping.

**CAD and BIM files via plain folder watch:** `.dwg`, `.ifc`, `.rvt`, `.dxf` are binary formats and are **not** parsed by the generic `FolderConnector` described in this doc — only the text-based document types listed above are indexed through it. This does *not* mean Doctus can't handle BIM/CAD at all: `.ifc` and `.dwg`/`.dxf` each have their own dedicated connector and source type (`parser/connectors/ifc.py`, `parser/connectors/dwg.py` — see `docs/IFC_EXPORT_REQUIREMENTS.md`), created via a separate flow in the UI, not the folder watch. Only `.rvt` (Revit) has no connector at all today. Scoping conversations with architecture or engineering customers should establish whether their IFC/DWG files go through those dedicated connectors or whether relevant knowledge instead lives in accompanying PDFs/Word files indexed via folder watch.

**No real-time watching:** The scanner runs on a fixed hourly schedule (top of the hour, via Celery Beat). A file added at 00:01 will be indexed by 01:00 at the latest. If the customer needs faster updates, the manual sync button in the UI triggers an immediate re-scan of that specific source.

**Network share availability:** If the NAS is unreachable during a scheduled scan (e.g. network outage, planned maintenance), the scan fails with an error logged to the knowledge source's sync log. No data is lost — the next scheduled scan picks up normally once the share is reachable again.

---

## Troubleshooting

**"Ordnerpfad nicht gefunden oder kein Verzeichnis"**
The path entered in the UI is not accessible inside the container. Check that:
- `WATCHED_FOLDER` in `.env` points to an existing directory on the host.
- The stack was restarted (`docker compose down && docker compose up -d`) after changing `.env` — a `docker compose restart` does not re-evaluate volume mounts.
- The subdirectory path matches exactly (case-sensitive on Linux hosts).

**Files present in the folder but not appearing in search results**
Open the knowledge source card → sync log. Common causes:
- File extension not in the supported list (`.pdf`, `.docx`, `.doc`, `.txt`, `.md`).
- PDF has no text layer (see Limitations above).
- File is currently open/locked by another process and couldn't be read.
- The embedding model (`bge-m3`) hasn't been pulled yet — the log will show an Ollama pull in progress.

**`parser-beat` container exits immediately**
Check `docker compose logs parser-beat`. A common cause is a missing or malformed `MASTER_ENCRYPTION_KEY` in `.env` — the parser service imports `models.crypto_types` on startup, which requires this key.

**Scan runs but no new files are picked up after an update**
The delta-sync compares MD5 hashes. If a file's content is identical to what was previously indexed (same bytes, different modification time), it will not be re-indexed — this is intentional. To force a full re-index of a specific source, delete it in the UI and re-create it: this clears all `folder_scan_files` records and `document_chunks` for that source, and the next scan treats everything as new.
