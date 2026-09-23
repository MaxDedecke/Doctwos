from types import SimpleNamespace

from api.graph import _attach_graph_analysis_status, _entity_node
from models.database import SourceScanFile


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_conditions):
        return self

    def all(self):
        return self.rows


class _ReadOnlySession:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        assert model is SourceScanFile
        return _Rows(self.rows)


def test_graph_code_node_carries_language_and_file_analysis_limitation():
    entity = SimpleNamespace(
        id=42,
        name="report.xsl",
        type="xslt_stylesheet",
        file_path="resources/report.xsl",
        start_line=1,
        project_id=9,
        source_id=7,
        qualified_name="resources/report.xsl",
        variant_key="default",
        meta_json={"language": "xslt"},
    )
    scan = SimpleNamespace(
        source_id=7,
        file_path="resources/report.xsl",
        parse_status="partial",
        parse_error="unterminated template; ambiguous match",
    )
    node = _entity_node(entity)

    _attach_graph_analysis_status(_ReadOnlySession([scan]), [node])

    assert node["language"] == "xslt"
    assert node["entity_type"] == "xslt_stylesheet"
    assert node["analysis_status"] == "partial"
    assert node["analysis_reasons"] == ["unterminated template", "ambiguous match"]
