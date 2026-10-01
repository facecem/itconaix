# Lead-Finder

Findet lokale Betriebe **ohne Website** oder mit **schwacher Website** und verwaltet sie in einem kleinen Dashboard.
Kostenlos, ohne Kreditkarte, alle Daten bleiben auf eurem Rechner (`leads.db`).

## Starten

1. Einmalig **Python** installieren: https://www.python.org/downloads/ (unter Windows beim Installieren „Add Python to PATH“ anhaken).
2. Doppelklick auf
   - **Windows:** `start-windows.bat`
   - **Mac:** `start-mac.command` (beim ersten Mal: Rechtsklick → Öffnen)
3. Der Browser öffnet `http://127.0.0.1:8765`. Das schwarze Fenster offen lassen, solange ihr arbeitet.

## So arbeitet ihr damit

1. **Suchen:** Branche + Ort + Umkreis wählen → das Tool holt alle Betriebe aus OpenStreetMap.
2. **Selbst eintragen:** Betriebe, die ihr in Google Maps seht, zeilenweise einfügen: `Name; Ort; Website; Telefon`.
3. **Automatische Prüfung** jedes Betriebs – bewertet wird immer die **Startseite**:
   - **Keine Website** (oder nur Facebook/Instagram/Branchenbuch-Eintrag) → Score 100.
     Ist keine eingetragen, sucht das Tool naheliegende Domains (`firmenname.de` …); gefunden wird nur,
     wenn der Firmenname auch auf der Seite steht.
   - **Kein Impressum** → Link auf der Startseite und typische Adressen (`/impressum`, `/impressum.html` …) werden geprüft.
   - **Veraltetes Design** → nicht handytauglich, alter HTML-Standard, Tabellen-Layout, Font-Tags, Frames, Flash,
     uraltes Copyright-Jahr, veraltetes CMS, kein HTTPS.
   - **Ignoriert** werden Fehlerseiten, nicht erreichbare Seiten und Filialketten (gleiche Domain bei 3+ Betrieben).
     Mit „Ignorierte zeigen“ blendet ihr sie ein.
4. **Score 0–100:** je höher, desto besser der Kontakt (100 = keine Website, kein Impressum = +50, veraltetes Design bis +60).
5. Zeile anklicken → Befunde, Notizen, **„Anschreiben“** (druckfertiger Brief als PDF), Link zu Google Maps.
6. Status pflegen: Neu → Interessant → Angeschrieben → Termin → Kunde.
7. **CSV-Export** öffnet sich in Excel.

Tipp: Vor dem Anschreiben einmal „Google Maps“ klicken – OpenStreetMap kennt nicht jede Website.
Steht dort eine, ins Feld „Website“ eintragen und „Neu prüfen“.

## Rechtliches (kurz)

- **Keine Werbe-E-Mails** ohne Einwilligung (§ 7 UWG) – auch nicht an Firmen.
- **Brief und persönlicher Besuch** sind erlaubt → dafür ist der Bericht gedacht.
- Wer keinen Kontakt möchte: Eintrag löschen.

Datenquelle: © OpenStreetMap-Mitwirkende (ODbL).
