"""
O-159 — Deployment-Doku und OIDC-Code auseinandergelaufen.

Die Doku beschrieb einen Login, den es so nie gab: `OIDC_ISSUER_URL` statt
`OIDC_ISSUER`, eine frei konfigurierbare `OIDC_REDIRECT_URI` (die es nicht
gibt, der Wert wird aus `API_URL` abgeleitet), den Callback-Pfad
`/auth/callback` statt `/auth/oidc/callback` und ein `ADMIN_EMAILS`, das im
Backend nirgends vorkommt. Wer sich daran hielt, bekam vom IdP „Invalid
parameter: redirect_uri" und von Doctus gar keine Fehlermeldung.

Solche Abweichungen fallen niemandem auf, solange niemand eine echte
Installation gegen die Doku fährt. Deshalb hier festgenagelt: jeder in der
Doku genannte OIDC-Konfigurationsname muss einer sein, den der Code auch
liest, und der dokumentierte Callback-Pfad muss der echte sein.
"""

import os
import re

import core.config as cfg
from core.oidc import redirect_uri

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC_PATHS = [
    os.path.join(REPO_ROOT, "docs", "DEPLOYMENT.md"),
    os.path.join(REPO_ROOT, "docs", "deployment-customer.md"),
    os.path.join(REPO_ROOT, ".env.example"),
]
REALM_PATH = os.path.join(REPO_ROOT, ".github", "keycloak", "doctus-realm.json")

# Die Namen, die core/config.py tatsaechlich aus der Umgebung liest.
SUPPORTED_OIDC_VARS = {"OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"}


def _documents() -> list[tuple[str, str]]:
    return [(p, open(p, encoding="utf-8").read()) for p in DOC_PATHS if os.path.exists(p)]


def test_config_reads_exactly_the_documented_variables():
    """Schutz gegen die andere Richtung: eine umbenannte Variable im Code."""
    assert {"OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"} <= set(dir(cfg))
    assert SUPPORTED_OIDC_VARS == {name for name in dir(cfg) if name.startswith("OIDC_")}


def test_docs_only_name_oidc_variables_that_exist():
    unknown: dict[str, set[str]] = {}
    for path, text in _documents():
        # Der Hinweis "OIDC_ISSUER, nicht OIDC_ISSUER_URL" nennt den falschen
        # Namen absichtlich -- solche Zeilen sind als Warnung markiert.
        names = {
            m.group(0)
            for line in text.splitlines()
            if "nicht `OIDC_ISSUER_URL`" not in line and "not `OIDC_ISSUER_URL`" not in line
            for m in re.finditer(r"OIDC_[A-Z_]+", line)
        }
        extra = names - SUPPORTED_OIDC_VARS
        if extra:
            unknown[os.path.relpath(path, REPO_ROOT)] = extra
    assert unknown == {}, f"Doku nennt OIDC-Variablen, die der Code nicht liest: {unknown}"


def test_docs_use_the_real_callback_path():
    expected_path = redirect_uri().split("://", 1)[1].split("/", 1)[1]
    assert expected_path == "auth/oidc/callback", expected_path

    wrong: list[str] = []
    for path, text in _documents():
        for match in re.finditer(r"/auth/[a-z/]*callback", text):
            if match.group(0) != "/auth/oidc/callback":
                wrong.append(f"{os.path.relpath(path, REPO_ROOT)}: {match.group(0)}")
    assert wrong == [], f"Doku nennt einen anderen Callback-Pfad als der Code: {wrong}"


def test_docs_do_not_promise_an_admin_email_variable():
    """`ADMIN_EMAILS` gab es nie -- Adminrechte haengen an User.role."""
    offenders = [
        os.path.relpath(path, REPO_ROOT) for path, text in _documents() if "ADMIN_EMAILS" in text
    ]
    assert offenders == [], f"ADMIN_EMAILS existiert im Backend nicht, steht aber in: {offenders}"


def test_test_realm_matches_the_derived_redirect_uri():
    """Der mitgelieferte Wegwerf-Keycloak muss zum Code passen, sonst
    scheitert die dokumentierte Demo am IdP statt an Doctus."""
    import json

    assert os.path.exists(REALM_PATH), "Die Doku verweist auf eine Realm-Datei, die es nicht gibt."
    realm = json.load(open(REALM_PATH, encoding="utf-8"))
    client = next(c for c in realm["clients"] if c["clientId"] == "doctus-backend")

    assert client["redirectUris"], "Client ohne Redirect-URI kann keinen Login abschliessen."
    for uri in client["redirectUris"]:
        assert uri.endswith("/auth/oidc/callback"), uri
    # Keycloak schneidet CLIENT.DESCRIPTION bei 255 Zeichen ab und bricht den
    # Import mit einem SQL-Fehler ab, statt zu kuerzen.
    assert len(client.get("description", "")) <= 255
