# Open Source License Clearing Report — Doctus

This document provides a license audit and compliance assessment for all third-party open-source components used by **Doctus**. 

While the Doctus core codebase is proprietary and closed-source (all rights reserved), it integrates several open-source libraries. This report verifies that all dependencies conform to the project's license policy and do not compromise Doctus's proprietary status.

---

## 🛡️ License Compliance Overview

The dependencies are classified into three licensing categories:
1. **Permissive Licenses (MIT, BSD, Apache 2.0, PostgreSQL, ISC):** 100% compliant. Allowed without restrictions.
2. **Weak Copyleft (LGPL-3.0):** Compliant under dynamic linking/subprocess conditions. Used by BIM parsing.
3. **Strong Copyleft (GPL-3.0):** Compliant **only** due to process-level isolation (subprocess CLI execution). Used by OCR parsing.

---

## 📦 Dependency Registry & Audit

### 1. Backend & Parser Dependencies (Python)

| Library | Version / Range | License | Compliance Assessment |
| :--- | :--- | :--- | :--- |
| **FastAPI** | Latest | MIT | Permissive. No restrictions. |
| **Uvicorn** | Latest | BSD-3-Clause | Permissive. No restrictions. |
| **SQLAlchemy** | Latest | MIT | Permissive. No restrictions. |
| **Psycopg2-binary** | Latest | LGPL-3.0 / BSD | **Cleared.** Pre-compiled binary distributed under the PostgreSQL/BSD-like license exception. |
| **Celery** | Latest | BSD-3-Clause | Permissive. No restrictions. |
| **Redis** | Latest | BSD-3-Clause | Permissive. No restrictions. |
| **Httpx** | Latest | BSD-3-Clause | Permissive. No restrictions. |
| **Pydantic** | Latest | MIT | Permissive. No restrictions. |
| **pgvector** | Latest | PostgreSQL License | Permissive. Compatible with proprietary software. |
| **pypdf** | Latest | BSD-3-Clause | Permissive. No restrictions. |
| **python-docx** | Latest | MIT | Permissive. No restrictions. |
| **Mammoth** | Latest | BSD-2-Clause | Permissive. No restrictions. |
| **Cryptography** | Latest | Apache-2.0 / BSD-3 | Dual permissive. No restrictions. |
| **Alembic** | Latest | MIT | Permissive. No restrictions. |
| **Authlib** | Latest | BSD-3-Clause | Permissive. *Note: Check for commercial subscription requirements if updated to newer versions.* |
| **ezdxf** | Latest | MIT | Permissive. No restrictions. |
| **Pillow** | Latest | HPND (MIT-like) | Permissive. No restrictions. |
| **Markdown** | Latest | BSD-3-Clause | Permissive. No restrictions. |
| **mcp-atlassian** | Latest | MIT | Permissive. No restrictions. |
| **gitpython** | Latest | BSD-3-Clause | Permissive. No restrictions. |
| **psutil** | Latest | BSD-3-Clause | Permissive. No restrictions. |
| **pdf2image** | Latest | MIT | Permissive. No restrictions. |
| **ifcopenshell** | Latest | **LGPL-3.0** | **Cleared (Weak Copyleft).** See detailed assessment below. |
| **pytesseract** | Latest | **GPL-3.0** | **Cleared (Strong Copyleft).** See detailed assessment below. |
| **itsdangerous** | Latest | BSD-3-Clause | Permissive. No restrictions. Used for session-cookie signing (see `docs/AVV_VORLAGE.md`, `docs/FEATURES.md`). |

### 2. Frontend Dependencies (Javascript/TypeScript)

All frontend dependencies are under permissive licenses and are fully cleared for use in a proprietary project:

| Library | Version / Range | License | Compliance Assessment |
| :--- | :--- | :--- | :--- |
| **Next.js** | `14.2.3` | MIT | Permissive. No restrictions. |
| **React / React DOM** | `^18` | MIT | Permissive. No restrictions. |
| **Tailwind CSS** | `^3.4.1` | MIT | Permissive. No restrictions. |
| **Monaco Editor** | `^4.6.0` | MIT | Permissive. No restrictions. |
| **Framer Motion** | `^12.40.0` | MIT | Permissive. No restrictions. |
| **Three.js** | `^0.185.0` | MIT | Permissive. No restrictions. |
| **Mermaid.js** | `^11.15.0` | MIT | Permissive. No restrictions. |
| **Lucide React** | `^0.378.0` | ISC / MIT | Permissive. No restrictions. |
| **Axios** | `^1.6.8` | MIT | Permissive. No restrictions. |
| **Radix UI** | `^1.x` | MIT | Permissive. No restrictions. |
| **react-force-graph-2d** | `^1.29.1` | MIT | Permissive. No restrictions. Used by `KnowledgeGraphView.tsx`. |
| **class-variance-authority** | `^0.7.1` | Apache-2.0 | Permissive. No restrictions. |
| **clsx** | `^2.1.1` | MIT | Permissive. No restrictions. |
| **tailwind-merge** | `^2.6.1` | MIT | Permissive. No restrictions. |
| **tailwindcss-animate** | `^1.0.7` | MIT | Permissive. No restrictions. |
| **@tailwindcss/container-queries** | `^0.1.1` | MIT | Permissive. No restrictions. |

---

## ⚖️ Detailed Copyleft Clearing Assessment

### 1. `ifcopenshell` (LGPL-3.0 — Weak Copyleft)
* **Usage:** Used in `parser-worker` and `backend-api` to parse `.ifc` models and extract metadata and 3D shapes.
* **Risk Analysis:** LGPL-3.0 is a weak copyleft license. If a proprietary application links to or imports an LGPL library, it does *not* force the proprietary application to become open source, provided that:
  1. The library is dynamically loaded (standard Python module import behaves as dynamic loading).
  2. Users can replace or modify the LGPL library version.
* **Compliance Resolution:** Cleared. Python imports resolve dynamically at runtime. The library is installed via `pip` inside the containerized environment. Doctus does not modify the source code of `ifcopenshell` itself.

### 2. `pytesseract` (GPL-3.0 — Strong Copyleft)
* **Usage:** Used in the `parser-worker` container to extract text from scanned images/PDFs.
* **Risk Analysis:** GPL-3.0 is a strong copyleft license. If a proprietary application statically or dynamically links to a GPL library, the proprietary application must also be licensed under the GPL ("license infection").
* **Compliance Resolution:** Cleared. `pytesseract` is a Python wrapper that communicates with the `tesseract` OCR binary via **subprocess CLI calls** (executing it as a separate operating system process, e.g. `tesseract image.png output.txt`). Under Free Software Foundation (FSF) guidelines, running a GPL tool in a separate process via standard command-line interfaces does *not* constitute a "derivative work" and does *not* trigger the copyleft copy-over requirements. Doctus does not link or bind directly to the Tesseract C++ library.

---

## 🤖 AI Model Licenses

Doctus runs 100% locally using Ollama. The default weights/models used are:
1. **Mistral NeMo (12B):** Licensed under **Apache-2.0** (jointly released by Mistral AI and NVIDIA, July 2024). Permissive and commercial use is fully cleared — no separate research/non-commercial restriction, unlike the larger Qwen tiers below. Sole default LLM since the 2026-07-11 model switch (`backend/core/config.py`, `parser/core/config.py`; see `docs/COMPLIANCE_EVAL.md` for the accuracy comparison that motivated moving off Qwen).
   - **Quantization provenance:** the shipped tag (`hf.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF:Q4_K_M`, or `:Q8_0` on the Premium tier) is a **third-party GGUF requantization by [bartowski](https://huggingface.co/bartowski)**, not an artifact published by Mistral AI/NVIDIA themselves. bartowski is a well-known, widely-used public requantizer (llama.cpp-based conversion of the upstream safetensors release); the Apache-2.0 license carries over unchanged since quantization is not a derivative-licensing event. This does not change the license conclusion above, but a customer with strict supply-chain requirements should be told the weights passed through an unaffiliated third party before reaching Ollama's registry. Every offline bundle records the actual pulled tag + digest in `MODEL_MANIFEST.txt` (generated by `scripts/build-offline-bundle.sh`) so the specific artifact shipped to that customer is independently verifiable against the bartowski HF repo, rather than only checksummed against itself.
2. **BGE-M3 (Embeddings):** Licensed under **MIT**. Permissive and commercial use is fully cleared. Sole default since the 2026-07-06 embedding migration (`backend/core/config.py`, `parser/core/config.py`).
3. **Nomic Embed Text (Embeddings):** Licensed under **Apache-2.0**. Permissive and commercial use is fully cleared. No longer the shipped default — legacy/optional, still supported if an operator explicitly sets `OLLAMA_EMBED_MODEL=nomic-embed-text`.
4. **Qwen 2.5 (1.5B):** Licensed under **Apache-2.0**. Permissive and commercial use was fully cleared while it was the default. **No longer used — superseded as the default LLM by Mistral NeMo above (2026-07-11) and must not be reintroduced as a default in production.** *(Note: Larger Qwen tiers like 3B and 72B use the proprietary Qwen Research License for non-commercial research, which is restricted — never applicable here regardless.)*
