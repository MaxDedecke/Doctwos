import pytest
from connectors.registry import REGISTRY, get_connector


def test_registry_contains_expected_connectors():
    assert "Git" in REGISTRY
    assert "Confluence" in REGISTRY
    assert "Jira" in REGISTRY
    assert "FolderWatch" in REGISTRY
    assert "WebDAV" in REGISTRY


def test_registry_has_no_aec_connectors():
    """Die AEC-Connectoren des Templates (IFC/DWG/GAEB/Dalux/Autodesk) und Notion
    sind mit dem Doctus-Fork entfallen — ein versehentliches Wiedereintragen
    würde eine nicht mehr existierende Klasse importieren."""
    for gone in ("IFC", "DWG", "GAEB", "Dalux", "Autodesk", "Notion"):
        assert gone not in REGISTRY


def test_get_connector_valid():
    connector = get_connector("Git")
    assert connector is not None
    assert connector.__name__ == "GitConnector"


def test_get_connector_case_insensitive():
    connector = get_connector("git")
    assert connector is not None
    assert connector.__name__ == "GitConnector"


def test_get_connector_invalid():
    with pytest.raises(ValueError):
        get_connector("invalid_source_type")
