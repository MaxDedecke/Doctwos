"""Code, den ein Eintrag beim Namen nennt: Abgleich der Wörter im Text mit dem Index, ohne LLM.

Gilt für jedes System, weil nur der fertige Text zählt. Vorrang hat die Genauigkeit: Ein gewöhnliches Wort wie
``Realm`` zählt nur mit Paket oder Dateiendung, ein Name in vielen Dateien gar nicht, denn er belegt nichts. Ein
genanntes Paket und eine genannte Datei müssen zum Treffer passen.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html import unescape

from sqlalchemy.orm import Session

from doctus_models.database import CodeEntity, User
from doctus_models.language_profile import role_of
from services.call_flow import TEST_PATH_PATTERN
from services.source_access import source_visible
from services.web_documents.base import CodeRef

MAX_REFS = 15
_MAX_NAMES = 400
_MAX_ROWS = 3000
_MAX_FILES_PER_NAME = 3
_MIN_NAME_LENGTH = 6

_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"[A-Za-z_$][\w$-]*(?:[./#][A-Za-z_$][\w$-]*)*")
_INNER_CAPITAL_RE = re.compile(r"[a-z0-9][A-Z]")
_CODE_LIKE_UPPER_RE = re.compile(r"[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+|[A-Z]+[0-9][A-Z0-9]*")
_TICKET_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*-\d+")
_FILE_SUFFIX_RE = re.compile(
    r"\.(?:java|cbl|cob|cpy|jcl|proc|xml|xsd|sql|py|ts|tsx|js|sh|kt|groovy)$", re.I
)
_PACKAGE_RE = re.compile(r"(?:[a-z_][a-z0-9_]*\.){2,}")


def _is_distinctive(word: str) -> bool:
    if len(word) < _MIN_NAME_LENGTH or _TICKET_KEY_RE.fullmatch(word):
        return False
    return bool(_INNER_CAPITAL_RE.search(word) or _CODE_LIKE_UPPER_RE.fullmatch(word))


@dataclass
class _Named:
    """Wie ein Name im Text vorkommt; davon hängt ab, welches Objekt er meinen kann."""

    bare: int = 0
    packages: Counter = field(default_factory=Counter)
    as_file: int = 0

    def mentions_of(self, name: str, qualified_name: str, file_path: str) -> int:
        count = self.bare + sum(n for pkg, n in self.packages.items() if pkg in qualified_name)
        return count + (self.as_file if _file_stem(file_path) == name else 0)


def _file_stem(file_path: str) -> str:
    return file_path.rsplit("/", 1)[-1].split(".", 1)[0]


def scan_names(text: str) -> dict[str, _Named]:
    names: dict[str, _Named] = defaultdict(_Named)
    for token in _TOKEN_RE.findall(text):
        if _FILE_SUFFIX_RE.search(token):
            stem = re.split(r"[./#]", _FILE_SUFFIX_RE.sub("", token))[-1]
            names[stem].as_file += 1
            continue
        parts = re.split(r"[./#]", token)
        package = _PACKAGE_RE.match(token)
        for word in parts:
            if not _is_distinctive(word) and not (
                package and word == parts[-1] and word[:1].isupper()
            ):
                continue
            if package:
                # Ein fremdes Paket (etwa im Stacktrace) meint nicht das gleichnamige Objekt im Projekt.
                names[word].packages[package.group(0).rstrip(".")] += 1
            else:
                names[word].bare += 1
    return names


def _plain_text(*parts: str) -> str:
    return unescape(_TAG_RE.sub(" ", " ".join(parts)))


def find_code_refs(
    db: Session, user: User, project_id: int | None, title: str, htmls: list[str]
) -> list[CodeRef]:
    if project_id is None:
        return []
    names = scan_names(_plain_text(title, *htmls))
    if not names:
        return []
    wanted = sorted(names, key=lambda name: names[name].bare + names[name].as_file, reverse=True)
    rows = (
        db.query(
            CodeEntity.id,
            CodeEntity.name,
            CodeEntity.qualified_name,
            CodeEntity.type,
            CodeEntity.file_path,
            CodeEntity.start_line,
            CodeEntity.source_id,
        )
        .filter(CodeEntity.project_id == project_id, CodeEntity.name.in_(wanted[:_MAX_NAMES]))
        .limit(_MAX_ROWS)
        .all()
    )
    by_name: dict[str, list] = defaultdict(list)
    counts: dict[int, int] = {}
    for row in rows:
        # Code ist eine Einheit, eine Routine oder eine Datei unter eigenem Namen (etwa ein Copybook),
        # nicht jeder Eintrag im Index: Dokumentabschnitte und Build-Angaben tragen auch Namen.
        path = row.file_path or ""
        if role_of(row.type) in ("container", "routine") or _file_stem(path) == row.name:
            counts[row.id] = names[row.name].mentions_of(row.name, row.qualified_name or "", path)
            if counts[row.id]:
                by_name[row.name].append(row)

    visible: dict[int | None, bool] = {}
    refs: list[tuple[int, int, CodeRef]] = []
    for name, entities in by_name.items():
        production = [e for e in entities if not re.search(TEST_PATH_PATTERN, e.file_path or "")]
        entities = production or entities
        if len({e.file_path for e in entities}) > _MAX_FILES_PER_NAME:
            continue
        # Aus Überladungen derselben Datei wird ein Eintrag; die Einheit geht ihren Routinen vor.
        rank = {"container": 0, "routine": 2}
        by_file: dict[str, object] = {}
        for entity in sorted(
            entities, key=lambda e: (rank.get(role_of(e.type), 1), e.start_line or 0)
        ):
            by_file.setdefault(entity.file_path, entity)
        for entity in by_file.values():
            if entity.source_id not in visible:
                visible[entity.source_id] = source_visible(db, user, entity.source_id)
            if visible[entity.source_id]:
                refs.append(
                    (
                        rank.get(role_of(entity.type), 1),
                        -counts[entity.id],
                        CodeRef(
                            entity_id=entity.id,
                            name=entity.name,
                            type=entity.type,
                            file_path=entity.file_path,
                            start_line=entity.start_line,
                            source_id=entity.source_id,
                            cite=f"{entity.file_path}:{entity.start_line or 0}",
                            mentions=counts[entity.id],
                        ),
                    )
                )
    refs.sort(key=lambda item: (item[0], item[1], item[2].name))
    return [item[2] for item in refs[:MAX_REFS]]
