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
3. **Automatische Prüfung** jedes Betriebs:
   - Keine Website eingetragen → Suche nach naheliegenden Domains (`firmenname.de` …).
     Gefunden wird nur, wenn der Firmenname auch auf der Seite steht.
   - Website vorhanden → Handy-tauglich? HTTPS? Impressum? Copyright-Jahr? veraltete Technik?
     Meta-Daten? Ladezeit? Google PageSpeed (Handy).
4. **Score 0–100:** je höher, desto dringender braucht der Betrieb eine neue Seite (100 = keine Website).
5. Zeile anklicken → Befunde, Notizen, **„Bericht / Anschreiben“** (druckfertiger Brief als PDF), Link zu Google Maps.
6. Status pflegen: Neu → Interessant → Angeschrieben → Termin → Kunde.
7. **CSV-Export** öffnet sich in Excel.

Tipp: Vor dem Anschreiben einmal „In Google Maps ansehen“ klicken – OpenStreetMap kennt nicht jede Website.
Steht dort eine, ins Feld „Website“ eintragen und „Neu prüfen“.

## Rechtliches (kurz)

- **Keine Werbe-E-Mails** ohne Einwilligung (§ 7 UWG) – auch nicht an Firmen.
- **Brief und persönlicher Besuch** sind erlaubt → dafür ist der Bericht gedacht.
- Wer keinen Kontakt möchte: Eintrag löschen.

## Optional: PageSpeed-Schlüssel

Ohne Schlüssel teilt sich das Tool ein öffentliches Google-Kontingent, das oft aufgebraucht ist – dann wird dieser
eine Punkt einfach übersprungen. Ein eigener Schlüssel ist **kostenlos und braucht keine Kreditkarte**:
console.cloud.google.com → Projekt anlegen → „PageSpeed Insights API“ aktivieren → Anmeldedaten → API-Schlüssel.
Dann vor dem Start setzen:

- Windows: in `start-windows.bat` vor der `where`-Zeile `set PAGESPEED_API_KEY=DEIN_SCHLÜSSEL` einfügen
- Mac: `PAGESPEED_API_KEY=DEIN_SCHLÜSSEL python3 leadfinder.py`

Datenquelle: © OpenStreetMap-Mitwirkende (ODbL).
