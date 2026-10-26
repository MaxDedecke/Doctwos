"""Finish source relationship resolution and stabilize incremental analysis inputs."""

import asyncio


async def finalize_source(connector, resolve_edges, read_dependencies):
    resolved = await asyncio.to_thread(resolve_edges, connector.db, connector.source_id)
    fingerprints = getattr(connector, "_dependency_fingerprints", None)
    if fingerprints is not None:
        await asyncio.to_thread(
            fingerprints.persist_discovered, connector.db, connector.source_id, read_dependencies
        )
    if resolved:
        connector._log(f"Beziehungsauflösung: {resolved} Beziehung(en) aufgelöst.")
