Erstelle eine vollständige, lokal installierbare Desktop-Anwendung zur KI-gestützten Auswertung medizinischer Dokumente bei Patientinnen und Patienten mit chronisch-entzündlichen Darmerkrankungen (CED).

Die Anwendung soll insbesondere papierbasierte CED-Patientenfragebögen verarbeiten, die eingescannt, fotografiert oder als Screenshot eingefügt werden. Zusätzlich sollen Arztbriefe, Laborbefunde, PDF-Dateien und weitere medizinische Dokumente verarbeitet werden können.

Die Anwendung verfolgt vier Hauptziele:

1. Strukturierte Extraktion definierter medizinischer Befunddaten.
2. Patientbezogene longitudinale Verlaufsdarstellung.
3. Erstellung klinischer Zusammenfassungstexte für die Dokumentation im KIS.
4. KI-gestützte Erkennung relevanter Veränderungen, Auffälligkeiten und neuer Befundkategorien.

Die Anwendung ist ausdrücklich als Assistenzsystem zu konzipieren. KI-Ergebnisse dürfen nicht ungeprüft als endgültige medizinische Fakten übernommen werden.

# 1. Technischer Rahmen

Bevorzugter Stack:

* Python 3
* PySide6 für die Desktop-GUI
* SQLite als lokale Datenbank
* SQLAlchemy als ORM
* pandas für Tabellen- und Pivot-Funktionen
* matplotlib oder Qt-basierte Charts für grafische Verläufe
* openpyxl für Excel-Export
* konfigurierbare REST/API-Schnittstelle zu einem multimodalen KI-Modell
* sichere Speicherung von Konfigurationsdaten und API-Zugangsdaten

Die KI-Anbindung muss abstrahiert sein:

```python
class DocumentAI:
    def analyze(self, document, document_type, categories, prompt_config):
        pass
```

Mögliche Implementierungen:

```text
DocumentAI
    ├── CloudAPIProvider
    ├── LocalAPIProvider
    └── weiterer Provider
```

Der restliche Programmcode darf nicht fest an einen KI-Anbieter gekoppelt sein.

# 2. Dokumentimport

Die Anwendung soll ein großes Dokumentfeld besitzen.

Unterstützt werden müssen:

* Screenshot aus der Windows-Zwischenablage per STRG+V
* mehrere Screenshots nacheinander
* Drag & Drop von PDF-Dateien
* Drag & Drop von JPG-Dateien
* Drag & Drop von PNG-Dateien
* Datei-Auswahldialog

Mehrere Screenshots können zu einem gemeinsamen Dokument gehören.

Nach dem Einfügen sollen Seiten als Vorschau dargestellt werden.

Funktionen:

* Seite anzeigen
* Seite vergrößern
* Seite löschen
* Reihenfolge verändern
* weitere Seite hinzufügen
* neues Dokument beginnen

# 3. Automatische Dokumenttyperkennung

Die KI soll zunächst versuchen, den Dokumenttyp automatisch zu erkennen.

Mindestens folgende Typen:

* CED-Patientenfragebogen
* Laborbefund
* Arztbrief
* Medikamentenplan
* Bildgebender Befund
* sonstiges medizinisches Dokument

Die erkannte Kategorie wird dem Benutzer angezeigt.

Beispiel:

```text
Dokumenttyp erkannt:
CED-Patientenfragebogen

Sicherheit:
hoch

[bestätigen]
[Dokumenttyp ändern]
```

Bei unsicherer Erkennung soll automatisch eine Auswahlliste angeboten werden.

Der Benutzer kann den Dokumenttyp jederzeit korrigieren.

Für den bekannten papierbasierten CED-Fragebogen soll die automatische Erkennung besonders robust implementiert werden, da das Layout weitgehend konstant ist.

# 4. Spezieller Workflow für den CED-Patientenfragebogen

Der CED-Fragebogen enthält:

* Textangaben
* Auswahlfelder
* numerische bzw. visuell markierte Skalen
* anatomische Skizzen
* handschriftliche Angaben

Die KI muss daher sowohl Text als auch visuelle Markierungen interpretieren.

Nach der Analyse entstehen zwei strikt getrennte Ergebnisbereiche:

## A. Strukturierte Fragebogendaten

Diese werden longitudinal gespeichert.

## B. KIS-Dokumentationstext

Dieser wird separat gespeichert und nicht in die tabellarischen Befunddaten übernommen.

# 5. Standardprompt für den CED-Fragebogen

Integriere folgenden Prompt als editierbaren Standardprompt des Dokumenttyps „CED-Patientenfragebogen“:

```text
Analysiere das beigefügte Bild eines Patientenfragebogens zum Thema Darmerkrankungen. Führe die Datenextraktion und eine Zusammenfassung nach folgenden Regeln durch:

Formatierung:
Gib das Ergebnis als schlichten Reintext aus.
Verwende keine einleitenden Sätze.
Verwende keine Markdown-Tabellen und keine fettgedruckten Überschriften.

Datenextraktion:

Beginne mit:

Daten aus Fragebogen:

Liste folgende Felder auf:

Stuhlfrequenz
Stuhlgang nachts
Blut im Stuhl
Schleim im Stuhl
Bauchschmerzen
Allgemeinbefinden
Gewicht
Gewichtsverlust
Fieber
Nachtschweiß
Gelenkschmerzen
Hautveränderungen
Auffälligkeiten Analregion

Wichtig für Skalen:

Werte für Bauchschmerzen und Allgemeinbefinden sind anhand der Markierungen auf der 6er-Skala als numerischer Wert zu extrahieren.

Berücksichtige explizit visuelle Markierungen in anatomischen Skizzen, zum Beispiel eingekreiste Bereiche am Bauch oder am Gesäß, und ordne diese dem passenden Feld zu.

Sollte ein Text unleserlich sein, vermerke:

unleserlich

Zusammenfassung:

Erstelle unter:

ZUSAMMENFASSUNG:

einen kurzen, medizinisch präzisen Fließtext.

Fasse Symptome, körperliche Befunde einschließlich Markierungen in Bildern sowie systemische Angaben wie Gewicht, Fieber usw. zusammen.

Ausgabeformat:

Daten aus Fragebogen:
Stuhlfrequenz: [x] pro Tag
Stuhlgang nachts: [...]
Blut im Stuhl: [...]
Schleim im Stuhl: [...]
Bauchschmerzen: [Beschreibung] (VAS [x] von 6), ggf. Markierung in Skizze
Allgemeinbefinden: [Beschreibung] ([x] von 6)
Gewicht: [x] kg
Gewichtsverlust: [...]
Fieber: [...]
Nachtschweiß: [...]
Gelenkschmerzen: [...]
Hautveränderungen: [...]
Auffälligkeiten Analregion: [...], ggf. Markierungen in der Skizze

Nur sofern Daten vorhanden:

Aktuelle Medikamente
Neue Aspekte (Was sollten wir wissen?)
Fragen des Patienten

ZUSAMMENFASSUNG:
[medizinischer Zusammenfassungstext]
```

# 6. Robuster Parser ohne zwingendes JSON

Die Anwendung darf nicht von frei generiertem JSON abhängig sein.

Die KI-Antwort des CED-Fragebogens soll anhand bekannter Feldnamen analysiert werden.

Beispiel:

```text
Stuhlfrequenz: 4 pro Tag
Stuhlgang nachts: nein
Blut im Stuhl: gelegentlich
Bauchschmerzen: moderat (VAS 3 von 6)
Gewicht: 74 kg
```

Der Parser muss tolerant sein gegenüber:

* zusätzlichen Leerzeichen
* kleinen Schreibabweichungen
* fehlenden Feldern
* unleserlichen Angaben
* zusätzlichen Kommentaren
* leeren Feldern
* verschiedenen Einheiten

Die vollständige KI-Rohantwort soll zusätzlich archiviert werden.

# 7. Initiale CED-Befundkategorien

Initial sollen mindestens folgende Kategorien vorhanden sein:

```text
CED-Fragebogen
    Stuhlfrequenz
    Stuhlgang nachts
    Blut im Stuhl
    Schleim im Stuhl
    Bauchschmerzen
    Bauchschmerzen VAS
    Allgemeinbefinden
    Allgemeinbefinden Skalenwert
    Gewicht
    Gewichtsverlust
    Fieber
    Nachtschweiß
    Gelenkschmerzen
    Hautveränderungen
    Auffälligkeiten Analregion
    Aktuelle Medikamente
    Neue Aspekte
    Fragen des Patienten
```

Zusätzlich sollen für CED insbesondere folgende Laborparameter vorbereitet sein:

```text
Labor
    CRP
    Hb
    Calprotectin
```

Weitere Laborparameter können dynamisch ergänzt werden.

# 8. Qualitätsanzeige pro extrahiertem Feld

Die KI soll möglichst für jedes extrahierte Feld eine Qualität bzw. Sicherheit liefern.

Beispiel:

```text
Gewicht: 74 kg              ✓ sicher
Stuhlfrequenz: 6 / Tag      ✓ sicher
Bauchschmerz: 3 / 6         ? unsicher
Analregion: unleserlich     ! prüfen
```

Dazu sollen intern mindestens folgende Zustände unterstützt werden:

```text
HIGH_CONFIDENCE
UNCERTAIN
UNREADABLE
CONFLICT
MISSING
```

Unsichere, widersprüchliche oder unleserliche Felder sollen in der Prüfansicht automatisch priorisiert werden.

Beim Öffnen der Prüfmaske springt die Anwendung zuerst zu problematischen Feldern.

Die KI darf Unsicherheit nicht durch erfundene Werte ersetzen.

# 9. Plausibilitätsprüfung

Nach der KI-Extraktion muss eine zusätzliche Plausibilitätsprüfung stattfinden.

Diese Prüfung darf Werte nicht automatisch verändern.

Sie markiert lediglich auffällige Angaben.

Beispiele:

```text
Gewicht: 7 kg
→ möglicherweise unplausibel für erwachsenen Patienten

Stuhlfrequenz: 40 / Tag
→ außergewöhnlich hoher Wert, bitte prüfen

Blut im Stuhl: nein
Freitext: "häufig Blut im Stuhl"
→ widersprüchliche Angaben erkannt
```

Es sollen mehrere Prüfmechanismen vorgesehen werden:

## A. technische Plausibilitätsregeln

Beispielsweise:

* numerischer Wertebereich
* Einheiten
* fehlende Dezimalstellen
* ungewöhnlich große Änderung zum Vorwert

## B. KI-basierte Plausibilitätsprüfung

Die KI soll den Fragebogen bzw. das Dokument auf interne Widersprüche prüfen.

Sie darf diese nicht korrigieren, sondern nur kennzeichnen.

Beispiel:

```text
Plausibilitätswarnung:
Angabe "Blut im Stuhl: nein" widerspricht der Freitextangabe "seit einer Woche wieder Blut".
```

Die Architektur muss offen bleiben, damit später definierte regelbasierte Prüfungen ergänzt oder KI-Prüfungen ersetzt werden können.

# 10. Vergleich mit dem letzten Fragebogen

Nach Einlesen eines neuen CED-Fragebogens sollen automatisch die Werte mit dem letzten bestätigten Fragebogen desselben Patienten verglichen werden.

Beispiel:

```text
Änderungen seit 15.05.2026:

Stuhlfrequenz:
3 → 7 / Tag

Stuhlgang nachts:
nein → ja
NEU

Gewicht:
78,2 → 74,0 kg
−4,2 kg

Bauchschmerz:
1 / 6 → 4 / 6

Blut im Stuhl:
nein → gelegentlich
```

Unterstütze die Zustände:

```text
NEU
VERBESSERT
VERSCHLECHTERT
UNVERÄNDERT
NICHT MEHR ANGEGEBEN
NICHT VERGLEICHBAR
```

Die Bewertung „verbessert/verschlechtert“ darf zunächst KI-basiert erfolgen, soll aber als separate Bewertung gespeichert werden.

Die ursprünglichen Werte bleiben unverändert.

# 11. KI-basierte Trend- und Warnansicht

Die Anwendung soll aus longitudinalen Daten klinisch relevante Veränderungen hervorheben können.

Beispiele:

* deutliche Zunahme der Stuhlfrequenz
* neu aufgetretener nächtlicher Stuhlgang
* neu aufgetretenes Blut
* Gewichtsverlust
* Fieber
* Verschlechterung des Allgemeinbefindens
* deutlicher Anstieg der Bauchschmerzen
* auffälliger Verlauf von CRP
* auffälliger Verlauf von Calprotectin
* Abfall des Hb

In Version 1 soll die Bewertung primär KI-gestützt erfolgen.

Die KI soll ihre Bewertung kurz begründen.

Beispiel:

```text
Auffälligkeit:
Mögliche klinische Verschlechterung

Begründung:
Stuhlfrequenz von 3 auf 7/Tag gestiegen, nächtlicher Stuhlgang neu und Blut im Stuhl neu angegeben.
```

Wichtig:

* KI-Bewertungen sind Vorschläge.
* Sie werden klar als KI-Bewertung gekennzeichnet.
* Sie dürfen keine strukturierten Messwerte verändern.
* Sie dürfen nicht automatisch Therapieentscheidungen auslösen.

Die Softwarearchitektur muss zusätzlich ein zukünftiges regelbasiertes Warnsystem ermöglichen.

# 12. Lernendes bzw. konfigurierbares Warnsystem

Das System soll so vorbereitet werden, dass der Benutzer KI-Warnungen bewerten kann.

Beispiel:

```text
KI markiert:
Gewichtsverlust von 1,5 kg als relevant.

[relevant]
[nicht relevant]
[für diesen Patienten relevant]
[ähnliche Veränderungen künftig immer markieren]
```

Diese Rückmeldungen sollen zunächst als strukturierte Benutzerpräferenzen gespeichert werden.

Es soll ausdrücklich kein unkontrolliertes selbstständiges Modelltraining stattfinden.

Stattdessen soll eine nachvollziehbare Präferenz- bzw. Regelbasis aufgebaut werden.

Beispiel:

```text
Benutzerpräferenz:
Gewichtsverlust > 3 kg innerhalb von 3 Monaten hervorheben.
```

Später kann daraus ein regelbasiertes bzw. lernendes System entwickelt werden.

# 13. CED-Dashboard pro Patient

Für jeden Patienten soll eine kompakte klinische Übersichtsseite vorhanden sein.

Sie zeigt mindestens:

```text
Patient
Name
Geburtsdatum
Diagnosen
Datum letzter Vorstellung
```

Danach:

## Letzter CED-Fragebogen

* Datum
* Stuhlfrequenz
* nächtlicher Stuhlgang
* Blut
* Bauchschmerzen
* Allgemeinbefinden
* Gewicht

## Wichtige Laborwerte

* CRP
* Hb
* Calprotectin

jeweils mit:

* letztem Wert
* Datum
* Veränderung zum Vorwert

## Aktuelle Auffälligkeiten

Beispiele:

```text
! Stuhlfrequenz 3 → 7/Tag
! nächtlicher Stuhlgang neu
! Gewichtsverlust −4,2 kg
! Calprotectin 220 → 840 µg/g
```

## Letzte KIS-Zusammenfassung

Anzeige des zuletzt erzeugten Dokumentationstextes.

## Wiedervorlagen / offene Befunde

Ein Befund oder Dokument soll manuell zur Wiedervorlage markiert werden können.

Beispiel:

```text
Wiedervorlage:

[ ] Calprotectin bei nächster Vorstellung prüfen
[ ] MRT-Befund besprechen
[ ] Verlauf nach Therapieänderung beurteilen
```

Eine Wiedervorlage benötigt mindestens:

```text
patient_id
text
source_document optional
created_at
due_date optional
status
completed_at optional
```

# 14. Grafische Verläufe

Numerische Parameter sollen als Zeitverlauf dargestellt werden können.

Mindestens:

* Gewicht
* Stuhlfrequenz
* Bauchschmerz-Skalenwert
* Allgemeinbefinden-Skalenwert
* CRP
* Hb
* Calprotectin

Der Benutzer kann Parameter über Checkboxen auswählen.

Beispiel:

```text
[x] Gewicht
[x] Stuhlfrequenz
[ ] CRP
[x] Calprotectin
[ ] Hb
```

Jeder Parameter soll über die Zeit dargestellt werden.

Die grafische Darstellung muss auf den bestätigten Daten basieren, nicht direkt auf ungeprüften KI-Ergebnissen.

# 15. Dokumentenvergleich

Die Anwendung soll zwei medizinische Dokumente desselben Patienten vergleichen können.

Insbesondere bei:

* Arztbriefen
* Medikamentenplänen
* Befunden
* Entlassungsbriefen

sollen Änderungen erkannt werden.

Kategorien:

```text
NEU
UNVERÄNDERT
GEÄNDERT
NICHT MEHR ERWÄHNT
UNSICHER
```

Beispiele:

```text
Medikation

NEU:
Azathioprin 100 mg

GEÄNDERT:
Prednisolon 20 mg → 10 mg

NICHT MEHR ERWÄHNT:
Mesalazin
```

oder:

```text
Diagnosen

NEU:
Eisenmangelanämie

UNVERÄNDERT:
Morbus Crohn

NICHT MEHR ERWÄHNT:
keine automatische Löschung!
```

# 16. Diagnosen als kumulative Patienteninformation

Das Diagnosenfeld darf niemals einfach durch die Diagnosen eines neuen Dokuments überschrieben werden.

Diagnosen müssen als separate strukturierte Einträge geführt werden.

Mindestens:

```text
diagnosis_id
patient_id
diagnosis_name
diagnosis_code optional
first_diagnosis_date optional
source_document_id
status
created_at
```

Status beispielsweise:

```text
AKTIV
INAKTIV
HISTORISCH
UNSICHER
```

Bei neuer Diagnose:

```text
Neue Diagnose erkannt:
Eisenmangelanämie

mögliche Erstdiagnose:
19.08.2026

[übernehmen]
[bestehender Diagnose zuordnen]
[ignorieren]
```

Wenn sich aus früheren Dokumenten ein älteres Erstdiagnosedatum ergibt, soll dieses nach Benutzerbestätigung aktualisiert werden können.

Neue Dokumente erweitern den Diagnosenbestand.

Das Fehlen einer Diagnose in einem späteren Arztbrief darf nicht automatisch zur Löschung führen.

# 17. Original und Extraktion nebeneinander

Die Prüfoberfläche soll möglichst folgende Darstellung unterstützen:

```text
┌───────────────────────┬─────────────────────────┐
│ Originaldokument      │ Erkannte Daten          │
│                       │                         │
│ [Screenshot]          │ Gewicht: 74 kg ✓        │
│                       │ Blut: ja ✓              │
│                       │ Bauchschmerz: 3/6 ?      │
│                       │ Analregion: unleserlich  │
└───────────────────────┴─────────────────────────┘
```

Wenn ein extrahiertes Feld ausgewählt wird, soll – sofern technisch möglich – die zugehörige Stelle im Original hervorgehoben oder vergrößert werden.

Ziel ist eine schnelle manuelle Validierung.

# 18. KIS-Text in mehreren Varianten

Der KIS-Dokumentationstext muss strikt getrennt von den tabellarischen Daten bleiben.

Es sollen mindestens zwei Varianten erzeugt werden können:

## KIS kompakt

Sehr kurze klinische Zusammenfassung.

Beispiel:

```text
CED-Verlauf mit aktuell 6 Stuhlgängen/Tag, teilweise nächtlich und intermittierend blutig. Zunahme der Bauchschmerzen auf 3/6. Gewicht 74 kg, gegenüber Vorbefund −4,2 kg. Kein Fieber.
```

## KIS ausführlich

Etwas ausführlicherer medizinischer Verlaufstext mit relevanten Veränderungen zum Vorbefund.

Beide Texte:

* werden separat gespeichert
* erscheinen nicht in der Befundtabelle
* können manuell bearbeitet werden
* besitzen einen Button „In Zwischenablage kopieren“

Optional soll später eine dritte konfigurierbare Vorlage ergänzt werden können.

# 19. Patientbezogene Verlaufsansicht

Intern werden Befunde patienten- und datumsbezogen gespeichert.

Beispiel:

| Patient | Datum      | Stuhlfrequenz | Blut         | Bauchschmerz | Gewicht |
| ------- | ---------- | ------------: | ------------ | -----------: | ------: |
| P001    | 01.03.2026 |             6 | ja           |            4 |      72 |
| P001    | 15.05.2026 |             4 | gelegentlich |            2 |      74 |
| P001    | 19.08.2026 |             2 | nein         |            1 |      75 |

Zusätzlich Pivot-Ansicht:

| Parameter     | 01.03.2026 | 15.05.2026   | 19.08.2026 |
| ------------- | ---------- | ------------ | ---------- |
| Stuhlfrequenz | 6          | 4            | 2          |
| Blut im Stuhl | ja         | gelegentlich | nein       |
| Bauchschmerz  | 4          | 2            | 1          |
| Gewicht       | 72         | 74           | 75         |

Neue Kategorien erscheinen automatisch.

# 20. Dynamischer Befundkatalog

Wenn ein neuer relevanter Parameter erkannt wird, darf dieser nicht automatisch dauerhaft angelegt werden.

Beispiel:

```text
Neue Kategorie erkannt:

Albumin
3,2 g/dl

Vorschlag:
Labor → Eiweißstoffwechsel
```

Benutzeroptionen:

```text
[neue Kategorie anlegen]
[bestehender Kategorie zuordnen]
[ignorieren]
```

Vor Anlage einer neuen Kategorie:

* Synonyme prüfen
* ähnliche Begriffe anzeigen
* typische Einheit prüfen
* Dubletten vermeiden

# 21. Flexibles Datenmodell

Neue Befundparameter dürfen nicht als ständig neue SQL-Spalten implementiert werden.

Verwende mindestens:

```text
PATIENTS
DOCUMENTS
DOCUMENT_TYPES
FINDING_CATEGORIES
FINDINGS
DIAGNOSES
AI_RESULTS
AI_WARNINGS
FOLLOW_UP_ITEMS
USER_PREFERENCES
AUDIT_LOG
```

FINDINGS enthält mindestens:

```text
patient_id
document_id
category_id
finding_date
numeric_value optional
text_value optional
unit optional
source_text optional
page optional
confidence_status
confirmed_by_user
created_at
```

AI_RESULTS enthält:

```text
document_id
raw_ai_response
kis_summary_compact
kis_summary_detailed
model
provider
created_at
```

AI_WARNINGS enthält:

```text
patient_id
document_id
warning_type
message
reason
severity
ai_generated
user_feedback
created_at
```

# 22. Prüf- und Freigabeprozess

Workflow:

```text
Dokument
   ↓
Dokumenttyp erkennen
   ↓
KI-Analyse
   ↓
Extraktion
   ↓
Plausibilitätsprüfung
   ↓
Vergleich mit Vorbefund
   ↓
KI-Trendbewertung
   ↓
Benutzerprüfung
   ↓
Korrektur
   ↓
Freigabe
   ↓
Speicherung
```

Erst nach „Befund übernehmen“ werden strukturierte Daten endgültig gespeichert.

# 23. Export

Implementiere:

* Excel-Export
* CSV-Export
* Export der longitudinalen Ansicht
* Export ausgewählter Befunde

Die KIS-Zusammenfassungen werden standardmäßig nicht in tabellarische Exporte aufgenommen.

# 24. Sicherheit

Berücksichtige:

* lokale Datenhaltung
* API-Schlüssel nie im Quellcode
* sichere Konfiguration
* Audit-Log
* keine unnötigen Patientendaten in Debug-Logs
* nachvollziehbare Änderungen
* Trennung von Originaldaten, KI-Extraktionen und KIS-Zusammenfassungen
* Benutzerbestätigung vor endgültiger Übernahme
* Backup-Konzept
* spätere Verschlüsselung vorbereiten
* spätere Rollen-/Rechteverwaltung vorbereiten

# 25. Projektstruktur

Verwende beispielsweise:

```text
ced_document_ai/
    app.py

    config/
        settings.py
        prompts/
        rules/

    database/
        database.py
        models.py
        migrations/

    services/
        ai/
        parsing/
        documents/
        patients/
        findings/
        diagnoses/
        plausibility/
        comparison/
        trends/
        follow_up/
        export/

    ui/
        main_window.py
        import_view.py
        review_view.py
        patient_dashboard.py
        longitudinal_view.py
        chart_view.py
        category_view.py
        settings_view.py

    tests/

    requirements.txt
    README.md
```

# 26. Umsetzung in Phasen

Arbeite schrittweise.

## Phase 1

Erstelle:

* Projektstruktur
* Python-Umgebung
* requirements.txt
* SQLite
* SQLAlchemy-Modelle
* Basis-GUI

## Phase 2

Implementiere:

* Patientenverwaltung
* Screenshot via STRG+V
* Drag & Drop
* PDF/JPG/PNG
* mehrseitige Dokumente
* Dokumentvorschau

## Phase 3

Implementiere:

* KI-Schnittstelle
* API-Konfiguration
* Dokumenttyperkennung
* Promptverwaltung

## Phase 4

Implementiere vollständig:

* CED-Fragebogen
* bestehenden Prompt
* Reintext-Parser
* Skalen
* visuelle Markierungen
* Qualitätsbewertung pro Feld
* KIS kompakt
* KIS ausführlich
* Copy-to-Clipboard

## Phase 5

Implementiere:

* Plausibilitätsprüfung
* Widerspruchserkennung
* Vergleich mit letztem Fragebogen
* Änderungsanzeige
* KI-basierte Trend- und Warnbewertung

## Phase 6

Implementiere:

* Patientendashboard
* Wiedervorlagen
* grafische Verläufe
* Pivot-Tabelle

## Phase 7

Implementiere:

* Dokumentenvergleich
* Medikamentenänderungen
* kumulative Diagnosen
* Erstdiagnosedatum
* dynamischen Befundkatalog

## Phase 8

Implementiere:

* Benutzerfeedback zu Warnungen
* konfigurierbare Regeln
* Präferenzspeicherung
* Vorbereitung eines lernenden Systems

## Phase 9

Implementiere:

* Excel/CSV-Export
* Audit-Log
* Einstellungen
* Backup-Funktion

## Phase 10

Führe umfangreiche Tests durch.

Mindestens:

* gut lesbarer CED-Fragebogen
* handschriftliche Angaben
* unleserliche Felder
* Skalenmarkierungen
* anatomische Markierungen
* unrealistisches Gewicht
* extrem hohe Stuhlfrequenz
* widersprüchliche Angaben
* Vergleich mit Vorfragebogen
* neu aufgetretener nächtlicher Stuhlgang
* Gewichtsdifferenz
* neue Blutangabe
* CRP-Verlauf
* Calprotectin-Verlauf
* Hb-Abfall
* neue Diagnose
* Diagnose bereits vorhanden
* Diagnose fehlt in neuem Arztbrief
* Medikament neu
* Medikament verändert
* Medikament nicht mehr erwähnt
* automatische Dokumenttyperkennung korrekt
* automatische Dokumenttyperkennung falsch
* unsichere Extraktion
* API-Ausfall
* fehlerhafte KI-Antwort
* mehrere Screenshots
* KIS-Zusammenfassung bleibt außerhalb der Befundtabelle

# 27. Anleitung für mich

Ich bin nicht als professioneller Softwareentwickler vorauszusetzen.

Bei jedem Schritt musst du erklären:

1. Welche Datei erstellt oder geändert wird.
2. Wo sie gespeichert wird.
3. Welcher vollständige Code hineingehört.
4. Welcher Windows-Terminalbefehl ausgeführt werden muss.
5. Was danach sichtbar sein sollte.
6. Wie die Funktion getestet wird.
7. Welche typischen Fehler auftreten können.
8. Wie diese Fehler behoben werden.

Treffe bei technischen Detailfragen sinnvolle Standardentscheidungen, statt die Umsetzung wegen jeder Kleinigkeit zu stoppen.

Arbeite von einer lauffähigen Minimalversion zu einer vollständigen Anwendung.

Beginne mit Phase 1.
