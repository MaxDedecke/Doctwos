"""JCL ist durch Leerzeichen getrennt, nicht spaltengebunden (CardDemo POSTTRAN.jcl)."""

from jcl.parse import parse_jcl_file

FREE_SPACING = """//POSTTRAN JOB 'POSTTRAN',CLASS=A,MSGCLASS=0,
// NOTIFY=&SYSUID
//*******************************************************************
//STEP15 EXEC PGM=CBTRN02C
//STEPLIB  DD DISP=SHR,
//         DSN=AWS.M2.CARDDEMO.LOADLIB
//DALYTRAN DD DISP=SHR,DSN=AWS.M2.CARDDEMO.DALYTRAN.PS
"""

ALIGNED = """//WAITSTEP JOB 'WAITSTEP',CLASS=A
//WAIT     EXEC PGM=COBSWAIT
//STEPLIB  DD DISP=SHR,DSN=AWS.M2.CARDDEMO.LOADLIB
"""


def _executes(result):
    return [(e.src_name, e.dst_name, e.src_start_line) for e in result.edges if e.type == "EXECUTES"]


def test_step_with_single_blank_between_name_and_exec_is_recognised():
    result = parse_jcl_file(FREE_SPACING, "app/jcl/POSTTRAN.jcl")
    steps = [e for e in result.entities if e.type == "jcl_step"]
    assert [(s.name, s.start_line) for s in steps] == [("STEP15", 4)]
    assert [(dst, line) for _src, dst, line in _executes(result)] == [("CBTRN02C", 4)]
    datasets = {e.name for e in result.entities if e.type == "jcl_dataset"}
    assert datasets == {"AWS.M2.CARDDEMO.LOADLIB", "AWS.M2.CARDDEMO.DALYTRAN.PS"}
    assert not result.diagnostics


def test_column_aligned_step_still_parses_and_continuation_cards_stay_with_their_statement():
    aligned = parse_jcl_file(ALIGNED, "app/jcl/WAITSTEP.jcl")
    assert [(dst, line) for _src, dst, line in _executes(aligned)] == [("COBSWAIT", 2)]
    free = parse_jcl_file(FREE_SPACING, "app/jcl/POSTTRAN.jcl")
    jobs = [e for e in free.entities if e.type == "jcl_job"]
    assert [(j.name, j.start_line) for j in jobs] == [("POSTTRAN", 1)]


def test_instream_star_data_ends_at_the_next_jcl_statement_without_a_delimiter():
    """`DD *` ohne `/*` endet an der nächsten `//`-Zeile (CardDemo `IMSMQCMP.jcl` verlor sonst drei Steps)."""
    source = (
        "//J1 JOB\n"
        "//A EXEC PGM=IEBGENER\n"
        "//SYSUT1 DD *\n"
        "  INCLUDE X\n"
        "//SYSUT2 DD DSN=&&T,DISP=(NEW,PASS)\n"
        "//B EXEC PGM=IEWL\n"
        "//SYSLIB DD DSN=SYS1.LINKLIB,DISP=SHR\n"
    )
    result = parse_jcl_file(source, "x.jcl")
    steps = [e.name for e in result.entities if e.type == "jcl_step"]
    assert steps == ["A", "B"]
    assert any(e.dst_name == "SYS1.LINKLIB" for e in result.edges)


def test_dd_data_and_dlm_keep_jcl_looking_lines_inside_the_data():
    source = (
        "//J1 JOB\n"
        "//A EXEC PGM=IEBGENER\n"
        "//SYSUT1 DD DATA,DLM=ZZ\n"
        "//B EXEC PGM=NOT.A.STEP\n"
        "ZZ\n"
        "//C EXEC PGM=IEWL\n"
    )
    steps = [e.name for e in parse_jcl_file(source, "x.jcl").entities if e.type == "jcl_step"]
    assert steps == ["A", "C"]
