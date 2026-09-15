from types import SimpleNamespace

from api.entities import _select_file_root


def _entity(entity_type: str, *, is_file_root: bool = False):
    return SimpleNamespace(type=entity_type, meta_json={"is_file_root": is_file_root})


def test_select_file_root_uses_marker_regardless_of_java_extension():
    compilation_unit = _entity("compilation_unit", is_file_root=True)
    class_entity = _entity("class")

    assert (
        _select_file_root(
            [class_entity, compilation_unit], "src/main/java/com/acme/PaymentService.java"
        )
        is compilation_unit
    )


def test_select_file_root_falls_back_to_legacy_program():
    program = _entity("program")

    assert _select_file_root([program], "MAIN.CBL") is program


def test_select_file_root_falls_back_to_legacy_copybook():
    copybook = _entity("copybook")

    assert _select_file_root([copybook], "FIELDS.CPY") is copybook


def test_select_file_root_does_not_guess_for_unmarked_java_entities():
    assert _select_file_root([_entity("class")], "Example.java") is None
