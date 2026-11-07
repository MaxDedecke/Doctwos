"""Symbole in Fragen und Code finden: Erwähnungen erkennen, Namen und Signaturen vergleichen, Entitäten auflösen.

Gemeinsame Grundlage der MCP-Werkzeuge und des Belegpakets (aus mcp_server.py herausgelöst).
"""

import logging
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api import entities as entity_api
from core.projects import (
    assert_project_visible,
    get_visible_project_ids,
)
from core.teams import get_visible_team_ids
from doctus_models.database import (
    CodeEntity,
    Project,
    User,
)
from services.search import search_nodes


logger = logging.getLogger(__name__)


def _search_code_alternatives(query: str) -> list[str]:
    """Normalize symbol alternatives supplied as prose or source declarations."""
    alternatives = []
    seen = set()
    for part in query.split("|"):
        term = re.sub(r"^(?:class|interface|enum|record)\s+", "", part.strip(), flags=re.I)
        if term and term.casefold() not in seen:
            seen.add(term.casefold())
            alternatives.append(term)
    return alternatives


def _research_terms(query: str) -> list[str]:
    """Split explicit symbol lists while keeping ordinary prose intact."""
    explicit = _search_code_alternatives(query)
    if len(explicit) > 1:
        return explicit[:8]
    term = explicit[0] if explicit else ""
    pieces = [part for part in re.split(r"\s+", term) if part]

    def symbol_like(part: str) -> bool:
        # Prose such as "approval/decline" or "how" must not be split into symbols.
        if not re.fullmatch(r"[\w$./:#<>(),-]+", part):
            return False
        return bool(
            any(mark in part for mark in ".#:()_$")
            or re.search(r"[a-z][A-Z]", part)
            or re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", part)
            # COBOL-Programm- und Copybook-Namen ohne Bindestrich (COSGN00C, CBTRN03C): Großbuchstaben mit Ziffer.
            or re.fullmatch(r"(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z][A-Z0-9]{3,}", part)
        )

    if len(pieces) > 1 and all(symbol_like(part) for part in pieces):
        return pieces[:8]
    return [term] if term else []


_MENTION_PATTERNS = (
    re.compile(
        r"\b(?=[A-Z0-9-]*[0-9])(?=[A-Z0-9-]*[A-Z])[A-Z][A-Z0-9-]{3,}\b"
    ),  # COSGN00C, CBTRN03C
    re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b"),  # PA-TRANSACTION-AMT
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b"),  # UserLogic
    re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+)+\b"),  # doCreate
    re.compile(r"\b[A-Za-z_]\w*(?:[#.][A-Za-z_]\w*)+\b"),  # UserLogic.create, Class#method
)


def _mentioned_symbols(text: str, limit: int = 4) -> list[str]:
    """Symbol-like names inside a prose question (``Welche Rolle spielt COSGN00C bei der Anmeldung?``).

    The names are only candidates: ``research_project`` keeps those that resolve to an indexed entity."""
    plain = text.replace("`", " ")
    found: list[str] = []
    for pattern in _MENTION_PATTERNS:
        for token in pattern.findall(plain):
            token = token.rstrip(".")
            if len(token) >= 4 and token.casefold() not in {item.casefold() for item in found}:
                found.append(token)
    return found[:limit]


def _symbol_key(value: str | None) -> str:
    value = (value or "").replace("\\", "/").casefold()
    value = value.split("(", 1)[0].replace("#", ".")
    return re.sub(r"\s+", "", value).strip(".")


def _split_params(text: str) -> list[str]:
    """Split a parameter list at top-level commas; generic arguments keep theirs."""
    parts, depth, current = [], 0, ""
    for char in text:
        if char in "<(":
            depth += 1
        elif char in ">)":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current)
    return parts


def _param_type(param: str) -> str:
    """Parameter type without modifiers or a trailing parameter name (``final UserUR req`` -> ``userur``)."""
    param = re.sub(r"\b(?:final)\b", " ", param.strip())
    named = re.match(r"^(.*[>\]\w])\s+[\w$]+$", param.strip())
    return re.sub(r"\s+", "", (named.group(1) if named else param)).casefold()


def _query_signature(term: str) -> list[str] | None:
    """Parameter types a query asks for, ``None`` when it names no signature."""
    match = re.search(r"\((.*)\)\s*$", term.strip())
    return [_param_type(part) for part in _split_params(match.group(1))] if match else None


def _entity_signature(entity: CodeEntity) -> list[str] | None:
    """Parameter types of a method/constructor (``Klasse#name(A,B)``); ``None`` for everything else."""
    match = re.search(r"#[^#@()]*\((.*)\)$", entity.qualified_name or "")
    return [_param_type(part) for part in _split_params(match.group(1))] if match else None


def _symbol_matches(entity: CodeEntity, term: str) -> bool:
    wanted = _query_signature(term)
    if wanted is not None and _entity_signature(entity) != wanted:
        return False
    return _symbol_name_matches(entity, term)


def _symbol_name_matches(entity: CodeEntity, term: str) -> bool:
    needle = _symbol_key(term)
    name = _symbol_key(entity.name)
    qualified = _symbol_key(entity.qualified_name)
    path = _symbol_key(entity.file_path)
    if needle in {name, qualified, path}:
        return True
    return bool(needle and (qualified.endswith("." + needle) or path.endswith("/" + needle)))


_DOTTED = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+$")
_NOISE_TYPES = {"parameter", "local_variable", "local", "record_component"}
_STOPWORDS = {
    "wie",
    "was",
    "der",
    "die",
    "das",
    "und",
    "oder",
    "the",
    "and",
    "how",
    "does",
    "what",
    "for",
    "with",
    "von",
    "mit",
}
_STRUCTURAL = {
    "program",
    "cobol_program",
    "section",
    "paragraph",
    "class",
    "interface",
    "enum",
    "record",
    "method",
    "constructor",
}
_TYPE_RANK = {
    "method": 0,
    "paragraph": 0,
    "constructor": 1,
    "program": 0,
    "cobol_program": 0,
    "section": 1,
    "class": 1,
    "interface": 1,
    "enum": 1,
    "record": 1,
    "field": 2,
    "data_item": 2,
    "compilation_unit": 3,
}


def _query_variants(term: str) -> list[str]:
    """Spellings an index may use for one symbol: Java methods are stored as ``Klasse#methode``."""
    term = term.strip()
    base = term.split("(", 1)[0]
    variants = [term]
    if _DOTTED.match(base):
        parts = base.split(".")
        variants.append(".".join(parts[:-1]) + "#" + parts[-1])
        if len(parts) > 2:
            variants.append(parts[-2] + "#" + parts[-1])
            variants.append(parts[-2] + "." + parts[-1])
    out, seen = [], set()
    for variant in variants:
        if variant.casefold() not in seen:
            seen.add(variant.casefold())
            out.append(variant)
    return out


def _symbol_like(token: str) -> bool:
    return bool(
        any(mark in token for mark in ".#:()_$")
        or re.search(r"[a-z][A-Z]", token)
        or re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", token)
    )


def _entity_haystack(entity: CodeEntity) -> str:
    return " ".join(
        [entity.name or "", (entity.qualified_name or "").replace("#", "."), entity.file_path or ""]
    ).casefold()


def _find_entities(
    db: Session, user: User, project_id: int, term: str, limit: int
) -> tuple[list[CodeEntity], list[dict], str]:
    """Tolerant symbol lookup: spelling variants, multi-word fallback, suggestions when nothing matches.

    Returns ``(entities, suggestions, mode)``; ``mode`` is ``exact``, ``tokens`` or ``none``.
    Exact symbol matches are listed first, then structural entities before fields.
    """
    visible_teams = get_visible_team_ids(user, db)
    visible_projects = get_visible_project_ids(user, db)

    def search(query: str, size: int) -> list[CodeEntity]:
        hits, _ = search_nodes(
            db,
            q=query,
            types="entity",
            project_id=project_id,
            limit=size,
            visible_team_ids=visible_teams,
            visible_project_ids=visible_projects,
            count_total=False,
        )
        found = []
        for hit in hits:
            try:
                found.append(_entity(db, user, project_id, hit["node_id"]))
            except HTTPException:
                continue
        return found

    found: list[CodeEntity] = []
    seen: set[int] = set()
    mode = "exact"
    for variant in _query_variants(term):
        for entity in search(variant, limit + 1):
            if entity.id not in seen:
                seen.add(entity.id)
                found.append(entity)
        if any(_symbol_matches(entity, variant) for entity in found):
            break
    if (
        found
        and len(term.split()) > 1
        and not any(
            _symbol_matches(entity, variant)
            for entity in found
            for variant in _query_variants(term)
        )
    ):
        # `search_nodes` löst Mehrwortbegriffe selbst auf (UND über die Teilbegriffe); das ist kein exakter Symboltreffer.
        mode = "tokens"
    if not found:
        tokens = [
            t
            for t in re.split(r"[\s,;|]+", term.strip())
            if len(t) >= 3 and t.casefold() not in _STOPWORDS
        ]
        if len(tokens) > 1:
            mode = "tokens"
            anchor = max(tokens, key=lambda t: (_symbol_like(t), len(t)))
            rest = [t.casefold() for t in tokens if t != anchor]
            pool: dict[int, CodeEntity] = {}
            for variant in _query_variants(anchor):
                for entity in search(variant, 80):
                    pool[entity.id] = entity
            scored = sorted(
                ((sum(t in _entity_haystack(e) for t in rest), e) for e in pool.values()),
                key=lambda x: -x[0],
            )
            found = [e for score, e in scored if score == len(rest)] or [
                e for score, e in scored if score > 0
            ]
            found = found[: limit + 1]
    suggestions: list[dict] = []
    if not found:
        mode = "none"
        for head in [t for t in re.split(r"[.#\s(|]+", term) if len(t) >= 3][:2]:
            for entity in search(head, 5):
                suggestions.append(
                    {
                        "qualified_name": entity.qualified_name,
                        "type": entity.type,
                        "file_path": entity.file_path,
                        "start_line": entity.start_line,
                    }
                )
            if suggestions:
                break
    found.sort(
        key=lambda e: (
            0 if _symbol_matches(e, term) else 1,
            _TYPE_RANK.get(e.type, 4),
            e.file_path or "",
            e.start_line or 0,
        )
    )
    return found, suggestions[:5], mode


def _compact_entity(entity: CodeEntity) -> dict:
    meta = entity.meta_json or {}
    item = {
        "id": entity.id,
        "qualified_name": entity.qualified_name,
        "type": entity.type,
        "file_path": entity.file_path,
        "start_line": entity.start_line,
        "end_line": entity.end_line,
    }
    if meta.get("signature"):
        item["signature"] = meta["signature"]
    return item


class ToolInputError(ValueError):
    """Input problem whose message is safe to show: it only names symbols the caller may already see."""


def _pick_entity(structural: list[CodeEntity]) -> tuple[CodeEntity | None, list[CodeEntity]]:
    """Choose one entity among exact matches or return (None, candidates) when it stays ambiguous.

    Overloads in one file: first by line. Otherwise prefer non-test paths, then one declaring type/program.
    """
    if len(structural) == 1:
        return structural[0], []
    pool = structural
    if len({e.file_path for e in pool}) > 1:
        non_test = [e for e in pool if "/test/" not in (e.file_path or "")]
        pool = non_test or pool
    if len({e.file_path for e in pool}) > 1:
        declaring = [
            e
            for e in pool
            if e.type in {"class", "interface", "enum", "record", "program", "cobol_program"}
        ]
        pool = declaring or pool
    if len({e.file_path for e in pool}) > 1:
        return None, structural
    pool = sorted(pool, key=lambda e: (_TYPE_RANK.get(e.type, 4), e.start_line or 0))
    return pool[0], [e for e in structural if e is not pool[0]]


def _resolve_symbol(db: Session, user: User, project_id: int, symbol: str) -> CodeEntity:
    """One entity for a symbol name, or a ValueError that names the candidates."""
    found, suggestions, _ = _find_entities(db, user, project_id, symbol, 8)
    exact = [e for e in found if _symbol_matches(e, symbol)] or found
    structural = [e for e in exact if e.type in _STRUCTURAL] or exact
    if not structural:
        hint = "; ".join(str(s["qualified_name"]) for s in suggestions) or "none"
        raise ToolInputError(f"symbol not found: {symbol}. Similar: {hint}")
    picked, _ = _pick_entity(structural)
    if picked is not None:
        return picked
    names = "; ".join(f"{e.qualified_name} ({e.file_path}:{e.start_line})" for e in structural[:6])
    raise ToolInputError(f"symbol is ambiguous: {symbol}. Use one qualified name: {names}")


def _bounded(value: str | None, limit: int = 1200) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    return value[:limit], len(value) > limit


def _project(db: Session, user: User, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404)
    assert_project_visible(project_id, user, db)
    return project


def _entity(db: Session, user: User, project_id: int, entity_id: int) -> CodeEntity:
    _project(db, user, project_id)
    entity = (
        db.query(CodeEntity)
        .filter(CodeEntity.id == entity_id, CodeEntity.project_id == project_id)
        .first()
    )
    if entity is None:
        raise HTTPException(status_code=404)
    entity_api._assert_entity_visible(entity, user, db, project_id)
    return entity


def _entity_analysis(entity: CodeEntity) -> dict:
    meta = entity.meta_json or {}
    keys = (
        "signature",
        "parameter_types",
        "return_type",
        "return_expressions",
        "throws_types",
        "exception_flow",
        "data_flow_truncated",
        "data_flow_omitted",
        "annotations",
        "annotation_details",
        "modifiers",
        "visibility",
    )
    return {key: meta[key] for key in keys if key in meta}
