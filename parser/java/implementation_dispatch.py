"""Dispatch eines Interface- oder abstrakten Aufrufs zur einzigen Implementierung im Quelltext.

Ein virtueller Aufruf löst statisch auf die deklarierte Methode auf (``dispatch_scope: static_declaration_only``),
etwa ``logic.create(...)`` mit Empfängertyp ``UserLogicOp`` auf ``AnyCRUDLogicOp#create(C,boolean)``. Dort endete
jede Aufrufkette, obwohl die ausführende Methode im Quelltext steht (Katalogtest 08.11.2026, J3/J5/J12).

Implementiert genau ein konkreter Untertyp des statischen Empfängertyps die Methode (gleicher Name, gleiche
Parameterzahl; auch von einer abstrakten Oberklasse geerbt), entsteht ``DISPATCHES_TO`` zu dieser Methode. Bei
mehreren Implementierungen wird nichts gewählt: Welche zur Laufzeit läuft, entscheidet die Konfiguration. Gezählt
werden nur Implementierungen aus demselben Quellbereich (Haupt- oder Testcode) wie der Aufruf.
"""

from __future__ import annotations

from collections import defaultdict

from core.model import ParsedEdge

_TYPES = {"class", "interface", "enum", "record"}
_HIERARCHY = {"EXTENDS", "IMPLEMENTS"}
MAX_SUBTYPES = 2000


def derive_implementation_dispatch(results):
    entities = {}
    path_of = {}
    for result in results:
        for entity in result.entities:
            entities[entity.qualified_name] = entity
            path_of[entity.qualified_name] = result.path
    methods_by_owner = defaultdict(list)
    for entity in entities.values():
        if entity.type == "method" and entity.parent_qualified_name:
            methods_by_owner[entity.parent_qualified_name].append(entity)
    supertypes = defaultdict(list)
    subtypes = defaultdict(list)
    for result in results:
        for edge in result.edges:
            target = edge.meta.get("target_qualified_name")
            if edge.type in _HIERARCHY and target in entities and edge.src_name in entities:
                supertypes[edge.src_name].append(target)
                subtypes[target].append(edge.src_name)

    def concrete(type_name: str) -> bool:
        entity = entities.get(type_name)
        return (
            entity is not None
            and entity.type in _TYPES - {"interface"}
            and "abstract" not in entity.meta.get("modifiers", [])
        )

    def all_subtypes(type_name: str) -> set[str]:
        found, pending = set(), [type_name]
        while pending and len(found) < MAX_SUBTYPES:
            for sub in subtypes.get(pending.pop(), []):
                if sub not in found:
                    found.add(sub)
                    pending.append(sub)
        return found

    def implementation(type_name: str, name: str, arity: int):
        """Erste nicht abstrakte Methode entlang der Oberklassen eines konkreten Typs."""
        seen, current = set(), [type_name]
        while current:
            owner = current.pop(0)
            if owner in seen:
                continue
            seen.add(owner)
            owner_entity = entities.get(owner)
            if owner_entity is None:
                continue
            for method in methods_by_owner.get(owner, []):
                if (
                    method.name == name
                    and len(method.meta.get("parameter_types", [])) == arity
                    and "abstract" not in method.meta.get("modifiers", [])
                    and (
                        owner_entity.type != "interface"
                        or "default" in method.meta.get("modifiers", [])
                    )
                ):
                    return method
            current.extend(supertypes.get(owner, []))
        return None

    cache: dict[tuple[str, str, int, str], list] = {}
    for result in results:
        for call in result.edges:
            meta = call.meta
            if (
                call.type != "CALLS"
                or call.resolution != "resolved"
                or meta.get("dispatch_scope") != "static_declaration_only"
            ):
                continue
            declared = entities.get(meta.get("target_qualified_name"))
            if declared is None or declared.type != "method":
                continue
            owner = entities.get(declared.parent_qualified_name)
            if owner is None or (
                owner.type != "interface" and "abstract" not in declared.meta.get("modifiers", [])
            ):
                continue
            receiver = meta.get("receiver_type_qualified_name") or owner.qualified_name
            caller = entities.get(call.src_name)
            source_set = (caller.meta.get("source_set") if caller else None) or "main"
            arity = len(declared.meta.get("parameter_types", []))
            key = (receiver, declared.name, arity, source_set)
            if key not in cache:
                found = {}
                for sub in all_subtypes(receiver):
                    if (
                        not concrete(sub)
                        or entities[sub].meta.get("source_set", "main") != source_set
                    ):
                        continue
                    method = implementation(sub, declared.name, arity)
                    if method is not None:
                        found[method.qualified_name] = method
                cache[key] = list(found.values())
            candidates = cache[key]
            if len(candidates) != 1:
                continue
            target = candidates[0]
            yield (
                result,
                ParsedEdge(
                    type="DISPATCHES_TO",
                    src_name=call.src_name,
                    dst_name=target.qualified_name,
                    resolution="resolved",
                    src_start_line=call.src_start_line,
                    src_end_line=call.src_end_line,
                    meta={
                        **meta,
                        "derivation": "framework",
                        "target_qualified_name": target.qualified_name,
                        "target_file_path": path_of[target.qualified_name],
                        "declared_qualified_name": declared.qualified_name,
                        "resolution_reason": "only_implementation_in_source",
                        "dispatch_scope": "single_source_implementation",
                    },
                ),
            )
