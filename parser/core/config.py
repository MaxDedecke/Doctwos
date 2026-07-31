"""
parser/core/config.py
=====================
Zentrale Konfiguration für den Doctus-Parser-Worker.

Alle Konstanten, die in mehreren Modulen gebraucht werden, sind hier definiert.
Neue Module importieren von hier statt Werte zu duplizieren — so reicht eine
Änderung an einer Stelle, um z. B. das Embedding-Modell zu wechseln.

Umgebungsvariablen überschreiben die Defaults (Docker-Compose-kompatibel).
"""

import os

# ── Ollama (lokales LLM + Embedding) ─────────────────────────────────────────

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# Modell für Vektor-Embeddings. Alle Connectoren, Tasks und der Link Builder
# referenzieren diesen Namen — Modell-Wechsel hier, nirgendwo sonst.
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "bge-m3")

# Lokales Chat-/Compliance-LLM. Bis zur ersten Auslieferung auf CPU-only-Piloten
# bewusst deaktiviert; bge-m3-Embeddings bleiben davon unabhängig aktiv.
LLM_MODEL: str = os.getenv("LLM_MODEL", "disabled")

# Timeout (Sekunden) pro LLM-Aufruf im Compliance-Checker. Höher als der
# get_chat_json-Default von 60s, weil ein 12B-Modell auf CPU-only Hosts (kein
# GPU) pro Bauteil-Urteil deutlich länger braucht — bei 60s liefen reale Läufe
# in Timeouts, die still als llm_error gezählt wurden (kein Verdikt für das
# Bauteil). Auf GPU-Hosts kostet der höhere Wert nichts, da die Antwort lange
# vorher da ist. Auf sehr kleinen CPU-Hosts ggf. weiter erhöhen.
COMPLIANCE_LLM_TIMEOUT: float = float(os.getenv("COMPLIANCE_LLM_TIMEOUT", "180"))

# ── Datenbank & Queue ─────────────────────────────────────────────────────────

DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://admin:password@db:5432/doctus")
REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Pfad innerhalb des Containers, in den Repositories geklont werden
REPOS_ROOT: str = "/repos"

# ── Chunking ──────────────────────────────────────────────────────────────────

# Maximale Zeichenanzahl pro Dokument-Chunk vor dem Einbetten.
# Größere Chunks = mehr Kontext pro Suchtreffer, aber langsameres Embedding.
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))

# Anzahl paralleler Chunk+Embed-Tasks im Git-Konnektor (Producer/Consumer-Loop,
# Plan §7.3/NF-004). Env-steuerbar, damit eine schwächere Ollama-Instanz
# gedrosselt werden kann, ohne Code zu ändern.
EMBED_CONCURRENCY: int = int(os.getenv("EMBED_CONCURRENCY", "20"))
