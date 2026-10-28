"""
backend/services/chat_start.py
==============================
Inhalte der leeren Chat-Startansicht: eine Beispielfrage und ein „Projektpuls"
aus echten Objektnamen, aus dem das Frontend passende Beispielfragen baut.
"""

import logging
import random

import httpx
from sqlalchemy.orm import Session

import core.config as cfg
from core.inference_admission import admitted_post
from doctus_models.database import CodeEntity

logger = logging.getLogger(__name__)

_FALLBACK_STATEMENTS = [
    "Was macht dieses COBOL-Programm?",
    "Welche Programme ruft dieser Batch-Job auf?",
    "Wo wird dieses Feld im Copybook verwendet?",
    "Welche JCL-Steps laufen in dieser Kette?",
    "Was passiert in dieser CICS-Transaktion?",
    "Wo wird auf diese DB2-Tabelle zugegriffen?",
    "Welche Programme sind noch nicht dokumentiert?",
    "Wie hängen diese beiden Module zusammen?",
]


async def generate_typing_statement() -> str:
    """Kurze Beispielfrage für den leeren Chat; ohne LLM oder bei Fehlern eine feste."""
    # Embedding-only pilot: do not turn a decorative start-screen prompt into
    # an LLM request. This endpoint is polled by the frontend even if nobody is
    # chatting, so attempting the disabled model would create log noise forever.
    if not cfg.OLLAMA_LLM_MODEL or cfg.OLLAMA_LLM_MODEL == "disabled":
        return random.choice(_FALLBACK_STATEMENTS)

    try:
        url = f"{cfg.OLLAMA_BASE_URL}/v1/chat/completions"
        model_to_use = cfg.resolve_ollama_model(None)
        payload = {
            "model": model_to_use,
            "messages": [
                {
                    "role": "system",
                    "content": "Du bist ein Assistent, der kurze Fragen generiert. Antworte in der Sprache des Nutzers (Deutsch oder Englisch).",
                },
                {
                    "role": "user",
                    "content": "Generiere eine berechtigte, relevante Frage mit bis zu 8 Wörtern zum Thema COBOL, Mainframe-Programme oder Softwarearchäologie für den Chat-Startbildschirm. Antworte NUR mit der Frage, kein Begleittext, keine Anführungszeichen.",
                },
            ],
            "temperature": 0.8,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if cfg.OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {cfg.OLLAMA_API_KEY}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await admitted_post(
                client,
                url,
                kind="batch",
                wait_timeout_seconds=1.0,
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                # Clean up any quotes
                text = text.strip("\"'")
                # Check if it has up to 10 words
                words = text.split()
                if 2 <= len(words) <= 10:
                    return text
    except Exception as e:
        logger.warning("Startfrage konnte nicht erzeugt werden: %s", e)

    # Fallback if Ollama fails or returns invalid count
    return random.choice(_FALLBACK_STATEMENTS)


# COBOL- und Java-Typen; die Startansicht leitet daraus ab, zu welchem
# Technologie-Stack des Projekts sie Karten und Beispielfragen zeigt.
PULSE_ENTITY_TYPES = (
    "program",
    "copybook",
    "sql_table",
    "jcl_job",
    "class",
    "interface",
    "method",
    "maven_module",
)
# Für diese Typen gibt es Namensstichproben; Methoden (Getter, Setter, ...)
# und Maven-Module taugen nicht als Beispielfrage und werden nur gezählt.
PULSE_SAMPLED_TYPES = frozenset(
    {"program", "copybook", "sql_table", "jcl_job", "class", "interface"}
)
PULSE_SAMPLES_PER_TYPE = 3


def project_pulse(db: Session, project_id: int) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Zähler je Typ und Zufallsstichprobe echter Objektnamen.

    Kein LLM-Aufruf; Offset statt ORDER BY random(), damit der Aufruf auch bei
    sehr großen Beständen billig bleibt.
    """
    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    for entity_type in PULSE_ENTITY_TYPES:
        base = db.query(CodeEntity).filter(
            CodeEntity.project_id == project_id,
            CodeEntity.type == entity_type,
            CodeEntity.name.isnot(None),
        )
        total = base.count()
        counts[entity_type] = total
        picked: list[str] = []
        sample_count = (
            min(PULSE_SAMPLES_PER_TYPE, total) if entity_type in PULSE_SAMPLED_TYPES else 0
        )
        for _ in range(sample_count):
            row = (
                base.with_entities(CodeEntity.name)
                .order_by(CodeEntity.id)
                .offset(random.randrange(total))
                .limit(1)
                .first()
            )
            if row and row[0] not in picked:
                picked.append(row[0])
        samples[entity_type] = picked
    return counts, samples
