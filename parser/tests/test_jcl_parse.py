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
