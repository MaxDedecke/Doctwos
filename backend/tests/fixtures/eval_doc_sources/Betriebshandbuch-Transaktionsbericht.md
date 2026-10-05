# Betriebshandbuch: Transaktionsbericht im Batch

Status: gültig (synthetisches Testdokument für O-284)

## Zweck
Das Batch-Programm `CBTRN03C` druckt den Transaktionsdetailbericht. Es liest die Transaktionsdatei (DD `TRANFILE`), die Kartenkreuzreferenz (`CARDXREF`), die Transaktionstypen (`TRANTYPE`) und die Kategorien (`TRANCATG`) und schreibt den Bericht in die Ausgabe `TRANREPT`.

## Zeitraum
Der auszuwertende Zeitraum kommt aus der Parameterdatei mit dem DD-Namen `DATEPARM`. Ohne diese Datei läuft der Bericht nicht.

## Wiederanlauf
Bei einem Abbruch wird der Bericht vollständig neu erzeugt; ein teilweiser Wiederanlauf ist nicht vorgesehen. Ein Abbruch durch einen Dateifehler läuft über den Absatz `9999-ABEND-PROGRAM`.
