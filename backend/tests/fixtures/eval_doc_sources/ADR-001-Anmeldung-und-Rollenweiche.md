# ADR-001: Anmeldung und Rollenweiche im Kartenprogramm

Status: akzeptiert (synthetisches Testdokument für O-284)

## Entscheidung
Die Anmeldung läuft ausschließlich über die CICS-Transaktion des Programms `COSGN00C`. Das Programm liest den Benutzersatz aus dem VSAM-Dataset `USRSEC` über die eingegebene Benutzerkennung als Schlüssel.

## Rollenweiche
Nach erfolgreicher Prüfung entscheidet der Benutzertyp über das Folgeprogramm: Administratoren werden per XCTL an `COADM01C` übergeben, alle anderen Benutzer an `COMEN01C`. Die Übergabe erfolgt über die gemeinsame Kommunikationsstruktur `CARDDEMO-COMMAREA`.

## Fehlerfälle
- Bleibt die Benutzerkennung leer, lautet die Meldung „Please enter User ID ...“.
- Bleibt das Passwort leer, lautet die Meldung „Please enter Password ...“.
- Ist die Kennung im Dataset nicht vorhanden (CICS-Antwortcode 13), lautet die Meldung „User not found. Try again ...“.
- Stimmt das Passwort nicht überein, lautet die Meldung „Wrong Password. Try again ...“.

## Konsequenzen
Kennung und Passwort werden vor dem Vergleich in Großbuchstaben umgewandelt. Das Passwort steht im Dataset im Klartext; eine Härtung ist nicht Teil dieser Entscheidung.
