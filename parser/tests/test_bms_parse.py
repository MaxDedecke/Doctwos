from bms.parse import parse_bms_file
from core.registry import STRUCTURE_PARSERS


def _line(text: str, continued: bool = False) -> str:
    assert len(text) <= 71, text
    return (text.ljust(71) + "-" if continued else text) + "\n"


SOURCE = (
    "* Anmeldemaske\n"
    + _line("SIGNSET DFHMSD TYPE=&&SYSPARM,MODE=INOUT,LANG=COBOL,", continued=True)
    + _line("               CTRL=(FREEKB)")
    + _line("SIGNMAP DFHMDI SIZE=(24,80),LINE=1,COLUMN=1")
    + _line("        DFHMDF POS=(1,1),LENGTH=10,ATTRB=ASKIP,", continued=True)
    + _line("               INITIAL='User ID :'")
    + _line("USERID  DFHMDF POS=(1,12),LENGTH=8,ATTRB=(UNPROT,IC),", continued=True)
    + _line("               COLOR=GREEN")
    + _line("TITLE   DFHMDF POS=(1,30),LENGTH=40,ATTRB=ASKIP")
    + _line("        DFHMDF POS=(3,1),LENGTH=60,ATTRB=ASKIP,", continued=True)
    + _line("               INITIAL='Bitte melden Sie sich mit Ihrer Kennung", continued=True)
    + _line("               an, Kollege''s Hinweis'")
    + _line("        DFHMSD TYPE=FINAL")
    + _line("        END")
)


def test_bms_mapset_maps_and_named_fields_keep_their_lines_and_screen_labels():
    result = parse_bms_file(SOURCE, "app/bms/SIGNSET.bms")

    assert result.errors == []
    assert [(e.type, e.name, e.start_line, e.end_line) for e in result.entities] == [
        ("bms_mapset", "SIGNSET", 2, 13),
        ("bms_map", "SIGNMAP", 4, 12),
        ("bms_field", "USERID", 7, 8),
        ("bms_field", "TITLE", 9, 9),
    ]
    mapset, screen, userid, title = result.entities
    assert mapset.meta["ctrl"] == ["FREEKB"] and mapset.meta["is_file_root"] is True
    assert screen.parent_qualified_name == mapset.qualified_name
    assert screen.meta["size"] == [24, 80]
    assert screen.meta["texts"][1]["text"] == (
        # Das Literal läuft bis Spalte 71 und geht in Spalte 16 der Folgezeile weiter.
        "Bitte melden Sie sich mit Ihrer Kennung".ljust(71 - 24) + "an, Kollege's Hinweis"
    )
    assert userid.meta == {
        "language": "bms",
        "mapset": "SIGNSET",
        "map": "SIGNMAP",
        "label": "User ID :",
        "pos": [1, 12],
        "length": 8,
        "attrb": ["UNPROT", "IC"],
        "color": "GREEN",
    }
    assert "label" not in title.meta  # links daneben steht ein benanntes Feld, kein Text
    assert result.chunks and result.chunks[0].start_line == 1


def test_bms_files_are_parsed_as_their_own_language():
    assert STRUCTURE_PARSERS["bms"].root_entity_types == ("bms_mapset",)
