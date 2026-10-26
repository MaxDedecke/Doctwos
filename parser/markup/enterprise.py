"""Spring XML bean declarations and configuration-to-Java references."""

from core.model import Entity, ParsedEdge
from .xml_facts import xml_facts

SPRING_BEANS = "http://www.springframework.org/schema/beans}"


def add_enterprise_xml(result, source, *, facts=None):
    facts = xml_facts(source) if facts is None else facts
    root = result.entities[0]
    beans = {}
    for index, fact in enumerate(facts):
        if fact["tag"] != SPRING_BEANS + "bean":
            continue
        attrs = fact["attrs"]
        names = [attrs.get("id")] if attrs.get("id") else []
        names += attrs.get("name", "").replace(",", " ").replace(";", " ").split()
        implementation = attrs.get("class")
        name = next(iter(names), implementation or f"bean:{fact['start_line']}")
        qname = f"{result.path}::bean:{name}:{index}"
        entity = Entity(
            "spring_bean",
            name,
            fact["start_line"],
            fact["end_line"],
            parent_name=root.name,
            parent_qualified_name=root.qualified_name,
            qualified_name=qname,
            meta={
                "language": "xml",
                "bean_class": implementation,
                "bean_names": names,
                "scope": attrs.get("scope", "singleton"),
                "primary": attrs.get("primary") == "true",
                "factory_method": attrs.get("factory-method"),
                "factory_bean": attrs.get("factory-bean"),
            },
        )
        result.entities.append(entity)
        beans[index] = entity
        if implementation:
            result.edges.append(
                ParsedEdge(
                    "CONFIGURES",
                    qname,
                    implementation,
                    "unresolved",
                    fact["start_line"],
                    fact["start_line"],
                    meta={
                        "language": "xml",
                        "source_qualified_name": qname,
                        "requested_java_type": implementation,
                    },
                )
            )
    for fact in facts:
        bean = beans.get(fact["parent"])
        if bean is None or fact["local"] not in {"property", "constructor-arg"}:
            continue
        reference = fact["attrs"].get("ref")
        if reference:
            result.edges.append(
                ParsedEdge(
                    "INJECTS",
                    bean.qualified_name,
                    reference,
                    "unresolved",
                    fact["start_line"],
                    fact["end_line"],
                    meta={
                        "language": "xml",
                        "source_qualified_name": bean.qualified_name,
                        "bean_reference": reference,
                        "property_name": fact["attrs"].get("name"),
                        "parameter_index": fact["attrs"].get("index"),
                    },
                )
            )
