"""O-375: Systemziele, die per Definition nicht im Repository liegen.

CICS-/MQ-/DB2-Copybooks, Language-Environment-/IMS-/MQ-Routinen und IBM-
Utilities sind keine Indexlücken. Sie bleiben `unresolved` (kein Ziel im Index),
tragen aber `meta["external"]`, damit „unaufgelöst“ nur echte Lücken meint.
"""

from __future__ import annotations

_COPY_PREFIXES = (("DFH", "cics"), ("CMQ", "mq"))
_COPY_NAMES = {"SQLCA": "db2", "SQLDA": "db2"}
_CALL_PREFIXES = (("CEE", "language_environment"), ("IGZ", "language_environment"), ("ILBO", "language_environment"))
_CALL_NAMES = {
    **dict.fromkeys(("CBLTDLI", "AIBTDLI", "PLITDLI", "ASMTDLI", "DFSRRC00"), "ims"),
    **dict.fromkeys(
        ("MQCONN", "MQCONNX", "MQDISC", "MQOPEN", "MQCLOSE", "MQPUT", "MQPUT1", "MQGET",
         "MQINQ", "MQSET", "MQBEGIN", "MQCMIT", "MQBACK"), "mq"),
    **dict.fromkeys(("DSNALI", "DSNRLI", "DSNCLI", "DSNTIAR"), "db2"),
}
_UTILITIES = frozenset({
    "IEBGENER", "IEBCOPY", "IEBCOMPR", "IEBUPDTE", "IEFBR14", "IDCAMS", "SORT", "ICEMAN",
    "DFSORT", "ICETOOL", "IKJEFT01", "IKJEFT1B", "IEWL", "IEWBLINK", "HEWL", "ADRDSSU",
    "SDSF", "IGYCRCTL",
})


def classify_external(edge_type: str, dst_name: str, language: str | None) -> dict | None:
    """`{"category": ..., "kind": ...}` für ein bekanntes Systemziel, sonst None."""
    name = (dst_name or "").strip().upper()
    # CALL/COPY gibt es nur in COBOL und tragen kein `language`-Meta (Java nutzt CALLS).
    if not name or language not in {None, "cobol", "copybook", "jcl"}:
        return None
    if edge_type == "COPY":
        category = _COPY_NAMES.get(name) or next((c for p, c in _COPY_PREFIXES if name.startswith(p)), None)
        return {"category": category, "kind": "system_copybook"} if category else None
    if edge_type == "CALL":
        category = _CALL_NAMES.get(name) or next((c for p, c in _CALL_PREFIXES if name.startswith(p)), None)
        return {"category": category, "kind": "system_routine"} if category else None
    if edge_type == "EXECUTES" and language == "jcl":
        if name in _UTILITIES:
            return {"category": "ibm_utility", "kind": "utility_program"}
        # `EXEC PGM=DFSRRC00` startet die IMS-Region, `DFHCSDUP`/`DFHECP1$` sind CICS-Werkzeuge.
        category = (
            _CALL_NAMES.get(name)
            or ("cics" if name.startswith("DFH") else None)
            or next((c for p, c in _CALL_PREFIXES if name.startswith(p)), None)
        )
        return {"category": category, "kind": "system_program"} if category else None
    return None
