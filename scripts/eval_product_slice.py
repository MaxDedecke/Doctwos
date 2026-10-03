#!/usr/bin/env python3
"""Misst den Produktschnitt (O-304) gegen eine laufende Doctus-Instanz.

    DOCTUS_USER=admin DOCTUS_PASSWORD=... python3 scripts/eval_product_slice.py [--url http://localhost:8000]

Jedes Szenario aus `backend/tests/fixtures/eval_product_scenarios.json` ruft den REST-Endpunkt der jeweiligen
Arbeitsansicht auf und vergleicht mit der Ground Truth. Exit-Code 1 bei Abweichung oder Überschreitung der
Latenzgrenze. Szenarien eines nicht sichtbaren Projekts werden übersprungen.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

SCENARIOS = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures" / "eval_product_scenarios.json"


class Client:
    def __init__(self, base: str, user: str, password: str):
        self.base = base.rstrip("/")
        self.http = requests.Session()
        response = self.http.post(f"{self.base}/auth/login", json={"username": user, "password": password}, timeout=30)
        response.raise_for_status()

    def get(self, path, **params):
        started = time.monotonic()
        response = self.http.get(f"{self.base}{path}", params=params, timeout=120)
        return response, int((time.monotonic() - started) * 1000)

    def resolve(self, project_id, entity):
        """Entity-ID über die Kopfzeilen-Suche; der Treffer muss den erwarteten Qualified Name tragen."""
        response, _ = self.get("/search", q=entity["query"], project_id=project_id, types="entity", limit=10)
        response.raise_for_status()
        for hit in response.json().get("results", []):
            detail, _ = self.get(f"/entities/{hit['node_id']}", project_id=project_id)
            if detail.ok and detail.json().get("entity", detail.json()).get("qualified_name") == entity["qualified_name"]:
                return hit["node_id"]
        return None


def check_structure(client, project_id, entity_id, scenario):
    response, ms = client.get(f"/entities/{entity_id}/neighbors", project_id=project_id)
    if not response.ok:
        return False, ms, f"HTTP {response.status_code}"
    group = response.json().get("groups", {}).get(scenario["expect"]["group"], [])
    names = {(item.get("dst_name"), item.get("resolution")) for item in group}
    missing = [t for t in scenario["expect"]["targets"] if (t["name"], t["resolution"]) not in names]
    return not missing, ms, f"fehlt: {missing}" if missing else f"{len(group)} Kanten in {scenario['expect']['group']}"


def check_process(client, project_id, entity_id, scenario):
    response, ms = client.get("/process/focus", entity_id=entity_id, project_id=project_id, hops=scenario.get("hops", 2))
    if not response.ok:
        return False, ms, f"HTTP {response.status_code}"
    body, expect = response.json(), scenario["expect"]
    labels = {node["label"] for node in body["nodes"]}
    root = next((node["label"] for node in body["nodes"] if node["id"] == body["root_node_id"]), None)
    problems = []
    if root != expect["root_label"]:
        problems.append(f"Wurzel {root!r}")
    problems += [f"Schritt {label!r} fehlt" for label in expect["labels"] if label not in labels]
    if "truncated" in expect and body["truncation"]["truncated"] != expect["truncated"]:
        problems.append("Kürzung weicht ab")
    return not problems, ms, "; ".join(problems) or f"{len(body['nodes'])} Knoten, {len(body['transitions'])} Übergänge"


def check_impact(client, project_id, entity_id, scenario):
    response, ms = client.get(f"/projects/{project_id}/change-package", entity_id=entity_id, direction="incoming", hops=scenario.get("hops", 2))
    if not response.ok:
        return False, ms, f"HTTP {response.status_code}"
    body, expect = response.json(), scenario["expect"]
    names = {item["qualified_name"] for item in body["affected_code"]}
    problems = []
    if body["impact_status"] != expect["impact_status"]:
        problems.append(f"impact_status {body['impact_status']!r}")
    if len(body["affected_code"]) != expect["affected_count"]:
        problems.append(f"{len(body['affected_code'])} statt {expect['affected_count']} betroffene Objekte")
    problems += [f"{name} fehlt" for name in expect.get("affected_names", []) if name not in names]
    # Ehrlichkeit: nichts Belegtes darf als gesichert erscheinen, solange keine Evidenz existiert.
    for section in expect.get("honest_unknowns", []):
        if body[section]["status"] != "unknown" and not body[section]["items"]:
            problems.append(f"{section}: Status {body[section]['status']!r} ohne Belege")
    if not body["evidence_gaps"] or not body["limitations"]:
        problems.append("Belegslücken/Einschränkungen fehlen")
    return not problems, ms, "; ".join(problems) or f"{len(names)} betroffen, Lücken ausgewiesen"


def check_graph(client, project_id, entity_id, scenario):
    response, ms = client.get("/graph/neighborhood", node_id=f"entity:{entity_id}", project_id=project_id, relationships="code_dependency", limit=50)
    if not response.ok:
        return False, ms, f"HTTP {response.status_code}"
    labels = {node.get("label") for node in response.json()["nodes"]}
    missing = [label for label in scenario["expect"]["labels"] if label not in labels]
    return not missing, ms, f"fehlt: {missing}" if missing else f"{len(labels)} Knoten"


def check_negative(client, project_id, _entity_id, scenario):
    if scenario["request"] == "process":
        response, ms = client.get("/process/focus", entity_id=scenario["entity_id"], project_id=project_id)
    else:
        response, ms = client.get(f"/projects/{project_id}/change-package")
    return response.status_code == scenario["expect"]["status"], ms, f"HTTP {response.status_code}"


CHECKS = {"structure": check_structure, "process": check_process, "impact": check_impact, "graph": check_graph, "negative": check_negative}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("DOCTUS_URL", "http://localhost:8000"))
    args = parser.parse_args()
    user, password = os.environ.get("DOCTUS_USER"), os.environ.get("DOCTUS_PASSWORD")
    if not user or not password:
        sys.exit("DOCTUS_USER und DOCTUS_PASSWORD fehlen")
    catalogue = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    client = Client(args.url, user, password)
    projects = {item["name"]: item["id"] for item in client.get("/projects")[0].json()}
    failed, total, slow = 0, 0, 0
    for scenario in catalogue["scenarios"]:
        name = catalogue["projects"][scenario["project"]]["name"]
        if name not in projects:
            print(f"SKIP {scenario['id']}: Projekt {name!r} nicht sichtbar")
            continue
        project_id, entity_id = projects[name], None
        if "entity" in scenario:
            entity_id = client.resolve(project_id, scenario["entity"])
            if entity_id is None:
                print(f"FAIL {scenario['id']} [{scenario['view']}]: Entity {scenario['entity']['qualified_name']!r} nicht auflösbar")
                failed, total = failed + 1, total + 1
                continue
        ok, ms, detail = CHECKS[scenario["view"]](client, project_id, entity_id, scenario)
        too_slow = ms > catalogue["max_latency_ms"]
        total += 1
        failed += (not ok) or too_slow
        slow += too_slow
        print(f"{'PASS' if ok and not too_slow else 'FAIL'} {scenario['id']} [{scenario['view']}] {ms} ms: {detail}{' (zu langsam)' if too_slow else ''}")
    print(f"{total - failed} von {total} bestanden, {slow} über der Latenzgrenze")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
