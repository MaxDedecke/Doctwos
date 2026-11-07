"""Belegpaket für eine Frage in einem Werkzeugaufruf (CLAUDE.md, „MCP-Ziel“).

MCP-Werkzeug answer_context und der Chat-Agent nutzen dasselbe Paket; früher importierte der Agent es aus
mcp_server.py (aus mcp_server.py herausgelöst).
"""

import logging
import asyncio
import concurrent.futures
import json
import math
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from doctus_models.database import (
    CodeEntity,
    DocumentChunk,
    EmbeddingProfile,
    KnowledgeSource,
    User,
)
from services.ai_settings import get_active_embedding_profile
from services.index_state import stale_sources
from services.ollama_client import embed_text
from doctus_models.language_profile import role_of
from services import evidence as evidence_blocks
from services.source_access import site_excerpt as _site_excerpt


from services.code_symbols import (
    ToolInputError,
    _STRUCTURAL,
    _compact_entity,
    _find_entities,
    _pick_entity,
    _project,
    _symbol_matches,
)
from services.call_flow_page import (
    _call_flow_page,
    _flow_summary,
)
from services.entity_explanation import (
    _CHILD_SKIP,
    _explain_entity,
    _extract_symbols,
    _question_stems,
    _relevant_children,
)

logger = logging.getLogger(__name__)


def _embedding_profile_for_project(db: Session, project_id: int):
    """Use the unique embedding profile matching a project's indexed vectors.

    The active profile is deployment-wide, while projects may have been
    indexed with different models. Prefer an unambiguous project model so an
    MCP query is embedded in the same vector space as its chunks. For legacy
    projects with multiple models or multiple profiles for the same model,
    retain the active-profile behavior.
    """
    source_models = {
        model
        for (model,) in db.query(KnowledgeSource.embedding_model)
        .filter(KnowledgeSource.project_id == project_id)
        .distinct()
        .all()
        if model
    }
    chunk_models = {
        model
        for (model,) in db.query(DocumentChunk.embedding_model)
        .filter(DocumentChunk.project_id == project_id)
        .distinct()
        .all()
        if model
    }
    models = source_models or chunk_models
    if len(models) == 1:
        model = next(iter(models))
        profiles = db.query(EmbeddingProfile).filter(EmbeddingProfile.model == model).all()
        if len(profiles) == 1:
            return profiles[0]
    return get_active_embedding_profile(db)


def _shrink_largest_source(entry: dict) -> bool:
    """Cut the last fifth of the longest expanded/helper/chain source (whole lines, at least 4 kept)."""
    parts = [
        p
        for key in ("expanded", "helper_methods", "callee_chain")
        for p in entry.get(key) or []
        if (p.get("source") or {}).get("text")
    ]
    if not parts:
        return False
    target = max(parts, key=lambda p: len(p["source"]["text"]))
    lines = target["source"]["text"].splitlines()
    if len(lines) <= 4:
        return False
    keep = max(4, int(len(lines) * 0.8))
    target["source"]["text"] = "\n".join(lines[:keep])
    target["source"]["truncated"] = True
    return True


def _fit_evidence(evidence: list[dict], limit: int) -> None:
    """Shrink an evidence pack in steps until it fits.

    Order: redundant extras first (a control-flow block makes ``callees`` and ``callee_chain`` redundant), then lists,
    never the primary source and last of all the evidence blocks (includes, control flow, data origin) that answer
    the question directly."""

    def size() -> int:
        return len(json.dumps(evidence, ensure_ascii=False))

    def trim_sites(entry: dict) -> bool:
        trimmed = False
        for site in entry.get("call_sites") or []:
            if isinstance(site, dict) and len(site.get("text") or "") > 700:
                site["text"] = site["text"][:700]
                trimmed = True
        return trimmed

    def trim_includes(entry: dict) -> bool:
        block = entry.get("includes")
        if not block or not any(
            len(block[key]) > 14 for key in ("resolved", "external", "unresolved")
        ):
            return False
        for key in ("resolved", "external", "unresolved"):
            del block[key][14:]
        block["truncated"] = True
        return True

    def trim_shared(entry: dict) -> bool:
        files = (entry.get("shared_files") or {}).get("files")
        if not files:
            return False
        for item in files:
            if len(item["users"]) > 4:
                item["more_users"] = item.get("more_users", 0) + len(item["users"]) - 4
                del item["users"][4:]
                return True
        if len(files) > 2:
            files.pop()
            return True
        return False

    def trim_flow(entry: dict) -> bool:
        flow = (entry.get("control_flow") or {}).get("flow")
        if not flow or len(flow) <= 6:
            return False
        flow.pop()
        return True

    steps = [
        lambda e: e.pop("other_matches", None),
        _shrink_largest_source,
        lambda e: e.get("control_flow") and (e.pop("callees", None) or e.pop("callee_chain", None)),
        trim_sites,
        lambda e: (
            e.__setitem__("data_access", e["data_access"][:6])
            if len(e.get("data_access") or []) > 6
            else None
        ),
        lambda e: (
            e.__setitem__("used_by", e["used_by"][:8]) if len(e.get("used_by") or []) > 8 else None
        ),
        lambda e: (
            e.__setitem__("callers", e["callers"][:3]) if len(e.get("callers") or []) > 3 else None
        ),
        lambda e: (
            e.__setitem__("callees", e["callees"][:6]) if len(e.get("callees") or []) > 6 else None
        ),
        lambda e: e.get("call_sites") and len(e["call_sites"]) > 1 and e["call_sites"].pop(),
        lambda e: e.pop("call_sites", None),
        lambda e: e.pop("data_access", None),
        lambda e: e.get("expanded") and len(e["expanded"]) > 1 and e["expanded"].pop(),
        lambda e: (
            e.get("helper_methods") and len(e["helper_methods"]) > 1 and e["helper_methods"].pop()
        ),
        lambda e: e.pop("helper_methods", None),
        lambda e: e.pop("callees", None),
        lambda e: e.pop("callee_chain", None),
        lambda e: e.get("data_origin") and len(e["data_origin"]) > 5 and e["data_origin"].pop(),
        trim_shared,
        trim_includes,
        trim_flow,
    ]
    for step in steps:
        for entry in reversed(evidence):
            for _ in range(8):
                if size() <= limit:
                    return
                if not step(entry):
                    break


def _embedding_scores(
    db: Session, project_id: int, query: str, texts: list[str]
) -> list[float] | None:
    """Cosine similarity of the query to each text in the project's embedding space; None if unavailable."""
    if not query or not texts:
        return None
    try:
        profile = _embedding_profile_for_project(db, project_id)
        config = {
            "model": profile.model,
            "provider": profile.provider,
            "base_url": profile.base_url,
            "path": profile.path,
            "api_key": profile.api_key,
            "dimension": profile.dimension,
            "context_length": profile.context_length,
        }

        async def run() -> list[list[float]]:
            return list(
                await asyncio.gather(
                    *(
                        embed_text(t[:600], is_query=(i == 0), **config)
                        for i, t in enumerate([query, *texts])
                    )
                )
            )

        # FastMCP calls sync tools on the server's event loop, so the embeddings get a loop of their own.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            vectors = pool.submit(asyncio.run, run()).result(timeout=20)
    except (
        Exception
    ) as exc:  # embedding service down, wrong profile, ... -> lexical ranking stays in charge
        logger.info(
            "answer_context embedding relevance unavailable (%s: %s)",
            type(exc).__name__,
            str(exc)[:160],
        )
        return None
    head, rest = vectors[0], vectors[1:]
    norm = math.sqrt(sum(x * x for x in head)) or 1.0
    return [
        sum(a * b for a, b in zip(head, v)) / (norm * (math.sqrt(sum(x * x for x in v)) or 1.0))
        for v in rest
    ]


def _embedding_similarities(
    db: Session, project_id: int, topic: str, texts: dict[str, str]
) -> dict[str, float]:
    keys = list(texts)
    scores = _embedding_scores(db, project_id, topic, [texts[k] for k in keys])
    return dict(zip(keys, scores)) if scores is not None else {}


def _rank_by_embedding(
    db: Session, project_id: int, topic: str, items: list[tuple[float, dict]], key
) -> list[tuple[float, dict]]:
    """Blend the lexical score with embedding similarity for the best lexical candidates (top 16)."""
    head = sorted(items, key=lambda row: -row[0])[:12]
    scores = _embedding_scores(db, project_id, topic, [key(item) for _s, item in head])
    if scores is None:
        return items
    blended = [(lex + 8.0 * max(0.0, sim), item) for (lex, item), sim in zip(head, scores)]
    return sorted(blended, key=lambda row: -row[0]) + [row for row in items if row not in head]


def _resolve_chain_target(db: Session, project_id: int, name: str) -> CodeEntity | None:
    rows = (
        db.query(CodeEntity)
        .filter(CodeEntity.project_id == project_id, CodeEntity.qualified_name == name)
        .limit(4)
        .all()
    )
    structural = [e for e in rows if e.type in _STRUCTURAL]
    return (structural or rows or [None])[0]


def build_answer_context(
    db: Session,
    user: User,
    project_id: int,
    *,
    question: str = "",
    symbols: list[str] | None = None,
    topic: str = "",
    max_chars: int = 8000,
    use_embeddings: bool = True,
) -> dict:
    """Evidence pack for a question: source, callers, callees (two hops), data access and users of the named symbols.

    Shared by the MCP tool and the chat prefetch. `symbols` are names the caller already extracted; without them
    they are taken from the free text."""
    text = " ".join(part for part in (question, topic) if part).strip()
    relevance_query = (topic or question).strip()
    max_chars = max(3000, min(max_chars, 14000))
    if not text or len(text) > 1500:
        raise ToolInputError("invalid query")
    _project(db, user, project_id)
    callers_intent = bool(
        re.search(
            r"aufrufer|wer ruft|ruft .{0,90}auf|rufen .{0,90}auf|welche (klasse|klassen|programm|programme|methode|methoden|modul|module)|binden .{0,60}ein|einbind|"
            r"verwendet von|verwenden|nutzen|callers?|called by|included? by|who calls|which (classes|programs)",
            text.lower(),
        )
    )
    includes_intent = bool(evidence_blocks.INCLUDES_INTENT.search(text))
    flow_intent = bool(evidence_blocks.FLOW_INTENT.search(text))
    shared_intent = bool(evidence_blocks.SHARED_FILES_INTENT.search(text))
    given = [
        s.strip() for s in (symbols or []) if isinstance(s, str) and 2 < len(s.strip()) <= 160
    ][:8]
    terms = given or _extract_symbols(text)
    resolved: list[tuple[str, CodeEntity, list[CodeEntity], str]] = []
    seen: set[int] = set()
    unresolved: list[str] = []
    ambiguous: list[tuple[str, list[CodeEntity], str]] = []
    data_intent = bool(evidence_blocks.DATA_INTENT.search(text))
    looked: list[tuple[str, list[CodeEntity], list[CodeEntity], str]] = []
    for term in terms:
        found, _suggestions, mode = _find_entities(db, user, project_id, term, 6)
        exact = [e for e in found if _symbol_matches(e, term)]
        structural = [e for e in exact if e.type in _STRUCTURAL or e.type == "copybook"] or exact
        looked.append((term, exact, structural, mode))
    # Containers named in the question (a class, a program): a member name next to them belongs to them
    # (`expirationDate` of `MfaTrustedDevice`), and a question about a value prefers the data entity.
    containers = [
        structural[0]
        for _t, _e, structural, _m in looked
        if structural
        and role_of(structural[0].type) == "container"
        and len({e.file_path for e in structural}) == 1
    ]
    for term, exact, structural, mode in looked:
        pool, candidates = structural, exact
        if (
            containers
            and "." not in term
            and "#" not in term
            and not any(c.name.casefold() == term.casefold() for c in containers)
        ):
            for container in containers:
                scoped_term = f"{container.name}.{term}"
                scoped_found, _s, _m = _find_entities(db, user, project_id, scoped_term, 6)
                scoped = [e for e in scoped_found if _symbol_matches(e, scoped_term)]
                if scoped:
                    pool, candidates = scoped, scoped
                    break
        if data_intent:
            data = [e for e in candidates if role_of(e.type) == "data" and e.type != "parameter"]
            if data:
                pool = data
        if not pool:
            unresolved.append(term)
            continue
        # Derselbe Dataset- oder Tabellenname aus mehreren Jobs oder Programmen ist dieselbe Datei.
        if pool and all(
            item.type in evidence_blocks.SAME_NAME_RESOURCE_TYPES
            and item.name.upper() == pool[0].name.upper()
            for item in pool
        ):
            pool = pool[:1]
        entity, others = _pick_entity(pool)
        if entity is None or entity.id in seen:
            if entity is None:
                ambiguous.append((term, pool, mode))
            continue
        seen.add(entity.id)
        resolved.append((term, entity, others, mode))
    # A bare name that exists in many files (`1000-INITIALIZE`) belongs to the file of the symbols named next to it.
    named_files = {entity.file_path for _t, entity, _o, _m in resolved}
    for term, structural, mode in ambiguous:
        scoped = [e for e in structural if e.file_path in named_files]
        entity, others = _pick_entity(scoped) if scoped else (None, [])
        if entity is None or entity.id in seen:
            if entity is None:
                unresolved.append(term)
            continue
        seen.add(entity.id)
        resolved.append((term, entity, others, mode))
    if not resolved:
        found, suggestions, _mode = _find_entities(db, user, project_id, text[:200], 6)
        return _with_index_status(
            db,
            project_id,
            {
                "project_id": project_id,
                "question": text,
                "resolved": [],
                "unresolved_terms": unresolved or terms,
                "candidates": [_compact_entity(e) for e in found[:6]],
                "did_you_mean": suggestions,
                "hint": "No named symbol found. Use search_code with a name from the candidates or search_knowledge for wording.",
            },
        )
    # Method-level references first, then the rest; at most three entities share the budget.
    resolved.sort(key=lambda row: 0 if row[1].type in {"method", "paragraph"} else 1)
    primary = resolved[:3]
    per_entity = max(2500, max_chars // len(primary))
    evidence = []
    for term, entity, others, mode in primary:
        entry = _explain_entity(
            db,
            user,
            project_id,
            entity,
            others,
            mode,
            term,
            per_entity,
            None,
            None,
            with_context=True,
            used_by_limit=40 if callers_intent else 12,
            compact=True,
        )
        role = role_of(entity.type)
        if role == "container" and includes_intent:
            included = evidence_blocks.includes(db, user, project_id, entity)
            if included:
                entry["includes"] = included
        if shared_intent or entity.type in evidence_blocks.RESOURCE_ENTITY_TYPES:
            shared = evidence_blocks.shared_files(db, user, entity)
            if shared:
                entry["shared_files"] = shared
        if role in {"container", "routine"} and flow_intent:
            flow = evidence_blocks.control_flow(
                db, user, project_id, entity, budget_chars=min(3000, per_entity)
            )
            if flow:
                entry["control_flow"] = flow
        if role == "data":
            origin = evidence_blocks.data_origin(db, user, project_id, entity)
            if origin:
                entry["data_origin"] = origin
                entry["data_origin_notice"] = (
                    "Indexed writes of this data entity, followed backwards through the operands of each write "
                    "(`reads`). Each step is an index fact with its source line; cite it as `cite`. It is not a complete runtime flow."
                )
        if "outline" in entry:
            expanded = []
            child_budget = max(600, min(2200, int(per_entity * 0.62) // 5))
            for item in _relevant_children(
                relevance_query or text,
                entry["outline"],
                4,
                sims=(
                    lambda items: _embedding_similarities(
                        db,
                        project_id,
                        relevance_query,
                        {i["symbol"]: f"{i['symbol']} {i.get('facts', '')}" for i in items},
                    )
                )
                if use_embeddings and relevance_query
                else None,
            ):
                child = (
                    db.query(CodeEntity)
                    .filter(
                        CodeEntity.project_id == project_id,
                        CodeEntity.file_path == entity.file_path,
                        CodeEntity.qualified_name == item["symbol"],
                    )
                    .first()
                )
                if child is None:
                    continue
                part = _explain_entity(
                    db,
                    user,
                    project_id,
                    child,
                    [],
                    "exact",
                    item["symbol"],
                    child_budget,
                    None,
                    None,
                    with_context=False,
                    compact=True,
                )
                if part.get("source"):
                    expanded.append(
                        {
                            "symbol": item["symbol"],
                            "lines": item["lines"],
                            "facts": item.get("facts"),
                            "source": part["source"],
                        }
                    )
            shown = {x["symbol"] for x in expanded}
            entry["outline"] = [
                dict(i, facts=i["facts"][:70]) if i.get("facts") else i
                for i in entry["outline"]
                if i["symbol"] not in shown and i.get("type") not in _CHILD_SKIP
            ][:6]
            if expanded:
                entry["expanded"] = expanded
            entry["notice"] = (
                "Outline of the whole unit plus the source of the parts that match the question best."
            )
        elif entry.get("callees"):
            full_callees = entry["callees"]
            entry["callees"] = [
                f"{c['to'].split('(', 1)[0].rsplit('.', 1)[-1]} (Zeile {c.get('line')})"
                for c in full_callees[:12]
                if c.get("to")
            ]
            # Methods often delegate to a helper in the same class: read the most relevant one as well.
            q_stems = _question_stems(text)
            same_file = [
                c
                for c in full_callees
                if c.get("location", "").startswith(f"{entity.file_path}:") and c.get("to")
            ]
            candidates = []
            for c in same_file[:8]:
                child = (
                    db.query(CodeEntity)
                    .filter(
                        CodeEntity.project_id == project_id,
                        CodeEntity.file_path == entity.file_path,
                        CodeEntity.qualified_name == c["to"],
                    )
                    .first()
                )
                if child is None or child.id == entity.id:
                    continue
                tail = re.split(r"[.#]", c["to"].split("(", 1)[0])[-1].lower()
                relevance = len(q_stems & {t[:5] for t in re.findall(r"[a-z0-9]{3,}", tail)}) * 2
                size = (child.end_line or 0) - (child.start_line or 0)
                candidates.append(
                    (relevance + min(4, size // 25), {"child": child, "name": c["to"]})
                )
            if use_embeddings and relevance_query and len(candidates) > 1:
                candidates = _rank_by_embedding(
                    db, project_id, relevance_query, candidates, lambda i: i["name"]
                )
            helpers = []
            for _score, item in sorted(candidates, key=lambda row: -row[0])[:2]:
                child, name = item["child"], item["name"]
                if any(h["symbol"] == name for h in helpers):
                    continue
                part = _explain_entity(
                    db,
                    user,
                    project_id,
                    child,
                    [],
                    "exact",
                    name,
                    4200,
                    None,
                    None,
                    with_context=False,
                    compact=True,
                )
                if part.get("source"):
                    helpers.append(
                        {
                            "symbol": name,
                            "lines": f"{child.start_line}-{child.end_line}",
                            "source": part["source"],
                        }
                    )
            if helpers:
                entry["helper_methods"] = helpers
            # Second hop: the callees that are not helpers already read, with their own callees.
            taken = {h["symbol"] for h in helpers} | {entity.qualified_name}
            chain_candidates, tried = [], set()
            for c in full_callees:
                name = c.get("to")
                if not name or name in taken or name in tried or len(tried) >= 10:
                    continue
                tried.add(name)
                target = _resolve_chain_target(db, project_id, name)
                size = (
                    ((target.end_line or 0) - (target.start_line or 0)) if target is not None else 0
                )
                if target is None or target.id == entity.id or size < 4:
                    continue  # unresolved, recursive or a trivial accessor
                tail = re.split(r"[.#]", name.split("(", 1)[0])[-1].lower()
                relevance = len(q_stems & {t[:5] for t in re.findall(r"[a-z0-9]{3,}", tail)}) * 2
                chain_candidates.append(
                    (
                        relevance + min(4, size // 25),
                        {"target": target, "name": name, "line": c.get("line")},
                    )
                )
            if use_embeddings and relevance_query and len(chain_candidates) > 1:
                chain_candidates = _rank_by_embedding(
                    db, project_id, relevance_query, chain_candidates, lambda i: i["name"]
                )
            chain = []
            for _score, item in sorted(chain_candidates, key=lambda row: -row[0])[:2]:
                target, name = item["target"], item["name"]
                part = _explain_entity(
                    db,
                    user,
                    project_id,
                    target,
                    [],
                    "exact",
                    name,
                    2600,
                    None,
                    None,
                    with_context=False,
                    compact=True,
                )
                if not part.get("source"):
                    continue
                try:
                    onward = _flow_summary(
                        _call_flow_page(
                            db,
                            user,
                            project_id,
                            target.id,
                            hops=1,
                            direction="outgoing",
                            scope="execution",
                            page_size=10,
                            cursor=None,
                            include_source=False,
                        ),
                        "outgoing",
                        10,
                    )
                except (ValueError, HTTPException):
                    onward = []
                chain.append(
                    {
                        "symbol": name,
                        "lines": f"{target.start_line}-{target.end_line}",
                        "file": target.file_path,
                        "called_at_line": item["line"],
                        "source": part["source"],
                        "calls": [
                            f"{o['to'].split('(', 1)[0].rsplit('.', 1)[-1]} (Zeile {o.get('line')})"
                            for o in onward
                            if o.get("to")
                        ],
                    }
                )
            if chain:
                entry["callee_chain"] = chain
        if callers_intent:
            sites = []
            for caller in (entry.get("callers") or [])[:2]:
                caller_entity = (
                    db.query(CodeEntity)
                    .filter(
                        CodeEntity.project_id == project_id,
                        CodeEntity.qualified_name == caller.get("from"),
                    )
                    .first()
                )
                if caller_entity is not None and caller.get("line"):
                    site = _site_excerpt(db, user, caller_entity, int(caller["line"]), 16)
                    if site:
                        site["caller"] = caller.get("from")
                        sites.append(site)
            if sites:
                entry["call_sites"] = sites
        evidence.append(entry)
    _fit_evidence(evidence, max_chars - 600)
    return _with_index_status(
        db,
        project_id,
        {
            "project_id": project_id,
            "resolved": [
                {
                    "symbol": e.qualified_name,
                    "type": e.type,
                    "location": f"{e.file_path}:{e.start_line}-{e.end_line}",
                }
                for _t, e, _o, _m in primary
            ],
            "unresolved_terms": unresolved,
            "evidence": evidence,
            "notice": "Evidence assembled by the server from the index. Cite every fact as `path/file.ext:line` in backticks, "
            "copying the `cite` fields where present; never write 'line N of file'. Call explain_symbol for any other symbol.",
        },
    )


def _with_index_status(db: Session, project_id: int, result: dict) -> dict:
    """Hängt den Indexstand an, wenn eine Quelle des Projekts nicht auf einem einheitlichen Stand ist."""
    stale = stale_sources(db, project_id=project_id)
    if stale:
        result["index_status"] = {
            "sources": stale,
            "notice": "The index is not on one consistent revision for these sources; files may come "
            "from different revisions and relations to changed files may be missing. Say so in the answer.",
        }
    return result
