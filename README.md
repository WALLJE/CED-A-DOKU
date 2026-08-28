# CED-A-DOKU

CED-A-DOKU ist eine lokal installierbare Desktop-Anwendung zur assistierten
Auswertung medizinischer Dokumente bei chronisch-entzündlichen Darmerkrankungen.
Die aktuelle **Phase-1-Testversion** legt das flexible SQLite-Datenmodell an und
ermöglicht, Bilder sowie PDFs an eine multimodale KI zu senden. Das Ergebnis wird
zunächst ausschließlich als ungeprüfter Reintext angezeigt.

> **Medizinischer Sicherheitshinweis:** KI-Ausgaben sind Vorschläge und dürfen
> nicht ungeprüft als medizinische Fakten oder Therapieentscheidung übernommen
> werden. Die Testversion speichert KI-Ausgaben noch nicht als Befunde.

## Aktueller Funktionsumfang

- Startmodus „Nur Dokument einlesen“
- passwortgeschützter zukünftiger Datenbankmodus über `CED_DATA_PASS`
- Dateiimport und Drag & Drop für PDF, PNG, JPG und JPEG
- mehrere Seiten und Bilder in einer gemeinsamen Dokumentanalyse
- Bildimport aus der Zwischenablage
- PDF-Seitenvorschau
- UK-Halle-API mit Modell `gemma4-31b`
- maximal fünf Bilder je Anfrage; größere Dokumente werden geordnet aufgeteilt
- manuell wählbare OpenAI-Anbindung, **kein automatischer stiller Fallback**
- farbige Provider-Anzeige unten rechts: UK-API grün, OpenAI rot
- lokales SQLite-Grundschema mit SQLAlchemy

## 1. Installation unter Windows

Voraussetzung ist Python 3.11 oder neuer. In PowerShell im Projektordner:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Falls PowerShell die Aktivierung blockiert, kann für den aktuellen Prozess vorher
`Set-ExecutionPolicy -Scope Process Bypass` ausgeführt werden. Die Umgebung ist
erfolgreich aktiv, wenn links in der Eingabezeile `(.venv)` erscheint.

## 2. Secrets für den aktuellen Terminalprozess setzen

GitHub-Codespaces-Secrets stehen in einem Codespace als Umgebungsvariablen bereit.
Auf einem lokalen Windows-PC müssen sie vor dem Start gesetzt werden:

```powershell
$env:UK_API_KEY = "persönlichen Schlüssel hier einsetzen"
$env:OPENAI_API_KEY = "persönlichen OpenAI-Schlüssel hier einsetzen"
$env:CED_DATA_PASS = "persönliches Datenbankpasswort hier einsetzen"
```

Die Werte gelten nur für das aktuelle PowerShell-Fenster. Sie gehören niemals in
Quellcode, `.env.example`, Bildschirmfotos oder Git. Für reines Einlesen über die
UK-API sind `OPENAI_API_KEY` und `CED_DATA_PASS` nicht erforderlich.

## 3. Anwendung starten

```powershell
python -m ced_document_ai.app
```

Danach erscheint zuerst die Modusauswahl. Der Datenbankmodus verlangt das Passwort
aus `CED_DATA_PASS`. Im Hauptfenster können Dokumente ausgewählt, abgelegt oder als
Zwischenablagebild eingefügt werden. Nach „Dokument auslesen“ erscheint rechts der
ungeprüfte Reintext. Unten rechts ist immer der tatsächlich gewählte API-Provider
sichtbar; der Schlüssel selbst wird nie dargestellt.

## Funktion testen

1. „Nur Dokument einlesen“ wählen.
2. Ein Testbild **ohne echte Patientendaten** auswählen.
3. Unten rechts die grüne Anzeige `UK-API · UK_API_KEY` kontrollieren.
4. „Dokument auslesen“ anklicken.
5. Prüfen, ob rechts ein Reintext erscheint.
6. Optional sechs Testbilder auswählen. Die Anwendung sendet automatisch zwei
   geordnete Anfragen mit fünf und einem Bild.

Automatisierte Tests werden mit folgendem Windows-Befehl ausgeführt:

```powershell
python -m pytest
```

Für die Entwicklung muss `pytest` gegebenenfalls separat mit
`python -m pip install pytest` installiert werden; es ist keine Laufzeitabhängigkeit.

## Typische Fehler und gezieltes Debugging

- **`UK_API_KEY fehlt`:** Secret im selben Terminal setzen und die App neu starten.
- **HTTP-/API-Fehler:** Endpunktzugriff, Modell-ID `gemma4-31b` und Berechtigung des
  Keys prüfen. Es erfolgt absichtlich kein versteckter Wechsel zu OpenAI.
- **OpenAI soll verwendet werden:** Provider sichtbar im Auswahlfeld umstellen und
  `OPENAI_API_KEY` setzen.
- **PDF lässt sich nicht öffnen:** Prüfen, ob sie beschädigt oder kennwortgeschützt
  ist; die App überspringt fehlerhafte Seiten nicht still.
- **PowerShell findet `python` nicht:** `py -3 -m ced_document_ai.app` verwenden und
  kontrollieren, ob die virtuelle Umgebung aktiv ist.
- **API-Fehler genauer untersuchen:** Nur lokal den HTTP-Status protokollieren.
  Authorization-Header, Anfrageinhalt und Antworttext dürfen wegen Schlüssel- und
  Patientendatenschutz niemals in Debug-Logs geschrieben werden.

## Projektstruktur

```text
ced_document_ai/
├── app.py
├── config/settings.py
├── database/{database.py,models.py}
├── services/ai/providers.py
├── services/documents/converter.py
└── ui/main_window.py
tests/
requirements.txt
```

Die nächsten Phasen ergänzen Patientenverwaltung, strukturierte Freigabe,
Plausibilitätsprüfung und longitudinale Auswertung. Diese Funktionen sind in der
vorliegenden Testversion bewusst noch nicht vorgetäuscht oder vorweggenommen.
