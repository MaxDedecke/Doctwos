"""Auswahl der Knoten für die gekappte Graph-Übersicht (api/graph.py::_capped_overview).

Reihenfolge der Auswahl, bis das Knotenbudget erreicht ist:

1. Abdeckung: von jeder Knotenart und von jeder Kantenart kommen mindestens `min_per_kind`
   Vertreter (bei Kanten samt beider Endpunkte) in den Graphen, damit keine Art im Gedränge
   der häufigsten Art untergeht.
2. Fokus-Quelle (optional): so viele Knoten dieser Wissensquelle wie möglich, danach die Knoten,
   die am stärksten mit ihr verbunden sind. So sieht man, wie ihre Informationen mit dem Rest
   verwoben sind.
3. Geschützte Knoten (dokumentierte Code-Dateien, Endpunkte von Wissens-Links).
4. Je Dokumentquelle ein Vertreter.
5. Alle übrigen nach Grad.
"""

from collections import defaultdict
from typing import Iterable, Optional

# Anteil des Budgets, den die Fokus-Quelle selbst belegen darf; der Rest gehört ihren Nachbarn.
FOCUS_SOURCE_SHARE = 0.7
# Die Abdeckung darf höchstens diesen Anteil des Budgets verbrauchen.
COVERAGE_MAX_SHARE = 0.5


def _end(edge: dict, key: str) -> str:
    value = edge[key]
    return value if isinstance(value, str) else value["id"]


def compute_degree(nodes: dict[str, dict], edges: list[dict]) -> dict[str, int]:
    degree = {nid: 0 for nid in nodes}
    for edge in edges:
        for end in (_end(edge, "source"), _end(edge, "target")):
            if end in degree:
                degree[end] += 1
    return degree


def node_kind(node: dict) -> tuple:
    return (node.get("type"), node.get("resource_type"))


def edge_kind(edge: dict) -> tuple:
    return (edge.get("link_type"), edge.get("relation_type"))


def select_overview_nodes(
    nodes: dict[str, dict],
    edges: list[dict],
    degree: dict[str, int],
    max_nodes: int,
    preserved_node_ids: Optional[Iterable[str]] = None,
    min_per_kind: int = 0,
    focus_source_id: Optional[int] = None,
) -> list[str]:
    ranked_ids = sorted(nodes.keys(), key=lambda nid: (-degree[nid], nid))
    preserved = set(preserved_node_ids or ())
    order: list[str] = []
    chosen: set[str] = set()

    def take(nid: str, limit: Optional[int] = None) -> bool:
        if nid not in nodes:
            return False
        if nid in chosen:
            return True
        if len(order) >= (max_nodes if limit is None else min(limit, max_nodes)):
            return False
        chosen.add(nid)
        order.append(nid)
        return True

    if min_per_kind > 0:
        coverage_limit = max(1, int(max_nodes * COVERAGE_MAX_SHARE))
        by_edge_kind: dict[tuple, list[dict]] = defaultdict(list)
        for edge in edges:
            if _end(edge, "source") in nodes and _end(edge, "target") in nodes:
                by_edge_kind[edge_kind(edge)].append(edge)
        # Seltene Kantenarten zuerst: Ihre Endpunkte zählen zugleich für die Knotenarten.
        for kind_edges in sorted(by_edge_kind.values(), key=len):
            present = sum(
                1 for e in kind_edges if _end(e, "source") in chosen and _end(e, "target") in chosen
            )
            for edge in sorted(kind_edges, key=lambda e: -(e.get("score") or 0)):
                if present >= min_per_kind:
                    break
                src, tgt = _end(edge, "source"), _end(edge, "target")
                if src in chosen and tgt in chosen:
                    continue
                needed = (src not in chosen) + (tgt not in chosen)
                if len(order) + needed > coverage_limit:
                    continue
                take(src, coverage_limit)
                take(tgt, coverage_limit)
                present += 1

        by_node_kind: dict[tuple, list[str]] = defaultdict(list)
        for nid in ranked_ids:
            by_node_kind[node_kind(nodes[nid])].append(nid)
        for ids in by_node_kind.values():
            already = sum(1 for nid in ids if nid in chosen)
            for nid in ids:
                if already >= min_per_kind:
                    break
                if nid not in chosen and take(nid, coverage_limit):
                    already += 1

    if focus_source_id is not None:
        focus_ids = [nid for nid in ranked_ids if nodes[nid].get("source_id") == focus_source_id]
        focus_set = set(focus_ids)
        focus_budget = int(max_nodes * FOCUS_SOURCE_SHARE)
        in_focus = sum(1 for nid in order if nid in focus_set)
        for nid in focus_ids:
            if in_focus >= focus_budget:
                break
            if nid in chosen:
                continue
            if not take(nid):
                break
            in_focus += 1
        links_to_focus: dict[str, int] = defaultdict(int)
        for edge in edges:
            src, tgt = _end(edge, "source"), _end(edge, "target")
            if src in focus_set and tgt not in focus_set:
                links_to_focus[tgt] += 1
            elif tgt in focus_set and src not in focus_set:
                links_to_focus[src] += 1
        for nid in sorted(links_to_focus, key=lambda n: (-links_to_focus[n], -degree.get(n, 0), n)):
            if not take(nid):
                break

    for nid in ranked_ids:
        if nid in preserved:
            take(nid)

    represented_sources: set[object] = set()
    for nid in ranked_ids:
        node = nodes[nid]
        source_id = node.get("source_id")
        if node.get("type") != "document" or source_id is None or source_id in represented_sources:
            continue
        represented_sources.add(source_id)
        take(nid)

    for nid in ranked_ids:
        take(nid)
    return order[:max_nodes]
