from cobol.parse import parse_program
from connectors import git as git_connector


def test_sourcewide_index_expands_nested_copybooks_and_replacing(tmp_path, monkeypatch):
    """Pass 0 muss den vollstaendigen Baum kennen, bevor Programme parsen."""
    copy_dir = tmp_path / "copy"
    copy_dir.mkdir()
    (copy_dir / "BASE.CPY").write_text("01 BASE-RECORD.\n   05 BASE-ID PIC X.\n")
    (copy_dir / "WRAP.CPY").write_text(
        "COPY BASE REPLACING ==BASE== BY ==CUSTOMER==.\n"
    )
    monkeypatch.setattr(
        git_connector.git_utils,
        "list_tracked_files",
        lambda _: ["copy/BASE.CPY", "copy/WRAP.CPY"],
    )

    index = git_connector._build_copybook_index(
        str(tmp_path), {"copybook": {".cpy"}}
    )

    assert index.fields_by_path["copy/WRAP.CPY"][0]["effective_name"] == "CUSTOMER-RECORD"
    program = (
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. MAIN.\n"
        "DATA DIVISION.\n"
        "COPY WRAP REPLACING ==CUSTOMER== BY ==ACCOUNT==.\n"
        "PROCEDURE DIVISION.\n"
        "MAIN-PARA.\n"
        "    DISPLAY ACCOUNT-ID.\n"
    )
    result = parse_program(program, "MAIN.CBL", index)
    uses = next(edge for edge in result.edges if edge.type == "USES")

    assert uses.resolution == "resolved"
    assert uses.meta["copybook_path"] == "copy/BASE.CPY"
    assert uses.meta["target_qualified_name"] == "BASE.BASE-RECORD.BASE-ID"
