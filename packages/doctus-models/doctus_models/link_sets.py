"""Mengen eines Link-Laufs: welche Objekte der Wissensbasis gegeneinander geprüft werden.

Ein Lauf prüft Menge A gegen Menge B. Eine Menge hat eine Art (``code`` = Code-Entitäten, ``docs`` =
Dokumentations-Abschnitte) und ist entweder ``all`` (alles dieser Art im Projekt) oder ``custom``: die Vereinigung
aus Facetten-Treffern und explizit gewählten Objekten. Mehrere Facetten verknüpfen sich mit UND, die Werte einer
Facette mit ODER (wie in einer Facettensuche). Eine eigene Auswahl darf leer sein; dann prüft der Lauf nichts.

Erweitern, ohne Backend- und Parser-Code anzufassen, der Mengen nur benutzt:
- neue Facette: Eintrag in ``FACETS`` (Bedingung) und in ``backend/services/link_set_options.py`` (Werte);
- neue Objektart: Eintrag in ``ITEM_KINDS`` (Schlüsselfelder) und ``_ITEM_CONDITIONS`` (Bedingung);
- neue Paarung: Eintrag in ``PAIRINGS``; der zugehörige Lauf liest Menge A und B über ``set_condition``.
Backend und Parser lesen dasselbe Format aus ``LinkBuilderRun.scope_json["sets"]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import and_, false, or_, select, tuple_

from doctus_models.database import CodeEntity, DocumentChunk, KnowledgeSource

CODE = "code"
DOCS = "docs"
KINDS = (CODE, DOCS)
MODE_ALL = "all"
MODE_CUSTOM = "custom"

MAX_FACET_VALUES = 200
MAX_ITEMS = 500
MAX_LABEL = 200

# Dokumentations-Entitäten sind nie die Code-Seite eines Laufs (parser/core/doc_resolution.py).
DOC_ENTITY_TYPES = frozenset({"asciidoc_document", "doc_section"})
DOC_LANGUAGES = ("asciidoc", "markdown", "text")


@dataclass(frozen=True)
class Pairing:
    key: str
    a: str
    b: str
    task_type: str  # LinkBuilderRun.task_type des Laufs
    admin_only: bool = False


PAIRINGS: tuple[Pairing, ...] = (
    Pairing("code_docs", CODE, DOCS, "entity_links"),
    Pairing("docs_docs", DOCS, DOCS, "knowledge_links", admin_only=True),
)


def pairing(key: str | None) -> Pairing | None:
    return next((item for item in PAIRINGS if item.key == key), None)


def _ints(values) -> list[int]:
    result = []
    for value in values:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


# Facette -> Bedingung über die Werte (immer als Zeichenketten gespeichert).
FACETS: dict[str, dict[str, Callable[[tuple[str, ...]], Any]]] = {
    CODE: {
        "entity_type": lambda values: CodeEntity.type.in_(values),
        "source": lambda values: CodeEntity.source_id.in_(_ints(values)),
    },
    DOCS: {
        "source": lambda values: DocumentChunk.source_id.in_(_ints(values)),
        "source_type": lambda values: DocumentChunk.source_id.in_(
            select(KnowledgeSource.id).where(KnowledgeSource.type.in_(values))
        ),
    },
}

# Objektart -> Schlüsselfelder in der gespeicherten Form, je Mengenart.
ITEM_KINDS: dict[str, dict[str, tuple[tuple[str, type], ...]]] = {
    CODE: {"entity": (("id", int),)},
    DOCS: {"document": (("source_id", int), ("file_path", str))},
}

_ITEM_CONDITIONS: dict[str, dict[str, Callable[[list[tuple]], Any]]] = {
    CODE: {"entity": lambda keys: CodeEntity.id.in_([key[0] for key in keys])},
    DOCS: {
        "document": lambda keys: tuple_(DocumentChunk.source_id, DocumentChunk.file_path).in_(keys)
    },
}


@dataclass(frozen=True)
class LinkItem:
    kind: str
    key: tuple
    label: str = ""
    detail: str = ""

    def to_json(self, kind_of_set: str) -> dict:
        fields = ITEM_KINDS[kind_of_set][self.kind]
        data = {"kind": self.kind, **{name: value for (name, _), value in zip(fields, self.key)}}
        if self.label:
            data["label"] = self.label
        if self.detail:
            data["detail"] = self.detail
        return data


@dataclass(frozen=True)
class LinkSet:
    kind: str
    mode: str = MODE_ALL
    facets: tuple[tuple[str, tuple[str, ...]], ...] = ()
    items: tuple[LinkItem, ...] = field(default=())

    @property
    def everything(self) -> bool:
        return self.mode == MODE_ALL

    @property
    def is_empty(self) -> bool:
        return not self.everything and not self.facets and not self.items

    def facet(self, name: str) -> tuple[str, ...]:
        return dict(self.facets).get(name, ())

    def item_keys(self, kind: str) -> list[tuple]:
        return [item.key for item in self.items if item.kind == kind]

    def to_json(self) -> dict:
        data: dict = {"kind": self.kind, "mode": self.mode}
        if not self.everything:
            data["facets"] = {name: list(values) for name, values in self.facets}
            data["items"] = [item.to_json(self.kind) for item in self.items]
        return data

    @classmethod
    def everything_of(cls, kind: str) -> "LinkSet":
        return cls(kind=kind)

    @classmethod
    def from_json(cls, raw: Any, kind: str | None = None) -> "LinkSet":
        """Prüft und normalisiert eine Menge; ``ValueError`` bei Unbekanntem oder zu Großem."""
        if not isinstance(raw, dict):
            raise ValueError("Menge muss ein Objekt sein")
        set_kind = raw.get("kind") or kind
        if set_kind not in KINDS or (kind is not None and set_kind != kind):
            raise ValueError(f"Unbekannte oder falsche Mengenart: {set_kind!r}")
        mode = raw.get("mode") or MODE_ALL
        if mode not in (MODE_ALL, MODE_CUSTOM):
            raise ValueError(f"Unbekannter Modus: {mode!r}")
        if mode == MODE_ALL:
            return cls(kind=set_kind)

        facets = []
        for name, values in sorted((raw.get("facets") or {}).items()):
            if name not in FACETS[set_kind]:
                raise ValueError(f"Unbekannte Facette {name!r} für {set_kind}")
            normalized = sorted(
                {str(value).strip() for value in values or [] if str(value).strip()}
            )
            if len(normalized) > MAX_FACET_VALUES:
                raise ValueError(f"Zu viele Werte in Facette {name!r}")
            if name == "entity_type" and DOC_ENTITY_TYPES.intersection(normalized):
                raise ValueError("Dokumentations-Typen gehören nicht in eine Code-Menge")
            if normalized:
                facets.append((name, tuple(normalized)))

        items: dict[tuple, LinkItem] = {}
        for entry in raw.get("items") or []:
            if not isinstance(entry, dict) or entry.get("kind") not in ITEM_KINDS[set_kind]:
                raise ValueError("Unbekannte Objektart in der Menge")
            fields = ITEM_KINDS[set_kind][entry["kind"]]
            try:
                key = tuple(cast(entry[name]) for name, cast in fields)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("Unvollständiges Objekt in der Menge") from error
            items[(entry["kind"], key)] = LinkItem(
                entry["kind"],
                key,
                str(entry.get("label") or "")[:MAX_LABEL],
                str(entry.get("detail") or "")[:MAX_LABEL],
            )
        if len(items) > MAX_ITEMS:
            raise ValueError(f"Höchstens {MAX_ITEMS} Objekte je Menge")
        ordered = tuple(
            items[key] for key in sorted(items, key=lambda k: (k[0], tuple(map(str, k[1]))))
        )
        return cls(kind=set_kind, mode=MODE_CUSTOM, facets=tuple(facets), items=ordered)


def set_condition(link_set: LinkSet):
    """SQL-Bedingung über ``CodeEntity`` bzw. ``DocumentChunk``; ``None`` heißt: keine Einschränkung."""
    if link_set.everything:
        return None
    parts = []
    facet_conditions = [FACETS[link_set.kind][name](values) for name, values in link_set.facets]
    if facet_conditions:
        parts.append(and_(*facet_conditions))
    for item_kind, condition in _ITEM_CONDITIONS[link_set.kind].items():
        keys = link_set.item_keys(item_kind)
        if keys:
            parts.append(condition(keys))
    return or_(*parts) if parts else false()


def documentation_condition():
    """Nur Dokumentation: Inhalte nicht-Git-Quellen sowie Doku-Dateien (AsciiDoc/Markdown/Text) in Git-Quellen.

    Quellcode-Abschnitte einer Git-Quelle sind der Code selbst; Code-zu-Code-Beziehungen gehören in den Aufrufgraphen.
    """
    non_git = DocumentChunk.source_id.in_(
        select(KnowledgeSource.id).where(KnowledgeSource.type != "Git")
    )
    doc_language = DocumentChunk.metadata_json["language"].as_string().in_(DOC_LANGUAGES)
    return or_(non_git, doc_language)


def code_scope(project_id: int, link_set: LinkSet) -> list:
    """Bedingungen der Code-Seite in einem Projekt."""
    conditions = [CodeEntity.project_id == project_id, CodeEntity.type.notin_(DOC_ENTITY_TYPES)]
    condition = set_condition(link_set)
    if condition is not None:
        conditions.append(condition)
    return conditions


def docs_scope(project_id: int, link_set: LinkSet) -> list:
    """Bedingungen der Dokumentationsseite in einem Projekt (ohne Embedding-Filter)."""
    conditions = [
        DocumentChunk.project_id == project_id,
        DocumentChunk.source_id.isnot(None),
        documentation_condition(),
    ]
    condition = set_condition(link_set)
    if condition is not None:
        conditions.append(condition)
    return conditions


@dataclass(frozen=True)
class RunSets:
    """Menge A und B eines Laufs; ohne Angabe beider: alles gegen alles (früheres Verhalten)."""

    pairing: Pairing
    a: LinkSet
    b: LinkSet

    @property
    def targeted(self) -> bool:
        return not (self.a.everything and self.b.everything)

    def to_json(self) -> dict:
        return {"pairing": self.pairing.key, "a": self.a.to_json(), "b": self.b.to_json()}

    @classmethod
    def from_json(cls, raw: Any, default_pairing: str = "code_docs") -> "RunSets":
        raw = raw if isinstance(raw, dict) else {}
        selected = pairing(raw.get("pairing") or default_pairing)
        if selected is None:
            raise ValueError(f"Unbekannte Analyseart: {raw.get('pairing')!r}")
        a = LinkSet.from_json(raw["a"], selected.a) if raw.get("a") else LinkSet(selected.a)
        b = LinkSet.from_json(raw["b"], selected.b) if raw.get("b") else LinkSet(selected.b)
        return cls(selected, a, b)

    @classmethod
    def from_scope(cls, scope: dict | None, default_pairing: str = "code_docs") -> "RunSets":
        """Mengen eines gespeicherten Laufs. Ohne ``sets`` alles gegen alles; unlesbare Mengen sind ein Fehler
        (``ValueError``), damit ein eingeschränkter Lauf nie unbemerkt den ganzen Bestand prüft."""
        return cls.from_json((scope or {}).get("sets"), default_pairing)
