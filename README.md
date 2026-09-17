# CED-A-DOKU – KI-gestützte Auswertung medizinischer Dokumente

## API-Schlüssel eintragen

Die API-Schlüssel werden beim Programmstart mit `python-dotenv` aus einer lokalen
Datei namens `.env` geladen. Die Schlüssel gehören **nicht** in eine Python-Datei.

1. Abhängigkeiten installieren:

   ```bash
   pip install -r requirements.txt
   ```

2. Die Vorlage im Projektstamm kopieren:

   ```bash
   cp .env.example .env
   ```

3. Die neu angelegte `.env` öffnen und die Werte hinter dem jeweiligen
   Gleichheitszeichen eintragen:

   ```dotenv
   # Lokale Geheimnisse: Diese Datei niemals an Git übergeben.
   UK_API_KEY=hier_den_uk_api_schluessel_eintragen
   OPEN_AI_KEY=hier_den_openai_api_schluessel_eintragen
   ```

   Es sind keine Anführungszeichen erforderlich. Für den in `CED_AI_PROVIDER`
   ausgewählten Anbieter muss der entsprechende Schlüssel gesetzt sein.

4. Die Browseranwendung aus dem Projektstamm starten:

   ```bash
   python main.py
   ```

## Dokumente einlesen

PDF-, JPG- und PNG-Dateien können gemeinsam ausgewählt, in das farblich markierte
Ablagefeld gezogen oder als Bild mit `Strg+V` beziehungsweise `Cmd+V` eingefügt
werden. Alle übernommenen Dokumentteile erscheinen sofort als Vorschauen in bis zu zwei
Spalten. Mit den Pfeilen lässt sich die Reihenfolge vor der Analyse manuell ändern;
der Papierkorb entfernt ein einzelnes Teil. Die zusätzliche Standardvorschau im
Upload-Feld wird ausgeblendet, weil das Bild bereits im sortierbaren Raster sichtbar
ist. „Alles löschen / neu beginnen“ setzt
Dokument und KI-Ergebnis vollständig zurück.

Bei mehreren Bildern oder Dateien wird jedes Dokumentteil zuerst einzeln und
vollständig transkribiert. Anschließend prüft die KI anhand sichtbarer
Seitenzahlen, Datumsangaben und inhaltlicher Anschlüsse die wahrscheinliche
Reihenfolge und verarbeitet alle Transkriptionen als ein gemeinsames Dokument.
Das Transkript enthält dabei weder Seiten- oder Dokumentnummern noch automatisch
erzeugte Teilkennzeichnungen; ausgegeben wird ausschließlich der übrige Text aus
dem Originaldokument, ohne Ergänzungen.
Währenddessen kennzeichnen ein drehendes Statussymbol und ein Statustext die laufende
Bearbeitung. Da die automatische Reihenfolge nur ein Vorschlag sein kann, muss das
Ergebnis weiterhin medizinisch geprüft werden.

Die Auswahl zwischen Rohtext, strukturierter Darstellung und KI-Zusammenfassung
startet keine neue Bildanalyse. Bei einem einzelnen Bild erzeugt genau eine
multimodale Anfrage alle drei Ansichten gemeinsam. Bei mehreren Dokumentteilen wird
jeder Teil einmal vollständig transkribiert; anschließend erzeugt genau eine weitere
reine Textanfrage Dokumenttyp, strukturierten Text und KIS-Zusammenfassung aus diesen
Transkriptionen. Nur der ausdrücklich betätigte Schalter zur erneuten Bearbeitung
sendet das Dokument nochmals an den gewählten Anbieter.

Die `.env` ist in `.gitignore` ausgeschlossen. `.env.example` bleibt dagegen als
leere, sichere Vorlage versioniert. Bereits außerhalb der Datei gesetzte
Umgebungsvariablen haben Vorrang vor Einträgen aus `.env`.

> **Debugging-Hinweis:** Falls eine Variable angeblich fehlt, zuerst prüfen, ob
> die Datei wirklich `.env` heißt, im selben Ordner wie `main.py` liegt und kein
> Leerzeichen vor dem Variablennamen enthält. Schlüsselwerte nicht in Logs oder
> Screenshots ausgeben.

## Geschützte Patientenzuordnung

Die normale Textextraktion bleibt ohne Datenbankfreigabe nutzbar. Erst nach Eingabe
des in `CED_DATA_PASS` gesetzten Passworts wird die lokale Patientenzuordnung
eingeblendet. Das Werkzeug liest ausdrücklich beschriftete Patienten-ID-, Namens-
und Geburtsdatumszeilen aus dem bereits erzeugten Rohtext und sucht damit lokal im
Patientenverzeichnis. Das Verzeichnis wird nicht an den KI-Anbieter übertragen.

Ein gefundener Patient ist immer nur ein Vorschlag und muss ausdrücklich bestätigt
werden. Gibt es keinen eindeutigen Treffer oder wurde kein Name erkannt, fordert die
Oberfläche zur Auswahl aus dem Verzeichnis oder zur vollständigen manuellen Eingabe
von Patienten-ID, Name und Geburtsdatum auf. Ein neuer Patient wird erst durch den
zugehörigen Bestätigungsschalter angelegt. Testpatienten können über die Oberfläche
angelegt und anschließend durch Löschen der lokalen Entwicklungsdatenbank
`data/ced_document_ai.sqlite3` vollständig entfernt werden.

> **Debugging-Hinweis:** Wenn trotz sichtbarer Stammdaten kein Vorschlag erscheint,
> zuerst prüfen, ob jede Angabe im Rohtext in einer eigenen, eindeutig beschrifteten
> Zeile wie `Patienten-ID:`, `Name:` und `Geburtsdatum:` steht. Medizinische Inhalte
> oder Stammdaten nicht zur Fehlersuche in Konsolen- oder Server-Logs ausgeben.

## CED-Prüftabelle

Nach bestätigter Patientenzuordnung kann ein als `CED-Patientenfragebogen` erkanntes
Dokument in eine vorläufige Prüftabelle übernommen werden. Der dafür verwendete
Reintextparser arbeitet auf der bereits vorhandenen strukturierten Darstellung; die
allgemeine Dokument- und Textextraktion wird dadurch nicht verändert. Erkannter
Wert, Einheit, Qualitätsstatus und unveränderte Quellzeile werden nebeneinander
angezeigt und können vor einer späteren Speicherung geprüft werden.

Die CED-Prüfung wird über den Menüpunkt „CED-Daten einlesen“ in der linken geschützten
Steuerung als eigener Vollbild-Arbeitsbereich geöffnet. Beim Klick werden die
CED-Felder unmittelbar extrahiert und in der Tabelle angezeigt; ein zusätzlicher
Extraktionsschalter ist nicht erforderlich. „Zurück zum Einlesen“ führt ohne erneute
KI-Anfrage zum Dokument zurück. Im Kopf stehen der gespeicherte Name und das
Geburtsdatum des ausdrücklich bestätigten Patienten zur Kontrolle. Umfangreiche
Befundlisten besitzen innerhalb der Tabelle einen eigenen vertikalen Scrollbereich,
sodass Befunddatum und Speicherschalter erreichbar bleiben.

Ein eindeutig beschriftetes `Befunddatum`, `Fragebogendatum`, Erhebungs- oder
Untersuchungsdatum wird aus dem bereits eingelesenen Text als Vorschlag übernommen.
Das Geburtsdatum wird dabei ausdrücklich nicht verwendet. Bei mehreren
widersprüchlichen gleichrangigen Datumsangaben oder wenn kein gültiges Datum erkannt
wird, bleibt das Feld leer und muss manuell ausgefüllt werden. Ein vorgeschlagenes
Datum kann vor der Speicherung jederzeit korrigiert werden.

Auch zusätzliche, klar mit `Feldname: Wert` beschriftete Angaben bleiben sichtbar.
Sie werden als **neue Kategorie** gekennzeichnet und sind zunächst ausdrücklich von
der Übernahme ausgeschlossen. Damit kann eine neue Kategorie später bewusst
bestätigt oder einer vorhandenen Kategorie zugeordnet werden; unbekannte Felder
werden weder automatisch dauerhaft angelegt noch verworfen. Das Befunddatum bleibt
ebenfalls eine verpflichtende manuelle Angabe.

Mit „Geprüfte CED-Daten speichern“ werden ausschließlich die in der Tabelle zur
Übernahme markierten Zeilen zusammen mit Dokumentbezug, unveränderter KI-Rohantwort
und KIS-Vorschlag in einer gemeinsamen SQLite-Transaktion gespeichert. Auch eine
neue Kategorie wird nur angelegt, wenn ihre Zeile zuvor ausdrücklich aktiviert
wurde. Schlägt ein Teil der Speicherung fehl, werden keine Teildaten übernommen.
Nach erfolgreicher Speicherung ist der Schalter für diese Prüfung gesperrt, damit
dasselbe Dokument nicht versehentlich doppelt angelegt wird. Anschließend öffnet die
Anwendung automatisch die aktualisierte Patientenübersicht. Fehlt beispielsweise das
Befunddatum oder schlägt die Transaktion fehl, bleibt die CED-Prüfung dagegen offen
und zeigt den Fehler sowohl im Prüfbereich als auch im Statusfeld an.

Solange ausschließlich Testdaten verwendet werden, kann der gesamte lokale
Testbestand bei beendeter Anwendung durch Löschen von
`data/ced_document_ai.sqlite3` entfernt werden. Dieser Schritt löscht die komplette
Datenbank und darf deshalb später mit realen Daten nicht mehr verwendet werden.

> **Debugging-Hinweis:** Erscheint eine erwartete Angabe nicht in der Prüftabelle,
> die strukturierte Darstellung auf eine eigene Zeile im Format `Feldname: Wert`
> prüfen. Unbeschrifteter Freitext wird absichtlich nicht geraten. Zum Debugging
> höchstens Feldname und Parserstatus verwenden, niemals den medizinischen Wert.

## Patientenübersicht

Nach bestätigter Patientenzuordnung steht in der geschützten Seitenleiste zusätzlich
„Patientenübersicht“ zur Verfügung. Die lesende Übersicht zeigt Name, Geburtsdatum,
Patienten-ID und das am aktuellen Tag berechnete vollendete Alter. Das Alter wird
nicht gespeichert; bei fehlendem oder zukünftigem Geburtsdatum wird ausdrücklich
„nicht berechenbar“ angezeigt.

Direkt nach Aktivierung des Datenbankmodus wird das lokale Patientenverzeichnis in
der Seitenleiste angeboten. Damit kann die Patientenübersicht auch ohne zuvor
eingelesenes Dokument geöffnet werden: Die Auswahl im Dropdown aktiviert den
Patienten unmittelbar; ein zusätzlicher Bestätigungsschalter ist nicht erforderlich.
Anschließend kann „Patientenübersicht“ aufgerufen werden. Unter dem am unteren Rand
angeordneten Schalter „Datenbankmodus beenden“ bleibt Name und Geburtsdatum des
aktiven Patienten sichtbar. Beim Dokumentwechsel wird diese Zuordnung aus
Sicherheitsgründen aufgehoben und muss erneut bestätigt werden.

Neue Patienten werden mit getrennten Feldern für Nachname und Vorname gespeichert
und in allen neuen Ansichten einheitlich als „Nachname, Vorname“ angezeigt. Die alte
Gesamtnamenspalte bleibt ausschließlich zur verlustfreien Migration bestehender
lokaler Testdatenbanken erhalten. Bestehende Namen werden nicht automatisch zerlegt,
weil dies bei mehrteiligen Namen fachlich falsche Zuordnungen erzeugen könnte.

Darunter erscheinen bereits gespeicherte Diagnosen mit Status und möglichem
Erstdiagnosedatum sowie die Werte des jüngsten bestätigten CED-Befunddatums. Ein
Eintrag mit dem ausdrücklichen Status `HAUPTDIAGNOSE` wird hervorgehoben;
unklassifizierte Diagnosen werden nicht willkürlich zugeordnet. CED-Stammdaten sowie
der medikamentöse und chirurgische Therapieverlauf bleiben ohne bestätigte Erfassung
sichtbar leer.

Die aktiven Verlaufsansichten für Labor, Calprotectin, Endoskopie, Sonografie und
MRT/CT befinden sich zentral in der geschützten Seitenleiste. Jede Ansicht zeigt nur
bestätigte Werte ihrer ausdrücklich zugeordneten Fachgruppe in einer scrollbaren
Zeitmatrix. Die redundante Fachansicht innerhalb der Patientenübersicht entfällt. Es
wird kein Ersatzinhalt aus Freitext oder medizinischem Allgemeinwissen erzeugt.

Die Fachansicht „Klinischer Verlauf“ ist bereits aktiv. Sie stellt sämtliche
bestätigten Kategorien aus CED-Fragebögen als kumulative Tabelle dar: Kategorien
stehen in den Zeilen, Befundzeitpunkte in dynamisch erzeugten Spalten. Dadurch lassen
sich beispielsweise Stuhlfrequenz, Blut im Stuhl, Bauchschmerzen, Skalenwerte und
Gewicht über mehrere Fragebögen vergleichen. Die Parameter-Spalte bleibt beim
horizontalen Scrollen sichtbar; viele Parameter und Datumswerte können innerhalb der
Tabelle vertikal beziehungsweise horizontal gescrollt werden. Laborwerte bleiben
bewusst außerhalb dieser Ansicht und werden ausschließlich in der eigenen aktiven
Laboransicht dargestellt.

Auch die kompakte Tabelle des letzten CED-Befunds besitzt nun einen begrenzten
Scrollbereich und kann den Patientenbildschirm nicht mehr unbegrenzt verbreitern oder
verlängern. Erstdiagnose und Befallsmuster starten als schreibgeschützte Formfelder.
Über „Stammdaten bearbeiten“ können fehlende oder zu korrigierende Angaben bewusst
freigegeben und gespeichert werden. Jede Speicherung legt eine neue bestätigte
Version mit der Quelle „MANUELL“ und einem Audit-Eintrag an; ältere Versionen bleiben
erhalten. Leere Felder löschen keine frühere Angabe und unveränderte Werte werden
nicht erneut versioniert. Die automatische Übernahme solcher Stammdaten aus
Dokumenten bleibt einem späteren, ebenfalls bestätigungspflichtigen Schritt
vorbehalten.

> **Debugging-Hinweis:** Bleibt die Übersicht trotz gespeicherter CED-Werte leer,
> zunächst prüfen, ob `confirmed_by_user` gesetzt ist und `patient_id` mit dem oben
> bestätigten Patienten übereinstimmt. In Debug-Ausgaben nur IDs und Trefferanzahlen,
> niemals Namen, Diagnosen oder Befundwerte verwenden.

## Synthetische Demo-Daten

Für die visuelle Prüfung können fünf vollständig erfundene Patienten mit Haupt- und
Nebendiagnosen, CED-Stammdaten, medikamentösem und chirurgischem Therapieverlauf
sowie jeweils drei Zeitpunkten für Fragebogen, Labor, Calprotectin, Endoskopie,
Sonografie, MRT und CT angelegt werden:

```bash
PYTHONPATH=. python scripts/seed_demo_data.py
```

Der Seeder läuft niemals automatisch und verwendet ausschließlich die reservierten
Patienten-IDs `DEMO-001` bis `DEMO-005`. Existiert bereits eine davon, bricht er mit
einer verständlichen Meldung ab, statt Datensätze zu überschreiben oder doppelt
anzulegen. Die Werte sind medizinisch frei erfunden und dürfen nicht als fachliche
Referenz verwendet werden. Zum Entfernen der Testdaten kann – solange garantiert
keine realen Daten enthalten sind – die lokale Entwicklungsdatenbank gelöscht werden.

## Verbleibende Entwicklungsschritte

1. **Dokumentbasierte Fachparser:** Labor-, Endoskopie-, Sonografie- und
   Schnittbilddokumente benötigen je Dokumenttyp eigene Extraktions- und
   Bestätigungsregeln, bevor ihre Werte aus realen Dokumenten gespeichert werden.
2. **Stammdatenmigration prüfen:** Altdaten mit ungetrenntem Gesamtnamen benötigen
   eine manuelle Prüfmaske; eine automatische Zerlegung ist absichtlich ausgeschlossen.
3. **Diagnose- und Therapieeditor:** Haupt-/Nebendiagnosen und Therapieverläufe sind
   in der Übersicht sichtbar, benötigen für den Produktivbetrieb aber noch eine
   versionierte manuelle Bearbeitung mit Dokumentquelle und Auditspur.
4. **Calprotectin-Grafik:** Zusätzlich zur jetzt aktiven Tabelle ist die geplante
   skalierbare Zeitgrafik mit Datum auf der X- und Messwert auf der Y-Achse umzusetzen.
5. **Berechtigungen und Betrieb:** Vor realen Patientendaten sind Benutzerkonten,
   Rollen, Sitzungsablauf, verschlüsselte Datensicherung und ein Lösch-/Exportkonzept
   festzulegen und technisch abzusichern.
