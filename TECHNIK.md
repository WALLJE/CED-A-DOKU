# Technische Übersicht

Dieses Dokument richtet sich an Entwicklerinnen und Entwickler. Es beschreibt die
zentralen Programmteile, Zustände und die Grenze zwischen KI-Verarbeitung und
deterministischer Logik. Fachliche Bedienhinweise stehen weiterhin in der README.

## Einstieg und Laufzeit

- `main.py` ruft `ced_document_ai.medical_ui.starte_anwendung()` auf.
- `medical_ui.py` baut die NiceGUI-Oberfläche und hält pro Browserverbindung einen
  `Sitzungszustand`. Darin liegen nur temporäre Uploadseiten, KI-Ausgaben,
  Patientenauswahl und noch nicht gespeicherte Prüftabellen.
- `config/settings.py` liest unter anderem `CED_DATA_PASS`, `CED_DATABASE_PATH`,
  Provider-Schlüssel und Modellnamen aus der Umgebung.
- `database/database.py` erzeugt die SQLAlchemy-Session und führt die wenigen
  ausdrücklich implementierten SQLite-Spaltenerweiterungen aus.
- `database/models.py` enthält das relationale Modell. Medizinische Einzelwerte
  werden als `Finding` mit `FindingCategory`, Quelldokument und Bestätigungsstatus
  gespeichert.

## Dokumentworkflow

1. Die Oberfläche sammelt PDF- oder Bildseiten im temporären Sitzungsordner.
2. `services/ai/providers.py` sendet die Seiten an den bewusst ausgewählten Provider.
3. `services/ai/document_workflow.py` definiert erlaubte `Dokumenttyp`-Werte, den
   Prompt und das strikt geparste Antwortformat aus Rohtext, strukturierter
   Darstellung und KIS-Vorschlag.
4. `services/ced/patient_matching.py` liest nur klar bezeichnete Patientenmerkmale
   und vergleicht sie lokal mit dem ausgewählten Patienten.
5. Dokumenttypspezifische Parser erzeugen temporäre Tabellenzeilen. Erst eine
   manuelle Auswahl und Datumsbestätigung ruft einen Speicherdienst auf.

Wichtige Zustandsvariablen in `Sitzungszustand` sind `seiten`, `dokumentnamen`,
`dokumenttyp`, `ausgelesener_inhalt`, `strukturierte_darstellung`, `kis_vorschlag`,
`kis_vorschlag_ausfuehrlich`,
`rohe_ki_antwort`, `patient_id`, `patientenabgleich_erlaubt`, `ced_befunde`,
`labor_befunde`, `arztbrief_abschnitte` und `fachbefund_abschnitte`.

## Regelbasierte Dienste

- `questionnaire_parser.py`: CED-Standardfelder, Synonyme, Werte und Einheiten.
- `validation.py`: technische Wertebereichs- und Einheitenhinweise ohne Korrektur.
- `laboratory_parser.py`: Tabellen- und Langformat für Labor, Virologie,
  Mikrobiologie und Calprotectin.
- `letter_parser.py`: vorhandene, ausdrücklich überschriebene Arztbriefabschnitte.
- `procedure_parser.py`: beschriftete Endoskopie- und Sonografieabschnitte. SES-CD
  und CDEIS werden nur für Morbus Crohn, UC-EIS nur für Colitis ulcerosa als passend
  markiert; kein Score wird aus Freitext berechnet.
- `document_categories.py`: kontrollierte Zuordnung von Dokumenttypen zu sichtbaren
  Fachgruppen.
- `patient_overview.py`: ausschließlich lesende Patienten-, Pivot-, Archiv- und
  Längsansichten bestätigter Daten.

Die zugehörigen Module `storage.py`, `laboratory_storage.py`,
`document_storage.py` und `patient_profile.py` führen die atomaren Schreibvorgänge
und technischen Audit-Einträge aus. Ein Fehler bricht den jeweiligen Vorgang ab;
es wird kein Teilbestand als Fallback gespeichert.

## Wann KI verwendet wird

KI wird ausschließlich für diese dokumentbezogenen Aufgaben eingesetzt:

- Transkription sichtbarer Dokumentseiten,
- Vorschlag eines Dokumenttyps aus dem festen Katalog,
- originalnahe strukturierte Darstellung,
- kompakter und ausführlicher KIS-Textvorschlag,
- bei mehreren Seiten ein Vorschlag zur logischen Reihenfolge anhand sichtbarer
  Seitenzahlen und inhaltlicher Anschlüsse.

KI ordnet niemals selbstständig einen Patienten zu und schreibt nicht direkt in die
Datenbank. Sie darf keine fehlenden Werte, Diagnosen, Referenzbereiche, Einheiten
oder Aktivitätsscores ergänzen.

## Wann Regeln oder manuelle Entscheidungen verwendet werden

- Patientensuche und Stammdatenvergleich erfolgen lokal und regelbasiert.
- Datumserkennung verwendet eng gefasste beschriftete Muster.
- Fachparser akzeptieren nur bekannte Feldnamen oder Tabellenformen.
- Plausibilitätsprüfungen markieren Auffälligkeiten, ändern aber keinen Wert.
- Duplikatprüfung vergleicht derzeit die vollständige gespeicherte KI-Rohantwort
  bytegenau; eine unsichere Ähnlichkeitssuche findet nicht statt.
- Patient, Dokumentdatum und jede zu speichernde Tabellenzeile werden vom Benutzer
  bestätigt. Die Schalter „Alle auswählen“ und „Alle abwählen“ sind ausdrückliche
  Sammelaktionen und keine automatische Freigabe.

## Tests und Debugging

Die fachlichen Tests liegen unter `tests/` und laufen mit:

```bash
PYTHONPATH=. pytest -q
```

Für Parserfehler zuerst die strukturierte Darstellung, den erkannten Dokumenttyp
und die bekannte Feldliste prüfen. In Logs gehören nur technische IDs,
Trefferanzahlen und Exception-Typen, niemals Namen, Dokumenttexte oder Befundwerte.
Neue Dokumentparser sollen ohne universellen Freitext-Fallback implementiert und mit
synthetischen positiven, fehlenden, widersprüchlichen und unbekannten Feldern
getestet werden.
