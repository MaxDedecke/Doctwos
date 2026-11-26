Beispieldateien für `tests/test_doc_rtf.py`: `beispiel.docx` wurde mit python-docx erzeugt, `beispiel.doc` und
`beispiel.rtf` daraus mit LibreOffice (`soffice --headless --convert-to doc|rtf`), `einfach.doc` aus einer ASCII-Textdatei.
LibreOffice schreibt kein gezipptes Design in die .doc und kein Word 6; deshalb zusätzlich drei von Word geschriebene
Dateien aus den Testdaten von Apache POI (`test-data/document`, Apache License 2.0), umbenannt:
`poi-word2007-als-doc.doc` (SampleDoc.doc, Word 2007+ als .doc gespeichert), `poi-word6.doc` (Word6.doc) und
`poi-textfeld.doc` (Bug41898.doc, Text nur in einem Textfeld).
