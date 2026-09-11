from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import core.config as cfg
from core.db_setup import get_db
from models.database import (
    KnowledgeLink,
    CodeEntity,
    DocumentChunk,
    LinkBuilderRun,
    Project,
    KnowledgeSource,
    User,
)
from api.schemas import KnowledgeLinkCreate, KnowledgeLinkUpdate, LlmReviewRequest
from api.serializers import serialize_knowledge_link
from core.tracing import get_trace_id
from core.auth_dependency import get_current_user
from core.teams import get_visible_team_ids, is_admin
from core.projects import get_visible_project_ids
from services.ollama_client import ask_llm_json_for_profile
from services.job_control import send_tracked_task
from sqlalchemy.sql import func

router = APIRouter(prefix="/knowledge-links", tags=["knowledge-links"])


def _serialize_link_builder_run(run: LinkBuilderRun) -> dict:
    return {
        "id": run.id,
        "task_type": run.task_type,
        "project_id": run.project_id,
        "status": run.status,
        "progress_message": run.progress_message,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "links_created": run.links_created,
    }


def is_side_visible(
    source_type: str, entity_id: Optional[int], chunk_id: Optional[int], user: User, db: Session
) -> bool:
    visible_team_ids = get_visible_team_ids(user, db)
    if visible_team_ids is None:
        return True  # admin
    visible_project_ids = get_visible_project_ids(user, db)

    if source_type == "entity" and entity_id is not None:
        ent = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
        if not ent:
            return False
        if ent.project_id:
            proj = db.query(Project).filter(Project.id == ent.project_id).first()
            return (
                proj is not None
                and proj.team_id in visible_team_ids
                and ent.project_id in (visible_project_ids or [])
            )
        if ent.source_id:
            source = db.query(KnowledgeSource).filter(KnowledgeSource.id == ent.source_id).first()
            return (
                source is not None
                and source.team_id in visible_team_ids
                and (source.project_id is None or source.project_id in (visible_project_ids or []))
            )
    elif source_type == "document" and chunk_id is not None:
        chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
        if not chunk:
            return False
        if chunk.project_id:
            proj = db.query(Project).filter(Project.id == chunk.project_id).first()
            return (
                proj is not None
                and proj.team_id in visible_team_ids
                and chunk.project_id in (visible_project_ids or [])
            )
        if chunk.source_id:
            source = db.query(KnowledgeSource).filter(KnowledgeSource.id == chunk.source_id).first()
            return (
                source is not None
                and source.team_id in visible_team_ids
                and (source.project_id is None or source.project_id in (visible_project_ids or []))
            )
    return True


class LinkVisibilityIndex:
    """Sichtbarkeitsprüfung für viele KnowledgeLinks auf einmal.

    `is_side_visible` fragt pro Link-Seite einzeln die DB ab. Der Link-Manager
    listet je Status die komplette Vorschlagsmenge (real über 1000 Stück), was
    dort zu mehreren tausend Einzel-Queries pro Aufruf führte. Hier werden der
    Team-/Projekt-Scope des Nutzers und alle referenzierten Entities/Chunks samt
    ihrer Projekte/Wissensquellen gebündelt geladen; geprüft wird danach nur
    noch im Speicher. Die Regeln sind dieselben wie in `is_side_visible` --
    diese Funktion bleibt für Einzel-Links (PATCH/DELETE/llm-review) bestehen.
    """

    # Postgres verträgt zwar große IN-Listen, aber der Query-Plan wird mit jedem
    # zusätzlichen Parameter teurer -- lieber in Blöcken nachschlagen.
    _BATCH = 500

    def __init__(self, links, user: User, db: Session):
        visible_team_ids = get_visible_team_ids(user, db)
        self._unrestricted = visible_team_ids is None  # Admin: sieht alles
        if self._unrestricted:
            return

        self._teams = set(visible_team_ids)
        self._projects = set(get_visible_project_ids(user, db) or [])

        entity_ids = {
            i
            for link in links
            for i in (link.source_a_entity_id, link.source_b_entity_id)
            if i is not None
        }
        chunk_ids = {
            i
            for link in links
            for i in (link.source_a_chunk_id, link.source_b_chunk_id)
            if i is not None
        }

        # Pro Entity/Chunk interessiert nur die Herkunft (Projekt bzw. Wissensquelle).
        self._entities = {
            row.id: (row.project_id, row.source_id)
            for row in self._lookup(
                db,
                (CodeEntity.id, CodeEntity.project_id, CodeEntity.source_id),
                CodeEntity.id,
                entity_ids,
            )
        }
        self._chunks = {
            row.id: (row.project_id, row.source_id)
            for row in self._lookup(
                db,
                (DocumentChunk.id, DocumentChunk.project_id, DocumentChunk.source_id),
                DocumentChunk.id,
                chunk_ids,
            )
        }

        origins = list(self._entities.values()) + list(self._chunks.values())
        project_ids = {p for p, _ in origins if p is not None}
        source_ids = {s for _, s in origins if s is not None}

        self._project_teams = {
            row.id: row.team_id
            for row in self._lookup(db, (Project.id, Project.team_id), Project.id, project_ids)
        }
        self._sources = {
            row.id: (row.team_id, row.project_id)
            for row in self._lookup(
                db,
                (KnowledgeSource.id, KnowledgeSource.team_id, KnowledgeSource.project_id),
                KnowledgeSource.id,
                source_ids,
            )
        }

    @classmethod
    def _lookup(cls, db: Session, columns, id_column, ids) -> list:
        ids = list(ids)
        rows = []
        for start in range(0, len(ids), cls._BATCH):
            rows.extend(
                db.query(*columns).filter(id_column.in_(ids[start : start + cls._BATCH])).all()
            )
        return rows

    def _origin_visible(self, project_id: Optional[int], source_id: Optional[int]) -> bool:
        if project_id:
            return (
                self._project_teams.get(project_id) in self._teams and project_id in self._projects
            )
        if source_id:
            source = self._sources.get(source_id)
            if source is None:
                return False
            team_id, source_project_id = source
            return team_id in self._teams and (
                source_project_id is None or source_project_id in self._projects
            )
        # Weder Projekt noch Wissensquelle: nichts, woran die Sichtbarkeit hängt.
        return True

    def _side_visible(
        self, source_type: str, entity_id: Optional[int], chunk_id: Optional[int]
    ) -> bool:
        if source_type == "entity" and entity_id is not None:
            origin = self._entities.get(entity_id)
            return origin is not None and self._origin_visible(*origin)
        if source_type == "document" and chunk_id is not None:
            origin = self._chunks.get(chunk_id)
            return origin is not None and self._origin_visible(*origin)
        # Manuell angelegte Links ohne Entity-/Chunk-Bezug bleiben sichtbar.
        return True

    def is_visible(self, link) -> bool:
        if self._unrestricted:
            return True
        return self._side_visible(
            link.source_a_type, link.source_a_entity_id, link.source_a_chunk_id
        ) and self._side_visible(
            link.source_b_type, link.source_b_entity_id, link.source_b_chunk_id
        )


@router.post("")
def create_knowledge_link(
    link: KnowledgeLinkCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if not (
        is_side_visible(
            link.source_a_type, link.source_a_entity_id, link.source_a_chunk_id, user, db
        )
        and is_side_visible(
            link.source_b_type, link.source_b_entity_id, link.source_b_chunk_id, user, db
        )
    ):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf eine der verknüpften Quellen")

    db_link = KnowledgeLink(
        source_a_type=link.source_a_type,
        source_a_entity_id=link.source_a_entity_id,
        source_a_chunk_id=link.source_a_chunk_id,
        source_a_title=link.source_a_title,
        source_a_url=link.source_a_url,
        source_a_source_type=link.source_a_source_type,
        source_b_type=link.source_b_type,
        source_b_entity_id=link.source_b_entity_id,
        source_b_chunk_id=link.source_b_chunk_id,
        source_b_title=link.source_b_title,
        source_b_url=link.source_b_url,
        source_b_source_type=link.source_b_source_type,
        link_type=link.link_type or "manual",
        status=link.status or "approved",
        context=link.context,
        created_by="user",
        chat_session_id=link.chat_session_id,
    )
    db.add(db_link)
    db.commit()
    db.refresh(db_link)
    return serialize_knowledge_link(db_link)


def _knowledge_link_filters(query, status, source_type, min_score):
    """Gemeinsame Filterung für Liste und Zähler, damit beide nie auseinanderlaufen."""
    if status:
        query = query.filter(KnowledgeLink.status == status)
    if source_type:
        query = query.filter(
            (KnowledgeLink.source_a_source_type == source_type)
            | (KnowledgeLink.source_b_source_type == source_type)
        )
    if min_score is not None:
        query = query.filter(KnowledgeLink.score >= min_score)
    return query


# Spalten, die die Sichtbarkeitsprüfung braucht -- für den Zähler-Endpunkt, der
# die Links nicht serialisiert und deshalb nicht die vollen Zeilen laden muss.
_VISIBILITY_COLUMNS = (
    KnowledgeLink.status,
    KnowledgeLink.source_a_type,
    KnowledgeLink.source_a_entity_id,
    KnowledgeLink.source_a_chunk_id,
    KnowledgeLink.source_b_type,
    KnowledgeLink.source_b_entity_id,
    KnowledgeLink.source_b_chunk_id,
)


@router.get("")
def list_knowledge_links(
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    min_score: Optional[float] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = _knowledge_link_filters(db.query(KnowledgeLink), status, source_type, min_score)
    links = query.order_by(KnowledgeLink.created_at.desc()).all()
    visibility = LinkVisibilityIndex(links, user, db)
    return [serialize_knowledge_link(link) for link in links if visibility.is_visible(link)]


@router.get("/counts")
def count_knowledge_links(
    source_type: Optional[str] = None,
    min_score: Optional[float] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Zähler je Status für die Tab-Badges im Link-Manager.

    Vorher holte sich das Frontend dafür alle drei Statuslisten komplett --
    beim Offen-Tab also die über 1000 Vorschläge gleich zweimal (einmal als
    Liste, einmal nur, um sie zu zählen). Hier zählt die Datenbank."""
    counts = {"pending": 0, "approved": 0, "rejected": 0}

    if get_visible_team_ids(user, db) is None:  # Admin: keine Sichtbarkeitsfilterung nötig
        rows = _knowledge_link_filters(
            db.query(KnowledgeLink.status, func.count(KnowledgeLink.id)),
            None,
            source_type,
            min_score,
        ).group_by(KnowledgeLink.status)
        for link_status, count in rows:
            if link_status in counts:
                counts[link_status] = count
        return counts

    # Sonst muss jede Zeile durch die Sichtbarkeitsprüfung -- dafür reichen die
    # wenigen dafür nötigen Spalten statt der vollen Link-Objekte.
    rows = _knowledge_link_filters(
        db.query(*_VISIBILITY_COLUMNS), None, source_type, min_score
    ).all()
    visibility = LinkVisibilityIndex(rows, user, db)
    for row in rows:
        if row.status in counts and visibility.is_visible(row):
            counts[row.status] += 1
    return counts


@router.patch("/{link_id}")
def update_knowledge_link_status(
    link_id: int,
    update: KnowledgeLinkUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    db_link = db.query(KnowledgeLink).filter(KnowledgeLink.id == link_id).first()
    if not db_link:
        raise HTTPException(status_code=404, detail="Link nicht gefunden")

    if not (
        is_side_visible(
            db_link.source_a_type, db_link.source_a_entity_id, db_link.source_a_chunk_id, user, db
        )
        and is_side_visible(
            db_link.source_b_type, db_link.source_b_entity_id, db_link.source_b_chunk_id, user, db
        )
    ):
        raise HTTPException(status_code=404, detail="Link nicht gefunden")

    if update.status is not None:
        db_link.status = update.status
        db_link.reviewed_at = func.now()
    # Beschreibung ist unabhängig vom Status editierbar (leerer String löscht sie
    # wieder) — Pendant zur gleichen Erweiterung bei entity_links.py::update_link_status.
    if update.context is not None:
        db_link.context = update.context.strip() or None
    db.commit()
    db.refresh(db_link)
    return serialize_knowledge_link(db_link)


@router.post("/{link_id}/llm-review")
async def llm_review_knowledge_link(
    link_id: int,
    body: LlmReviewRequest = LlmReviewRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Bewertet ein einzelnes Knowledge-Link-Paar erneut per LLM (Nutzer-Klick im
    Link Manager, nicht Teil des Batch-Scans) — Pendant zu
    entity_links.py::llm_review_link, Prompt-Stil analog
    parser/tasks/cross_link_builder.py::_llm_review_pair, aber für ein
    einzelnes Paar statt den vollen Cross-Source-Scan. Ändert bewusst nicht
    den Status — der Nutzer entscheidet danach selbst per Bestätigen/Ablehnen.
    Nutzt das im Link-Manager-Header aktive LLM-Profil (body.llm_*), Cloud-
    Provider gated wie beim normalen Chat (api/chat.py).
    """
    requested_provider = (body.llm_provider or "ollama").lower()
    if requested_provider in cfg.CLOUD_LLM_PROVIDERS and not cfg.cloud_llm_allowed():
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cloud-LLM-Provider '{requested_provider}' ist für dieses Deployment deaktiviert "
                "(config/features.json: llm.allowCloudProviders). Bitte ein lokales Ollama-Profil verwenden."
            ),
        )

    db_link = db.query(KnowledgeLink).filter(KnowledgeLink.id == link_id).first()
    if not db_link:
        raise HTTPException(status_code=404, detail="Link nicht gefunden")

    if not (
        is_side_visible(
            db_link.source_a_type, db_link.source_a_entity_id, db_link.source_a_chunk_id, user, db
        )
        and is_side_visible(
            db_link.source_b_type, db_link.source_b_entity_id, db_link.source_b_chunk_id, user, db
        )
    ):
        raise HTTPException(status_code=404, detail="Link nicht gefunden")

    if not (db_link.source_a_chunk_id and db_link.source_b_chunk_id):
        raise HTTPException(
            status_code=400,
            detail="Kein Dokument-Inhalt zu diesem Link vorhanden — manuell angelegte Links können nicht geprüft werden",
        )

    chunk_a = db.query(DocumentChunk).filter(DocumentChunk.id == db_link.source_a_chunk_id).first()
    chunk_b = db.query(DocumentChunk).filter(DocumentChunk.id == db_link.source_b_chunk_id).first()
    if not chunk_a or not chunk_b:
        raise HTTPException(
            status_code=404, detail="Verknüpfte Dokument-Chunks nicht mehr vorhanden"
        )

    prompt = (
        "Du bewertest, ob zwei Dokument-Ausschnitte aus unterschiedlichen Quellen wirklich inhaltlich zusammenhängen.\n\n"
        f'Dokument A [{db_link.source_a_source_type or "—"}] "{db_link.source_a_title}": {(chunk_a.content or "")[:300]}\n\n'
        f'Dokument B [{db_link.source_b_source_type or "—"}] "{db_link.source_b_title}": {(chunk_b.content or "")[:300]}\n\n'
        "Antworte NUR mit einem JSON-Objekt der Form "
        '{"confidence": <Ganzzahl 0-100>, "reason": "<kurze Begründung auf Deutsch>"}.'
    )

    try:
        data = await ask_llm_json_for_profile(
            prompt,
            provider=requested_provider,
            model=body.llm_model,
            api_key=body.llm_api_key,
            base_url=body.llm_base_url,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM-Prüfung fehlgeschlagen: {e}")

    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        raise HTTPException(status_code=502, detail="LLM lieferte keine gültige Konfidenz")

    db_link.score = round(max(0.0, min(100.0, float(confidence))) / 100.0, 4)
    if data.get("reason"):
        db_link.context = data["reason"]
    db.commit()
    db.refresh(db_link)
    return serialize_knowledge_link(db_link)


@router.delete("/{link_id}")
def delete_knowledge_link(
    link_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    db_link = db.query(KnowledgeLink).filter(KnowledgeLink.id == link_id).first()
    if not db_link:
        raise HTTPException(status_code=404, detail="Link nicht gefunden")

    if not (
        is_side_visible(
            db_link.source_a_type, db_link.source_a_entity_id, db_link.source_a_chunk_id, user, db
        )
        and is_side_visible(
            db_link.source_b_type, db_link.source_b_entity_id, db_link.source_b_chunk_id, user, db
        )
    ):
        raise HTTPException(status_code=404, detail="Link nicht gefunden")

    db.delete(db_link)
    db.commit()
    return {"message": "Link erfolgreich gelöscht"}


@router.post("/compute")
def trigger_knowledge_link_computation(
    min_confidence: Optional[int] = Query(
        None,
        ge=0,
        le=100,
        description="Vom Nutzer eingestellte Mindest-Wahrscheinlichkeit (%) für die LLM-Bewertung, ab der ein Kandidatenpaar als Vorschlag gespeichert wird.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only admins can trigger cross-source computation
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Nur für Administratoren")

    # Ein Refresh startet den Cross-Source-Scan von neuem — bisher unbestätigte
    # (pending) Vorschläge sind noch nicht reviewt und würden sonst als
    # Karteileichen neben den frisch berechneten liegen bleiben, da
    # compute_knowledge_links_async einen bestehenden Link (jeden Status) pro
    # Chunk-Paar nie überschreibt. Approved/rejected Links bleiben unangetastet.
    db.query(KnowledgeLink).filter(KnowledgeLink.status == "pending").delete(
        synchronize_session=False
    )

    run = LinkBuilderRun(task_type="knowledge_links", project_id=None, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)

    send_tracked_task(
        db,
        run,
        "compute_knowledge_links",
        [run.id],
        {"trace_id": get_trace_id(), "min_confidence": min_confidence},
    )
    return {"message": "Cross-Source Analyse gestartet", "run_id": run.id}


@router.get("/runs")
def list_knowledge_link_runs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    History of /knowledge-links/compute invocations (most recent first) —
    including runs that crashed or found 0 new links, so a silent failure
    stays distinguishable from a clean run that found nothing.
    """
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Nur für Administratoren")
    runs = (
        db.query(LinkBuilderRun)
        .filter(LinkBuilderRun.task_type == "knowledge_links")
        .order_by(LinkBuilderRun.created_at.desc())
        .all()
    )
    return [_serialize_link_builder_run(r) for r in runs]
