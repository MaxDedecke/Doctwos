"""Conservative source-backed CDI/EJB/Spring injection and implementation candidates."""

import os
from collections import defaultdict

from core.model import ParsedEdge
from .annotations import annotations, namespaced, qualified_type, strings
from .scope import scope_candidates

SPRING_BEANS = namespaced(
    ["Component", "Service", "Repository", "Controller"], ["org.springframework.stereotype"]
) | {
    "org.springframework.web.bind.annotation.RestController",
    "org.springframework.context.annotation.Configuration",
}
CDI_BEANS = (
    namespaced(
        ["ApplicationScoped", "RequestScoped", "SessionScoped", "Dependent"],
        ["jakarta.enterprise.context", "javax.enterprise.context"],
    )
    | namespaced(["Named", "Singleton"], ["jakarta.inject", "javax.inject"])
    | namespaced(["Stateless", "Stateful", "Singleton"], ["jakarta.ejb", "javax.ejb"])
)
INJECTION = (
    namespaced(["Inject"], ["jakarta.inject", "javax.inject"])
    | namespaced(["EJB"], ["jakarta.ejb", "javax.ejb"])
    | namespaced(["Resource"], ["jakarta.annotation", "javax.annotation"])
    | {"org.springframework.beans.factory.annotation.Autowired"}
)
QUALIFIERS = namespaced(["Named"], ["jakarta.inject", "javax.inject"]) | {
    "org.springframework.beans.factory.annotation.Qualifier"
}


def _bean(entity, result):
    ann = annotations(entity, result)
    factory = entity.type == "method" and bool(
        ann.keys()
        & (
            {"org.springframework.context.annotation.Bean"}
            | namespaced(["Produces"], ["jakarta.enterprise.inject", "javax.enterprise.inject"])
        )
    )
    if not factory and not (entity.type == "class" and ann.keys() & (SPRING_BEANS | CDI_BEANS)):
        return None
    bean_names = []
    for name, values in ann.items():
        if name in SPRING_BEANS | QUALIFIERS | {"org.springframework.context.annotation.Bean"}:
            bean_names.extend(strings(values.get("name", values.get("value"))))
    default = entity.name if entity.type == "method" else entity.name[:1].lower() + entity.name[1:]
    profiles = strings(ann.get("org.springframework.context.annotation.Profile", {}).get("value"))
    active_profiles = set(filter(None, os.getenv("DOCTUS_SPRING_PROFILES", "").split(","))) or {
        "default"
    }
    active = not profiles or any(
        (p[1:] not in active_profiles) if p.startswith("!") else p in active_profiles
        for p in profiles
    )
    conditional = any(
        name.startswith("org.springframework.boot.autoconfigure.condition.") for name in ann
    )
    alternative = bool(
        ann.keys()
        & namespaced(["Alternative"], ["jakarta.enterprise.inject", "javax.enterprise.inject"])
    )
    return {
        "names": bean_names or [default],
        "provided_type": qualified_type(
            entity.meta.get("return_type") if factory else entity.qualified_name, result
        ),
        "primary": "org.springframework.context.annotation.Primary" in ann,
        "active": active and not conditional and not alternative,
        "activation_unknown": conditional or alternative,
        "framework": "spring" if any(n.startswith("org.springframework.") for n in ann) else "cdi",
        "factory": factory,
        "profiles": profiles,
        "scopes": [name for name in ann if name in CDI_BEANS or name.endswith(".Scope")],
    }


def add_bean_metadata(result):
    for entity in result.entities:
        bean = _bean(entity, result)
        if bean is not None:
            entity.meta["bean"] = bean


def _injection_sites(result):
    by_qname = {e.qualified_name: e for e in result.entities}
    constructors = defaultdict(list)
    for entity in result.entities:
        if entity.type == "constructor":
            constructors[entity.parent_qualified_name].append(entity)
    for entity in result.entities:
        if entity.type not in {"field", "parameter"}:
            continue
        ann = annotations(entity, result)
        owner = by_qname.get(entity.parent_qualified_name)
        injected = bool(ann.keys() & INJECTION)
        if entity.type == "parameter" and owner:
            injected |= bool(annotations(owner, result).keys() & INJECTION)
            declaring = by_qname.get(owner.parent_qualified_name)
            injected |= bool(
                owner.type == "constructor"
                and declaring
                and declaring.meta.get("bean", {}).get("framework") == "spring"
                and len(constructors[owner.parent_qualified_name]) == 1
            )
        if injected:
            yield entity, ann


def derive_injection_edges(results, xml_beans=()):
    beans, hierarchy, result_by_entity, all_entities = [], defaultdict(set), {}, []
    custom_qualifiers = set()
    for result in results:
        add_bean_metadata(result)
        for entity in result.entities:
            result_by_entity[id(entity)] = result
            all_entities.append(entity)
            if entity.type == "annotation_type" and annotations(entity, result).keys() & namespaced(
                ["Qualifier"], ["jakarta.inject", "javax.inject"]
            ):
                custom_qualifiers.add(entity.qualified_name)
            if entity.meta.get("bean"):
                beans.append(entity)
        for edge in result.edges:
            if edge.type in {"EXTENDS", "IMPLEMENTS"} and edge.resolution == "resolved":
                hierarchy[edge.src_name].add(edge.meta.get("target_qualified_name", edge.dst_name))
    for result, entity in xml_beans:
        implementation = entity.meta.get("bean_class")
        if not implementation:
            continue
        entity.meta["bean"] = {
            "names": entity.meta.get("bean_names") or [entity.name],
            "provided_type": implementation,
            "primary": entity.meta.get("primary", False),
            "active": True,
            "factory": bool(entity.meta.get("factory_method")),
            "framework": "spring",
            "profiles": [],
        }
        beans.append(entity)
        result_by_entity[id(entity)] = result

    def compatible(bean, requested):
        queue, seen = [bean.meta["bean"]["provided_type"]], set()
        while queue:
            name = queue.pop()
            if name == requested:
                return True
            if name not in seen:
                seen.add(name)
                queue.extend(hierarchy[name])
        return False

    derived, bindings = [], {}
    for result in results:
        for site, ann in _injection_sites(result):
            raw_type = site.meta.get("field_type") or site.meta.get("parameter_type")
            requested = qualified_type(raw_type, result)
            qualifiers = [
                v
                for n, values in ann.items()
                if n in QUALIFIERS
                for v in strings(values.get("value", values.get("name")))
            ]
            qualifiers.extend(
                v
                for n, values in ann.items()
                if n in INJECTION
                for v in strings(values.get("name", values.get("beanName")))
            )
            candidates = scope_candidates(
                [b for b in beans if b.meta["bean"]["active"] and compatible(b, requested)],
                result,
                runtime=True,
            )
            if qualifiers:
                candidates = [
                    b for b in candidates if all(q in b.meta["bean"]["names"] for q in qualifiers)
                ]
            required = {n: values for n, values in ann.items() if n in custom_qualifiers}
            if required:
                candidates = [
                    b
                    for b in candidates
                    if all(
                        annotations(b, result_by_entity[id(b)]).get(n) == values
                        for n, values in required.items()
                    )
                ]
            if len(candidates) > 1:
                primary = [b for b in candidates if b.meta["bean"]["primary"]]
                if len(primary) == 1:
                    candidates = primary
            if len(candidates) > 1:
                named = [
                    b
                    for b in candidates
                    if site.name in b.meta["bean"]["names"]
                    and b.meta["bean"]["framework"] == "spring"
                ]
                if len(named) == 1:
                    candidates = named
            target = candidates[0] if len(candidates) == 1 else None
            meta = {
                "language": "java",
                "derivation": "framework",
                "source_file_path": result.path,
                "source_qualified_name": site.qualified_name,
                "qualifiers": qualifiers,
                "requested_type": requested,
                "candidate_count": len(candidates),
                "resolution_reason": "bean_selection"
                if target
                else ("ambiguous_beans" if candidates else "bean_not_found_or_inactive"),
            }
            if target:
                meta.update(
                    target_qualified_name=target.qualified_name,
                    target_file_path=result_by_entity[id(target)].path,
                )
                bindings[(result.path, site.qualified_name)] = target
            edge = ParsedEdge(
                "INJECTS",
                site.qualified_name,
                requested,
                "resolved" if target else "unresolved",
                site.start_line,
                site.end_line,
                meta=meta,
            )
            derived.append((result, edge))
    _field_bindings(results, bindings)
    derived.extend(_dispatch_edges(results, bindings, all_entities, result_by_entity))
    return derived


def _field_bindings(results, bindings):
    for result in results:
        for method in result.entities:
            if method.type not in {"constructor", "method"}:
                continue
            for flow in method.meta.get("data_flow", []):
                sources = flow.get("sources", [])
                target = flow.get("target", {})
                if (
                    flow.get("operation") == "assign"
                    and target.get("kind") == "field"
                    and len(sources) == 1
                ):
                    bean = bindings.get((result.path, sources[0].get("qualified_name")))
                    if bean:
                        bindings[(result.path, target.get("qualified_name"))] = bean


def _dispatch_edges(results, bindings, entities, result_by_entity):
    for result in results:
        for call in result.edges:
            if call.type != "CALLS":
                continue
            bean = bindings.get((result.path, call.meta.get("receiver_symbol_qualified_name")))
            if bean is None or bean.meta["bean"]["factory"]:
                continue
            methods = [
                m
                for m in entities
                if m.type == "method"
                and m.parent_qualified_name == bean.meta["bean"]["provided_type"]
                and (
                    bean.type == "spring_bean"
                    or result_by_entity[id(m)].path == result_by_entity[id(bean)].path
                )
                and m.name == call.meta.get("method_name")
                and len(m.meta.get("parameter_types", [])) == call.meta.get("argument_count")
            ]
            if len(methods) == 1:
                target = methods[0]
                yield (
                    result,
                    ParsedEdge(
                        "DISPATCHES_TO",
                        call.src_name,
                        target.qualified_name,
                        "resolved",
                        call.src_start_line,
                        call.src_end_line,
                        meta={
                            "language": "java",
                            "derivation": "framework",
                            "source_qualified_name": call.src_name,
                            "target_qualified_name": target.qualified_name,
                            "target_file_path": result_by_entity[id(target)].path,
                            "bean_qualified_name": bean.qualified_name,
                            "resolution_reason": "selected_injected_bean",
                            "dispatch_scope": "configured_candidate",
                        },
                    ),
                )
