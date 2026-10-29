"""Graph-Übersicht mit Gruppen-Knoten (vorberechnet in doctus_models.code_file_groups).

Ab der Grundgerüst-Schwelle zeigt die Übersicht eines Projekts statt einzelner Dateien die
Gruppen. Der Browser schickt mit, welche Gruppen aufgeklappt sind; der Server bleibt zustandslos
und liefert die passende Szene:

- Sichtbar ist je Datei die oberste nicht aufgeklappte Gruppe auf ihrem Weg; sind alle aufgeklappt,
  die Datei selbst.
- Code-Beziehungen zwischen Gruppen kommen gebündelt aus `code_group_edges`. Für Dateien einer
  aufgeklappten Gruppe fasst der Server ihre Beziehungen direkt zusammen; Kanten zu Dateien in
  eingeklappten Gruppen hängen an deren Gruppen-Knoten.
- Dokumente, Erkenntnisse und Wissens-Links bleiben eigene Knoten. Ihre Kanten zu Dateien in
  eingeklappten Gruppen zeigen auf die Gruppe. Dokumente eines Topics gehören zu dessen Gruppe.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from doctus_models.code_file_edges import (
    BACKBONE_MIN_FILE_EDGES,
    file_edges_params,
    file_edges_query,
)
from doctus_models.database import (
    CodeEdge,
    CodeEntity,
    CodeFileGroup,
    DocumentChunk,
    Topic,
    TopicNode,
)

GROUP_NODE_PREFIX = "group:"
FileKey = tuple[Optional[int], Optional[int], str]


@dataclass
class GraphHelpers:
    """Bausteine aus api/graph.py, damit beide Wege dieselben Knoten und Kanten erzeugen."""

    file_id: Callable[[Optional[int], Optional[int], str], str]
    ensure_file: Callable[[dict, CodeEntity], str]
    doc_node_id: Callable
    doc_node: Callable
    append_code_dependencies: Callable


def grouping_available(db: Session, project_id: Optional[int]) -> bool:
    if not project_id:
        return False
    file_edges = db.execute(
        text("SELECT coalesce(max(total_pairs), 0) FROM code_file_edges WHERE project_id = :p"),
        {"p": project_id},
    ).scalar_one()
    if file_edges <= BACKBONE_MIN_FILE_EDGES:
        return False
    return (
        db.query(CodeFileGroup.id).filter(CodeFileGroup.project_id == project_id).first()
        is not None
    )


def _group_node(group, topic: Optional[tuple[str, str]], doc_count: int, project_id: int) -> dict:
    label = topic[0] if topic else group.label
    return {
        "id": GROUP_NODE_PREFIX + group.group_key,
        "type": "group",
        "label": label,
        "group_key": group.group_key,
        "group_kind": group.kind,
        "group_parent": group.parent_key,
        "level": group.level,
        "file_count": group.file_count,
        "doc_count": doc_count,
        "topic_id": group.topic_id,
        "topic_color": topic[1] if topic else None,
        "path_prefix": group.path_prefix,
        "central_file": group.central_file,
        "project_id": project_id,
    }


def _bundle(bundles: dict, source: str, target: str, kind: str, count: int, files: int, types):
    key = (source, target, kind)
    bundle = bundles.setdefault(
        key, {"edge_count": 0, "file_edge_count": 0, "edge_types": set(), "edges": 0}
    )
    bundle["edge_count"] += count
    bundle["file_edge_count"] += files
    bundle["edge_types"].update(types)
    bundle["edges"] += 1


def grouped_overview(
    db: Session,
    project_id: int,
    nodes: dict[str, dict],
    edges: list[dict],
    expanded_keys: list[str],
    helpers: GraphHelpers,
) -> dict:
    groups = {
        g.group_key: g
        for g in db.query(CodeFileGroup).filter(CodeFileGroup.project_id == project_id).all()
    }
    topic_ids = {g.topic_id for g in groups.values() if g.topic_id is not None}
    topics = (
        {t.id: (t.name, t.color) for t in db.query(Topic).filter(Topic.id.in_(topic_ids)).all()}
        if topic_ids
        else {}
    )

    def chain(key: str) -> list[str]:
        path = []
        while key is not None and key in groups:
            path.append(key)
            key = groups[key].parent_key
        return path[::-1]

    requested = set(expanded_keys)
    expanded = {k for k in requested if k in groups and all(a in requested for a in chain(k))}

    def visible(leaf_key: Optional[str]) -> Optional[str]:
        """Sichtbarer Gruppen-Knoten für eine feinste Gruppe; None = deren Dateien sind sichtbar."""
        for key in chain(leaf_key) if leaf_key else []:
            if key not in expanded:
                return key
        return None

    has_children = {g.parent_key for g in groups.values() if g.parent_key}
    open_leaves = [k for k in expanded if k not in has_children]

    # ── Zugehörigkeit von Dateien ────────────────────────────────────────────
    membership: dict[FileKey, str] = {}

    def load_members(condition: str, params: dict) -> None:
        for row in db.execute(
            text(
                "SELECT file_project_id, file_source_id, file_path, group_key "
                f"FROM code_file_group_members WHERE project_id = :p AND {condition}"
            ),
            {"p": project_id, **params},
        ):
            membership[(row.file_project_id, row.file_source_id, row.file_path)] = row.group_key

    if open_leaves:
        load_members("group_key = ANY(:keys)", {"keys": open_leaves})
    open_files = {f for f, k in membership.items() if k in open_leaves}

    referenced = {
        (n.get("project_id"), n.get("source_id"), n["file_path"])
        for n in nodes.values()
        if n.get("type") == "code_file" and n.get("file_path")
    }

    # ── Code-Beziehungen der Dateien aufgeklappter Gruppen ───────────────────
    out_nodes: dict[str, dict] = {}
    pair_rows = []
    if open_files:
        entities = (
            db.query(CodeEntity)
            .filter(
                CodeEntity.project_id == project_id,
                CodeEntity.file_path.in_({f[2] for f in open_files}),
            )
            .all()
        )
        entities = [e for e in entities if (e.project_id, e.source_id, e.file_path) in open_files]
        for entity in entities:
            helpers.ensure_file(out_nodes, entity)
        pair_rows = db.execute(
            text(
                "SELECT src_project_id, src_source_id, src_file_path, dst_project_id, dst_source_id, "
                "dst_file_path, edge_count, edge_types, sample_edge_ids FROM ("
                + file_edges_query(
                    "e.project_id = :project_id AND (e.src_entity_id = ANY(:ids) "
                    "OR e.dst_entity_id = ANY(:ids))"
                )
                + ") f"
            ),
            {**file_edges_params(), "project_id": project_id, "ids": [e.id for e in entities]},
        ).all()
        referenced |= {(r.src_project_id, r.src_source_id, r.src_file_path) for r in pair_rows}
        referenced |= {(r.dst_project_id, r.dst_source_id, r.dst_file_path) for r in pair_rows}

    unknown = [f for f in referenced if f not in membership]
    if unknown:
        load_members("file_path = ANY(:paths)", {"paths": sorted({f[2] for f in unknown})})

    def file_end(key: FileKey) -> str:
        """Knoten-ID, unter der eine Datei gerade sichtbar ist."""
        group = visible(membership.get(key))
        return GROUP_NODE_PREFIX + group if group else helpers.file_id(*key)

    # ── Topic-Dokumente ──────────────────────────────────────────────────────
    doc_group: dict[str, str] = {}
    topic_doc_counts: dict[str, int] = defaultdict(int)
    if topic_ids:
        doc_members = (
            db.query(TopicNode.topic_id, DocumentChunk)
            .join(DocumentChunk, DocumentChunk.id == TopicNode.node_id)
            .filter(TopicNode.topic_id.in_(topic_ids), TopicNode.node_type == "document")
            .all()
        )
        for topic_id, chunk in sorted(doc_members, key=lambda m: m[0]):
            meta = chunk.metadata_json or {}
            title = meta.get("title") or chunk.file_path
            node_id = helpers.doc_node_id(title, meta.get("source_type"), meta.get("url"), chunk)
            key = f"t{topic_id}"
            if key not in groups or node_id in doc_group:
                continue
            doc_group[node_id] = key
            topic_doc_counts[key] += 1
            if key in expanded and node_id not in nodes:
                nodes[node_id] = helpers.doc_node(
                    title, meta.get("source_type"), meta.get("url"), chunk
                )

    # ── Knoten ───────────────────────────────────────────────────────────────
    for group in groups.values():
        if group.group_key in expanded:
            continue
        if group.parent_key is not None and group.parent_key not in expanded:
            continue
        node = _group_node(
            group, topics.get(group.topic_id), topic_doc_counts[group.group_key], project_id
        )
        out_nodes[node["id"]] = node
    for node in out_nodes.values():
        if node.get("type") == "code_file":
            node["group_parent"] = membership.get(
                (node.get("project_id"), node.get("source_id"), node["file_path"])
            )

    remap: dict[str, str] = {}

    def group_label(key: Optional[str]) -> Optional[str]:
        group = groups.get(key) if key else None
        if group is None:
            return None
        return topics.get(group.topic_id, (group.label,))[0] if group.topic_id else group.label

    for node_id, node in nodes.items():
        if node.get("type") == "code_file" and node.get("file_path"):
            key = (node.get("project_id"), node.get("source_id"), node["file_path"])
            target = file_end(key)
            if target != node_id:
                remap[node_id] = target
                continue
            node = {**node, "group_parent": membership.get(key)}
        elif node_id in doc_group:
            group = doc_group[node_id]
            if group not in expanded:
                remap[node_id] = GROUP_NODE_PREFIX + group
                continue
            node = {**node, "group_parent": group}
        out_nodes.setdefault(node_id, node)
    # Aufgeklappte Inhalte nennen ihre Gruppe, damit sie sich von dort wieder einklappen lässt.
    for node in out_nodes.values():
        if node.get("group_parent"):
            node["group_parent_label"] = group_label(node["group_parent"])

    # ── Kanten ───────────────────────────────────────────────────────────────
    out_edges: list[dict] = []
    bundles: dict = {}
    # Verbindungen eines sichtbaren Knotens, die nur gebündelt in eine eingeklappte Gruppe laufen.
    hidden: Counter = Counter()

    def count_hidden(source: str, target: str, original_source: str, original_target: str):
        if source != original_source and target == original_target:
            hidden[target] += 1
        elif target != original_target and source == original_source:
            hidden[source] += 1

    for edge in edges:
        source = remap.get(edge["source"], edge["source"])
        target = remap.get(edge["target"], edge["target"])
        if source == target:
            continue
        if source == edge["source"] and target == edge["target"]:
            out_edges.append(edge)
            continue
        count_hidden(source, target, edge["source"], edge["target"])
        kind = edge.get("relation_type") or edge.get("link_type")
        _bundle(bundles, source, target, kind, 1, 0, [])
        bundles[(source, target, kind)].setdefault("template", edge)

    for row in db.execute(
        text(
            "SELECT src_group_key, dst_group_key, edge_count, file_edge_count, edge_types "
            "FROM code_group_edges WHERE project_id = :p"
        ),
        {"p": project_id},
    ):
        source, target = visible(row.src_group_key), visible(row.dst_group_key)
        if source is None or target is None or source == target:
            continue
        _bundle(
            bundles,
            GROUP_NODE_PREFIX + source,
            GROUP_NODE_PREFIX + target,
            "code_dependency",
            row.edge_count,
            row.file_edge_count,
            row.edge_types,
        )

    detailed, totals = [], {}
    for row in pair_rows:
        a = (row.src_project_id, row.src_source_id, row.src_file_path)
        b = (row.dst_project_id, row.dst_source_id, row.dst_file_path)
        source, target = file_end(a), file_end(b)
        if source == target:
            continue
        if source.startswith(GROUP_NODE_PREFIX) or target.startswith(GROUP_NODE_PREFIX):
            count_hidden(source, target, helpers.file_id(*a), helpers.file_id(*b))
            _bundle(bundles, source, target, "code_dependency", row.edge_count, 1, row.edge_types)
            continue
        detailed.extend(row.sample_edge_ids)
        totals[(source, target)] = (row.edge_count, sorted(row.edge_types))
    if detailed:
        code_edges = db.query(CodeEdge).filter(CodeEdge.id.in_(detailed)).all()
        entity_ids = {
            i for e in code_edges for i in (e.src_entity_id, e.dst_entity_id) if i is not None
        }
        entities = {e.id: e for e in db.query(CodeEntity).filter(CodeEntity.id.in_(entity_ids))}
        helpers.append_code_dependencies(out_nodes, out_edges, code_edges, entities, totals=totals)

    for (source, target, kind), bundle in bundles.items():
        template = bundle.get("template")
        if template is not None and bundle["edges"] == 1:
            # Zeigt auf die Gruppe statt auf die Datei: gilt wie ein Bündel, nicht als Einzelkante.
            meta = {**(template.get("meta") or {}), "bundled": True, "edge_count": 1}
            out_edges.append({**template, "source": source, "target": target, "meta": meta})
            continue
        types = sorted(t for t in bundle["edge_types"] if t)
        if kind == "code_dependency":
            context = (
                f"{bundle['edge_count']} Beziehungen in {bundle['file_edge_count']} Dateikante(n)"
            )
            if types:
                context += f": {', '.join(types)}"
        else:
            context = f"{bundle['edges']} gebündelte Verknüpfung(en)"
        out_edges.append(
            {
                "id": f"bundle:{kind}:{source}->{target}",
                "source": source,
                "target": target,
                "link_type": kind,
                "relation_type": kind,
                "direction": "directed"
                if kind in {"code_dependency", "documented"}
                else "undirected",
                "score": None,
                "context": context,
                "meta": {
                    "bundled": True,
                    "edge_count": bundle["edge_count"]
                    if kind == "code_dependency"
                    else bundle["edges"],
                    "file_edge_count": bundle["file_edge_count"],
                    "edge_types": types,
                },
            }
        )

    # Einzelknoten ohne Kante tragen nichts bei; Gruppen und Erkenntnisse bleiben immer.
    connected = {e["source"] for e in out_edges} | {e["target"] for e in out_edges}
    result_nodes = [
        n
        for n in out_nodes.values()
        if n["id"] in connected or n.get("type") in {"group", "insight"} or n.get("group_parent")
    ]
    # Echte Verbindungszahl: einzeln sichtbare Kanten plus die nur gebündelt sichtbaren. Das
    # Frontend zeigt die Differenz zu den einzeln geladenen Kanten als „+N“.
    individual: Counter = Counter()
    for edge in out_edges:
        if not (edge.get("meta") or {}).get("bundled"):
            individual[edge["source"]] += 1
            individual[edge["target"]] += 1
    for node in result_nodes:
        if node.get("type") != "group":
            node["degree"] = individual[node["id"]] + hidden[node["id"]]
    return {
        "nodes": result_nodes,
        "edges": [e for e in out_edges if e["source"] in out_nodes and e["target"] in out_nodes],
        "grouped": True,
        "expanded": sorted(expanded),
        "truncated": False,
        "edges_sampled": False,
        "total_nodes": len(result_nodes),
        "total_edges": len(out_edges),
    }


def annotate_group_membership(db: Session, project_id: Optional[int], nodes: list[dict]) -> None:
    """Dateien, die einzeln aus ihrer Gruppe geholt werden (Nachbarschaft, Einblenden), nennen sie."""
    files = {
        (n.get("project_id"), n.get("source_id"), n["file_path"]): n
        for n in nodes
        if n.get("type") == "code_file" and n.get("file_path")
    }
    if not project_id or not files:
        return
    rows = db.execute(
        text(
            "SELECT m.file_project_id, m.file_source_id, m.file_path, m.group_key, g.label, "
            "g.topic_id, t.name AS topic_name FROM code_file_group_members m "
            "JOIN code_file_groups g ON g.project_id = m.project_id AND g.group_key = m.group_key "
            "LEFT JOIN topics t ON t.id = g.topic_id "
            "WHERE m.project_id = :p AND m.file_path = ANY(:paths)"
        ),
        {"p": project_id, "paths": sorted({key[2] for key in files})},
    )
    for row in rows:
        node = files.get((row.file_project_id, row.file_source_id, row.file_path))
        if node is not None:
            node["member_group"] = row.group_key
            node["member_group_label"] = row.topic_name or row.label


def group_path(db: Session, project_id: int, leaf_key: Optional[str]) -> list[str]:
    """Gruppen von der obersten bis zur feinsten, die man aufklappen muss, um den Inhalt zu sehen."""
    if not leaf_key:
        return []
    parents = dict(
        db.query(CodeFileGroup.group_key, CodeFileGroup.parent_key)
        .filter(CodeFileGroup.project_id == project_id)
        .all()
    )
    path, key = [], leaf_key
    while key is not None and key in parents:
        path.append(key)
        key = parents[key]
    return path[::-1]


def locate_file(
    db: Session, project_id: int, file_path: str, source_id: Optional[int]
) -> Optional[str]:
    """Feinste Gruppe einer Datei (bei mehreren Quellen mit gleichem Pfad die angegebene)."""
    rows = db.execute(
        text(
            "SELECT file_source_id, group_key FROM code_file_group_members "
            "WHERE project_id = :p AND file_path = :path ORDER BY file_source_id"
        ),
        {"p": project_id, "path": file_path},
    ).all()
    match = next((r for r in rows if source_id is None or r.file_source_id == source_id), None)
    return match.group_key if match else None


def locate_topic_document(db: Session, project_id: int, chunk: DocumentChunk) -> Optional[str]:
    """Topic-Gruppe, in der ein Dokument steckt (das kleinste Topic, wie bei Dateien)."""
    topic_ids = [
        row.topic_id
        for row in db.query(TopicNode.topic_id)
        .join(Topic, Topic.id == TopicNode.topic_id)
        .filter(
            Topic.project_id == project_id,
            TopicNode.node_type == "document",
            TopicNode.node_id == chunk.id,
        )
        .all()
    ]
    keys = {f"t{t}" for t in topic_ids}
    existing = {
        g.group_key
        for g in db.query(CodeFileGroup.group_key).filter(
            CodeFileGroup.project_id == project_id, CodeFileGroup.group_key.in_(keys)
        )
    }
    if not existing:
        return None
    sizes = Counter(
        row.topic_id
        for row in db.query(TopicNode.topic_id).filter(
            TopicNode.topic_id.in_([int(k[1:]) for k in existing]),
            TopicNode.node_type.in_(["entity", "document"]),
        )
    )
    return f"t{min(sizes, key=lambda t: (sizes[t], t))}"
