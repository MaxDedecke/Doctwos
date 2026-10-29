"""Gruppen-Knoten der Graph-Übersicht: Dateien nach Kopplung gruppiert, Topics gehen vor.

Am Ende jedes Syncs (und nach Topic-Änderungen) wird je Projekt neu berechnet:

1. Topics sind von Menschen gebildete Gruppen. Code-Elemente eines Topics bringen ihre Datei in die
   Topic-Gruppe; liegt eine Datei in mehreren Topics, gewinnt das kleinste. Topics, die nur ganze
   Quellen, Repositories oder Projekte enthalten, bilden keine Gruppe. Dokumente eines Topics ordnet
   das Backend beim Lesen zu.
2. Alle übrigen vernetzten Dateien gruppiert Louvain (Modularität) auf dem vollständigen
   Dateigraphen; Gruppen über `GROUP_MAX_FILES` Dateien werden auf dieselbe Weise unterteilt.
3. Kanten zwischen den feinsten Gruppen werden gebündelt (Zahl der Beziehungen und Dateikanten).

Gewicht einer Dateikante wie beim Grundgerüst: Zahl der Beziehungen, verstärkt nach Rolle.

Ab `LOUVAIN_MAX_FILE_EDGES` Dateikanten (gemessen: 1 Mio. ≈ 26 s und 1 GB im Parser) gruppiert
Louvain Verzeichnisse statt Dateien; die Datenbank fasst die Beziehungen dafür zusammen. Topics
gehen dann nur noch bei der Zuordnung der Dateien vor, die gebündelten Kanten bleiben auf
Verzeichnisebene.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from posixpath import commonpath, splitext
from typing import Iterable, Optional

from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from doctus_models.code_file_edges import file_edges_params, file_edges_query
from doctus_models.database import (
    CodeEntity,
    CodeFileGroup,
    CodeFileGroupMember,
    CodeGroupEdge,
    Topic,
    TopicNode,
)

GROUP_MAX_FILES = 150
LOUVAIN_MAX_FILE_EDGES = 1_000_000
_MAX_SPLIT_DEPTH = 3
_MAX_PASSES = 50

FileKey = tuple[Optional[int], Optional[int], str]


# ── Louvain ──────────────────────────────────────────────────────────────────


def _one_level(graph: list[dict[int, float]], loops: list[float], resolution: float):
    size = len(graph)
    degree = [sum(graph[i].values()) + 2 * loops[i] for i in range(size)]
    total = sum(degree)
    community = list(range(size))
    if not total:
        return community, False
    community_degree = degree[:]
    improved = False
    for _ in range(_MAX_PASSES):
        moved = False
        for node in range(size):
            current, node_degree = community[node], degree[node]
            links: dict[int, float] = defaultdict(float)
            for other, weight in graph[node].items():
                links[community[other]] += weight
            community_degree[current] -= node_degree
            best = current
            best_gain = (
                links.get(current, 0.0)
                - resolution * community_degree[current] * node_degree / total
            )
            for candidate, weight in links.items():
                gain = weight - resolution * community_degree[candidate] * node_degree / total
                if gain > best_gain + 1e-12:
                    best, best_gain = candidate, gain
            community_degree[best] += node_degree
            if best != current:
                community[node] = best
                moved = improved = True
        if not moved:
            break
    return community, improved


def _aggregate(graph: list[dict[int, float]], loops: list[float], community: list[int], count: int):
    merged: list[dict[int, float]] = [defaultdict(float) for _ in range(count)]
    merged_loops = [0.0] * count
    for node, neighbours in enumerate(graph):
        own = community[node]
        merged_loops[own] += loops[node]
        for other, weight in neighbours.items():
            if community[other] == own:
                # Jede innere Kante wird von beiden Enden aus gesehen.
                merged_loops[own] += weight / 2
            else:
                merged[own][community[other]] += weight
    return merged, merged_loops


def louvain(adjacency: dict[str, dict[str, float]], resolution: float = 1.0) -> dict[str, int]:
    """Gemeinschaften eines ungerichteten, gewichteten Graphen (symmetrische Adjazenz).

    Deterministisch: Knoten werden in sortierter Reihenfolge besucht. Rückgabe: Gruppennummer je
    Knoten, nach Gruppengröße absteigend nummeriert.
    """
    nodes = sorted(adjacency)
    index = {node: i for i, node in enumerate(nodes)}
    graph: list[dict[int, float]] = [defaultdict(float) for _ in nodes]
    for node, neighbours in adjacency.items():
        for other, weight in neighbours.items():
            if other != node:
                graph[index[node]][index[other]] += weight
    loops = [0.0] * len(nodes)
    membership = list(range(len(nodes)))
    while True:
        community, improved = _one_level(graph, loops, resolution)
        if not improved:
            break
        renumber: dict[int, int] = {}
        community = [renumber.setdefault(c, len(renumber)) for c in community]
        membership = [community[m] for m in membership]
        graph, loops = _aggregate(graph, loops, community, len(renumber))
    sizes = Counter(membership)
    order = {c: i for i, (c, _) in enumerate(sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0])))}
    return {node: order[membership[index[node]]] for node in nodes}


# ── Gruppen bilden ───────────────────────────────────────────────────────────


@dataclass
class Group:
    key: str
    kind: str  # "community" | "topic"
    parent_key: Optional[str] = None
    level: int = 0
    topic_id: Optional[int] = None
    files: set = field(default_factory=set)
    label: str = ""
    path_prefix: str = ""
    central_file: str = ""


@dataclass
class GroupEdge:
    source: str
    target: str
    edge_count: int = 0
    file_edge_count: int = 0
    edge_types: set = field(default_factory=set)


def _label(files: Iterable[FileKey], weighted_degree: dict[FileKey, float]):
    files = sorted(files, key=lambda f: f[2])
    central = max(files, key=lambda f: (weighted_degree.get(f, 0.0), f[2]))
    directories = [f[2].rsplit("/", 1)[0] if "/" in f[2] else "" for f in files]
    prefix = commonpath(directories) if all(directories) else ""
    stem = splitext(central[2].rsplit("/", 1)[-1])[0]
    short = "/".join(prefix.split("/")[-2:]) if prefix else ""
    return (f"{short} · {stem}" if short else stem), prefix, central[2]


def build_groups(
    pairs: list[tuple[FileKey, FileKey, int, int, list[str]]],
    topic_files: dict[int, set[FileKey]],
    topic_sizes: dict[int, int],
) -> tuple[list[Group], dict[FileKey, str], list[GroupEdge]]:
    """Gruppen, Zuordnung Datei → feinste Gruppe und gebündelte Kanten zwischen feinsten Gruppen.

    `pairs`: (Quelldatei, Zieldatei, Beziehungen, Priorität, Arten). `topic_files`: Dateien je Topic,
    `topic_sizes`: Zahl der Einträge je Topic (für „das kleinste Topic gewinnt“).
    """
    adjacency: dict[FileKey, dict[FileKey, float]] = defaultdict(lambda: defaultdict(float))
    for source, target, count, priority, _ in pairs:
        weight = count * (1 + priority)
        adjacency[source][target] += weight
        adjacency[target][source] += weight
    weighted_degree = {f: sum(n.values()) for f, n in adjacency.items()}

    leaf: dict[FileKey, str] = {}
    groups: list[Group] = []
    for topic_id in sorted(topic_files, key=lambda t: (topic_sizes.get(t, 0), t)):
        group = Group(key=f"t{topic_id}", kind="topic", topic_id=topic_id)
        for file in topic_files[topic_id]:
            if file not in leaf:
                leaf[file] = group.key
                group.files.add(file)
        groups.append(group)

    def split(files: set, parent: Optional[str], level: int, prefix: str):
        sub = {f: {o: w for o, w in adjacency[f].items() if o in files} for f in files}
        communities = louvain(sub)
        members: dict[int, set] = defaultdict(set)
        for file, community in communities.items():
            members[community].add(file)
        if parent is not None and len(members) == 1:
            return False
        for community in sorted(members):
            group = Group(
                key=f"{prefix}{community}",
                kind="community",
                parent_key=parent,
                level=level,
                files=members[community],
            )
            groups.append(group)
            divided = (
                len(group.files) > GROUP_MAX_FILES
                and level < _MAX_SPLIT_DEPTH
                and split(group.files, group.key, level + 1, f"{group.key}.")
            )
            if not divided:
                for file in group.files:
                    leaf[file] = group.key
        return True

    free = {f for f in adjacency if f not in leaf}
    if free:
        split(free, None, 0, "c")

    for group in groups:
        if group.kind == "community":
            group.label, group.path_prefix, group.central_file = _label(
                group.files, weighted_degree
            )
        elif group.files:
            _, group.path_prefix, group.central_file = _label(group.files, weighted_degree)

    edges: dict[tuple[str, str], GroupEdge] = {}
    for source, target, count, _, types in pairs:
        a, b = leaf.get(source), leaf.get(target)
        if a is None or b is None or a == b:
            continue
        edge = edges.setdefault((a, b), GroupEdge(a, b))
        edge.edge_count += count
        edge.file_edge_count += 1
        edge.edge_types.update(types)
    return groups, leaf, list(edges.values())


# ── Persistenz ───────────────────────────────────────────────────────────────


def _topic_files(db: Session, project_id: Optional[int]):
    if project_id is None:
        return {}, {}
    topics = db.query(Topic.id).filter(Topic.project_id == project_id).all()
    topic_ids = [t.id for t in topics]
    if not topic_ids:
        return {}, {}
    nodes = (
        db.query(TopicNode.topic_id, TopicNode.node_type, TopicNode.node_id)
        .filter(TopicNode.topic_id.in_(topic_ids), TopicNode.node_type.in_(["entity", "document"]))
        .all()
    )
    sizes = Counter(n.topic_id for n in nodes)
    entity_ids = {n.node_id for n in nodes if n.node_type == "entity"}
    entities = (
        {
            e.id: (e.project_id, e.source_id, e.file_path)
            for e in db.query(
                CodeEntity.id, CodeEntity.project_id, CodeEntity.source_id, CodeEntity.file_path
            )
            .filter(CodeEntity.id.in_(entity_ids))
            .all()
        }
        if entity_ids
        else {}
    )
    files: dict[int, set] = {topic_id: set() for topic_id in sizes}
    for node in nodes:
        if node.node_type == "entity" and node.node_id in entities:
            files[node.topic_id].add(entities[node.node_id])
    return files, dict(sizes)


# Grobe Stufe: Beziehungen zwischen Verzeichnissen statt Dateien (path = Verzeichnis).
_DIRECTORY_EDGES = """
SELECT coalesce(s.project_id, 0) AS sp, coalesce(s.source_id, 0) AS ss,
       regexp_replace(s.file_path, '/[^/]*$', '') AS sd,
       coalesce(d.project_id, 0) AS dp, coalesce(d.source_id, 0) AS ds,
       regexp_replace(d.file_path, '/[^/]*$', '') AS dd,
       count(*) AS edge_count, array_agg(DISTINCT e.type) AS edge_types,
       max(CASE WHEN e.type = ANY(:strong) THEN 3 WHEN e.type = ANY(:data) THEN 2
                WHEN e.type = ANY(:naming) THEN 0 ELSE 1 END) AS priority
FROM code_edges e
JOIN code_entities s ON s.id = e.src_entity_id
JOIN code_entities d ON d.id = e.dst_entity_id
WHERE {scope}
  AND NOT (regexp_replace(s.file_path, '/[^/]*$', '') = regexp_replace(d.file_path, '/[^/]*$', '')
           AND coalesce(s.source_id, 0) = coalesce(d.source_id, 0)
           AND coalesce(s.project_id, 0) = coalesce(d.project_id, 0))
GROUP BY 1, 2, 3, 4, 5, 6
"""
_DIRECTORY_EDGES = (
    "SELECT nullif(sp, 0) AS src_project_id, nullif(ss, 0) AS src_source_id, sd AS src_file_path, "
    "nullif(dp, 0) AS dst_project_id, nullif(ds, 0) AS dst_source_id, dd AS dst_file_path, "
    "edge_count, priority, edge_types FROM (" + _DIRECTORY_EDGES + ") directory_edges"
)


def _files_by_directory(db: Session, project_id: Optional[int], directory_leaf: dict) -> dict:
    """Ordnet jede Datei der Gruppe ihres Verzeichnisses zu (grobe Stufe)."""
    query = db.query(CodeEntity.project_id, CodeEntity.source_id, CodeEntity.file_path).distinct()
    query = query.filter(
        CodeEntity.project_id.is_(None)
        if project_id is None
        else CodeEntity.project_id == project_id
    )
    leaf = {}
    for file_project, file_source, path in query.yield_per(10_000):
        directory = path.rsplit("/", 1)[0] if "/" in path else ""
        key = directory_leaf.get((file_project, file_source, directory))
        if key is not None:
            leaf[(file_project, file_source, path)] = key
    return leaf


def rebuild_code_file_groups(db: Session, project_id: Optional[int]) -> int:
    """Berechnet die Gruppen eines Projekts neu und gibt ihre Zahl zurück (Transaktion des Aufrufers)."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('code_file_groups'), :key)"),
        {"key": project_id or 0},
    )
    scope = "e.project_id IS NULL" if project_id is None else "e.project_id = :project_id"
    params = {**file_edges_params(), "project_id": project_id}
    file_edges = db.execute(
        text(
            "SELECT coalesce(max(total_pairs), 0) FROM code_file_edges WHERE "
            + ("project_id IS NULL" if project_id is None else "project_id = :project_id")
        ),
        {"project_id": project_id},
    ).scalar_one()
    coarse = file_edges > LOUVAIN_MAX_FILE_EDGES
    query = (
        _DIRECTORY_EDGES.format(scope=scope)
        if coarse
        else (
            "SELECT src_project_id, src_source_id, src_file_path, dst_project_id, dst_source_id, "
            f"dst_file_path, edge_count, priority, edge_types FROM ({file_edges_query(scope)}) f"
        )
    )
    pairs = [
        (
            (r.src_project_id, r.src_source_id, r.src_file_path),
            (r.dst_project_id, r.dst_source_id, r.dst_file_path),
            r.edge_count,
            r.priority,
            list(r.edge_types),
        )
        for r in db.execute(text(query), params).all()
    ]
    topic_files, topic_sizes = _topic_files(db, project_id)
    if not coarse:
        groups, leaf, edges = build_groups(pairs, topic_files, topic_sizes)
    else:
        groups, directory_leaf, edges = build_groups(pairs, {}, {})
        leaf = _files_by_directory(db, project_id, directory_leaf)
        for topic_id in sorted(topic_files, key=lambda t: (topic_sizes.get(t, 0), t)):
            groups.append(Group(key=f"t{topic_id}", kind="topic", topic_id=topic_id))
            for file in topic_files[topic_id]:
                if not leaf.get(file, "").startswith("t"):
                    leaf[file] = f"t{topic_id}"
        # Gruppen enthielten bisher Verzeichnisse; gezählt werden Dateien samt Untergruppen.
        by_key = {g.key: g for g in groups}
        for g in groups:
            g.files = set()
        for file, key in leaf.items():
            while key is not None:
                by_key[key].files.add(file)
                key = by_key[key].parent_key

    for model in (CodeGroupEdge, CodeFileGroupMember, CodeFileGroup):
        query = db.query(model)
        query = query.filter(
            model.project_id.is_(None) if project_id is None else model.project_id == project_id
        )
        query.delete(synchronize_session=False)
    if groups:
        db.execute(
            insert(CodeFileGroup),
            [
                {
                    "project_id": project_id,
                    "group_key": g.key,
                    "parent_key": g.parent_key,
                    "level": g.level,
                    "kind": g.kind,
                    "topic_id": g.topic_id,
                    "label": g.label,
                    "path_prefix": g.path_prefix,
                    "central_file": g.central_file,
                    "file_count": len(g.files),
                }
                for g in groups
            ],
        )
    if leaf:
        db.execute(
            insert(CodeFileGroupMember),
            [
                {
                    "project_id": project_id,
                    "group_key": key,
                    "file_project_id": file[0],
                    "file_source_id": file[1],
                    "file_path": file[2],
                }
                for file, key in leaf.items()
            ],
        )
    if edges:
        db.execute(
            insert(CodeGroupEdge),
            [
                {
                    "project_id": project_id,
                    "src_group_key": e.source,
                    "dst_group_key": e.target,
                    "edge_count": e.edge_count,
                    "file_edge_count": e.file_edge_count,
                    "edge_types": sorted(e.edge_types),
                }
                for e in edges
            ],
        )
    return len(groups)
