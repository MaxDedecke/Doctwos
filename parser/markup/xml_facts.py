"""Namespace-aware XML facts with Expat's physical element line ranges."""

from xml.parsers import expat


def xml_facts(source):
    parser = expat.ParserCreate(namespace_separator="}")
    facts, stack, namespaces = [], [], [{}]
    pending = {}

    def namespace(prefix, uri):
        pending[prefix or ""] = uri

    def start(tag, attributes):
        context = {**namespaces[-1], **pending}
        pending.clear()
        namespaces.append(context)
        fact = {
            "tag": tag,
            "local": tag.rsplit("}", 1)[-1],
            "attrs": attributes,
            "namespaces": context,
            "start_line": parser.CurrentLineNumber,
            "end_line": parser.CurrentLineNumber,
            "parent": stack[-1] if stack else None,
        }
        facts.append(fact)
        stack.append(len(facts) - 1)

    def end(tag):
        facts[stack.pop()]["end_line"] = parser.CurrentLineNumber
        namespaces.pop()

    def reject(*args):
        raise ValueError("XML entity/DTD declarations are not supported")

    parser.StartNamespaceDeclHandler = namespace
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.Parse(source, True)
    return facts


def qname(value, namespaces, default_namespace=""):
    if ":" in value:
        prefix, local = value.split(":", 1)
        namespace = namespaces.get(prefix)
        return "{" + namespace + "}" + local if namespace is not None else None
    return "{" + namespaces.get("", default_namespace) + "}" + value
