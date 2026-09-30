from doc_structure import boundary_lines, markdown_outline, section_path

MD = """# Autorisierung

Einleitung.

## Entscheidung

Text zur Entscheidung.

```
# kein Heading im Codeblock
```

### Kreditprüfung

Details.

## Antwort
"""


def test_outline_ignores_code_fences_and_captures_levels():
    outline = markdown_outline(MD)
    assert outline == [
        (1, 1, "Autorisierung"), (5, 2, "Entscheidung"), (13, 3, "Kreditprüfung"), (17, 2, "Antwort"),
    ]
    assert boundary_lines(outline) == frozenset({1, 5, 13, 17})


def test_section_path_follows_the_heading_stack():
    outline = markdown_outline(MD)
    assert section_path(outline, 3) == "Autorisierung"
    assert section_path(outline, 7) == "Autorisierung > Entscheidung"
    assert section_path(outline, 15) == "Autorisierung > Entscheidung > Kreditprüfung"
    assert section_path(outline, 18) == "Autorisierung > Antwort"
    assert section_path([], 3) is None
    assert section_path(markdown_outline("Vorspann\n# Erst hier\n"), 1) is None
