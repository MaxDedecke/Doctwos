"""
O-073 — die Trace-ID muss beim Nutzer ankommen, nicht nur im Log stehen.

Zwei Bedingungen, die beide leicht unbemerkt kaputtgehen:

  1. Der `X-Request-ID`-Header steht auf JEDER Antwort — auch auf der eines
     Fehlers, denn genau dann liest ihn das Frontend aus.
  2. Er ist per CORS für JavaScript freigegeben. Frontend und Backend sind
     verschiedene Origins; ohne `Access-Control-Expose-Headers` gibt der
     Browser dem JS von einer Cross-Origin-Antwort nur die sechs
     CORS-safelisted Header heraus. Der Header wäre dann zwar gesetzt, für das
     Frontend aber unsichtbar — ohne Fehlermeldung, ohne Logzeile. Deshalb ist
     die Freigabe hier eigens festgenagelt.

Dazu der Rückweg: der Crash-Reporter darf die vom Nutzer gesehene ID
mitschicken (`trace_id`), damit der Support-Fall an derselben ID hängt.
"""

import logging

import core.config as cfg


def test_response_carries_the_trace_id_header(unauthenticated_client):
    response = unauthenticated_client.get("/health")

    assert response.headers.get("X-Request-ID")


def test_an_error_response_carries_the_trace_id_header_too(unauthenticated_client):
    """Der Fehlerfall ist der einzige, in dem der Nutzer die ID je zu sehen bekommt."""
    response = unauthenticated_client.get("/projects")

    assert response.status_code == 401
    assert response.headers.get("X-Request-ID")


def test_an_incoming_trace_id_is_kept_instead_of_replaced(unauthenticated_client):
    response = unauthenticated_client.get("/health", headers={"X-Request-ID": "abc123"})

    assert response.headers.get("X-Request-ID") == "abc123"


def test_the_trace_id_header_is_exposed_to_cross_origin_javascript(unauthenticated_client):
    """Ohne diese Freigabe sieht das Frontend den Header nicht (siehe Modul-Docstring)."""
    response = unauthenticated_client.get("/health", headers={"Origin": cfg.FRONTEND_URL})

    exposed = response.headers.get("access-control-expose-headers", "")
    assert "x-request-id" in exposed.lower()


def test_client_error_report_logs_the_trace_id_the_user_saw(unauthenticated_client, caplog):
    with caplog.at_level(logging.ERROR):
        response = unauthenticated_client.post(
            "/diagnostics/client-error",
            json={"message": "Boom", "trace_id": "deadbeef", "url": "http://localhost:3000/"},
        )

    assert response.status_code == 200
    assert "client_trace=deadbeef" in caplog.text


def test_client_error_report_stays_valid_without_a_trace_id(unauthenticated_client):
    """Ein Absturz vor dem ersten API-Aufruf hat keine ID — das darf nicht 422 werden."""
    response = unauthenticated_client.post("/diagnostics/client-error", json={"message": "Boom"})

    assert response.status_code == 200
