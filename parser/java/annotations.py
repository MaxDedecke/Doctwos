"""Source-backed annotation names and literal values; expressions remain unknown."""

import json
import re

KNOWN = {
    "org.springframework.stereotype": ["Component", "Service", "Repository", "Controller"],
    "org.springframework.beans.factory.annotation": ["Autowired", "Qualifier", "Value"],
    "org.springframework.context.annotation": [
        "Bean",
        "Configuration",
        "Primary",
        "Profile",
        "Scope",
    ],
    "org.springframework.web.bind.annotation": [
        "RestController",
        "RequestMapping",
        "GetMapping",
        "PostMapping",
        "PutMapping",
        "DeleteMapping",
        "PatchMapping",
        "PathVariable",
        "RequestParam",
        "RequestBody",
    ],
    "org.springframework.ws.server.endpoint.annotation": [
        "Endpoint",
        "PayloadRoot",
        "RequestPayload",
        "ResponsePayload",
    ],
}
for prefix in ("jakarta", "javax"):
    for package, names in {
        "inject": ["Inject", "Named", "Singleton", "Qualifier"],
        "enterprise.context": ["ApplicationScoped", "RequestScoped", "SessionScoped", "Dependent"],
        "enterprise.inject": ["Produces", "Alternative"],
        "ejb": ["EJB", "Stateless", "Stateful", "Singleton"],
        "annotation": ["Resource"],
        "jws": ["WebService", "WebMethod", "WebParam", "WebResult"],
        "ws.rs": [
            "Path",
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
            "HEAD",
            "OPTIONS",
            "Produces",
            "Consumes",
            "ApplicationPath",
        ],
        "xml.bind.annotation": [
            "XmlRootElement",
            "XmlType",
            "XmlElement",
            "XmlAttribute",
            "XmlElementRef",
            "XmlAccessorType",
            "XmlSchema",
        ],
    }.items():
        KNOWN[prefix + "." + package] = names


def strings(raw):
    if raw is None:
        return []
    text = raw.strip()
    if text.startswith("{") and text.endswith("}"):
        values = re.findall(r'"(?:[^"\\]|\\.)*"', text)
        if re.sub(r'"(?:[^"\\]|\\.)*"|[,\s]', "", text[1:-1]):
            return []
    else:
        values = [text]
    try:
        decoded = [json.loads(v) for v in values]
        return decoded if all(isinstance(v, str) for v in decoded) else []
    except (ValueError, TypeError):
        return []


def annotations(entity, result):
    imports = [e.dst_name for e in result.edges if e.type == "IMPORTS" and not e.meta.get("static")]
    explicit = {name.rsplit(".", 1)[-1]: name for name in imports if not name.endswith(".*")}
    wildcards = [name[:-1] for name in imports if name.endswith(".*")]
    found = {}
    for annotation in entity.meta.get("annotation_details", []):
        name = annotation["name"]
        if "." not in name:
            candidates = [
                prefix + name for prefix in wildcards if name in KNOWN.get(prefix[:-1], [])
            ]
            name = explicit.get(name) or (candidates[0] if len(candidates) == 1 else name)
        found[name] = annotation.get("values", {})
    return found


def matching(entity, result, names):
    return {
        name.rsplit(".", 1)[-1]: values
        for name, values in annotations(entity, result).items()
        if name in names
    }


def qualified_type(raw, result):
    name = re.sub(r"<.*>", "", raw or "").replace("[]", "").strip()
    if "." in name:
        return name
    for edge in result.edges:
        if edge.type == "IMPORTS" and edge.dst_name.endswith("." + name):
            return edge.dst_name
    package = next((e.name for e in result.entities if e.type == "package"), "")
    return package + "." + name if package else name


def namespaced(names, packages):
    return {package + "." + name for package in packages for name in names}
