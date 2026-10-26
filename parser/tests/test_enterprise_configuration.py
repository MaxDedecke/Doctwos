from markup.parse import parse_xml_document
from resources.configuration import parse_configuration


def test_spring_xml_beans_references_and_java_types_keep_source_lines():
    result = parse_xml_document(
        """<beans xmlns="http://www.springframework.org/schema/beans">
 <bean id="fast" class="impl.Fast" primary="true"/>
 <bean id="client" class="app.Client">
  <property name="port" ref="fast"/>
 </bean>
</beans>""",
        "app/src/main/resources/beans.xml",
    )
    assert not result.diagnostics
    assert len([e for e in result.entities if e.type == "spring_bean"]) == 2
    edge = next(e for e in result.edges if e.type == "INJECTS")
    assert edge.src_start_line == 4 and edge.meta["bean_reference"] == "fast"
    assert len([e for e in result.edges if e.type == "CONFIGURES"]) == 2


def test_yaml_keys_profiles_and_german_text_are_structured_without_execution():
    result = parse_configuration(
        """service:
  title: Größe
  password: secret
---
spring:
  config:
    activate:
      on-profile: prod
service:
  title: Production
""",
        "application.yml",
    )
    props = [e for e in result.entities if e.type == "property"]
    titles = [e for e in props if e.name == "service.title"]
    assert titles[0].start_line == 2 and titles[0].meta["value_preview"] == "Größe"
    assert titles[1].meta["configuration_profile"] == "prod"
    assert next(e for e in props if e.name == "service.password").meta["value_redacted"]


def test_malformed_configuration_has_diagnostics_and_text_fallback_content():
    result = parse_configuration("x: [broken", "application.yaml")
    assert result.diagnostics and result.chunks
