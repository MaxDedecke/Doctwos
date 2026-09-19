"""
parser/connectors/git.py
=========================
Connector für Git-Repositories (AP-3, Plan §7) — monorepo-tauglich, resumable.

Ablauf:
    1. Bare-Mirror unter /repos/bare/<fingerprint>.git anlegen/aktualisieren
       (geteilt über alle Wissensquellen desselben Repos), Worktree unter
       /repos/wt/ks_<source_id>/ anlegen oder per reset --hard FETCH_HEAD
       aktualisieren (§7.1/7.2, parser/git_utils.py).
    2. Geänderte Dateien bestimmen: beim allerersten Sync per `git ls-files`
       (voller Baum), danach per `git diff --name-status` gegen den zuletzt
       gesehenen Commit (source.sync_cursor).
    3. Vor dem Einbetten: Blob-SHA gegen SourceScanFile.content_hash prüfen —
       unverändert seit dem letzten (ggf. abgebrochenen) Sync = überspringen.
       Das ist der günstigste Resume-Mechanismus (NF-004): git kennt den
       Content-Hash über den Blob-SHA bereits, kein erneutes Hashen nötig.
    4. Chunking + Embedding parallel (Semaphore), DB-Schreiben sequenziell.
       Nach jedem persistierten Dokument wird SourceScanFile im selben Commit
       aktualisiert — ein Abbruch mitten im Lauf lässt den nächsten Sync exakt
       dort fortsetzen.
"""

import asyncio
import json
import logging
import os
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import redis

import git_utils
from git_utils import MAX_READ_BYTES
from core.model import ParseResult, classify_completeness
from core.analysis_fingerprint import analysis_fingerprint
from core.language_detection import DEFAULT_LANGUAGE_EXTENSIONS, detect_language
from core.source_decoder import SourceDecodeError, decode_source, looks_like_text
from cobol import copybook as copybook_mod
from cobol.copybook import CopybookIndex
from cobol.profile import BuildProfile, ProfileFragment, SourceColumns, resolve_profile
from core.registry import STRUCTURE_PARSERS
from structure_persist import persist_parse_result
from connectors.base import BaseConnector, Document, _SYNC_LOCK_LEASE_SECONDS
from db import REPOS_ROOT
from java.modules import module_from_path
from models.database import CodeEdge, CodeEntity, DocumentChunk, KnowledgeSource, SourceScanFile
from ollama_client import (
    ensure_model_pulled,
    get_embeddings_batch,
    get_embedding,
    is_gpu_accelerated,
)
from code_parser import CodeParser
from chunk_reindex import reindex_chunks_preserving_links
from tasks.edge_resolver import resolve_global_edges
from tasks.shared import get_authenticated_url
from core import config

logger = logging.getLogger(__name__)
redis_client = redis.from_url(config.REDIS_URL)

# F-016: grobe Dateiklassifikation fürs generische Chunking (CodeParser ist
# language-agnostisch, siehe code_parser.py — das Feld landet nur informativ
# in metadata_json). Die eigentliche Strukturanalyse wird anschließend über
# STRUCTURE_PARSERS anhand der automatisch erkannten Sprache gewählt.
_DEFAULT_EXTENSIONS: dict[str, set[str]] = {
    **{language: set(suffixes) for language, suffixes in DEFAULT_LANGUAGE_EXTENSIONS.items()},
    "cobol": {".cbl", ".cob", ".cobol"},
    "copybook": {".cpy", ".copy"},
    "jcl": {".jcl", ".proc", ".prc"},  # v1: nur Text-Index, keine Strukturanalyse (F-026)
}
_JAVA_BUILD_EXCLUDED_DIRS = {
    "target",
    "build",
    ".gradle",
    "bin",
    "out",
    ".idea",
    ".settings",
}

_JAVA_MODULE_METADATA_NAMES = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradle.properties",
}


def _delete_file_entities(db, *, source_id: int, file_path: str) -> None:
    """Delete one file's entities without cascading shared Java containers.

    Java package/module entities are shared across files, but their legacy
    ``file_path`` stores the first file that created them.  Deleting that file
    must therefore move the container to another surviving Java entity before
    deleting file-owned declarations; otherwise the self-referential CASCADE
    removes the package and declarations from unchanged files as well.
    """
    # Keep incoming references as explicit unresolved evidence.  PostgreSQL's
    # FK cascade would otherwise erase a caller edge together with a deleted
    # target before the unchanged caller gets reparsed, making a deletion look
    # like it never had a relationship at all.
    file_entity_ids = [
        entity_id
        for (entity_id,) in db.query(CodeEntity.id)
        .filter(CodeEntity.source_id == source_id, CodeEntity.file_path == file_path)
        .all()
    ]
    if file_entity_ids:
        db.query(CodeEdge).filter(CodeEdge.dst_entity_id.in_(file_entity_ids)).update(
            {CodeEdge.dst_entity_id: None, CodeEdge.resolution: "unresolved"},
            synchronize_session=False,
        )

    shared_types = ("package", "module")
    shared = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.source_id == source_id,
            CodeEntity.file_path == file_path,
            CodeEntity.type.in_(shared_types),
        )
        .all()
    )

    for container in shared:
        survivor = (
            db.query(CodeEntity)
            .filter(
                CodeEntity.source_id == source_id,
                CodeEntity.variant_key == container.variant_key,
                CodeEntity.file_path != file_path,
                CodeEntity.type.notin_(shared_types),
            )
            .order_by(CodeEntity.id)
            .first()
        )
        if survivor is not None:
            # Use SQL-level DML so the self-referential ORM cascade cannot
            # interpret the shared container as an orphan while its owner file
            # is removed.
            db.execute(
                CodeEntity.__table__.update()
                .where(CodeEntity.id == container.id)
                .values(file_path=survivor.file_path)
            )
        else:
            db.execute(CodeEntity.__table__.delete().where(CodeEntity.id == container.id))
    db.execute(
        CodeEntity.__table__.delete().where(
            CodeEntity.source_id == source_id,
            CodeEntity.file_path == file_path,
        )
    )
    db.expire_all()


# O-074: anders als folder.py/webdav.py (SUPPORTED_EXTENSIONS-Allowlist) hatte
# GitConnector gar keine Dateityp-Filterung -- jede Datei im Repo wurde mit
# open(path, "r", errors="ignore") als Text gelesen, auch Bilder/Archive/
# Binärformate. Ergebnis (live an einem echten Bestand nachvollzogen): die
# Rohbytes "dekodieren" zu Steuerzeichen-Datenmüll, der dann durch bge-m3
# geschickt wird -- verschwendet Rechenzeit UND verschmutzt den Vektorindex
# mit Rauschen, das später als falscher Suchtreffer auftauchen kann. Diese
# Sperrliste deckt bekannte Formate ab, die byteweise als Text gelesen
# garantiert keinen sinnvollen Inhalt ergeben. PDF/DOCX/XLSX/PPTX sind
# bewusst mit drin: hier fehlt (anders als bei folder.py/webdav.py/dem
# lokalen Upload-Pfad) jede Extraktionsfunktion für dieses Format -- lieber
# ehrlich überspringen als denselben Datenmüll erzeugen. Eine geteilte
# Extraktion (analog zu O-031s extract_pdf_pages) wäre der bessere
# Folgeschritt, kein Ersatz für diese Sperrliste.
_SKIPPED_BINARY_EXTENSIONS = {
    # Bilder
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".tif",
    ".tiff",
    # Archive/komprimierte Formate
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".rar",
    ".7z",
    ".jar",
    ".war",
    # Ausführbare/kompilierte Dateien
    ".exe",
    ".dll",
    ".so",
    ".bin",
    ".class",
    ".pyc",
    ".o",
    # Office-Binärformate ohne geteilte Extraktionsfunktion in diesem Connector
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
}

# O-074 (Ergänzung): eine reine Endungssperre erfasst z. B. eine EBCDIC-
# Mainframe-Datei wie AWS.M2.CARDDEMO.ACCTDATA.PS nicht -- ".PS" sieht wie
# eine normale Textdatei aus, der Byteinhalt ist aber kein UTF-8 und
# "dekodiert" mit errors="ignore" zu genau demselben Steuerzeichen-Datenmüll
# wie ein Bild (live an diesem Fund beobachtet, siehe O-072s Notiz zu
# GitConnector._save_document_chunks). Anteil an nicht druckbaren
# Steuerzeichen (Whitespace ausgenommen), ab dem eine ansonsten gültige
# UTF-8-Datei als Datenmüll statt als Text gilt.
_MAX_CONTROL_CHAR_RATIO = 0.05


def _looks_like_text(raw: bytes) -> bool:
    """True, wenn `raw` sinnvoll als Text embedd-bar ist: gültiges UTF-8
    UND kein ungewöhnlich hoher Anteil an Steuerzeichen danach. EBCDIC (und
    andere Nicht-UTF-8-Kodierungen) fallen bereits beim strikten Decode
    durch; ein paar vereinzelte Steuerzeichen in echtem Text (z. B. Form
    Feed in alten COBOL-Quellen) bleiben unter der Schwelle toleriert."""
    if not raw:
        return True
    try:
        text, _ = decode_source(raw)
    except SourceDecodeError:
        return False
    return looks_like_text(text, _MAX_CONTROL_CHAR_RATIO)


# AP-4: Sprachen mit einem Eintrag in STRUCTURE_PARSERS (O-077) bekommen eine
# echte Strukturanalyse (parser/cobol/) statt des generischen CodeParser-
# Zeilenchunkings.


async def _run_prepare_hooks(
    wt: str,
    extensions: dict[str, set[str]],
    profiles_by_path: dict[str, BuildProfile | None] | None = None,
) -> dict[str, Any]:
    """O-079: ruft für jede Sprache mit Registry-Eintrag deren optionalen
    `prepare_source()`-Hook einmal auf, bevor die erste Datei dieser Sprache
    geparst wird -- generisch über STRUCTURE_PARSERS (core/registry.py),
    ohne dass dieser Connector weiß, was ein Hook tut oder wie er heißt.
    Vorher rief fetch_documents() dafür `_build_copybook_index()` fest
    verdrahtet auf, eine COBOL-spezifische Voranalyse mitten im sonst
    sprachneutralen Connector-Code.

    Mehrere Sprachen können sich denselben Hook teilen (COBOL/Copybook teilen
    sich `prepare_copybook_index` für den quellenweiten Copybook-Index) --
    der läuft dann trotzdem nur einmal, nicht pro Sprache."""
    prepared: dict[str, Any] = {}
    results_by_hook: dict[int, Any] = {}
    for lang, entry in STRUCTURE_PARSERS.items():
        hook = entry.prepare_source
        if hook is None:
            continue
        key = id(hook)
        if key not in results_by_hook:
            results_by_hook[key] = await asyncio.to_thread(
                hook, wt, extensions, profiles_by_path or {}
            )
        prepared[lang] = results_by_hook[key]
    return prepared


# Nur der Fetch/Worktree-Schritt läuft unter diesem Lock, nicht das komplette
# Einbetten — sonst blockiert ein langer Embed-Lauf jeden anderen Sync
# desselben Bare-Mirrors unnötig lange.
_GIT_FETCH_LOCK_SECONDS = 600


def _resolve_extension_config(spaces: dict) -> dict[str, set[str]]:
    """Konfigurierbar über DOCTUS_LANGUAGE_EXTENSIONS (Worker-weiter Default)
    und optional spaces.language_extensions (überschreibt pro Wissensquelle).
    Beide erwarten ein Mapping aus Sprachlabeln auf Dateiendungen. Die
    eingebauten Standard-Endungen decken gängige Programmiersprachen ab;
    die Konfiguration dient nur noch für kundenspezifische Endungen oder
    bewusste Overrides.

    O-078: der Schlüssel hieß bis 06.09.2026 `cobol_extensions`, obwohl
    `classify_extension()`/`_DEFAULT_EXTENSIONS` selbst nichts COBOL-
    Spezifisches tun (reine Endung-zu-Label-Zuordnung). Der alte Schlüssel
    wird als Fallback weitergelesen, damit bestehende Wissensquellen mit
    gespeicherter Alt-Konfiguration nicht brechen."""
    cfg = dict(_DEFAULT_EXTENSIONS)

    raw_env = os.environ.get("DOCTUS_LANGUAGE_EXTENSIONS") or os.environ.get(
        "DOCTUS_COBOL_EXTENSIONS"
    )
    if raw_env:
        try:
            cfg.update({k: set(v) for k, v in json.loads(raw_env).items()})
        except Exception:
            logger.warning("DOCTUS_LANGUAGE_EXTENSIONS ist kein gültiges JSON, ignoriere.")

    override = None
    if isinstance(spaces, dict):
        override = spaces.get("language_extensions") or spaces.get("cobol_extensions")
    if override:
        cfg.update({k: set(v) for k, v in override.items()})

    return {k: {e.lower() for e in exts} for k, exts in cfg.items()}


def classify_extension(
    path: str, extensions: dict[str, set[str]], content: str | bytes | None = None
) -> str:
    """Backward-compatible name for the repository language detector."""
    return detect_language(path, extensions, content=content)


def _is_java_build_excluded(path: str, extensions: dict[str, set[str]]) -> bool:
    if classify_extension(path, extensions) != "java":
        return False
    return any(
        part.lower() in _JAVA_BUILD_EXCLUDED_DIRS
        for part in path.replace("\\", "/").split("/")[:-1]
    )


def _fingerprint_libraries(
    path: str,
    language: str,
    existing: SourceScanFile | None,
    copybook_hashes: dict[str, str],
    copybook_index: CopybookIndex | None,
) -> dict[str, str] | None:
    """O-137: präzise statt konservative Bibliotheks-Menge für den Analyse-
    Fingerprint, wo sicher möglich - sonst wie vor O-137 der GESAMTE
    Copybook-Bestand (kann nie eine betroffene Änderung übersehen).

    - Copybook-Dateien: die AST-Kette aus dem Pass-0-Index
      (`copybook.transitive_dependencies()`) ist bei jedem Sync ohnehin
      schon vollständig aufgebaut - kein Zusatzaufwand, kein "Henne-Ei"-
      Problem wie bei Programmen (siehe unten).
    - Programme: deren eigene COPY-Ziele sind an dieser Stelle unbekannt,
      ohne die Datei selbst schon strukturell zu parsen - genau das soll
      der Fingerprint-Vergleich ja gerade vermeiden. Es wird deshalb die
      beim LETZTEN erfolgreichen Parse entdeckte Menge verwendet
      (`SourceScanFile.copybook_dependencies`, siehe _save_document_chunks());
      ohne einen solchen Eintrag (neue Datei, oder eine, deren COPY-Kette
      zuletzt nicht eindeutig auflösbar war) bleibt es konservativ.
    """
    if language not in {"cobol", "copybook"}:
        return None

    if language == "copybook" and copybook_index is not None:
        visited, ambiguous = copybook_mod.transitive_dependencies([path], copybook_index)
        if not ambiguous:
            return {p: copybook_hashes[p] for p in visited if p in copybook_hashes}

    if language == "cobol" and existing is not None and existing.copybook_dependencies is not None:
        # Ein seither gelöschtes Copybook fehlt in copybook_hashes - der
        # damit andere Fingerprint-Wert (statt KeyError) löst korrekt einen
        # Reparse aus, der die veraltete Abhängigkeit dann bereinigt.
        return {p: copybook_hashes.get(p, "") for p in existing.copybook_dependencies}

    return copybook_hashes


def _discover_copybook_dependencies(
    result: ParseResult, copybook_index: CopybookIndex | None
) -> set[str] | None:
    """O-137: die (transitiv) tatsächlich verwendete Copybook-Pfadmenge
    dieser gerade fertig geparsten Datei, oder None, wenn irgendein COPY-
    Vorkommen (direkt oder in der Kette) nicht eindeutig auflösbar war -
    dann bleibt die künftige Fingerprint-Eingrenzung für diese Datei
    konservativ (siehe _fingerprint_libraries()), statt eine unaufgelöste
    Abhängigkeit stillschweigend zu übersehen (E-2 "kein Raten")."""
    if copybook_index is None:
        return None
    copy_edges = [e for e in result.edges if e.type == "COPY"]
    if any(e.resolution != "resolved" for e in copy_edges):
        return None
    direct_paths = [
        copybook_mod.resolve_path(e.dst_name, (e.meta or {}).get("library"), copybook_index)
        for e in copy_edges
    ]
    direct_paths = [p for p in direct_paths if p is not None]
    if not direct_paths:
        return set()
    visited, ambiguous = copybook_mod.transitive_dependencies(direct_paths, copybook_index)
    return None if ambiguous else visited


def _analysis_dependency_paths(db, source_id: int) -> dict[str, set[str]]:
    """Return persisted file-to-file analysis dependencies for one source.

    The resolver stores resource targets in edge metadata, while code and
    resource edges may also already have a concrete ``dst_entity_id``. Using
    both forms means a changed, deleted, or moved target invalidates its
    unchanged caller on the next sync instead of leaving a stale edge behind.
    """
    entities = {
        entity.id: entity.file_path
        for entity in db.query(CodeEntity)
        .filter(CodeEntity.source_id == source_id)
        .all()
        if entity.file_path
    }
    dependencies: dict[str, set[str]] = defaultdict(set)
    for edge in db.query(CodeEdge).filter(CodeEdge.source_id == source_id).all():
        source_path = entities.get(edge.src_entity_id)
        if not source_path:
            continue
        metadata = edge.meta_json or {}
        target_path = metadata.get("target_file_path")
        if not target_path and edge.dst_entity_id:
            target_path = entities.get(edge.dst_entity_id)
        if target_path and target_path != source_path:
            dependencies[source_path].add(target_path)
    return dependencies


def _java_module_metadata_paths(path: str, current_paths: set[str]) -> set[str]:
    """Find checked-in build/module descriptors affecting a Java source file.

    This is intentionally path-based and conservative: Doctus does not run a
    Maven/Gradle build or resolve external dependencies. A module descriptor
    or build file changing is nevertheless enough reason to reparse the Java
    sources in that module.
    """
    module = module_from_path(path)
    module_root = "" if module in (None, ".") else module.strip("/")
    prefixes = [""]
    if module_root:
        parts = module_root.split("/")
        prefixes.extend("/".join(parts[:index]) for index in range(1, len(parts) + 1))

    dependencies: set[str] = set()
    for prefix in prefixes:
        for name in _JAVA_MODULE_METADATA_NAMES:
            candidate = f"{prefix}/{name}" if prefix else name
            if candidate in current_paths:
                dependencies.add(candidate)

    for candidate in current_paths:
        if not candidate.endswith("/module-info.java"):
            continue
        if not module_root or candidate.startswith(module_root + "/"):
            dependencies.add(candidate)
    return dependencies


_PROFILE_FIELDS = {
    "compiler_family",
    "compiler_version",
    "source_format",
    "source_columns",
    "encoding",
    "debug_mode",
    "literal_delimiter",
    "defines",
    "copy_search_order",
}


def _profile_fragment(raw: object) -> ProfileFragment | None:
    """Konvertiert die bereits gespeicherte Git-Quellenkonfiguration in ein
    O-121-Fragment. Eine Bedienoberfläche oder ein Importformat gehört weiter
    zu O-151; der Connector liest hier nur den bestehenden JSON-Konfigurations-
    container ``spaces.build_profile``.
    """
    if not isinstance(raw, dict):
        return None
    values = {key: value for key, value in raw.items() if key in _PROFILE_FIELDS}
    if not values:
        return None
    if isinstance(values.get("copy_search_order"), list):
        values["copy_search_order"] = tuple(values["copy_search_order"])
    if isinstance(values.get("source_columns"), dict):
        try:
            values["source_columns"] = SourceColumns(**values["source_columns"])
        except (TypeError, ValueError):
            # O-151 verantwortet die Konfigurationsoberfläche und ihre
            # Diagnose. Bis dahin darf ungültiges gespeichertes JSON keinen
            # Importabbruch verursachen; es wirkt schlicht nicht als Layout.
            values.pop("source_columns")
    return ProfileFragment(**values)


def _resolve_document_profile(spaces: dict, path: str) -> BuildProfile | None:
    """Löst das effektive O-121-Profil einer Git-Datei auf.

    ``build_profile.source`` gilt für das ganze Repository;
    ``build_profile.paths`` kann Verzeichnispräfixe gezielt übersteuern. Das
    ist absichtlich nur ein Lesekontrakt für die vorhandene JSON-Konfiguration
    (keine neue Einstellungsoberfläche, O-151). Bei überlappenden Präfixen
    gewinnt der längste, also spezifischste Pfad.
    """
    config = spaces.get("build_profile") if isinstance(spaces, dict) else None
    if not isinstance(config, dict):
        return None

    source = _profile_fragment(config.get("source", config))
    path_fragment = None
    path_configs = config.get("paths")
    if isinstance(path_configs, dict):
        normalized_path = path.strip("/")
        matches = [
            (prefix.strip("/"), raw)
            for prefix, raw in path_configs.items()
            if isinstance(prefix, str)
            and (
                normalized_path == prefix.strip("/")
                or normalized_path.startswith(prefix.strip("/") + "/")
            )
        ]
        if matches:
            _, raw = max(matches, key=lambda item: len(item[0]))
            path_fragment = _profile_fragment(raw)

    profile, _ = resolve_profile(source=source, path=path_fragment)
    return profile


def _reuse_unchanged_embeddings(
    chunks: list[dict], old_chunks: list[DocumentChunk], embedding_model: str | None = None
) -> list[dict]:
    """Übernimmt Vektoren textgleicher Vorgänger-Chunks und gibt nur die
    verbleibenden Inhalte zum neuen Embedding zurück (O-122)."""
    reusable = {
        chunk.content: chunk.embedding
        for chunk in old_chunks
        if chunk.embedding is not None
        and (
            embedding_model is None
            or getattr(chunk, "embedding_model", None) == embedding_model
        )
    }
    for chunk in chunks:
        if chunk["content"] in reusable:
            chunk["embedding"] = reusable[chunk["content"]]
    return [chunk for chunk in chunks if "embedding" not in chunk]


@asynccontextmanager
async def _git_fetch_lock(fingerprint: str, log=None):
    """Verhindert paralleles Fetch/Worktree-Setup auf demselben Bare-Mirror,
    wenn zwei Wissensquellen (verschiedene Branches) desselben Repos
    gleichzeitig synchronisieren. Anders als beim Sync-Lock ist Überspringen
    hier keine Option — der Fetch muss passieren — daher blockierendes Warten
    statt Verzicht."""
    lock_key = f"lock:git_fetch:{fingerprint}"
    owner = uuid.uuid4().hex
    waited = 0
    announced = False
    while not redis_client.set(lock_key, owner, nx=True, ex=_GIT_FETCH_LOCK_SECONDS):
        if not announced and log:
            log("Bare-Mirror wird gerade von einer anderen Wissensquelle aktualisiert, warte…")
            announced = True
        if waited >= _GIT_FETCH_LOCK_SECONDS:
            raise TimeoutError(
                f"Bare-Mirror-Lock für {fingerprint} nach {_GIT_FETCH_LOCK_SECONDS}s nicht frei geworden."
            )
        await asyncio.sleep(1)
        waited += 1
    try:
        yield
    finally:
        current = redis_client.get(lock_key)
        if current == owner.encode("utf-8"):
            redis_client.delete(lock_key)


class GitConnector(BaseConnector):
    """
    Connector für Git-Repositories. Bare-Mirror + Worktree statt Flat-Clone
    (F-019, monorepo-tauglich), resumable über SourceScanFile (NF-004).
    """

    def __init__(self, source_id: int) -> None:
        super().__init__(source_id)
        self._new_commit: str | None = None
        # O-079: pro Sprache das Ergebnis ihres optionalen prepare_source-
        # Hooks (STRUCTURE_PARSERS[lang], core/registry.py), gefüllt in
        # fetch_documents() bevor die erste Datei geparst wird. Für COBOL/
        # Copybook ist das der quellenweite Copybook-Index (Pass 0, AP-4),
        # den copybook.scan() zur COPY-Auflösung braucht -- dieser Connector
        # muss das aber nicht wissen, er reicht das Ergebnis nur durch.
        self._prepared_by_lang: dict[str, Any] = {}
        # O-122: `fetch_documents()` bestimmt das aufgelöste Profil zusammen
        # mit dem Resume-Fingerprint. Beim später parallel laufenden Parse
        # wird genau dieses Objekt verwendet, statt die Konfiguration erneut
        # (und potenziell anders) zu lesen.
        self._profiles_by_path: dict[str, BuildProfile | None] = {}
        # O-137: aktueller Copybook-Pfad -> Git-Blob-SHA, gefüllt in
        # fetch_documents() - _save_document_chunks() braucht das, um die
        # dort neu entdeckte Abhängigkeitsmenge in Blob-SHAs statt nur
        # Pfade umzuwandeln (siehe _discover_copybook_dependencies()).
        self._copybook_hashes: dict[str, str] = {}

    async def _embed_document(self, doc: Document, semaphore: asyncio.Semaphore):
        async with semaphore:
            # O-072: bis zu EMBED_CONCURRENCY Dateien laufen gleichzeitig,
            # aber vorher loggte nur "fertig"/"Fehler" pro Datei -- aus dem
            # Sync-Log allein ließ sich nie ablesen, an welcher Datei gerade
            # tatsächlich gearbeitet wird, nur wie viele noch offen sind.
            self._log(f"Embedding gestartet für '{doc['title']}'.")
            lang = doc.get("extra_meta", {}).get("language", "text")

            parse_result: ParseResult | None = None
            entry = STRUCTURE_PARSERS.get(lang)
            if entry is not None and not doc["extra_meta"].get("deleted"):
                # F-020…034: struktur-bewusstes Parsen statt generischem
                # Zeilenchunking - parse_program()/parse_copybook() (und jeder
                # weitere STRUCTURE_PARSERS-Eintrag, O-077) sind rein
                # in-memory (E-6), deshalb in einen Thread ausgelagert wie
                # das generische Chunking auch (CPU-gebunden, würde sonst den
                # Event-Loop blockieren). prepared_source ist das Ergebnis von
                # entry.prepare_source() (O-079), sofern die Sprache einen
                # Hook hat -- sonst None.
                profile = self._profiles_by_path.get(doc["storage_key"])
                parse_kwargs = {"prepared_source": self._prepared_by_lang.get(lang)}
                # Registry-Einträge sind bewusst auch für künftige, nicht
                # COBOL-spezifische Strukturparser offen (O-077). Nur ein
                # tatsächlich konfiguriertes COBOL-Profil wird deshalb als
                # zusätzlicher Parser-Eingabewert übergeben.
                if profile is not None:
                    parse_kwargs["profile"] = profile
                parse_result = await asyncio.to_thread(
                    entry.parse, doc["content"], doc["storage_key"], **parse_kwargs
                )
                chunks = [
                    {
                        "content": c.content,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "meta": c.meta,
                    }
                    for c in parse_result.chunks
                ]
            else:
                parser = CodeParser(lang)
                chunks = await asyncio.to_thread(
                    parser.chunk_file, doc["content"], chunk_size=config.CHUNK_SIZE
                )

            # O-122: Ein Profil- oder Bibliothekswechsel kann die Struktur
            # ändern, obwohl einzelne indexierbare Textpassagen identisch
            # bleiben. Diese Vektoren werden aus den bisherigen Chunks
            # wiederverwendet; nur wirklich neuer Inhalt geht an das
            # Embedding-Modell.
            old_chunks: list[DocumentChunk] = []
            if doc["extra_meta"].get("analysis_fingerprint"):
                old_chunks = (
                    self.db.query(DocumentChunk)
                    .filter(
                        DocumentChunk.source_id == self.source_id,
                        DocumentChunk.file_path == doc["storage_key"],
                    )
                    .all()
                )
            to_embed = _reuse_unchanged_embeddings(chunks, old_chunks, self.embedding_model)
            embeddings = []
            if to_embed:
                try:
                    embeddings = await get_embeddings_batch(
                        [c["content"] for c in to_embed], model=self.embedding_model
                    )
                except Exception as e:
                    # str(e) ist bei httpx.TimeoutException & Co. oft leer -- der
                    # Exception-Typname macht die Meldung erst brauchbar (sonst
                    # nur "Embedding-Fehler für X: " ohne jeden Hinweis, was
                    # schiefging). Datei ist trotzdem nicht verloren: chunks
                    # bleiben ohne "embedding"-Feld, reindex_chunks_preserving_links
                    # embedded sie unten einzeln nach (langsamer, aber vollständig).
                    self._log(f"Embedding-Fehler für '{doc['title']}': {type(e).__name__}: {e}")

            for chunk, embedding in zip(to_embed, embeddings):
                chunk["embedding"] = embedding

            return doc, chunks, parse_result

    async def _save_document_chunks(
        self, doc: Document, chunks: list[dict], parse_result: ParseResult | None = None
    ) -> int:
        def build_chunk(chunk, embedding):
            return DocumentChunk(
                project_id=self.source.project_id,
                source_id=self.source.id,
                file_path=doc["storage_key"],
                content=chunk["content"],
                start_line=chunk["start_line"],
                end_line=chunk["end_line"],
                embedding=embedding,
                embedding_model=self.embedding_model,
                metadata_json={
                    **doc["extra_meta"],
                    "url": doc["url"],
                    "title": doc["title"],
                    "source_type": doc["source_type"],
                    "embedding_model": self.embedding_model,
                    **(chunk.get("meta") or {}),
                },
            )

        async def embed_content(content):
            return await get_embedding(content, model=self.embedding_model)

        def on_embed_error(chunk, e):
            # Without this, a chunk that fails the per-chunk fallback embed
            # inside reindex_chunks_preserving_links (get_embedding has no
            # retry, unlike the batch path above) was dropped in complete
            # silence -- the file still logged as "'X' indexiert (0 Chunks)",
            # indistinguishable from a genuinely empty file like .gitkeep.
            # Found via a real CardDemo import: an EBCDIC data file's batch
            # embed failed (logged), the fallback then failed for every one
            # of its chunks too, and none of that showed up anywhere.
            self._log(
                f"Embedding-Fehler für '{doc['title']}' (Chunk übersprungen): {type(e).__name__}: {e}"
            )

        path = doc["storage_key"]
        try:
            count = await reindex_chunks_preserving_links(
                self.db,
                source_id=self.source.id,
                file_path=path,
                chunks=chunks,
                build_chunk=build_chunk,
                embed_content=embed_content,
                on_embed_error=on_embed_error,
            )

            # NF-004: SourceScanFile wird im selben Commit wie die Chunks
            # aktualisiert — bricht der Sync danach ab, überspringt der Resume-Check
            # in fetch_documents() diese Datei beim nächsten Anlauf.
            if doc["extra_meta"].get("deleted"):
                self.db.query(SourceScanFile).filter(
                    SourceScanFile.source_id == self.source_id,
                    SourceScanFile.file_path == path,
                ).delete()
                # Entities dieser Datei sind wirklich weg (nicht nur reparst) -
                # CASCADE auf eingehende Kanten aus anderen Dateien ist hier
                # korrekt, anders als beim Reparse-Fall in structure_persist.py.
                # Java-Package-/Module-Entities sind allerdings dateiübergreifend
                # geteilt und werden deshalb vor dem Löschen umgehängt.
                _delete_file_entities(self.db, source_id=self.source_id, file_path=path)
            else:
                content_hash = doc["extra_meta"]["content_hash"]
                fingerprint = doc["extra_meta"].get("analysis_fingerprint")

                language = doc["extra_meta"].get("language", "text")
                encoding = doc["extra_meta"].get("encoding")
                parse_status = "text_fallback"
                parse_error = f"Sprache '{language}' hat keinen Strukturparser; als Text indexiert."
                if parse_result is not None:
                    # O-120: `errors == []` allein hieß bisher "ok" -- das
                    # übersah die O-119-Diagnosen (z.B. ein ANTLR-Syntaxfehler,
                    # der `errors` nie erreicht) und behandelte den F-029-
                    # Textfallback (keine PROCEDURE DIVISION) wie einen
                    # gewöhnlichen Fehlerfall statt wie eine eigene, dritte
                    # Kategorie. `classify_completeness()` bewertet stattdessen
                    # errors + diagnostics + den Fallback-Chunk-Marker
                    # gemeinsam (siehe core/model.py für die vier Werte).
                    parse_status, reasons = classify_completeness(parse_result)
                    parse_error = "; ".join(reasons) or None
                    persist_parse_result(
                        self.db,
                        project_id=self.source.project_id,
                        source_id=self.source_id,
                        file_path=path,
                        content_hash=content_hash,
                        result=parse_result,
                    )
                    # O-137: die gerade entdeckte (transitive) Copybook-
                    # Abhängigkeit dieser Datei für den NÄCHSTEN Sync
                    # merken, damit dessen Fingerprint-Vergleich präzise
                    # statt konservativ eingrenzen kann (siehe
                    # _fingerprint_libraries()). None (nicht eindeutig
                    # auflösbar) bleibt bewusst None statt {} - das ist der
                    # Unterschied zwischen "keine Abhängigkeiten" und
                    # "unbekannt, konservativ bleiben".
                    dependency_paths = _discover_copybook_dependencies(
                        parse_result, self._prepared_by_lang.get("cobol")
                    )
                    copybook_dependencies = (
                        {p: self._copybook_hashes.get(p, "") for p in dependency_paths}
                        if dependency_paths is not None
                        else None
                    )

                existing = (
                    self.db.query(SourceScanFile)
                    .filter(
                        SourceScanFile.source_id == self.source_id,
                        SourceScanFile.file_path == path,
                    )
                    .first()
                )
                if existing:
                    existing.content_hash = content_hash
                    existing.analysis_fingerprint = fingerprint
                    existing.language = language
                    existing.encoding = encoding
                    if parse_result is not None:
                        existing.parse_status = parse_status
                        existing.parse_error = parse_error
                        existing.copybook_dependencies = copybook_dependencies
                else:
                    self.db.add(
                        SourceScanFile(
                            source_id=self.source_id,
                            file_path=path,
                            content_hash=content_hash,
                            analysis_fingerprint=fingerprint,
                            parse_status=parse_status,
                            parse_error=parse_error,
                            language=language,
                            encoding=encoding,
                            copybook_dependencies=(
                                copybook_dependencies if parse_result is not None else None
                            ),
                        )
                    )

            self.db.commit()
            return count

        except Exception as e:
            # F-029 gilt auch für DB-seitige Persistenzfehler (z.B. ein
            # Constraint-Verstoß durch einen Parser-Grenzfall), nicht nur für
            # nicht-lesbare Dateien: eine einzelne Datei darf nie den
            # gesamten Sync mitreißen. Ohne den Rollback hier bliebe die
            # Session nach einem fehlgeschlagenen flush() "vergiftet" - jeder
            # weitere Query/Commit in diesem Sync-Lauf würde mit derselben
            # "transaction has been rolled back"-Meldung fehlschlagen.
            self.db.rollback()
            error_msg = str(e)
            self._log(f"Fehler bei '{doc['title']}', Datei übersprungen: {error_msg}")

            if not doc["extra_meta"].get("deleted"):
                content_hash = doc["extra_meta"].get("content_hash", "")
                fingerprint = doc["extra_meta"].get("analysis_fingerprint")
                existing = (
                    self.db.query(SourceScanFile)
                    .filter(
                        SourceScanFile.source_id == self.source_id,
                        SourceScanFile.file_path == path,
                    )
                    .first()
                )
                if existing:
                    existing.content_hash = content_hash
                    existing.analysis_fingerprint = fingerprint
                    existing.parse_status = "error"
                    existing.parse_error = error_msg
                    existing.language = doc["extra_meta"].get("language", "text")
                    existing.encoding = doc["extra_meta"].get("encoding")
                else:
                    self.db.add(
                        SourceScanFile(
                            source_id=self.source_id,
                            file_path=path,
                            content_hash=content_hash,
                            analysis_fingerprint=fingerprint,
                            parse_status="error",
                            parse_error=error_msg,
                            language=doc["extra_meta"].get("language", "text"),
                            encoding=doc["extra_meta"].get("encoding"),
                        )
                    )
                self.db.commit()

            return 0

    def _record_skip(
        self,
        path: str,
        content_hash: str,
        fingerprint: str,
        reason: str,
        *,
        language: str = "text",
        encoding: str | None = None,
    ) -> None:
        """O-120: eine Datei, die wegen `_SKIPPED_BINARY_EXTENSIONS`, der
        Größengrenze oder fehlgeschlagener UTF-8-Erkennung nie an
        `_save_document_chunks()` geht, hinterließ bisher NUR eine
        `self._log()`-Zeile -- kein SourceScanFile-Eintrag, also unsichtbar
        für Diagnosebericht/Editor/API. Damit fehlte "übersprungen" als
        eigener, abfragbarer Status komplett (siehe core/model.py::
        AnalysisStatus). Contentbezogener Hash ist an dieser Stelle im
        `to_process`-Loop bereits bekannt, macht die Datei damit auch
        resumable wie jede embedded Datei.
        """
        existing = (
            self.db.query(SourceScanFile)
            .filter(SourceScanFile.source_id == self.source_id, SourceScanFile.file_path == path)
            .first()
        )
        if existing:
            existing.content_hash = content_hash
            existing.analysis_fingerprint = fingerprint
            existing.parse_status = "skipped"
            existing.parse_error = reason
            existing.language = language
            existing.encoding = encoding
        else:
            self.db.add(
                SourceScanFile(
                    source_id=self.source_id,
                    file_path=path,
                    content_hash=content_hash,
                    analysis_fingerprint=fingerprint,
                    parse_status="skipped",
                    parse_error=reason,
                    language=language,
                    encoding=encoding,
                )
            )
        self.db.commit()

    async def fetch_documents(self, force_reindex: bool = False) -> AsyncIterator[Document]:
        spaces = self.source.spaces or {}
        if isinstance(spaces, str):
            try:
                spaces = json.loads(spaces)
            except Exception:
                spaces = {}

        requested_branch = self.source.branch or spaces.get("branch")
        sparse_paths = spaces.get("sparse_paths")
        extensions = _resolve_extension_config(spaces)

        if not self.source.repo_fingerprint:
            self.source.repo_fingerprint = git_utils.compute_repo_fingerprint(self.source.url)
            self.db.commit()
        fingerprint = self.source.repo_fingerprint

        auth_url = get_authenticated_url(self.source.url, self.source.username, self.source.token)
        branch = (
            requested_branch
            or await asyncio.to_thread(git_utils.remote_default_branch, auth_url)
            or "main"
        )
        bare = git_utils.bare_path(REPOS_ROOT, fingerprint)
        wt = git_utils.worktree_path(REPOS_ROOT, self.source_id)

        async with _git_fetch_lock(fingerprint, log=self._log):
            await asyncio.to_thread(
                git_utils.ensure_bare_mirror, REPOS_ROOT, fingerprint, auth_url, self._log
            )
            await asyncio.to_thread(git_utils.fetch_branch, bare, branch, self._log)

            worktree_is_new = not os.path.isdir(wt)
            if worktree_is_new:
                await asyncio.to_thread(
                    git_utils.ensure_worktree, bare, wt, branch, sparse_paths, self._log
                )
            else:
                await asyncio.to_thread(git_utils.reset_worktree_to_branch, wt, branch)

        current_hashes = await asyncio.to_thread(git_utils.list_tracked_files, wt)
        excluded_java_paths = {
            path for path in current_hashes if _is_java_build_excluded(path, extensions)
        }
        if excluded_java_paths:
            self._log(
                f"{len(excluded_java_paths)} Java-Datei(en) aus Build-/IDE-Verzeichnissen werden ignoriert."
            )
        profiles_by_path = {
            path: _resolve_document_profile(spaces, path)
            for path in current_hashes
            if classify_extension(path, extensions) in {"cobol", "copybook"}
        }

        # O-079: registry-deklarierte Vorlauf-Hooks statt eines fest
        # benannten _build_copybook_index()-Aufrufs - für COBOL/Copybook
        # baut das (wie zuvor) bei jedem Sync über den vollen Baum den
        # Copybook-Index (Pass 0, Plan §6.4/E-2), siehe
        # cobol/prepare.py::prepare_copybook_index.
        self._prepared_by_lang = await _run_prepare_hooks(wt, extensions, profiles_by_path)

        new_commit = await asyncio.to_thread(git_utils.current_commit, wt)
        self._new_commit = new_commit
        cursor = self.source.sync_cursor or {}
        old_commit = cursor.get("last_commit")

        # O-122: Der bisherige Resume-Schlüssel bestand nur aus dem Blob-SHA.
        # Ein unveränderter Git-Commit durfte deshalb sofort zurückkehren,
        # obwohl ein Profil-, Parser- oder Copybook-Wechsel dasselbe Programm
        # anders analysieren kann. Der Git-Index ist billig zu lesen; wir
        # vergleichen daher bei jedem Lauf pro materialisierter Datei den
        # vollständigen Analyse-Fingerprint. Unveränderte Eingaben bleiben
        # weiterhin ohne Datei-I/O, Parse oder Embedding inkrementell.
        existing_records = {
            r.file_path: r
            for r in self.db.query(SourceScanFile)
            .filter(SourceScanFile.source_id == self.source_id)
            .all()
        }
        # Excluded build/vendor files are deliberately journaled as skipped
        # below. They first pass through the deletion path so stale chunks and
        # entities cannot remain searchable, then receive a visible skip row.
        deleted_paths = sorted((set(existing_records) - set(current_hashes)) | excluded_java_paths)

        if worktree_is_new or not old_commit:
            self._log("Vollständige Ersteinlesung des Worktrees…")
        elif force_reindex:
            self._log("Vollständige Neu-Analyse erzwungen; alle Dateien werden erneut verarbeitet…")
        elif old_commit == new_commit:
            self._log("Repository unverändert; prüfe Analyse-Fingerprints…")

        copybook_hashes = {
            path: blob_sha
            for path, blob_sha in current_hashes.items()
            if os.path.splitext(path)[1].lower() in extensions.get("copybook", set())
        }
        self._copybook_hashes = copybook_hashes
        analysis_dependencies = _analysis_dependency_paths(self.db, self.source_id)

        # Resumability (NF-004) bleibt erhalten, jetzt aber über sämtliche
        # Analyse-Eingaben. O-137: statt IMMER der gesamten Copybook-Sammlung
        # (konservativ, kann nie einen COPY-Aufrufer übersehen, invalidiert
        # dafür aber jede Datei bei JEDER Copybook-Änderung) grenzt
        # _fingerprint_libraries() dort präzise ein, wo das sicher möglich
        # ist - Details dort.
        # O-176: `language` MUSS hier mit durchgereicht werden. Vor O-122 stand
        # dieselbe Klassifikation direkt in der Verarbeitungsschleife unten (als
        # `lang`); O-122 zog sie für die Fingerprint-Berechnung hierher vor, ohne
        # sie an `to_process` weiterzugeben -- die Verarbeitungsschleife griff
        # seither auf denselben Schleifenvariablennamen `language` zu, der dort
        # nie neu zugewiesen wurde und deshalb den Wert der ALPHABETISCH LETZTEN
        # Datei aus dieser Schleife trug (Python kennt keine Block-Scopes).
        # Live an CardDemo beobachtet: letzte sortierte Datei war
        # 'scripts/upld_module.sh' -> 'text', wodurch jede COBOL-/Copybook-Datei
        # im Repo mit `language="text"` embedded wurde -- STRUCTURE_PARSERS.get()
        # traf nie, `parse_result` blieb None, persist_parse_result() lief nie,
        # macht code_entities/code_edges für JEDEN Git-Sync seit O-122 leer
        # (0 Zeilen bestandsweit bestätigt, nicht nur bei CardDemo).
        copybook_index = self._prepared_by_lang.get("cobol")
        to_process: list[tuple[str, str, str, str]] = []
        excluded_fingerprints: dict[str, tuple[str, str, str]] = {}
        self._profiles_by_path.clear()
        fingerprint_inputs: dict[str, dict[str, Any]] = {}
        for path, blob_sha in sorted(current_hashes.items()):
            language = classify_extension(path, extensions)
            profile = profiles_by_path.get(path)
            parser_entry = STRUCTURE_PARSERS.get(language)
            dependencies = {
                f"module:{dependency}": current_hashes[dependency]
                for dependency in _java_module_metadata_paths(path, current_hashes)
            }
            fingerprint_inputs[path] = {
                "source_revision": blob_sha,
                "profile": profile,
                "parser_version": (
                    parser_entry.parser_version if parser_entry else "generic-chunker-2"
                ),
                "grammar_version": (
                    parser_entry.grammar_fingerprint()
                    if parser_entry and parser_entry.grammar_fingerprint
                    else "not-applicable"
                ),
                "libraries": _fingerprint_libraries(
                    path, language, existing_records.get(path), copybook_hashes, copybook_index
                ),
                "dependencies": dependencies,
                "embedding_model": self.embedding_model,
            }
            if os.path.splitext(path)[1].lower() == ".properties":
                fingerprint_inputs[path]["decoder_policy"] = (
                    "properties-utf8-then-iso-8859-1-v1"
                    if profile is None or not profile.encoding
                    else f"properties-explicit-{profile.encoding}-v1"
                )
        base_fingerprints = {
            path: analysis_fingerprint(**inputs)
            for path, inputs in fingerprint_inputs.items()
        }

        def expected_fingerprint(path: str, stack: frozenset[str] = frozenset()) -> str:
            """Build the current fingerprint including persisted dependencies."""
            inputs = fingerprint_inputs.get(path)
            if inputs is None:
                existing = existing_records.get(path)
                return existing.analysis_fingerprint or "" if existing else ""
            if path in stack:
                # Cyclic includes/imports are valid. The base fingerprint keeps
                # the cycle finite while direct content/model/parser changes
                # still invalidate every member of the cycle.
                return base_fingerprints[path]
            dependencies = dict(inputs.get("dependencies") or {})
            for dependency in sorted(analysis_dependencies.get(path, ())):
                dependencies[f"source:{dependency}:content_hash"] = current_hashes.get(dependency, "")
                dependencies[f"source:{dependency}:analysis_fingerprint"] = expected_fingerprint(
                    dependency, stack | {path}
                )
            return analysis_fingerprint(**{**inputs, "dependencies": dependencies})

        for path, blob_sha in sorted(current_hashes.items()):
            content_hash = git_utils.blob_content_hash(blob_sha)
            language = classify_extension(path, extensions)
            fingerprint = expected_fingerprint(path)
            if path in excluded_java_paths:
                excluded_fingerprints[path] = (content_hash, fingerprint, language)
                continue
            existing = existing_records.get(path)
            if (
                not force_reindex
                and existing
                and existing.language is not None
                and existing.analysis_fingerprint == fingerprint
            ):
                continue
            self._profiles_by_path[path] = profiles_by_path.get(path)
            to_process.append((path, content_hash, fingerprint, language))

        total = len(to_process) + len(deleted_paths)
        self.source.total_files = total
        self.db.commit()

        # O-075: parsed_files/progress werden NICHT hier gesetzt -- das würde nur
        # zählen, was gelesen und in die Embedding-Pipeline eingereiht wurde,
        # nicht was tatsächlich fertig embedded/gespeichert ist. Reines Einlesen
        # ist schnell (lokaler Datenträger); sobald es durch ist, bliebe die
        # Anzeige für den ganzen restlichen (oft langen) Embedding-Nachlauf
        # eingefroren, obwohl im Hintergrund echt weitergearbeitet wird -- live
        # am CardDemo-Import beobachtet. Die tatsächliche Fortschrittsmeldung
        # sitzt jetzt in sync()s Abschluss-Verarbeitung (`for t in done:`), wo
        # ein Dokument wirklich fertig ist.
        for path in deleted_paths:
            yield Document(
                title=os.path.basename(path),
                content="",
                url=None,
                source_type="Git",
                storage_key=path,
                extra_meta={"language": "text", "branch": branch, "deleted": True},
            )

        for path in sorted(excluded_java_paths):
            content_hash, fingerprint, language = excluded_fingerprints[path]
            reason = "Build-/IDE-Verzeichnis ausgeschlossen; nicht als Quellcode indexiert."
            self._log(f"[SKIP] '{path}' {reason}")
            self._record_skip(
                path,
                content_hash,
                fingerprint,
                reason,
                language=language,
            )

        for path, content_hash, analysis_fp, language in to_process:
            if os.path.splitext(path)[1].lower() in _SKIPPED_BINARY_EXTENSIONS:
                reason = "Binärformat ohne Textextraktion, wird nicht embedded."
                self._log(f"[SKIP] '{path}' ist ein {reason}")
                self._record_skip(path, content_hash, analysis_fp, reason, language="binary")
                continue
            full_path = os.path.join(wt, path)
            try:
                file_size = os.path.getsize(full_path)
            except OSError:
                continue
            if file_size > MAX_READ_BYTES:
                reason = f"überschreitet {MAX_READ_BYTES // (1024 * 1024)} MB, nicht embedded."
                self._log(f"[SKIP] '{path}' {reason}")
                self._record_skip(path, content_hash, analysis_fp, reason, language=language)
                continue
            try:
                with open(full_path, "rb") as f:
                    raw = f.read(MAX_READ_BYTES)
            except Exception as e:
                self._log(f"Fehler beim Lesen von '{path}': {e}")
                continue
            profile = profiles_by_path.get(path)
            try:
                configured_encoding = profile.encoding if profile is not None else None
                is_properties = os.path.splitext(path)[1].lower() == ".properties"
                content, codec = decode_source(
                    raw,
                    configured_encoding,
                    fallback_encoding=(
                        "iso-8859-1"
                        if is_properties and not configured_encoding
                        else None
                    ),
                )
            except SourceDecodeError as error:
                reason = f"{error} (vermutlich Binärdaten), wird nicht embedded."
                self._log(f"[SKIP] '{path}' ist {reason}")
                self._record_skip(path, content_hash, analysis_fp, reason, language=language)
                continue
            # The bounded content signal completes extension-based detection
            # for extensionless shell scripts without executing them.
            language = classify_extension(path, extensions, content=content)
            if not looks_like_text(content, _MAX_CONTROL_CHAR_RATIO):
                reason = (
                    f"kein sinnvoller {codec}-Text (zu viele Steuerzeichen), wird nicht embedded."
                )
                self._log(f"[SKIP] '{path}' ist {reason}")
                self._record_skip(
                    path,
                    content_hash,
                    analysis_fp,
                    reason,
                    language=language,
                    encoding=codec,
                )
                continue
            # O-175: looks_like_text() lässt leeren Inhalt bewusst durch (siehe
            # test_looks_like_text_accepts_empty_content) -- eine 0-Byte-Datei ist
            # kein Datenmüll, nur ohne Inhalt. folder.py/webdav.py überspringen so
            # etwas bereits ("[SKIP] Kein Textinhalt"), GitConnector tat das nicht
            # und ließ das Dokument bis zu _process_document()/_save_document_chunks()
            # durchlaufen, wo chunk_file("") eine leere Chunk-Liste liefert -- sichtbar
            # nur als irreführendes "indexiert (0 Chunks)" im Sync-Log, ohne den
            # skipped-Status aus O-120. Live an CardDemos 0-Byte-Marker-Dateien unter
            # scripts/markers/ beobachtet (CUSTFILE, CVTRA02Y, READCUST, ...).
            if not content.strip():
                reason = "leer (keine Textinhalte), wird nicht embedded."
                self._log(f"[SKIP] '{path}' ist {reason}")
                self._record_skip(
                    path,
                    content_hash,
                    analysis_fp,
                    reason,
                    language=language,
                    encoding=codec,
                )
                continue

            yield Document(
                title=os.path.basename(path),
                content=content,
                url=None,
                source_type="Git",
                storage_key=path,
                extra_meta={
                    "language": language,
                    "branch": branch,
                    "content_hash": content_hash,
                    "analysis_fingerprint": analysis_fp,
                    "encoding": codec,
                },
            )

    async def sync(self, force_reindex: bool = False) -> None:
        """
        Orchestriert Chunking und Embedding parallel (Semaphore), DB-Schreiben
        sequenziell. Der Git-Fetch/Worktree-Schritt selbst läuft unter einem
        eigenen, engeren Lock (siehe _git_fetch_lock) innerhalb von
        fetch_documents().
        """
        lock_key = f"lock:sync_source:{self.source_id}"
        lock_owner = uuid.uuid4().hex
        if not redis_client.set(lock_key, lock_owner, nx=True, ex=_SYNC_LOCK_LEASE_SECONDS):
            logger.warning(
                f"[Connector] Sync für KnowledgeSource {self.source_id} läuft bereits (Lock aktiv), überspringe."
            )
            return

        try:
            self.source = (
                self.db.query(KnowledgeSource).filter(KnowledgeSource.id == self.source_id).first()
            )
            if not self.source:
                logger.error(f"[Connector] KnowledgeSource {self.source_id} nicht gefunden.")
                return
            self.embedding_model = self.source.embedding_model or config.EMBED_MODEL

            self._sync_start_time = datetime.now(timezone.utc)
            self.source.sync_status = "syncing"
            self.source.parse_started_at = self._sync_start_time
            self.source.progress = 0
            self.source.progress_message = "Initialisiere…"
            self.source.last_error = None
            self.source.sync_log = ""
            self.db.commit()

            self._log(
                f"Starte Sync für '{self.source.name}' "
                f"(ID: {self.source_id}, Typ: {self.source.type})…"
            )
            self._log(f"Stelle sicher, dass Embedding-Modell '{self.embedding_model}' bereit ist…")
            await ensure_model_pulled(self.embedding_model)

            # O-071: CPU-only-Ollama rechnet Batches intern sequentiell --
            # EMBED_CONCURRENCY parallele Anfragen stauen sich dort nur und
            # laufen in Timeout/Fallback-Schleifen. GPU-Installationen
            # profitieren dagegen von echter Nebenläufigkeit, daher pro
            # Sync-Start neu ermitteln statt pauschal zu drosseln.
            if await is_gpu_accelerated(self.embedding_model):
                embed_concurrency = config.EMBED_CONCURRENCY
            else:
                embed_concurrency = min(config.EMBED_CONCURRENCY, config.EMBED_CONCURRENCY_CPU_ONLY)
                self._log(
                    f"Ollama läuft CPU-only — drossle Embedding-Nebenläufigkeit auf {embed_concurrency} "
                    f"(statt {config.EMBED_CONCURRENCY})."
                )
            semaphore = asyncio.Semaphore(embed_concurrency)
            pending_tasks = set()

            async def doc_producer():
                async for doc in self.fetch_documents(force_reindex=force_reindex):
                    task = asyncio.create_task(self._embed_document(doc, semaphore))
                    yield task

            total_chunks = 0
            processed = 0

            async for task in doc_producer():
                pending_tasks.add(task)
                redis_client.expire(lock_key, _SYNC_LOCK_LEASE_SECONDS)

                if len(pending_tasks) >= 50:
                    done, pending_tasks = await asyncio.wait(
                        pending_tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for t in done:
                        doc, chunks, parse_result = await t
                        chunk_count = await self._save_document_chunks(doc, chunks, parse_result)
                        total_chunks += chunk_count
                        processed += 1
                        self.has_changes = True
                        self._log(f"'{doc['title']}' indexiert ({chunk_count} Chunks).")
                        # O-075: parsed_files/progress hier setzen, nicht beim
                        # Einreihen (siehe fetch_documents()) -- das bildet ab,
                        # wie viele Dateien wirklich fertig sind, statt nur
                        # eingelesen, und friert dadurch nicht ein, während im
                        # Hintergrund noch an den letzten (oft langsamen)
                        # Dateien gearbeitet wird.
                        self.source.parsed_files = processed
                        self._update_progress(
                            processed,
                            self.source.total_files,
                            f"{processed} von {self.source.total_files} Dateien fertig",
                        )

            if pending_tasks:
                done, _ = await asyncio.wait(pending_tasks)
                for t in done:
                    doc, chunks, parse_result = await t
                    chunk_count = await self._save_document_chunks(doc, chunks, parse_result)
                    total_chunks += chunk_count
                    processed += 1
                    self.has_changes = True
                    self._log(f"'{doc['title']}' indexiert ({chunk_count} Chunks).")
                    self.source.parsed_files = processed
                    self._update_progress(
                        processed,
                        self.source.total_files,
                        f"{processed} von {self.source.total_files} Dateien fertig",
                    )

            # Pass 2 (Plan §6.4, E-1): globale Kanten (CALL/COPY) über den
            # gesamten Sync-Lauf hinweg nachauflösen - erst jetzt sind alle in
            # diesem Lauf geparsten Programme/Copybooks als Entities da.
            resolved = await asyncio.to_thread(resolve_global_edges, self.db, self.source_id)
            if resolved:
                self._log(f"Kanten-Nachauflösung: {resolved} CALL/COPY-Kante(n) aufgelöst.")

            # sync_cursor erst nach erfolgreichem Durchlauf vorrücken, damit ein
            # Abbruch den nächsten Sync exakt denselben Diff neu berechnen lässt
            # (der Resume-Check in fetch_documents() überspringt dann alles
            # bereits persistierte).
            if self._new_commit:
                self.source.sync_cursor = {"last_commit": self._new_commit}

            self.source.last_synced_at = self._sync_start_time
            self.source.sync_status = "completed"
            self.source.parse_finished_at = datetime.now(timezone.utc)
            self.source.progress = 100
            self.source.progress_message = "Synchronisierung abgeschlossen"
            self.db.commit()
            self._log(
                f"Sync abgeschlossen — {processed} Dokument(e), {total_chunks} Chunks gesamt."
            )

        except Exception as e:
            error_msg = str(e)
            self._log(f"Kritischer Fehler beim Sync: {error_msg}")
            if self.source:
                self.source.sync_status = "error"
                self.source.last_error = error_msg
                self.db.commit()
        finally:
            self.db.close()
            current_owner = redis_client.get(lock_key)
            if current_owner == lock_owner.encode("utf-8"):
                redis_client.delete(lock_key)
