# Fachkonzept: Kartenautorisierung über Nachrichtenwarteschlange

Status: Entwurf (synthetisches Testdokument für O-284)

## Ablauf
Das Programm `COPAUA0C` nimmt Autorisierungsanfragen aus einer Nachrichtenwarteschlange entgegen (Aufruf `MQGET`) und beantwortet sie über eine Antwortwarteschlange (`MQPUT1`). Die Anfragefelder stammen aus dem Copybook `CCPAURQY`; die Kartennummer heißt dort `PA-RQ-CARD-NUM`, der Betrag `PA-RQ-TRANSACTION-AMT`.

## Prüfung und Ablage
Die Kartennummer wird gegen die Kreuzreferenz der Karten nachgeschlagen. Die Entscheidung wird in einer hierarchischen IMS-Datenbank abgelegt (Zugriffe `EXEC DLI GU` und `EXEC DLI REPL`). Eine Zusammenfassung je Konto wird fortgeschrieben.

## Offene Punkte
Die Abstimmung der Genehmigungsgrenze mit dem Fachbereich steht aus. Die Antwortzeit-Vorgabe von 500 Millisekunden ist nicht gemessen.
