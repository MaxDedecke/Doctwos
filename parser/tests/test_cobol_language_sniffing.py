import pytest

from core.language_detection import detect_language, sniff_cobol_family

PROGRAM = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MEMBER1.
       PROCEDURE DIVISION.
           GOBACK.
"""

COPYBOOK = """\
      * Satzbeschreibung
       01  KUNDE-REC.
           05  KUNDE-NR       PIC 9(8).
           05  KUNDE-NAME     PIC X(30).
           05  KUNDE-SALDO    PIC S9(9)V99 COMP-3.
"""


def test_extensionless_program_is_recognized_as_cobol():
    assert sniff_cobol_family(PROGRAM) == "cobol"
    assert detect_language("COBOL/MEMBER1", content=PROGRAM) == "cobol"


def test_free_format_program_header_is_recognized():
    assert sniff_cobol_family("identification division.\nprogram-id. x.\n") == "cobol"


def test_extensionless_copybook_is_recognized_by_its_data_descriptions():
    assert sniff_cobol_family(COPYBOOK) == "copybook"
    assert detect_language("COPYLIB/KUNDEREC", content=COPYBOOK) == "copybook"


def test_copybook_with_procedure_division_is_not_a_copybook():
    mixed = COPYBOOK + "       PROCEDURE DIVISION.\n"
    assert sniff_cobol_family(mixed) is None


@pytest.mark.parametrize(
    "content",
    [
        "all:\n\tgcc -o main main.c\n",
        "Dies ist ein Readme.\nMit mehreren Zeilen Text.\n01 ist keine Zahl hier.\n",
        "",
        None,
    ],
)
def test_other_extensionless_files_stay_text(content):
    assert sniff_cobol_family(content) is None
    assert detect_language("Makefile", content=content) == "text"


def test_shell_shebang_wins_over_cobol_sniffing():
    assert detect_language("run", content="#!/bin/sh\necho hi\n") == "shell"


def test_files_with_an_extension_are_never_sniffed():
    assert detect_language("notes.txt", content=PROGRAM) == "text"
