"""
backend/services/chat_sources.py
================================
Quellenprüfung einer Chat-Antwort.

Eine Antwort darf nur auf Fundstellen verweisen, die in dieser Runde tatsächlich
abgerufen wurden (Vektor-Treffer, gepinnte Chunks, Werkzeugergebnisse des
Agenten). Dieses Modul sammelt diese Kandidaten, prüft Zitate und
Beziehungsaussagen der fertigen Antwort dagegen und löst die zitierten Stellen
zu den Quellen auf, die das Frontend als „Referenzierte Quellen" anzeigt.

Keine HTTP-, Streaming- oder Persistenzlogik: Eingabe sind Antworttext,
Werkzeugereignisse und Kandidaten, Ausgabe geprüfter Text und Quellenliste.
"""

import json
import logging
import os
import re
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from core.analysis_status import load_analysis_status
from core.projects import resolve_repository_id
from doctus_models.database import DocumentChunk, KnowledgeSource
from services.provenance import build_provenance

logger = logging.getLogger(__name__)


def record_agent_source(
    agent_sources: list,
    file_path: str,
    start_line: int,
    end_line: int,
    source_id: Optional[int],
) -> None:
    """Fügt eine vom Agenten tatsächlich gelesene Datei/Zeile zu den Quellen hinzu (dedupliziert)."""
    lines = [start_line, end_line]
    if any(s["file"] == file_path and s["lines"] == lines for s in agent_sources):
        return
    agent_sources.append({"file": file_path, "lines": lines, "source_id": source_id})


def extract_tool_sources(event: dict, agent_sources: list, source_id: Optional[int]) -> None:
    """
    Sammelt Dateien, die der Agent über Tools tatsächlich gelesen/gefunden hat
    (view_repo_file, search_repo_code, get_repo_entities) als zusätzliche Kandidaten
    für resolve_cited_sources — nur weil der Agent eine Datei geöffnet hat, heißt das
    noch nicht, dass sie für die finale Antwort relevant war; das entscheidet das LLM
    selbst über seine Zitate (siehe resolve_cited_sources).

    ``source_id`` is the single repository the agent's tools read from for this whole
    run (``resolved_repo_id``) — without it, a citation opened when no project is
    selected in the workspace stayed empty (same root cause as O-090's citation fix
    for the standard-RAG path, see ``resolve_citation_source_id``).
    """
    if event.get("type") != "tool_result":
        return
    tool_name = event.get("name")
    if tool_name not in (
        "view_repo_file",
        "search_repo_code",
        "get_repo_entities",
        "trace_call_flow",
        "inspect_change_impact",
        "inspect_change_package",
        "answer_context",
    ):
        return

    result = event.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            return
    if not isinstance(result, dict):
        return

    if tool_name == "view_repo_file":
        if result.get("file_path"):
            record_agent_source(
                agent_sources,
                result["file_path"],
                result.get("start_line", 1),
                result.get("end_line", 1),
                source_id,
            )
    elif tool_name == "search_repo_code":
        for match in result.get("matches", [])[:8]:
            if match.get("file"):
                record_agent_source(
                    agent_sources,
                    match["file"],
                    match.get("line", 1),
                    match.get("line", 1),
                    source_id,
                )
    elif tool_name == "get_repo_entities":
        for entity in result.get("entities", [])[:8]:
            if entity.get("file_path"):
                record_agent_source(
                    agent_sources,
                    entity["file_path"],
                    entity.get("start_line", 1),
                    entity.get("end_line", 1),
                    source_id,
                )
    elif tool_name in ("trace_call_flow", "inspect_change_impact"):
        # Damit die vom Agenten aus dem Ablauftrace genannten Schritte nicht
        # nur als Mermaid sichtbar, sondern auch als Code-Zitat anklickbar
        # werden. Der Tool-Trace ist bereits auf 150 Knoten begrenzt; für die
        # Quellenliste genügen die ersten 16, um die Antwort schlank zu halten.
        for entity in result.get("nodes", [])[:16]:
            if entity.get("file_path"):
                record_agent_source(
                    agent_sources,
                    entity["file_path"],
                    entity.get("start_line", 1),
                    entity.get("end_line", 1),
                    entity.get("source_id") or source_id,
                )
    elif tool_name == "answer_context":
        for entry in result.get("evidence", []):
            if not isinstance(entry, dict):
                continue
            located = [
                (entry.get("entity") or {}).get("file_path")
                or (entry.get("entity") or {}).get("file"),
                (entry.get("entity") or {}).get("start_line"),
                (entry.get("entity") or {}).get("end_line"),
            ]
            if located[0]:
                record_agent_source(
                    agent_sources,
                    located[0],
                    located[1] or 1,
                    located[2] or located[1] or 1,
                    source_id,
                )
            for caller in entry.get("callers") or []:
                location = caller.get("location") if isinstance(caller, dict) else None
                match = _FILE_LINE_RE.match(str(location or ""))
                if match:
                    record_agent_source(
                        agent_sources,
                        match.group(1),
                        int(match.group(2)),
                        int(match.group(2)),
                        source_id,
                    )
            for site in entry.get("call_sites") or []:
                numbers = (
                    [int(n) for n in re.findall(r"(?m)^(\d+):", site.get("text") or "")]
                    if isinstance(site, dict)
                    else []
                )
                if isinstance(site, dict) and site.get("file") and numbers:
                    record_agent_source(
                        agent_sources, site["file"], min(numbers), max(numbers), source_id
                    )
            # Herkunftskette und COPY-Liste tragen ihre Fundstellen selbst; sie werden zu klickbaren Quellen.
            for step in entry.get("data_origin") or []:
                if isinstance(step, dict) and step.get("file") and step.get("line"):
                    record_agent_source(
                        agent_sources, step["file"], int(step["line"]), int(step["line"]), source_id
                    )
            for group in ("resolved", "external", "unresolved"):
                for item in (entry.get("includes") or {}).get(group) or []:
                    match = (
                        _FILE_LINE_RE.match(str(item.get("cite") or ""))
                        if isinstance(item, dict)
                        else None
                    )
                    if match:
                        record_agent_source(
                            agent_sources,
                            match.group(1),
                            int(match.group(2)),
                            int(match.group(2)),
                            source_id,
                        )
            for key in ("expanded", "helper_methods", "callee_chain"):
                for part in entry.get(key) or []:
                    text = part.get("source") or {}
                    file_path = part.get("file") or located[0]
                    if file_path and text.get("start_line"):
                        record_agent_source(
                            agent_sources,
                            file_path,
                            text["start_line"],
                            text.get("end_line") or text["start_line"],
                            source_id,
                        )
    elif tool_name == "inspect_change_package":
        # The package's compact result retains the indexed source locations so
        # citations in the assistant answer remain clickable.
        for entity in result.get("affected_code", [])[:12]:
            if isinstance(entity, dict) and entity.get("file_path"):
                record_agent_source(
                    agent_sources,
                    entity["file_path"],
                    entity.get("start_line") or 1,
                    entity.get("end_line") or entity.get("start_line") or 1,
                    entity.get("source_id") or source_id,
                )


# Selbe Dateiendungen wie MarkdownContent.tsx im Frontend klickbar macht — eine Datei,
# die das LLM hier nicht im erkannten Format zitiert, taucht in "Referenzierte Quellen" nicht auf.
_FILE_EXT_RE = re.compile(
    r"\b[\w\-./]+\.(?:py|cob|cbl|cpy|java|js|ts|json|md|txt|yml|yaml|css|html|pdf|docx|doc|ifc|dwg)\b",
    re.IGNORECASE,
)
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_FILE_LINE_RE = re.compile(r"^(.+\.\w+):(\d+)(?:-\d+)?$")
# Backtick-Dateiname ohne Zeile (`CMQV.cpy`): wird gegen die abgerufenen Werkzeugergebnisse geprüft.
_BARE_SOURCE_FILE_RE = re.compile(
    r"^[\w./-]+\.(?:cbl|cob|cobol|cpy|copy|jcl|prc|proc|java|groovy|xml|xsl|xslt|sh|sql|properties|html|js)$",
    re.I,
)
_EMPTY_ANSWER_NOTICE = (
    "Das Modell hat nach der Recherche keine Antwort geliefert. Es ist deshalb nichts belegt. "
    "Bitte die Frage erneut stellen oder ein leistungsfähigeres Modell wählen."
)


def tool_evidence_text(agent_steps: list, question: str = "") -> str:
    """Frage und alle Werkzeugergebnisse eines Agentenlaufs als durchsuchbarer Kleintext."""
    parts = [question]
    for step in agent_steps:
        if isinstance(step, dict) and step.get("type") == "tool_result":
            result = step.get("result")
            parts.append(
                result
                if isinstance(result, str)
                else json.dumps(result, ensure_ascii=False, default=str)
            )
    return "\n".join(parts).casefold()


def resolve_citation_source_id(
    db: Session, chunk: DocumentChunk, repo_id_cache: dict
) -> Optional[int]:
    """A repo-backed chunk has ``source_id=None`` (see retrieve_chat_context — it's
    addressed by ``project_id`` instead), so a raw citation/pin built from it can't
    open a file once no project is selected in the workspace (a new, general chat
    spanning multiple projects) — there is no `project.repo_id` for the frontend to
    fall back to. Resolve it here to the project's Git KnowledgeSource id instead,
    the same id `project.repo_id` would already have supplied. Memoized per request
    since many result rows usually share one project.
    """
    if chunk.source_id is not None:
        return chunk.source_id
    if chunk.project_id is None:
        return None
    if chunk.project_id not in repo_id_cache:
        repo_id_cache[chunk.project_id] = resolve_repository_id(chunk.project_id, db)
    return repo_id_cache[chunk.project_id]


_TITLE_SUFFIX_RE = re.compile(r"^(.+):(\d+)(?:-\d+)?$")


def parse_citations(text: str, known_titles: set) -> List[tuple]:
    """Extrahiert Referenzen auf Dateien (`pfad/datei.ext` oder `pfad/datei.ext:zeile`,
    dasselbe Format, das MarkdownContent.tsx im Frontend als klickbaren Datei-Link rendert)
    oder Wissensquellen-Seiten ohne Dateiendung (Confluence-Titel), die exakt
    (case-insensitiv) mit `known_titles` übereinstimmen — sowohl in Backticks zitiert als
    auch, als Fallback, unformatiert im Fließtext, da lokale Modelle die Backtick-Vorgabe aus
    dem citation_note-Prompt gerade innerhalb von Tabellenzellen zuverlässig ignorieren
    (siehe MarkdownContent.tsx renderPlainKnownSources für dasselbe Problem im Frontend-Rendering).
    Reihenfolge des ersten Auftretens bleibt erhalten."""
    citations: List[tuple] = []
    seen_lower = set()

    def _add(file_path: str, line):
        key = file_path.lower()
        if key in seen_lower:
            return
        seen_lower.add(key)
        citations.append((file_path, line))

    for raw in _BACKTICK_RE.findall(text):
        file_path, line = raw, None
        m = _FILE_LINE_RE.match(raw)
        if m:
            file_path, line = m.group(1), int(m.group(2))
        elif file_path.lower() not in known_titles:
            # Extensionless Wissensquellen-Titel tragen keine echte Dateiendung -- ein Modell,
            # das trotz Anweisung dennoch ein `:seite`/`:start-ende`-Suffix anhängt (analog zum
            # file:line-Format oben), muss dieses Suffix erst abgestreift bekommen, bevor der
            # exakte Titel-Abgleich unten greift -- sonst fällt z.B. `Titel:17` unbelegt durch.
            suffix_m = _TITLE_SUFFIX_RE.match(raw)
            if suffix_m and suffix_m.group(1).lower() in known_titles:
                file_path, line = suffix_m.group(1), int(suffix_m.group(2))
        if _FILE_EXT_RE.search(file_path) or file_path.lower() in known_titles:
            _add(file_path, line)

    # Fallback ohne Backticks: nur für bekannte Wissensquellen-Titel, nie für rohe Dateipfade --
    # ein Titel wie "Fiktives Firmen Wiki" ist eindeutige Prosa, während ein bloßer Dateiname wie
    # "main.py" auch in ganz normaler Diskussion auftauchen kann, ohne eine echte Zitation zu sein.
    plain_titles = [t for t in known_titles if not _FILE_EXT_RE.search(t)]
    if plain_titles:
        pattern = re.compile(
            "("
            + "|".join(re.escape(t) for t in sorted(plain_titles, key=len, reverse=True))
            + r")(?::(\d+)(?:-\d+)?)?",
            re.IGNORECASE,
        )
        for m in pattern.finditer(text):
            _add(m.group(1), int(m.group(2)) if m.group(2) else None)

    return citations


def resolve_cited_sources(answer: str, candidates: List[dict]) -> List[dict]:
    """
    Baut "Referenzierte Quellen" ausschließlich aus Dateien, die das LLM in seiner
    Antwort tatsächlich zitiert hat UND die wirklich Teil der Recherche waren (Vektor-Treffer
    oder vom Agenten gelesene Dateien aus `candidates`) — nie einfach alle rohen
    Vektor-Suchtreffer, aber auch nie eine vom Modell frei erfundene Zitation ungeprüft
    übernehmen. Ein lokales LLM kann Dateinamen halluzinieren (z.B. ein plausibel klingendes
    `payroll.cbl`, das im Repo gar nicht existiert) — solche Treffer ohne Beleg in den
    candidates verwerfen wir, statt sie als unbelegte Quelle anzuzeigen.
    """
    by_path = {c["file"]: c for c in candidates}
    by_basename = {}
    by_path_lower = {}
    for c in candidates:
        by_basename.setdefault(os.path.basename(c["file"]).lower(), c)
        by_path_lower.setdefault(c["file"].lower(), c)

    resolved, seen = [], set()
    for file_path, line in parse_citations(answer, set(by_path_lower.keys())):
        candidate = (
            by_path.get(file_path)
            or by_basename.get(os.path.basename(file_path).lower())
            or by_path_lower.get(file_path.lower())
        )
        if not candidate:
            continue
        entry = {
            "file": candidate["file"],
            "lines": [line, line] if line else candidate["lines"],
            "source_id": candidate.get("source_id"),
            # Die ID wird nur für intern persistierte Quellen verwendet. Sie
            # verbindet ein Downvote eindeutig mit den Links des zitierten
            # Dokuments, statt später Dateinamen heuristisch nachzuschlagen.
            "chunk_id": candidate.get("chunk_id"),
        }
        # case-insensitiv je Datei deduplizieren — kleine Modelle zitieren dieselbe Datei
        # in einer Antwort manchmal mit wechselnder Schreibweise (`payroll.cbl` vs `Payroll.cbl`)
        dedup_key = entry["file"].lower()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        resolved.append(entry)
    return resolved


_NO_RESULT_RE = re.compile(
    r"\b(?:keine\s+(?:Treffer|Ergebnisse)|nichts\s+gefunden|no\s+(?:results|matches)|nothing\s+found)\b",
    re.IGNORECASE,
)


def append_agent_source_fallback(
    answer: str, agent_sources: list[dict], rejected: bool = False
) -> str:
    """Make tool-read code locations visible if the model omitted the citation syntax.

    Models sometimes use a different citation style even after being instructed to
    emit ``path/to/file.java:line``.  The locations below are not inferred: they
    come from repository tools that actually ran during this answer.  Keep this
    fallback explicit so the user can distinguish it from model-written prose.

    ``rejected``: the answer was replaced by a gap notice (O-346).  The tool-read
    locations are then listed as the only verified evidence instead of leaving
    ``sources=[]``.
    """
    if not rejected and _NO_RESULT_RE.search(answer):
        # „keine Treffer“: die zufällig gelesenen Stellen belegen nichts und würden als Beleg wirken.
        return answer
    if not rejected and (
        not agent_sources
        or any(_FILE_EXT_RE.search(source.get("file", "")) for source in agent_sources)
    ):
        if parse_citations(answer, {source.get("file", "") for source in agent_sources}):
            return answer
    if not agent_sources:
        return answer

    references = []
    seen = set()
    for source in agent_sources:
        file_path = source.get("file")
        lines = source.get("lines") or []
        if not file_path or not lines:
            continue
        line = lines[0] or 1
        key = (file_path.lower(), line)
        if key in seen:
            continue
        seen.add(key)
        references.append(f"- `{file_path}:{line}`")
    if not references:
        return answer
    if rejected:
        references = references[:10]
    header = (
        "Tatsächlich gelesene und belegte Code-Stellen (keine Aussage zur Anfrage):"
        if rejected
        else "Vom Agenten gelesene Code-Stellen:"
    )
    return answer.rstrip() + f"\n\n{header}\n" + "\n".join(references)


_CODE_QUOTE_RE = re.compile(
    r"`[^`]*`|\bCALL\s+['\"][^'\"]*['\"](?:\s+USING\s+[\w-]+(?:\s*,?\s*[\w-]+)*)?"
)
_EDGE_CLAIM_RE = re.compile(
    r"\b(?:ruft|calls?|invokes?)\b",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(
    r"\b(?:kein|keine|keinen|keiner|keinem|nicht|ohne|nie|niemals|no|not|without|never|nothing)\b",
    re.IGNORECASE,
)
_EDGE_NOUN_RE = re.compile(r"\baufruf", re.IGNORECASE)
_IDENTIFIER_RE = re.compile(
    r"\b[A-Z][A-Z0-9]*[-_][A-Z0-9_-]*\b|\b[A-Z]{4,}[A-Z0-9]*\b|\b\w+[.#]\w+\b|\b[a-z]+[A-Z]\w*\b|\b[A-Z][a-z]+[A-Z]\w*\b"
)


def _symbol_tail(value: str) -> str:
    """`Class#method(int)`, `pkg.Class.method`, `file::job:X::step:Y` -> kleinstes Namensstück."""
    head = str(value or "").split("(", 1)[0].strip()
    return re.split(r"[.#:/]+", head)[-1].casefold() if head else ""


def answer_context_edge_pairs(result: dict) -> set[tuple[str, str]]:
    """Directed pairs the server-built evidence pack states explicitly.

    The pack lists, per symbol, its callees (``NAME (Zeile n)``), its callers
    (``from``), and the second-hop ``callee_chain``/``calls``. These are index
    edges, not inferences from proximity."""
    pairs: set[tuple[str, str]] = set()
    for entry in result.get("evidence") or []:
        if not isinstance(entry, dict):
            continue
        entity = entry.get("entity") or {}
        symbol = _symbol_tail(
            entry.get("symbol") or entity.get("qualified_name") or entity.get("name")
        )
        if not symbol:
            continue
        for callee in entry.get("callees") or []:
            name = _symbol_tail(callee if isinstance(callee, str) else (callee or {}).get("to"))
            if name:
                pairs.add((symbol, name))
        for caller in entry.get("callers") or []:
            if not isinstance(caller, dict) or not caller.get("from"):
                continue
            origin = str(caller["from"])
            stem = os.path.splitext(os.path.basename(origin.split("::", 1)[0]))[0].casefold()
            for name in {_symbol_tail(origin), stem}:
                if name:
                    pairs.add((name, symbol))
        for hop in entry.get("callee_chain") or []:
            if not isinstance(hop, dict):
                continue
            hop_symbol = _symbol_tail(hop.get("symbol"))
            if hop_symbol:
                pairs.add((symbol, hop_symbol))
                for callee in hop.get("calls") or []:
                    name = _symbol_tail(callee)
                    if name:
                        pairs.add((hop_symbol, name))
        for helper in entry.get("helper_methods") or []:
            name = _symbol_tail((helper or {}).get("symbol")) if isinstance(helper, dict) else ""
            if name:
                pairs.add((symbol, name))
        # Evidence blocks (services/evidence.py) state their edges explicitly, for every language.
        for item in (entry.get("control_flow") or {}).get("flow") or []:
            routine = _symbol_tail(item.get("routine")) if isinstance(item, dict) else ""
            for call in (item.get("calls") or []) if isinstance(item, dict) else []:
                target = _symbol_tail(call.get("to"))
                if routine and target:
                    pairs.add((routine, target))
                for follow in call.get("then") or []:
                    follow_name = _symbol_tail(follow.get("to"))
                    if target and follow_name:
                        pairs.add((target, follow_name))
        for group in ("resolved", "external", "unresolved"):
            for item in (entry.get("includes") or {}).get(group) or []:
                name = _symbol_tail(item.get("name")) if isinstance(item, dict) else ""
                if name:
                    pairs.add((symbol, name))
        for step in entry.get("data_origin") or []:
            if (
                isinstance(step, dict)
                and step.get("operation") == "argument"
                and step.get("passed_by")
            ):
                callee = _symbol_tail(str(step.get("statement") or "").split("(", 1)[0])
                if callee:
                    pairs.add((_symbol_tail(step["passed_by"]), callee))
    return pairs


def extract_tool_edge_pairs(event: dict) -> set[tuple[str, str]]:
    """Return directed entity-name pairs from a successful flow-tool result."""
    if event.get("type") != "tool_result" or event.get("name") not in (
        "trace_call_flow",
        "answer_context",
    ):
        return set()
    result = event.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, json.JSONDecodeError):
            return set()
    if event.get("name") == "answer_context":
        return answer_context_edge_pairs(result) if isinstance(result, dict) else set()
    if not isinstance(result, dict) or result.get("status") != "ok":
        return set()
    names = {
        node.get("id"): str(node.get("name") or "").casefold()
        for node in result.get("nodes", [])
        if isinstance(node, dict) and node.get("id") is not None and node.get("name")
    }
    return {
        (names[edge["source"]], names[edge["target"]])
        for edge in result.get("edges", [])
        if isinstance(edge, dict)
        and edge.get("resolution") == "resolved"
        and edge.get("source") in names
        and edge.get("target") in names
    }


def _mentions_name(text: str, name: str) -> bool:
    """Whole-name match: ``wait`` must not be found inside ``cobswait``."""
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


def validate_answer_sources(
    answer: str,
    sources: list[dict],
    edge_pairs: Optional[set[tuple[str, str]]] = None,
    evidence_text: Optional[str] = None,
) -> tuple[str, bool]:
    """Reject file/line citations and relationship claims without delivered evidence.

    The model prompt is useful guidance, but it is not a provenance boundary:
    small local models can still turn a neighbouring file into a plausible
    citation.  In that case no partial answer is safer than presenting the
    neighbouring source as evidence for the requested file.  A basename is
    accepted only when it maps to exactly one tool-result file.

    ``evidence_text`` (question plus tool results, casefolded) enables the check for
    file names without a line: a name that occurs nowhere in it is marked as not
    evidenced instead of being presented like a retrieved source.
    """
    if not (answer or "").strip():
        logger.warning("Agent-Antwort ist leer; ersetze durch einen Hinweis")
        return _EMPTY_ANSWER_NOTICE, False
    evidence: dict[str, list[tuple[int, int]]] = {}
    basenames: dict[str, set[str]] = {}
    for source in sources:
        path = str(source.get("file") or "").replace("\\", "/").lstrip("./")
        lines = source.get("lines") or []
        if not path or len(lines) < 2:
            continue
        try:
            start, end = int(lines[0]), int(lines[1])
        except (TypeError, ValueError):
            continue
        path_key = path.lower()
        evidence.setdefault(path_key, []).append((min(start, end), max(start, end)))
        basenames.setdefault(os.path.basename(path_key), set()).add(path_key)

    # Only Markdown code spans are considered citations.  Plain prose can
    # legitimately mention a filename while explaining why it was not found.
    verified = 0
    unverified: list[tuple[str, str]] = []
    # Umzäunte Code-Blöcke (Mermaid-Diagramm, Quelltext-Auszug) sind Belege bzw.
    # Werkzeugausgabe und keine Behauptungen; sie werden weder geprüft noch markiert.
    scan = _FENCE_RE.sub(" ", answer)
    for raw in _BACKTICK_RE.findall(scan):
        match = _FILE_LINE_RE.match(raw.strip())
        if not match:
            continue
        claimed_path, claimed_line = (
            match.group(1).replace("\\", "/").lstrip("./"),
            int(match.group(2)),
        )
        path_key = claimed_path.lower()
        ranges = evidence.get(path_key)
        # A basename may be convenient in a human-written citation, but never
        # use it to bless a different, explicitly named path.  Otherwise
        # ``neighbour/Foo.java:12`` could be accepted for evidence from
        # ``actual/Foo.java:12``.
        if ranges is None and "/" not in claimed_path:
            candidates = basenames.get(os.path.basename(path_key), set())
            if len(candidates) == 1:
                ranges = evidence[next(iter(candidates))]
        if ranges and any(start <= claimed_line <= end for start, end in ranges):
            verified += 1
        else:
            unverified.append((raw, f"{claimed_path}:{claimed_line}"))

    unknown_files: list[str] = []
    if evidence_text:
        for raw in _BACKTICK_RE.findall(scan):
            name = raw.strip()
            if _BARE_SOURCE_FILE_RE.match(name):
                base = os.path.basename(name.replace("\\", "/")).casefold()
                stem = base.rsplit(".", 1)[0]
                if (
                    base not in evidence_text
                    and not any(stem == os.path.splitext(known)[0] for known in basenames)
                    and name not in unknown_files
                ):
                    unknown_files.append(name)

    if unverified and not verified:
        logger.warning("Verwerfe Agent-Antwort mit unbelegter Quellenangabe: %s", unverified[0][0])
        return (
            "Die angefragte Datei bzw. Code-Stelle ist im aktuellen Index oder in den "
            "abgerufenen Quellen nicht belastbar belegt. Ich nenne deshalb keine "
            "Ersatzdatei als Beleg; bitte den Import/Parserstatus prüfen oder die "
            "Zieldatei erneut indexieren.",
            False,
        )
    if unverified:
        # O-346: Eine belegte Antwort mit einer zusätzlichen, nicht abgerufenen
        # Nebenstelle wird nicht verworfen; die Stelle verliert ihren Quellen-Link
        # und wird als Lücke benannt.
        logger.warning("Markiere unbelegte Quellenangabe(n): %s", [item[1] for item in unverified])
        for raw, label in unverified:
            answer = answer.replace(f"`{raw}`", f"{label} (nicht belegt)")
        answer = (
            answer.rstrip()
            + "\n\n> Hinweis: "
            + ", ".join(label for _, label in unverified)
            + " stammt nicht aus den abgerufenen Quellen und ist deshalb nicht als Beleg verlinkt."
        )

    if unknown_files:
        # Ein Dateiname, den kein Werkzeugergebnis nennt, ist keine Fundstelle: kennzeichnen statt verlinken.
        logger.warning("Markiere nicht abgerufene Dateinamen: %s", unknown_files)
        for name in unknown_files:
            answer = answer.replace(f"`{name}`", f"{name} (nicht belegt)")
        answer = (
            answer.rstrip()
            + "\n\n> Hinweis: "
            + ", ".join(unknown_files)
            + " kommt in keinem abgerufenen Werkzeugergebnis vor und ist nicht belegt."
        )

    # A call assertion is only admissible when its directed pair was returned
    # by trace_call_flow in this turn. We intentionally do not infer edges
    # from proximity in a file snippet.
    # Punkte in Dateinamen (`COBSWAIT.cbl:36`) dürfen keine Satzgrenze sein.
    protected = _BACKTICK_RE.sub(lambda m: "`" + m.group(1).replace(".", "\u2024") + "`", scan)
    supported_claims = 0
    unsupported_claims: list[str] = []
    for sentence in (part.replace("\u2024", ".") for part in re.split(r"[.!?\n]+", protected)):
        # Zitierter Quelltext (`CALL 'X' USING ...`) ist keine Behauptung über den
        # Aufrufer, sondern der Beleg selbst.
        prose = _CODE_QUOTE_RE.sub(" ", sentence)
        if _NEGATION_RE.search(prose):
            # „keine nachgewiesene Kante“, „ruft … nicht auf“: eine Lückenaussage
            # behauptet keine Beziehung und darf nicht als solche verworfen werden.
            continue
        if not _EDGE_CLAIM_RE.search(prose):
            # Das bloße Substantiv „Aufruf“ behauptet erst dann eine Kante, wenn
            # der Satz mindestens zwei Bezeichner nennt.
            if not (_EDGE_NOUN_RE.search(prose) and len(_IDENTIFIER_RE.findall(prose)) >= 2):
                continue
        lowered = sentence.casefold()
        if any(
            _mentions_name(lowered, pair[0]) and _mentions_name(lowered, pair[1])
            for pair in (edge_pairs or ())
        ):
            supported_claims += 1
        else:
            unsupported_claims.append(sentence.strip())

    if unsupported_claims:
        if not (verified or supported_claims):
            # Nur unbelegte Kanten: keine Ersatzkante als Antwort anbieten.
            logger.warning(
                "Verwerfe Agent-Antwort mit unbelegter Kantenbehauptung: %s",
                unsupported_claims[0][:200],
            )
            return (
                "Die behauptete Codebeziehung ist in den abgerufenen Analyseergebnissen "
                "nicht belegt. Ich nenne deshalb keine plausible Ersatzkante; bitte die "
                "Zielentität erneut auflösen oder den Call-Flow prüfen.",
                False,
            )
        # O-346: Belegte Antwort mit einer zusätzlichen Kantenaussage ohne Index-Beleg:
        # Der Satz bleibt, wird aber als nicht belegt gekennzeichnet.
        logger.warning(
            "Markiere unbelegte Kantenbehauptung(en): %s", [c[:120] for c in unsupported_claims]
        )
        for claim in unsupported_claims:
            if claim and claim in answer:
                answer = answer.replace(claim, f"{claim} (Beziehung nicht im Index belegt)", 1)
        answer = (
            answer.rstrip()
            + "\n\n> Hinweis: Mindestens eine Beziehungsaussage stammt nicht aus den abgerufenen "
            "Analyseergebnissen und ist als „nicht im Index belegt“ markiert."
        )
    return answer, True


def attach_analysis_status(db: Session, sources: list[dict]) -> list[dict]:
    """O-120: eine zitierte Datei kann strukturell nur teilweise/gar nicht
    analysiert worden sein (COBOL-Diagnosen, F-029-Textfallback) oder beim
    Import ganz übersprungen worden sein — ein Zitat allein sagt darüber
    nichts. Ergänzt `analysis_status`/`analysis_reasons` nur dort, wo das der
    Fall ist (siehe core.analysis_status.load_analysis_status); die meisten
    Quellen bleiben unverändert. MarkdownContent.tsx rendert daraus eine
    Warnmarkierung am Zitat statt es unkommentiert wie eine uneingeschränkt
    verlässliche Quelle darzustellen (O-120-Abnahme)."""
    status_by_key = load_analysis_status(
        db, {(source.get("source_id"), source.get("file")) for source in sources}
    )
    source_ids = {
        source.get("source_id") for source in sources if isinstance(source.get("source_id"), int)
    }
    source_by_id = (
        {
            source.id: source
            for source in db.query(KnowledgeSource).filter(KnowledgeSource.id.in_(source_ids)).all()
        }
        if source_ids
        else {}
    )
    for source in sources:
        info = status_by_key.get((source.get("source_id"), source.get("file")))
        if info:
            source["analysis_status"] = info["status"]
            source["analysis_reasons"] = info["reasons"]
        knowledge_source = source_by_id.get(source.get("source_id"))
        is_code_source = bool(
            knowledge_source and (knowledge_source.type or "").casefold() == "git"
        )
        source["provenance"] = build_provenance(
            knowledge_source,
            kind="code_fact"
            if is_code_source
            else "document_claim"
            if knowledge_source
            else "unknown",
            verification_status="indexed_unreviewed"
            if is_code_source
            else "unverified"
            if knowledge_source
            else "unavailable",
            detail=(
                "Die Verknüpfung belegt die Fundstelle, nicht die fachliche Richtigkeit der Aussage."
                if knowledge_source and not is_code_source
                else "Code wurde automatisch aus dem Index gelesen; eine fachliche Freigabe ist nicht hinterlegt."
                if is_code_source
                else "Quellenmetadaten sind für diese Fundstelle nicht verfügbar."
            ),
            locator={"file": source.get("file"), "lines": source.get("lines")},
            analysis_status=info.get("status") if info else None,
            analysis_reasons=info.get("reasons", []) if info else [],
        )
    return sources


def build_candidate_sources(
    db: Session, results: Iterable[DocumentChunk], pinned_chunks: Iterable[DocumentChunk]
) -> list[dict]:
    """Kandidaten zum Auflösen von Zitaten auf vollen Pfad/source_id.

    Sichtbar in „Referenzierte Quellen" wird ein Kandidat erst, wenn die Antwort
    ihn zitiert (resolve_cited_sources). Gepinnte Chunks stehen vorn.
    """
    repo_id_cache: dict = {}

    def candidate(chunk: DocumentChunk) -> dict:
        return {
            "file": chunk.file_path,
            "lines": [chunk.start_line, chunk.end_line],
            "source_id": resolve_citation_source_id(db, chunk, repo_id_cache),
            "chunk_id": chunk.id,
        }

    candidates = [candidate(chunk) for chunk in results]
    for chunk in pinned_chunks:
        if not any(
            c["file"] == chunk.file_path and c["lines"] == [chunk.start_line, chunk.end_line]
            for c in candidates
        ):
            candidates.insert(0, candidate(chunk))
    return candidates


def merge_candidate_sources(candidates: list[dict], extra: Iterable[dict]) -> None:
    """Hängt weitere Kandidaten an, ohne dieselbe Datei/Zeilenspanne doppelt zu führen."""
    for source in extra:
        if not any(
            c["file"] == source["file"] and c["lines"] == source["lines"] for c in candidates
        ):
            candidates.append(source)


class ToolEvidence:
    """Was die Werkzeuge eines Agentenlaufs belegt haben: gelesene Stellen und Kanten.

    ``observe`` nimmt jedes Werkzeugereignis entgegen; ``validate`` prüft die
    fertige Antwort gegen genau diese Belege.
    """

    def __init__(self, repository_id: Optional[int]):
        self.repository_id = repository_id
        self.sources: list[dict] = []
        self.edge_pairs: set[tuple[str, str]] = set()

    def observe(self, event: dict) -> None:
        extract_tool_sources(event, self.sources, self.repository_id)
        self.edge_pairs.update(extract_tool_edge_pairs(event))

    def validate(self, answer: str, agent_steps: list, question: str) -> tuple[str, bool]:
        return validate_answer_sources(
            answer,
            self.sources,
            self.edge_pairs,
            evidence_text=tool_evidence_text(agent_steps, question) if agent_steps else None,
        )
