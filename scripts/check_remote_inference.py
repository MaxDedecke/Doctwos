#!/usr/bin/env python3
"""Exercise independent on-prem chat and embeddings from the application container."""
import argparse
import os
import sys
import httpx


def check(client, *, chat_url, chat_model, chat_provider, embedding_url, embedding_model, embedding_provider):
    chat_key = os.getenv('LLM_API_KEY') or os.getenv('OLLAMA_API_KEY', '')
    embed_key = os.getenv('EMBEDDING_API_KEY') or os.getenv('OLLAMA_API_KEY', '')
    chat_headers = {"Authorization": f"Bearer {chat_key}"} if chat_key else {}
    embed_headers = {"Authorization": f"Bearer {embed_key}"} if embed_key else {}
    native = chat_provider == "ollama"
    response = client.post(chat_url.rstrip("/") + ("/api/chat" if native else "/chat/completions"),
        headers=chat_headers, json={"model": chat_model, "messages": [{"role": "user", "content": "Reply with OK"}], "stream": False})
    response.raise_for_status()
    data = response.json()
    if not ((data.get("message") or {}).get("content") if native else data.get("choices")):
        raise ValueError("Chat returned no answer")
    native = embedding_provider == "ollama"
    response = client.post(embedding_url.rstrip("/") + ("/api/embed" if native else "/embeddings"),
        headers=embed_headers, json={"model": embedding_model, "input": "Doctus connectivity test"})
    response.raise_for_status()
    data = response.json()
    vectors = data.get("embeddings") if native else [row["embedding"] for row in data.get("data", [])]
    if not vectors or len(vectors) != 1 or len(vectors[0]) != 1024:
        raise ValueError("Embedding must contain exactly one 1024-dimensional vector")
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--chat-url', default=os.getenv('LLM_BASE_URL') or os.getenv('OLLAMA_BASE_URL'))
    p.add_argument('--chat-model', default=os.getenv('LLM_MODEL'))
    p.add_argument('--chat-provider', default=os.getenv('LLM_PROVIDER', 'ollama'))
    p.add_argument('--embedding-url', default=os.getenv('EMBEDDING_BASE_URL') or os.getenv('OLLAMA_BASE_URL'))
    p.add_argument('--embedding-model', default=os.getenv('OLLAMA_EMBED_MODEL', 'bge-m3'))
    p.add_argument('--embedding-provider', default=os.getenv('EMBEDDING_PROVIDER', 'ollama'))
    p.add_argument('--ca')
    args = p.parse_args(argv)
    if not all([args.chat_url, args.chat_model, args.embedding_url, args.embedding_model]):
        p.error('Configure separate chat and embedding URLs/models')
    values = vars(args); ca = values.pop('ca')
    try:
        with httpx.Client(timeout=120, verify=ca or True) as client:
            check(client, **values)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        print(f'FAILED: {type(exc).__name__}', file=sys.stderr)
        return 1
    print('OK: chat answer and 1024-dimensional embedding received')
    return 0


if __name__ == '__main__':
    sys.exit(main())
