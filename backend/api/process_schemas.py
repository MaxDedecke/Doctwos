"""Versionierter, sprachneutraler Vertrag der Process View (O-291).

Der Vertrag ist absichtlich von der späteren Traversierung getrennt: O-292
liefert eine begrenzte Projektion, O-293/O-294 ordnen Parserkanten den
Prozessarten zu.  Damit können beide Implementierungen dieselbe Antwortform
erzeugen, ohne die Prozesssemantik im Frontend zu duplizieren.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProcessNodeKind = Literal[
    "step", "call", "branch", "jump", "iteration", "data_access",
    "external_call", "entry", "exit",
]
ProcessTransitionKind = ProcessNodeKind
ProcessCertainty = Literal["certain", "possible", "unresolved"]
ProcessOriginKind = Literal["code_edge", "synthetic"]


class ProcessLocator(BaseModel):
    """A physical source location that can be opened by the client."""

    model_config = ConfigDict(extra="forbid")

    source_id: int | None = None
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)
    provenance: dict[str, Any] | None = None

    @model_validator(mode="after")
    def end_is_not_before_start(self):
        if self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line must not precede start_line")
        return self


class ProcessNode(BaseModel):
    """A visible step in a projection, including unresolved external targets."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ProcessNodeKind
    label: str
    language: str
    locator: ProcessLocator
    entity_id: int | None = None
    # Only parser-observed ordering is serialized. None explicitly means that
    # the graph did not establish an order for this node.
    sequence: int | None = Field(default=None, ge=0)
    condition: str | None = None


class ProcessTransition(BaseModel):
    """A directed, evidence-backed relationship between process nodes."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    kind: ProcessTransitionKind
    certainty: ProcessCertainty
    resolution: Literal["resolved", "dynamic", "unresolved"]
    locator: ProcessLocator
    origin_kind: ProcessOriginKind
    code_edge_ids: list[int] = Field(default_factory=list)
    code_edge_types: list[str] = Field(default_factory=list)
    # As with ProcessNode.sequence, this is omitted when the parser only knows
    # that a relationship exists, not its runtime order.
    sequence: int | None = Field(default=None, ge=0)
    condition: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_code_edge_provenance(self):
        if self.origin_kind == "code_edge" and (
            not self.code_edge_ids or not self.code_edge_types
        ):
            raise ValueError("code_edge transitions require edge IDs and edge types")
        if self.origin_kind == "synthetic" and (
            self.code_edge_ids or self.code_edge_types
        ):
            raise ValueError("synthetic transitions must not claim CodeEdge provenance")
        return self


class ProcessTruncation(BaseModel):
    """Limits actually applied by the server and their visible consequences."""

    model_config = ConfigDict(extra="forbid")

    truncated: bool = False
    node_limit: int = Field(ge=1)
    edge_limit: int = Field(ge=1)
    omitted_node_count: int = Field(default=0, ge=0)
    omitted_transition_count: int = Field(default=0, ge=0)
    reasons: list[str] = Field(default_factory=list)


class ProcessProjection(BaseModel):
    """The complete payload contract for one bounded Process View focus."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    projection_id: str
    project_id: int | None = None
    root_node_id: str
    direction: Literal["outgoing", "incoming", "both"]
    hops: int = Field(ge=0)
    nodes: list[ProcessNode]
    transitions: list[ProcessTransition]
    truncation: ProcessTruncation

    @model_validator(mode="after")
    def validate_graph_references(self):
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("process node IDs must be unique")
        if self.root_node_id not in set(node_ids):
            raise ValueError("root_node_id must identify a node in the projection")
        transition_ids = [transition.id for transition in self.transitions]
        if len(transition_ids) != len(set(transition_ids)):
            raise ValueError("process transition IDs must be unique")
        unknown_endpoints = {
            endpoint
            for transition in self.transitions
            for endpoint in (transition.source, transition.target)
            if endpoint not in set(node_ids)
        }
        if unknown_endpoints:
            raise ValueError("process transitions must reference nodes in the projection")
        return self
