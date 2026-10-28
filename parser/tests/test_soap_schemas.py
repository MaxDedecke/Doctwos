import uuid

import pytest

from db import SessionLocal
from java.parse import parse_java_file
from java.modules import is_build_excluded
from java.fingerprint import grammar_fingerprint
from markup.parse import parse_xml_document
from core.language_detection import DEFAULT_LANGUAGE_EXTENSIONS
from doctus_models.database import CodeEdge, KnowledgeSource, Project, Team
from structure_persist import persist_parse_result
from tasks.edge_resolver import resolve_global_edges

XSD = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:orders"
 targetNamespace="urn:orders" elementFormDefault="qualified">
 <xs:complexType name="OrderType">
  <xs:sequence><xs:element name="id" type="xs:string"/></xs:sequence>
 </xs:complexType>
 <xs:element name="submit" type="t:OrderType"/>
</xs:schema>"""
WSDL = """<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" xmlns:t="urn:orders"
 xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/" xmlns:xs="http://www.w3.org/2001/XMLSchema"
 targetNamespace="urn:orders">
 <types><xs:schema><xs:import namespace="urn:orders" schemaLocation="types.xsd"/></xs:schema></types>
 <message name="SubmitRequest"><part name="request" element="t:submit"/></message>
 <portType name="OrdersPort"><operation name="submit"><input message="t:SubmitRequest"/></operation></portType>
 <binding name="OrdersBinding" type="t:OrdersPort"><soap:binding transport="http://schemas.xmlsoap.org/soap/http"/>
  <operation name="submit"><soap:operation soapAction="urn:submit"/></operation>
 </binding>
 <service name="Orders"><port name="OrdersPort" binding="t:OrdersBinding"><soap:address location="https://example.invalid/orders"/></port></service>
</definitions>"""
JAVA = """package api;
import jakarta.jws.*; import jakarta.xml.bind.annotation.*;
@XmlType(name="OrderType", namespace="urn:orders")
@XmlRootElement(name="submit", namespace="urn:orders")
class Order { @XmlElement(name="id", namespace="urn:orders") String id; }
@WebService(name="OrdersPort", targetNamespace="urn:orders")
class Endpoint { @WebMethod(operationName="submit") public Order submit(Order request) { return request; } }
"""


@pytest.fixture
def workspace():
    db = SessionLocal()
    team = Team(name="soap-" + uuid.uuid4().hex)
    db.add(team)
    db.flush()
    project = Project(name="soap", team_id=team.id)
    db.add(project)
    db.flush()
    source = KnowledgeSource(name="soap", type="Git", team_id=team.id, project_id=project.id)
    db.add(source)
    db.commit()
    try:
        yield db, project, source
    finally:
        db.delete(project)
        db.commit()
        db.delete(team)
        db.commit()
        db.close()


def save(workspace, result):
    db, project, source = workspace
    persist_parse_result(
        db,
        source_id=source.id,
        project_id=project.id,
        file_path=result.path,
        content_hash="test",
        result=result,
    )
    db.commit()


def test_wsdl_xsd_qnames_actions_addresses_and_original_lines():
    xsd = parse_xml_document(XSD, "schemas/types.xsd")
    wsdl = parse_xml_document(WSDL, "schemas/orders.wsdl")
    assert not xsd.diagnostics and not wsdl.diagnostics
    order = next(e for e in xsd.entities if e.type == "xsd_complex_type")
    assert order.meta["xml_qname"] == "{urn:orders}OrderType" and order.start_line == 3
    binding = next(
        e
        for e in wsdl.entities
        if e.type == "wsdl_operation" and e.meta["operation_role"] == "binding"
    )
    assert binding.meta["soap_action"] == "urn:submit"
    assert (
        next(e for e in wsdl.entities if e.type == "wsdl_port").meta["endpoint_address"]
        == "https://example.invalid/orders"
    )


def test_java_endpoint_wsdl_messages_and_jaxb_types_resolve_and_survive_target_changes(workspace):
    for result in [
        parse_xml_document(XSD, "schemas/types.xsd"),
        parse_xml_document(WSDL, "schemas/orders.wsdl"),
        parse_java_file(JAVA, "api/src/main/java/api/Endpoint.java"),
    ]:
        save(workspace, result)
    db, _, source = workspace
    for _ in range(2):
        resolve_global_edges(db, source.id)
        edges = db.query(CodeEdge).filter(CodeEdge.source_id == source.id).all()
        for kind in [
            "BINDS_TO",
            "INPUT_MESSAGE",
            "MAPS_XML_TYPE",
            "MAPS_XML_ELEMENT",
            "IMPLEMENTS_OPERATION",
        ]:
            found = [e for e in edges if e.type == kind]
            assert found and all(e.resolution == "resolved" for e in found), kind
        assert any(e.type == "USES_XML_TYPE" and e.resolution == "external" for e in edges)
        assert (
            next(e for e in edges if (e.meta_json or {}).get("schema_import")).resolution
            == "resolved"
        )
    save(
        workspace,
        parse_xml_document(XSD.replace('name="OrderType"', 'name="Renamed"'), "schemas/types.xsd"),
    )
    resolve_global_edges(db, source.id)
    mapping = (
        db.query(CodeEdge)
        .filter(CodeEdge.source_id == source.id, CodeEdge.type == "MAPS_XML_TYPE")
        .one()
    )
    assert mapping.resolution == "unresolved" and mapping.dst_entity_id is None


def test_jaxb_package_defaults_and_namespace_identity(workspace):
    save(workspace, parse_xml_document(XSD, "schemas/types.xsd"))
    save(
        workspace,
        parse_java_file(
            '@jakarta.xml.bind.annotation.XmlSchema(namespace="urn:orders", elementFormDefault=jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED) package api;',
            "api/src/main/java/api/package-info.java",
        ),
    )
    save(
        workspace,
        parse_java_file(
            'package api; import jakarta.xml.bind.annotation.*; @XmlType(name="OrderType") class Order { @XmlElement(name="id") String id; }',
            "api/src/main/java/api/Order.java",
        ),
    )
    db, _, source = workspace
    resolve_global_edges(db, source.id)
    edges = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.source_id == source.id,
            CodeEdge.type.in_(["MAPS_XML_TYPE", "MAPS_XML_ELEMENT"]),
        )
        .all()
    )
    assert len(edges) == 2 and all(e.resolution == "resolved" for e in edges)
    save(workspace, parse_xml_document(XSD.replace("urn:orders", "urn:other"), "schemas/other.xsd"))
    resolve_global_edges(db, source.id)
    assert all(e.resolution == "resolved" for e in edges)


def test_generated_java_requires_explicit_opt_in_and_changes_fingerprint(monkeypatch):
    path = "client/target/generated-sources/wsimport/api/Orders.java"
    before = grammar_fingerprint()
    assert is_build_excluded(path, DEFAULT_LANGUAGE_EXTENSIONS)
    monkeypatch.setenv("DOCTUS_INCLUDE_GENERATED_JAVA", "true")
    assert not is_build_excluded(path, DEFAULT_LANGUAGE_EXTENSIONS)
    assert is_build_excluded("client/target/classes/Orders.java", DEFAULT_LANGUAGE_EXTENSIONS)
    assert grammar_fingerprint() != before
