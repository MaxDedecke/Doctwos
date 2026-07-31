#!/bin/sh
# Shared by install.sh and install-offline.sh. Source it, then call bootstrap_env.
set -e

bootstrap_env() {
    repo_root="$1"

    if [ -f "$repo_root/.env" ]; then
        echo "Found existing .env — leaving it as is."
        return
    fi

    echo "No .env found, creating one from .env.example..."
    cp "$repo_root/.env.example" "$repo_root/.env"

    master_key=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null) \
        || master_key=$(docker run --rm python:3.11-slim sh -c "pip install -q cryptography >/dev/null 2>&1 && python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    session_key=$(openssl rand -base64 32)

    # Portable in-place edit (BSD/GNU sed differ on -i): write to a temp file, then replace.
    sed -e "s|^MASTER_ENCRYPTION_KEY=.*|MASTER_ENCRYPTION_KEY=${master_key}|" \
        -e "s|^SESSION_SECRET_KEY=.*|SESSION_SECRET_KEY=${session_key}|" \
        "$repo_root/.env" > "$repo_root/.env.tmp"
    mv "$repo_root/.env.tmp" "$repo_root/.env"

    echo "Generated MASTER_ENCRYPTION_KEY and SESSION_SECRET_KEY in .env."
    echo "Review .env now and set API_URL/FRONTEND_URL before continuing."
}

# Called after bootstrap_env, right before/after bringing the stack up. Prints
# a loud, hard-to-miss warning for the way login silently ends up unreachable:
# URLs left on localhost when the browser isn't on this same machine. Das
# erreicht "Done, open the URL" ohne eigene Fehlermeldung — das Einzige zwischen
# erreichbarer und unerreichbarer Oberfläche ist, ob jemand das hier liest.
# Siehe docs/DEPLOYMENT.md#troubleshooting.
#
# Die frühere OIDC-Prüfung ist mit AP-0 entfallen: Doctus meldet lokal an und
# legt den ersten Superuser beim Start selbst an (BOOTSTRAP_SUPERUSER*).
check_env_ready() {
    repo_root="$1"
    env_file="$repo_root/.env"
    [ -f "$env_file" ] || return 0

    frontend_url=$(grep -E "^FRONTEND_URL=" "$env_file" | cut -d= -f2-)
    api_url=$(grep -E "^API_URL=" "$env_file" | cut -d= -f2-)

    warned=0
    case "$frontend_url$api_url" in
        *localhost*|*127.0.0.1*)
            echo
            echo "!! FRONTEND_URL/API_URL still reference localhost/127.0.0.1."
            echo "!! That only works if the browser opening Doctus runs on THIS machine. If you're deploying"
            echo "!! to a server you'll reach from another machine, replace localhost in both with this"
            echo "!! host's actual reachable address (e.g. its IP or hostname), then: docker compose up -d"
            warned=1
            ;;
    esac
    [ "$warned" = 1 ] && echo
    return 0
}
