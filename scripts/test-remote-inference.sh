#!/bin/sh
# scripts/test-remote-inference.sh
# =================================
# Pre-flight check for remote Ollama / GPU host connectivity and model readiness.
# Verifies that:
#   1. Remote Ollama host:port is reachable
#   2. Ollama responds with HTTP 200 on /api/tags
#   3. Required embedding model (bge-m3) is present
#   4. Live test embedding returns exactly 1024 dimensions (matching pgvector schema)
#
# Usage:
#   ./scripts/test-remote-inference.sh [URL]
# Example:
#   ./scripts/test-remote-inference.sh http://192.168.1.50:11434

set -e

target_url="$1"

if [ -z "$target_url" ]; then
    if [ -f .env ]; then
        target_url=$(grep -E "^EMBEDDING_BASE_URL=" .env | cut -d= -f2- | tr -d '"' | tr -d "'")
        [ -z "$target_url" ] && target_url=$(grep -E "^OLLAMA_BASE_URL=" .env | cut -d= -f2- | tr -d '"' | tr -d "'")
    fi
fi

target_url="${target_url:-http://localhost:11434}"
target_url=$(echo "$target_url" | sed 's:/*$::')

echo "================================================================="
echo " Doctus AI — Remote Inference Pre-Flight Check"
echo " Target Endpoint: $target_url"
echo "================================================================="

# 1. Connectivity check
echo "[1/4] Checking HTTP connection to ${target_url}/api/tags..."
tags_response=$(python3 -c "
import urllib.request, json, sys
url = '${target_url}/api/tags'
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Doctus-Healthcheck'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        if resp.status != 200:
            sys.exit(2)
        print(resp.read().decode('utf-8'))
except Exception as err:
    print(f'CONNECTION_ERROR: {err}', file=sys.stderr)
    sys.exit(1)
" 2>&1) || exit_code=$?

if [ "${exit_code:-0}" -ne 0 ]; then
    echo "  FAILED: Could not reach Ollama at ${target_url}."
    echo "  Details: $tags_response"
    echo
    echo "  Troubleshooting:"
    echo "    1. On the remote machine, ensure Ollama binds to 0.0.0.0 (OLLAMA_HOST=0.0.0.0)."
    echo "    2. On the remote machine, verify the firewall allows incoming traffic on port 11434:"
    echo "       ufw allow from <this-host-ip> to any port 11434 proto tcp"
    echo "    3. Verify routing and ping: ping $(echo "$target_url" | sed -E 's|https?://([^:/]+).*|\1|')"
    exit 1
fi
echo "  OK: Remote endpoint answered successfully."

# 2. Check for bge-m3 embedding model
echo "[2/4] Verifying presence of 'bge-m3' model on remote server..."
has_bge_m3=$(echo "$tags_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = [m.get('name', '') for m in data.get('models', [])]
    found = any('bge-m3' in m for m in models)
    sys.stdout.write('1' if found else '0')
except Exception:
    sys.stdout.write('0')
")

if [ "$has_bge_m3" != "1" ]; then
    echo "  WARNING: 'bge-m3' not found in models list on remote server."
    echo "  Available models on remote host:"
    echo "$tags_response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    print('    - ' + m.get('name', 'unknown'))
"
    echo "  To pull bge-m3 on the remote host, run:"
    echo "    ollama pull bge-m3"
    exit 1
fi
echo "  OK: 'bge-m3' is available."

# 3. Test live embedding generation
echo "[3/4] Generating test embedding using ${target_url}/api/embed..."
embed_result=$(python3 -c "
import urllib.request, json, sys
url = '${target_url}/api/embed'
payload = json.dumps({'model': 'bge-m3', 'input': 'Doctus AI connectivity test'}).encode('utf-8')
try:
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Doctus-Preflight'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status != 200:
            sys.exit(2)
        data = json.loads(resp.read().decode('utf-8'))
        embeddings = data.get('embeddings', [])
        if not embeddings or not embeddings[0]:
            print('EMPTY_EMBEDDING', file=sys.stderr)
            sys.exit(3)
        dim = len(embeddings[0])
        print(f'DIM:{dim}')
except Exception as err:
    print(f'EMBED_ERROR: {err}', file=sys.stderr)
    sys.exit(1)
" 2>&1) || embed_exit=$?

if [ "${embed_exit:-0}" -ne 0 ]; then
    echo "  FAILED: Embedding generation request failed."
    echo "  Details: $embed_result"
    exit 1
fi

dim=$(echo "$embed_result" | grep "DIM:" | cut -d: -f2)
echo "  OK: Successfully received embedding with ${dim} dimensions."

# 4. Verify dimensions match pgvector schema (1024)
echo "[4/4] Verifying vector dimension matches Doctus pgvector schema (1024)..."
if [ "$dim" -ne 1024 ]; then
    echo "  FATAL: Dimension mismatch! Received ${dim} dimensions, but Doctus requires exactly 1024."
    echo "  Ensure you are using 'bge-m3' and not a 768-dim model (e.g. nomic-embed-text) or 1536-dim model."
    exit 1
fi
echo "  OK: Dimensions match 1024."

echo
echo "================================================================="
echo " ALL CHECKS PASSED: Remote inference endpoint is ready for Doctus."
echo "================================================================="
exit 0
