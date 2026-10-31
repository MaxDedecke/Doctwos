from resources.csd import parse_csd_file


def test_cics_file_definitions_name_their_dataset_and_line():
    source = (
        " DEFINE PROGRAM(COSGN00C) GROUP(CARDDEMO)\n"
        "        LANGUAGE(COBOL)\n"
        " DEFINE FILE(TRANSACT) GROUP(CARDDEMO)\n"
        "        DESCRIPTION(TRANSACTIONS)\n"
        "        DSNAME(AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS) RLSACCESS(NO)\n"
        " DEFINE FILE(REMOTE) GROUP(CARDDEMO)\n"
        "        REMOTESYSTEM(CICB)\n"
    )
    result = parse_csd_file(source, "app/csd/CARDDEMO.CSD")
    files = {entity.name: entity for entity in result.entities if entity.type == "cics_file"}

    assert set(files) == {"TRANSACT", "REMOTE"}
    transact = files["TRANSACT"]
    assert transact.meta["dataset"] == "AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS"
    assert transact.meta["group"] == "CARDDEMO"
    assert transact.start_line == 3
    assert transact.end_line == 5
    assert files["REMOTE"].meta["dataset"] is None
    assert result.entities[0].type == "csd_file"
