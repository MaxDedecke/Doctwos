#!/usr/bin/env python3
"""Exercise independent on-prem chat and embeddings from the application container."""
import argparse
import json
import os
import sys
import httpx


PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "codena_profile_probe",
        "description": "Connection test. Do not perform external actions.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def check_tool_call(client, chat_url, chat_model, headers):
    """Send the chat agent's request shape: streamed, with usage and a forced tool call.

    A bridge that answers plain requests but drops streaming, ``stream_options`` or
    ``tools`` would otherwise pass this probe and fail in the first chat.
    """
    payload = {"model": chat_model, "messages": [{"role": "user", "content": "Call the probe tool now."}],
               "tools": [PROBE_TOOL], "tool_choice": "required", "stream": True,
               "stream_options": {"include_usage": True}, "max_tokens": 512}
    names = set()
    with client.stream("POST", chat_url.rstrip("/") + "/chat/completions", headers=headers, json=payload) as response:
        if response.status_code >= 400:
            raise ValueError(f"Streamed tool-call request rejected (HTTP {response.status_code}); the server or "
                             "bridge must accept stream, stream_options, tools and tool_choice")
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise ValueError("Streamed request was not answered as server-sent events; the chat needs streaming")
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            for choice in chunk.get("choices") or []:
                for part in (choice.get("delta") or {}).get("tool_calls") or []:
                    names.add((part.get("function") or {}).get("name"))
    if "codena_profile_probe" not in names:
        raise ValueError("Chat answered without a tool call. Enable tool calling on the model server "
                         "(vLLM: --enable-auto-tool-choice --tool-call-parser qwen3_coder for Qwen3-Coder; "
                         "llama.cpp: --jinja) and let a bridge pass tools and tool_calls through")


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
    if not native:
        check_tool_call(client, chat_url, chat_model, chat_headers)
    native = embedding_provider == "ollama"
    response = client.post(embedding_url.rstrip("/") + ("/api/embed" if native else "/embeddings"),
        headers=embed_headers, json={"model": embedding_model, "input": "Codena connectivity test"})
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
        detail = f'HTTP {exc.response.status_code}' if isinstance(exc, httpx.HTTPStatusError) else str(exc)
        print(f'FAILED: {type(exc).__name__}: {detail}', file=sys.stderr)
        if isinstance(exc, httpx.ConnectError) and 'localhost' in f'{args.chat_url}{args.embedding_url}':
            print('Hint: localhost is the container itself; use host.docker.internal (docs/PILOT_DEPLOYMENT.md).',
                  file=sys.stderr)
        return 1
    print('OK: chat answer, streamed tool call (OpenAI-compatible) and 1024-dimensional embedding received')
    return 0


if __name__ == '__main__':
    sys.exit(main())
