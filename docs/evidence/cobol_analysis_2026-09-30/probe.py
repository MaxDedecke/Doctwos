"""Offline audit probes; run from repository root with PYTHONPATH=parser."""
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from cobol.parse import parse_program, parse_copybook
from cobol.profile import BuildProfile

ROOT = Path(__file__).resolve().parent
PROFILE = BuildProfile(source_format="free")
DATA = "01 A PIC 9.\n01 B PIC 9.\n01 C PIC 9.\n01 IDX PIC 9.\n01 TAB.\n  05 CELL PIC 9 OCCURS 5 TIMES.\n"


def program(body, data=DATA):
    return ("IDENTIFICATION DIVISION.\nPROGRAM-ID. AUDIT.\nDATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n" + data + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body)


CASES = {
    "compute": program("COMPUTE C = A + B.\nGOBACK.\n"),
    "set_source": program("SET A TO B.\nGOBACK.\n"),
    "divide_by": program("DIVIDE A BY B GIVING C.\nGOBACK.\n"),
    "subscript_write": program("MOVE A TO CELL(IDX).\nGOBACK.\n"),
    "initialize_replacing": program("INITIALIZE TAB REPLACING NUMERIC DATA BY A.\nGOBACK.\n"),
    "multi_qualifier": program("DISPLAY VALUE-X OF GROUP-X OF ROOT-A.\nGOBACK.\n",
        "01 ROOT-A.\n  05 GROUP-X.\n    10 VALUE-X PIC 9.\n01 ROOT-B.\n  05 GROUP-X.\n    10 VALUE-X PIC 9.\n"),
    "wrong_qualifier": program("DISPLAY A OF WRONG-GROUP.\nGOBACK.\n", "01 ROOT-A.\n  05 A PIC 9.\n01 WRONG-GROUP PIC 9.\n"),
    "paragraph_field_collision": program("DISPLAY A.\nGOBACK.\nA.\nCONTINUE.\n"),
    "qualified_perform": program("PERFORM WORK-PARA OF SEC-A.\nGOBACK.\nSEC-A SECTION.\nWORK-PARA.\nCONTINUE.\nSEC-B SECTION.\nWORK-PARA.\nCONTINUE.\n"),
    "qualified_source": program("GOBACK.\nSEC-A SECTION.\nWORK-PARA.\nCALL 'SUB-A'.\nSEC-B SECTION.\nWORK-PARA.\nCALL 'SUB-B'.\n"),
    "sort_procedures": program("SORT SORT-FILE ON ASCENDING KEY SORT-KEY\nINPUT PROCEDURE IS INPUT-PARA OUTPUT PROCEDURE IS OUTPUT-PARA.\nGOBACK.\nINPUT-PARA.\nCONTINUE.\nOUTPUT-PARA.\nCONTINUE.\n"),
    "bare_call": "IDENTIFICATION DIVISION.\nPROGRAM-ID. AUDIT.\nPROCEDURE DIVISION.\nCALL 'SUB-A'.\nGOBACK.\n",
    "search_scope": program("SEARCH CELL\nWHEN CELL(IDX) = A\nCALL 'FOUND'\nEND-SEARCH\nCALL 'AFTER'.\nGOBACK.\n"),
    "sql_same_host": program("EXEC SQL SELECT COL INTO :A FROM BANK.ACCOUNTS WHERE ID = :A END-EXEC.\nGOBACK.\n"),
    "sql_comma_tables": program("EXEC SQL SELECT X.ID INTO :A FROM BANK.ACCOUNTS X, BANK.CUSTOMERS Y WHERE X.ID=Y.ID END-EXEC.\nGOBACK.\n"),
    "sql_comment_in_literal": program("EXEC SQL SELECT '-- JOIN FAKE' INTO :A FROM BANK.ACCOUNTS END-EXEC.\nGOBACK.\n"),
    "sql_end_exec_in_literal": program("EXEC SQL SELECT 'END-EXEC' INTO :A FROM BANK.ACCOUNTS END-EXEC.\nGOBACK.\n"),
    "sql_cte": program("EXEC SQL WITH TEMP AS (SELECT ID FROM BANK.ACCOUNTS) SELECT ID INTO :A FROM TEMP END-EXEC.\nGOBACK.\n"),
    "sql_merge": program("EXEC SQL MERGE INTO BANK.ACCOUNTS T USING BANK.UPDATES S ON T.ID=S.ID WHEN MATCHED THEN UPDATE SET T.VALUE=S.VALUE END-EXEC.\nGOBACK.\n"),
    "local_storage": "IDENTIFICATION DIVISION.\nPROGRAM-ID. AUDIT.\nDATA DIVISION.\nLOCAL-STORAGE SECTION.\n01 A PIC 9.\nPROCEDURE DIVISION.\nMAIN-PARA.\nDISPLAY A.\nGOBACK.\n",
    "copybook_exec_entities": "COPY-PARA.\nEXEC CICS READ FILE('ACCOUNTS') INTO(BUF) RESP(STATUS-X) END-EXEC.\n",
}


def main():
    results = {}
    for name, source in CASES.items():
        suffix = ".cpy" if name.startswith("copybook_") else ".cbl"
        path = name + suffix
        (ROOT / path).write_text(source)
        parse = parse_copybook if suffix == ".cpy" else parse_program
        result = parse(source, path, profile=PROFILE)
        results[name] = asdict(result)
        print(name, "diagnostics:", len(result.diagnostics), "errors:", result.errors)
        print("  entities:", [(e.type, e.qualified_name) for e in result.entities])
        print("  edges:", [(e.type, e.src_name, e.dst_name, e.resolution,
            {k:v for k,v in e.meta.items() if k != "evidence"}) for e in result.edges])
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    (ROOT / "results.json").write_text(json.dumps({"revision": revision, "cases": results}, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
