"""Generic parameter identities and Java-defined record accessor declarations."""

from core.model import Entity


def type_parameters(context):
    getter = getattr(context, "typeParameters", None)
    parameters = getter() if getter else None
    return (
        [item.identifier().getText() for item in parameters.typeParameter()] if parameters else []
    )


def add_record_accessors(entities, record):
    components = [
        entity
        for entity in entities
        if entity.type == "record_component"
        and entity.parent_qualified_name == record.qualified_name
    ]
    existing = {
        entity.name
        for entity in entities
        if entity.type == "method"
        and entity.parent_qualified_name == record.qualified_name
        and not entity.meta.get("parameter_types")
    }
    for component in components:
        if component.name in existing:
            continue
        entities.append(
            Entity(
                type="method",
                name=component.name,
                start_line=component.start_line,
                end_line=component.end_line,
                parent_name=record.name,
                parent_qualified_name=record.qualified_name,
                qualified_name=f"{record.qualified_name}#{component.name}()",
                meta={
                    **component.meta,
                    "signature": f"{component.name}()",
                    "parameter_types": [],
                    "return_type": component.meta["component_type"],
                    "visibility": "public",
                    "modifiers": ["public"],
                    "synthetic": True,
                    "generated_by": "record",
                    "source_component": component.qualified_name,
                },
            )
        )
