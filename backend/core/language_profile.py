"""Language-neutral roles of entity and edge types (CLAUDE.md, "MCP-Ziel: Antworten in O(1) Schritten").

The evidence blocks of the MCP server (includes, control flow, data origin) never name ``COPY``, ``PERFORM``,
``data_item`` or ``IMPORTS``: they ask this profile which entity types are containers, routines or data, and which
edge types include other units or transfer control. A new language is one entry here plus a parser that follows the
parser contract (``docs/ENTSCHEIDUNGEN.md`` E-15); the server needs no new code for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["container", "routine", "data"]


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    containers: frozenset[str]  # units that hold routines: program, class, job
    routines: frozenset[str]  # units of execution: paragraph, method, step
    data: frozenset[str]  # units that hold values: data item, field, dataset
    control_edges: frozenset[str]  # transfer of control between routines
    include_edges: frozenset[str]  # a unit includes, imports or extends another one


COBOL = LanguageProfile(
    name="cobol",
    containers=frozenset({"program", "cobol_program"}),
    routines=frozenset({"paragraph", "section"}),
    data=frozenset({"data_item", "file_fd", "sql_table"}),
    control_edges=frozenset({"PERFORM", "CALL", "GOTO"}),
    include_edges=frozenset({"COPY", "INCLUDES"}),
)
JAVA = LanguageProfile(
    name="java",
    containers=frozenset({"class", "interface", "enum", "record", "annotation_type", "anonymous_class"}),
    routines=frozenset({"method", "constructor", "lambda", "initializer"}),
    data=frozenset({"field", "local_variable", "parameter", "record_component"}),
    control_edges=frozenset({"CALLS"}),
    include_edges=frozenset({"IMPORTS", "EXTENDS", "IMPLEMENTS"}),
)
JCL = LanguageProfile(
    name="jcl",
    containers=frozenset({"jcl_job", "jcl_proc"}),
    routines=frozenset({"jcl_step"}),
    data=frozenset({"jcl_dataset", "jcl_file"}),
    control_edges=frozenset({"EXECUTES"}),
    include_edges=frozenset(),
)

# Use of values and types (reads, writes, dataset use, type use); the "data" kind of the drop view.
DATA_EDGES = frozenset({"READS", "WRITES", "USES", "USES_DATASET", "ASSIGNED_DATASET", "USES_TYPE", "INSTANTIATES"})

PROFILES: tuple[LanguageProfile, ...] = (COBOL, JAVA, JCL)

CONTROL_EDGES = frozenset().union(*(profile.control_edges for profile in PROFILES))
INCLUDE_EDGES = frozenset().union(*(profile.include_edges for profile in PROFILES))
ROUTINE_TYPES = frozenset().union(*(profile.routines for profile in PROFILES))
CONTAINER_TYPES = frozenset().union(*(profile.containers for profile in PROFILES))
DATA_TYPES = frozenset().union(*(profile.data for profile in PROFILES))


def profile_of(entity_type: str | None) -> LanguageProfile | None:
    for profile in PROFILES:
        if entity_type in profile.containers | profile.routines | profile.data:
            return profile
    return None


def role_of(entity_type: str | None) -> Role | None:
    profile = profile_of(entity_type)
    if profile is None:
        return None
    if entity_type in profile.containers:
        return "container"
    if entity_type in profile.routines:
        return "routine"
    return "data"
