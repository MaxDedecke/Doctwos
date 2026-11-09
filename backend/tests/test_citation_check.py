"""Zitate nicht gelesener Stellen gegen den Quelltext prüfen (Katalogtest 08.11.2026: J2, J3, C2)."""

import pytest

from services.citation_check import ToolEvidence

_LOGIC = "core/idrepo/logic/src/main/java/org/apache/syncope/core/logic/AbstractUserLogic.java"
_UR = "common/idrepo/lib/src/main/java/org/apache/syncope/common/lib/request/UserUR.java"


@pytest.fixture
def repository(monkeypatch, tmp_path):
    logic = (
        ["// header"] * 120
        + [
            "    protected ProvisioningResult<UserTO> doUpdate(UserUR userUR, boolean self) {",
            "        Set<String> realms = RealmUtils.getEffective(authRealms, before.getRealm());",
            "        userDAO.securityChecks(realms, before.getKey(), before.getRealm(), groups);",
            "        provisioningManager.update(userUR, nullPriorityAsync, updater, REST_CONTEXT);",
        ]
        + ["// tail"] * 20
    )
    files = {
        _LOGIC: logic,
        _UR: ["// line"] * 103 + ["    private StringReplacePatchItem username;"] + ["}"] * 5,
    }
    for path, lines in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True)
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        "services.agent_repo_tools.get_repo_path",
        lambda _repo_id, file_path="": str(tmp_path / file_path) if file_path else str(tmp_path),
    )


def _evidence(read_lines=(121, 121)):
    evidence = ToolEvidence(repository_id=4)
    evidence.sources.append({"file": _LOGIC, "lines": list(read_lines), "source_id": 4})
    return evidence


def test_an_existing_unread_line_that_matches_its_sentence_becomes_a_source(repository):
    evidence = _evidence()
    answer = (
        f"`doUpdate` lädt den Benutzer (`{_LOGIC}:121`). Danach wird `provisioningManager.update` "
        f"aufgerufen (`{_LOGIC}:124`)."
    )

    text, consistent = evidence.validate(answer, [], "")

    assert consistent and "nicht belegt" not in text
    assert {"file": _LOGIC, "lines": [124, 124], "source_id": 4} in evidence.sources


def test_an_invented_path_is_corrected_to_the_one_file_of_the_same_package(repository):
    invented = "core/idrepo/logic/src/main/java/org/apache/syncope/common/lib/request/UserUR.java"
    answer = f"`doUpdate` beginnt hier (`{_LOGIC}:121`). `UserUR` trägt den Namenspatch (`{invented}:104`)."

    text, consistent = _evidence().validate(answer, [], "")

    assert consistent
    assert f"`{_UR}:104`" in text and invented not in text


def test_a_path_that_exists_nowhere_is_removed_from_the_answer(repository):
    answer = f"`doUpdate` beginnt hier (`{_LOGIC}:121`). Siehe auch (`core/Missing/Ghost.java:12`)."

    text, consistent = _evidence().validate(answer, [], "")

    assert consistent
    assert "core/Missing/Ghost.java" not in text
    assert "Ghost.java (Fundstelle im Repository nicht gefunden)" in text


def test_a_call_shown_by_the_cited_source_is_marked_as_source_evidence_not_as_unproven(repository):
    answer = (
        f"`doUpdate` beginnt hier (`{_LOGIC}:121`).\n"
        f"- Die Methode ruft `userDAO.securityChecks` mit den Realms auf. `{_LOGIC}:123`\n"
        f"- Danach ruft sie `ghostService.purge` auf. `{_LOGIC}:121`"
    )

    text, consistent = _evidence((121, 124)).validate(answer, [], "")

    assert consistent
    assert (
        "`userDAO.securityChecks` mit den Realms auf (im Quelltext belegt, keine Index-Kante)"
        in text
    )
    assert "`ghostService.purge` auf (Beziehung nicht belegt)" in text


def test_an_answer_whose_only_citation_is_invented_is_still_rejected(repository):
    text, consistent = _evidence().validate("Siehe `core/Missing/Ghost.java:12`.", [], "")

    assert not consistent and "Ghost.java" not in text


def test_a_citation_by_file_name_alone_resolves_to_the_one_file_of_that_name(repository):
    answer = (
        f"`doUpdate` beginnt hier (`{_LOGIC}:121`). `UserUR` trägt den Namen (`UserUR.java:104`)."
    )

    text, consistent = _evidence().validate(answer, [], "")

    assert consistent and "`UserUR.java:104`" in text and "nicht" not in text
