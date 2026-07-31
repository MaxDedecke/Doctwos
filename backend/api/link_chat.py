"""
backend/api/link_chat.py
===========================
Geführter Chat-Assistent zum interaktiven Finden und Knüpfen von Wissenslinks.
"""

import json
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

import core.config as cfg
from api.schemas import ChatRequest
from api.serializers import serialize_knowledge_link
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from models.database import ChatMessage, ChatSession, CodeEntity, DocumentChunk, KnowledgeLink, KnowledgeSource, Project, User
from core.teams import get_visible_team_ids, is_admin
from core.projects import get_visible_project_ids, chunk_source_label

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/link-chat", tags=["link-chat"])


@router.get("/sources")
def get_link_sources(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    team_ids = get_visible_team_ids(user, db)
    project_ids = get_visible_project_ids(user, db)
    if team_ids is not None:
        projects = db.query(Project).filter(Project.team_id.in_(team_ids))
        if project_ids is not None:
            projects = projects.filter(Project.id.in_(project_ids))
        projects = projects.all()
        
        k_sources = db.query(KnowledgeSource).filter(KnowledgeSource.team_id.in_(team_ids))
        if project_ids is not None:
            k_sources = k_sources.filter(
                or_(
                    KnowledgeSource.project_id.in_(project_ids),
                    KnowledgeSource.project_id == None
                )
            )
        k_sources = k_sources.all()
    else:
        projects = db.query(Project).all()
        k_sources = db.query(KnowledgeSource).all()
    
    results = []
    for p in projects:
        results.append({
            "id": f"project_{p.id}",
            "type": "Project",
            "name": p.name,
            "item_count": db.query(CodeEntity).filter(CodeEntity.project_id == p.id).count(),
            "project_id": p.id
        })
    for s in k_sources:
        results.append({
            "id": f"source_{s.id}",
            "type": s.type,
            "name": s.name,
            "item_count": db.query(DocumentChunk).filter(DocumentChunk.source_id == s.id).count(),
            "source_id": s.id
        })
    return results


@router.get("/sessions/{session_id}/messages")
def get_link_chat_messages(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    if session.owner_id != user.id and not is_admin(user):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Chat-Sitzung")

    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
    return [{
        "id": m.id, "role": m.role, "content": m.content,
        "metadata_json": m.metadata_json, "created_at": m.created_at
    } for m in messages]


@router.post("/sessions/{session_id}/messages")
async def send_link_chat_message(
    session_id: int,
    request: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    if session.owner_id != user.id and not is_admin(user):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Chat-Sitzung")

    # User message speichern
    user_msg = ChatMessage(session_id=session_id, role="user", content=request.message)
    db.add(user_msg)
    db.commit()

    async def event_generator():
        query_text = request.message
        if cfg.OLLAMA_EMBED_MODEL.startswith("nomic-embed-text") and not query_text.startswith("search_query:"):
            query_text = f"search_query: {query_text}"
            
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{cfg.OLLAMA_BASE_URL}/api/embeddings", json={
                "model": cfg.OLLAMA_EMBED_MODEL,
                "prompt": query_text
            })
            query_embedding = resp.json()["embedding"]

        # Search across visible sources
        team_ids = get_visible_team_ids(user, db)
        project_ids = get_visible_project_ids(user, db)
        chunk_query = db.query(DocumentChunk)
        if team_ids is not None:
            chunk_query = chunk_query.filter(
                or_(
                    DocumentChunk.project_id.in_(project_ids or []),
                    DocumentChunk.source_id.in_(
                        [s[0] for s in db.query(KnowledgeSource.id).filter(
                            KnowledgeSource.team_id.in_(team_ids),
                            or_(
                                KnowledgeSource.project_id.in_(project_ids or []),
                                KnowledgeSource.project_id == None
                            )
                        ).all()]
                    )
                )
            )

        results = chunk_query.order_by(
            DocumentChunk.embedding.cosine_distance(query_embedding)
        ).limit(6).all()

        suggestions = []
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                a, b = results[i], results[j]
                if (a.source_id and a.source_id == b.source_id) or (a.project_id and a.project_id == b.project_id):
                    continue
                
                meta_a, meta_b = a.metadata_json or {}, b.metadata_json or {}
                suggestions.append({
                    "source_a_title": meta_a.get("title") or a.file_path,
                    "source_a_source_type": meta_a.get("source_type") or chunk_source_label(a, db),
                    "source_a_chunk_id": a.id,
                    "source_a_url": meta_a.get("url"),
                    "source_b_title": meta_b.get("title") or b.file_path,
                    "source_b_source_type": meta_b.get("source_type") or chunk_source_label(b, db),
                    "source_b_chunk_id": b.id,
                    "source_b_url": meta_b.get("url"),
                    "score": 0.85,
                    "context": f"Diese Dokumente sind semantisch verwandt."
                })

        yield f"data: {json.dumps({'type': 'link_suggestions', 'suggestions': suggestions[:3]})}\n\n"

        # LLM Answer
        prompt = (
            "Du bist der Doctus Link-Assistent. Deine Aufgabe ist es, dem Nutzer zu helfen, "
            "relevante Informationen über verschiedene Wissensquellen hinweg zu finden und zu verknüpfen.\n\n"
            "Kontext aus der Suche:\n"
        )
        for s in results:
            meta = s.metadata_json or {}
            stype = meta.get("source_type") or chunk_source_label(s, db)
            title = meta.get("title") or s.file_path
            prompt += f"- [{stype}] {title}: {s.content[:200]}\n"
        
        prompt += f"\nNutzer-Anfrage: {request.message}\n\n"
        prompt += "Antworte kurz und schlage konkret vor, welche der oben genannten Quellen verknüpft werden sollten."

        answer = ""
        provider = (request.llm_provider or "ollama").lower()
        try:
            if provider in ("openai", "ollama"):
                is_ollama = provider == "ollama"
                if is_ollama:
                    url = f"{cfg.OLLAMA_BASE_URL}/v1/chat/completions"
                    headers = {"Content-Type": "application/json"}
                    model_to_use = cfg.resolve_ollama_model(request.llm_model)
                else:
                    base = (request.llm_base_url or "https://api.openai.com/v1").rstrip("/")
                    url = base if "/chat/completions" in base else f"{base}/chat/completions"
                    headers = {"Content-Type": "application/json"}
                    if request.llm_api_key:
                        headers["Authorization"] = f"Bearer {request.llm_api_key}"
                    model_to_use = request.llm_model or "gpt-4o"

                payload = {
                    "model": model_to_use,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True
                }
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]": break
                                try:
                                    chunk = json.loads(data_str)
                                    content = chunk["choices"][0].get("delta", {}).get("content")
                                    if content:
                                        answer += content
                                        yield f"data: {json.dumps({'type': 'content_chunk', 'content': content})}\n\n"
                                except Exception:
                                    pass

            elif provider == "gemini":
                model_name = request.llm_model or "gemini-1.5-flash"
                key = request.llm_api_key or ""
                full_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(full_url, json=payload, headers={"Content-Type": "application/json"})
                    resp.raise_for_status()
                    answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    yield f"data: {json.dumps({'type': 'content_chunk', 'content': answer})}\n\n"

            elif provider == "anthropic":
                model_name = request.llm_model or "claude-3-5-sonnet-20241022"
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": request.llm_api_key or "",
                    "anthropic-version": "2023-06-01"
                }
                payload = {
                    "model": model_name,
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                }
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
                    resp.raise_for_status()
                    answer = resp.json()["content"][0]["text"]
                    yield f"data: {json.dumps({'type': 'content_chunk', 'content': answer})}\n\n"
        except Exception as e:
            error_detail = f"Fehler bei der Kommunikation mit dem LLM-Provider ({provider}): {str(e)}"
            logger.error(error_detail)
            yield f"data: {json.dumps({'type': 'error', 'error': error_detail})}\n\n"
            return

        assistant_msg = ChatMessage(session_id=session_id, role="assistant", content=answer, metadata_json={"type": "link_assistant", "suggestions": suggestions[:3]})
        db.add(assistant_msg)
        db.commit()
        yield f"data: {json.dumps({'type': 'answer', 'content': answer})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/confirm")
def confirm_suggested_links(
    session_id: int,
    links_data: List[dict],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    if session.owner_id != user.id and not is_admin(user):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Chat-Sitzung")

    from api.knowledge_links import is_side_visible
    created_links = []
    for data in links_data:
        if not (is_side_visible(data.get("source_a_type", "document"), data.get("source_a_entity_id"), data.get("source_a_chunk_id"), user, db) and
                is_side_visible(data.get("source_b_type", "document"), data.get("source_b_entity_id"), data.get("source_b_chunk_id"), user, db)):
            raise HTTPException(status_code=403, detail="Kein Zugriff auf eine der verknüpften Quellen")

        link = KnowledgeLink(
            source_a_type=data.get("source_a_type", "document"),
            source_a_entity_id=data.get("source_a_entity_id"),
            source_a_chunk_id=data.get("source_a_chunk_id"),
            source_a_title=data.get("source_a_title"),
            source_a_url=data.get("source_a_url"),
            source_a_source_type=data.get("source_a_source_type"),
            
            source_b_type=data.get("source_b_type", "document"),
            source_b_entity_id=data.get("source_b_entity_id"),
            source_b_chunk_id=data.get("source_b_chunk_id"),
            source_b_title=data.get("source_b_title"),
            source_b_url=data.get("source_b_url"),
            source_b_source_type=data.get("source_b_source_type"),
            
            score=data.get("score"),
            status="approved",
            created_by="chat",
            chat_session_id=session_id,
            context=data.get("context", "Manuell über geführten Chat bestätigt.")
        )
        db.add(link)
        created_links.append(link)
    
    db.commit()
    return [serialize_knowledge_link(l) for l in created_links]
