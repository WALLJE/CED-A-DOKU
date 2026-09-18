# Umsetzungsstand und nächste Schritte

Stand: 18. September 2026

Dieses Dokument gleicht den früheren Umsetzungsplan mit dem derzeitigen Quellcode
und den automatisierten Tests ab. Es ersetzt weder den fachlichen Gesamtplan in
`projektplan.md` noch behauptet es eine klinische Validierung. „Umgesetzt“ bedeutet
hier ausschließlich, dass ein nachvollziehbarer Codepfad vorhanden ist.

## Kurzfazit

Der im früheren Plan empfohlene End-to-End-Grundpfad ist weitgehend vorhanden:

> Passwort eingeben → Patient bewusst auswählen → vorhandenes CED-Ergebnis parsen
> → Werte prüfen/korrigieren → Befund atomar speichern → bestätigten Verlauf anzeigen

Die normale Dokumentauslesung blieb davon getrennt. Patientenabgleich, Parser,
Prüftabelle, transaktionale Speicherung, kompakte Patientenübersicht und dynamische
Pivot-Ansichten sind implementiert und durch fachliche Unit-Tests abgedeckt.

Der Grundpfad ist dennoch fachlich noch nicht abgeschlossen. Als nächster Schritt
soll deshalb die CED-Prüfung vervollständigt werden, bevor longitudinale Auswertungen
oder weitere Dokumentarten hinzukommen.

## Abgleich mit dem früheren Plan

| Arbeitspaket | Stand | Im Bestand vorhanden | Noch offen |
| --- | --- | --- | --- |
| 1. Zugriffsschranke | weitgehend umgesetzt | `CED_DATA_PASS`, zeitkonstanter Vergleich, geschützte Navigation, Leeren der Patientenauswahl beim Sperren | Benutzerkonten, Rollen, automatischer Sitzungsablauf und systematischer UI-Zugriffstest |
| 2. Patientenverwaltung | umgesetzt | Eindeutige externe ID, Suche/Auswahl, Neuanlage, getrennte Namen, lokaler Stammdatenabgleich, sichtbarer aktiver Patient | Manuelle Prüfmaske für Altdaten mit ungetrenntem Namen; optional eine zusätzliche finale Patientenbestätigung direkt vor dem Speichern |
| 3. CED-Reintextparser | weitgehend umgesetzt | Fester Katalog, Synonyme, Quellzeile, Zahlen/Einheiten, `UNREADABLE`, `UNCERTAIN`, `CONFLICT`, sichtbare `MISSING`-Zeilen, technische Wertebereichs- und Einheitenprüfung sowie neue Kategorien als ungeprüfte Vorschläge | Fachlich freizugebende Erweiterungen der bewusst kleinen Regelliste |
| 4. Temporäre Prüftabelle | teilweise umgesetzt | Editierbare Werte/Kategorien/Einheiten, Quelle, Qualitätsstatus, problematische Werte zuerst, Übernahme-Checkbox, neue und widersprüchliche Kategorien zunächst abgewählt | Bekannte sichere Felder sind standardmäßig zur Übernahme markiert statt einzeln bestätigt; „Auf KI-Wert zurücksetzen“ fehlt; Original und Extraktion stehen nicht nebeneinander; die Qualität ist nicht eigenständig editierbar |
| 5. Atomare Speicherung | umgesetzt | Pflichtdatum, bewusste Patientenzuordnung, Dokument, Rohantwort, KIS-Text und Befunde in einer Transaktion, Audit-Metadaten, Duplikatwarnung | Revisionshistorie für nachträgliche Befundkorrekturen und optionaler Originaldatei-/Seitenbezug fehlen; Migrationen sind noch nicht allgemein gelöst |
| 6. Patientenverlauf | teilweise umgesetzt | Dynamische CED-Pivot-Tabelle und getrennte Fach-Pivots, ausschließlich bestätigte Befunde, chronologische Werte | Die geplante Längstabelle sowie Datums-, Kategorie-, Dokumenttyp- und Bestätigungsfilter fehlen |
| 7. Kompakte Übersicht | teilweise umgesetzt | Stammdaten, Alter, Diagnosen, CED-Stammdaten, Therapieverlauf und Werte des letzten bestätigten CED-Befunds | Letzte KIS-Zusammenfassung, letzter Wert plus Veränderung für CRP/Hb/Calprotectin, aktuelle Auffälligkeiten und Wiedervorlagen fehlen |

## Stand der damaligen Iterationen

### Iteration 1 – sicherer Grundpfad: fast abgeschlossen

Der funktionale Weg bis zur gespeicherten patientenbezogenen Ansicht ist vorhanden.
Für den fachlich formulierten Abschluss fehlen vor allem:

1. eine echte Längstabelle mit den vorgesehenen Filtern,
2. eine ausdrückliche Einzelbestätigung auch der zunächst sicheren Zeilen,
3. „Auf KI-Wert zurücksetzen“ in der Prüftabelle,
4. automatisierte Tests der Zugriffsschranke und des Sperrens der Oberfläche.

### Iteration 2 – klinische Bedienung: teilweise abgeschlossen

Die Pivot-Ansicht, Qualitätskennzeichnung und getrennte Speicherung des KIS-Texts
sind vorhanden. Noch nicht umgesetzt sind:

1. Originalvorschau und Extraktion nebeneinander mit Feldbezug,
2. separat editierbare KIS-Varianten „kompakt“ und „ausführlich“,
3. technische Prüfung auffälliger Änderungen gegenüber bestätigten Vorwerten,
4. eine kontrollierte Katalogzuordnung neuer Kategorien mit Synonym- und
   Dublettenprüfung.

### Iteration 3 – Verlauf und Warnungen: überwiegend offen

Das Datenmodell enthält bereits Warnungen, Wiedervorlagen und Präferenzen, aber die
zugehörigen Dienste und Oberflächen fehlen. Offen sind:

1. Vergleich mit dem letzten bestätigten Fragebogen,
2. strukturierte Änderungszustände wie `NEU`, `VERBESSERT` und
   `NICHT VERGLEICHBAR`,
3. regelbasierte Warnungen vor einer späteren KI-Trendbewertung,
4. Feedback zu Warnungen und konfigurierbare Regeln,
5. grafische Verläufe ausschließlich aus bestätigten Daten,
6. Wiedervorlagen und offene Befunde im Patientendashboard.

## Weitere offene Punkte aus dem Gesamtprojektplan

Diese Anforderungen gehörten nicht zum schmalen ersten CED-Grundpfad und sind noch
nicht oder nur als Datenmodell vorbereitet:

- Fachparser und bestätigungspflichtiger Import für Labor, Calprotectin,
  Endoskopie, Sonografie sowie MRT/CT; die vorhandenen Fachansichten lesen bislang
  nur bereits gespeicherte beziehungsweise synthetische Werte.
- Dokumentvergleich für Arztbriefe, Medikamentenpläne und Befunde.
- Dokumentgestützte, kumulative Diagnose- und Medikationsübernahme. Die aktuelle
  manuelle Pflege ist versioniert, ersetzt aber diesen Importworkflow nicht.
- Excel-/CSV-Export der Längs- und Auswahldaten.
- Backup- und Wiederherstellungsfunktion, Verschlüsselungskonzept sowie
  Lösch-/Exportkonzept für reale Patientendaten.
- Vollwertige Datenbankmigrationen. Derzeit existiert nur eine gezielte
  SQLite-Erweiterung für `first_name` und `last_name`; `create_all()` ist kein
  allgemeiner Migrationsweg.
- Konfigurierbare Promptverwaltung in der Oberfläche. Der Dokumentworkflow besitzt
  feste Prompts, aber noch keinen fachlich versionierten Prompteditor.
- Breitere Fehler- und Integrationsprüfungen für API-Ausfall, fehlerhafte
  KI-Antworten, mehrere Sitzungen und Browser-Neuladen.

## Empfohlene neue Reihenfolge

### Priorität 1 – ersten CED-Workflow fachlich abschließen

1. Längstabelle samt Datums-, Kategorie- und Dokumenttypfiltern ergänzen.
2. KIS kompakt/ausführlich getrennt anzeigen, bearbeiten und speichern.
3. Die noch fehlenden Unit-, Transaktions- und Zugriffstests ergänzen und mit
   anonymisierten realistischen Fragebogenfällen fachlich abnehmen.

### Unmittelbar nächstes Arbeitspaket

Die regelbasierte technische Plausibilitätsprüfung ist umgesetzt. Sie prüft
vorhandene numerische Werte und Einheiten in einem eigenen Dienst, verändert keine
Angabe und zeigt Auffälligkeiten lediglich als Prüfhinweis mit Qualitätsstatus an.
`MISSING`- und `UNREADABLE`-Zeilen werden dabei nicht interpretiert. Als Nächstes
folgt die patientenbezogene Längstabelle mit Datums-, Kategorie- und
Dokumenttypfiltern.

### Priorität 2 – longitudinaler klinischer Nutzen

1. Deterministischen Vorbefundvergleich aus bestätigten Werten erstellen.
2. Regelbasierte Warnungen und Änderungsanzeige einführen.
3. Dashboard um Labor-Kernwerte, letzte KIS-Zusammenfassung und Wiedervorlagen
   erweitern.
4. Bestätigte numerische Werte als auswählbare Zeitreihen darstellen.

### Priorität 3 – weitere Dokumentarten

Erst danach sollte der Laborparser als nächster Importtyp folgen. Anschließend sind
Calprotectin, Endoskopie, Sonografie und MRT/CT jeweils als eigener, getesteter
Parser- und Freigabepfad umzusetzen. Ein allgemeiner Fallbackparser soll dabei nicht
eingeführt werden; unbekannte Inhalte bleiben sichtbar ungeklärt.

### Priorität 4 – Ausbau

Dokumentenvergleich, dynamischer Befundkatalog, Export, konfigurierbare Warnregeln
und erst zuletzt eine klar gekennzeichnete KI-Trendbewertung ergänzen. KI-Bewertungen
dürfen bestätigte Messwerte nie verändern.

## Prüfstand

Die fachlichen Tests laufen mit `PYTHONPATH=.` vollständig durch (52 Tests). Der
Aufruf `pytest -q` ohne gesetzten Projektpfad kann in der aktuellen Umgebung das
lokale Paket nicht importieren. Außerdem meldet SQLAlchemy derzeit Warnungen wegen
der Verwendung von `datetime.utcnow`; die Umstellung auf zeitzonenbewusste
Zeitstempel sollte zusammen mit der Migration geplant werden, nicht als unbemerkte
Schemaänderung.

Die Tests belegen einzelne Dienste und Datenbankpfade. Sie ersetzen keine klinische
Validierung, keine Datenschutzprüfung und keinen Ende-zu-Ende-Test im Browser.
