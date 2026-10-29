"""Echte Verbindungszahl je Übersichtsknoten.

Die Übersicht zeigt nur eine Auswahl der Kanten (Knotendeckel, Grundgerüst der Code-Beziehungen).
Damit das Frontend nicht geladene Verbindungen anzeigen und gezielt nachladen kann, trägt jeder
gelieferte Knoten `degree`: die Zahl seiner Kanten im vollständigen Übersichtsgraphen.
"""

from collections import defaultdict

from services.graph_overview_sampling import compute_degree

CODE_FILE_EDGE_PREFIX = "code-files:"


def overview_degrees(
    nodes: dict[str, dict], edges: list[dict], code_file_degree: dict[str, int]
) -> dict[str, int]:
    """Grad im gebauten Graphen, der Anteil der Dateikanten ersetzt durch `code_file_degree`."""
    degree = compute_degree(nodes, edges)
    built: dict[str, int] = defaultdict(int)
    for edge in edges:
        if edge["id"].startswith(CODE_FILE_EDGE_PREFIX):
            built[edge["source"]] += 1
            built[edge["target"]] += 1
    for node_id in degree:
        degree[node_id] += code_file_degree.get(node_id, built[node_id]) - built[node_id]
    return degree
