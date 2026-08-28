# CED-A-DOKU

CED-A-DOKU ist eine lokal ausführbare Browseranwendung zur assistierten
Auswertung medizinischer Dokumente bei chronisch-entzündlichen Darmerkrankungen.
Die aktuelle **Phase-1-Testversion** legt das flexible SQLite-Datenmodell an und
ermöglicht, Bilder sowie PDFs an eine multimodale KI zu senden. Das Ergebnis wird
zunächst ausschließlich als ungeprüfter Reintext angezeigt. Für GitHub Codespaces
steht eine medizinisch gestaltete NiceGUI-Browseroberfläche bereit.

> **Medizinischer Sicherheitshinweis:** KI-Ausgaben sind Vorschläge und dürfen
> nicht ungeprüft als medizinische Fakten oder Therapieentscheidung übernommen
> werden. Die Testversion speichert KI-Ausgaben noch nicht als Befunde.

## Aktueller Funktionsumfang

- direkter Start im Standardbereich „Nur Dokument einlesen“
- medizinisch gestaltete Arbeitsfläche mit getrenntem Steuerungs-/Adminbereich
- passwortgeschützte Aktivierung des Datenbankmodus über `CED_DATA_PASS`
- Dateiimport für PDF, PNG, JPG und JPEG
- mehrere Seiten und Bilder in einer gemeinsamen Dokumentanalyse
- PDF-Seitenvorschau
- UK-Halle-API mit Modell `gemma4-31b`
- maximal fünf Bilder je Anfrage; größere Dokumente werden geordnet aufgeteilt
- UK-API als feste Vorauswahl und manuell wählbare OpenAI-Anbindung, **kein
  automatischer stiller Fallback**
- bestätigungspflichtiger Datenschutzhinweis beim Wechsel zu OpenAI
- farbige Provider-Anzeige unten rechts: UK-API grün, OpenAI rot
- lokales SQLite-Grundschema mit SQLAlchemy
- browserfähige NiceGUI-Oberfläche ohne Linux-Desktop oder `libGL.so.1`

## Direkt in GitHub Codespaces starten

Die Browseroberfläche benötigt keine grafische Linux-Desktop-Sitzung. Die
Abhängigkeiten müssen im Codespace einmalig installiert werden:

```bash
/usr/local/python/3.12.1/bin/python -m pip install -r requirements.txt
```

Danach genügt dieser kurze Startbefehl:

```bash
python nicegui_app.py
```

Alternativ kann die geöffnete Datei `nicegui_app.py` über den ▶-Knopf
**Python-Datei ausführen** oben rechts gestartet werden.

Installation und Start müssen außerdem mit demselben Python-Interpreter erfolgen.
Andernfalls kann trotz einer vorhandenen NiceGUI-Installation die Meldung
`No module named nicegui` erscheinen. Nach erfolgreicher Installation kann mit
folgendem Befehl geprüft werden, welches NiceGUI-Modul genau dieser Interpreter
beim Start verwenden wird:

```bash
/usr/local/python/3.12.1/bin/python -m pip show nicegui
```

NiceGUI verwendet hier Port 8501. Codespaces zeigt nach dem Start eine
Meldung zum weitergeleiteten Port an. Dort **Im Browser öffnen** auswählen. Falls
keine Meldung erscheint, in VS Code den Bereich **Ports** öffnen, Port `8501`
hinzufügen und anschließend das Globus-Symbol anklicken.

Der frühere Fehler `ImportError: libGL.so.1` tritt bei diesem Startweg nicht auf,
weil `nicegui_app.py` keine Qt-Desktopbibliotheken importiert.
Die drei Repository-Secrets müssen für den Codespace freigegeben und der Codespace
nach einer Änderung der Secrets neu erstellt beziehungsweise neu gestartet werden.

## Installation unter Windows

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

## Secrets für den aktuellen Terminalprozess setzen

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

## Browseranwendung unter Windows starten

```powershell
python nicegui_app.py
```

Die Anwendung öffnet direkt die Funktion „Nur Dokument einlesen“. Die Auswahl des
LLM und die Aktivierung des CED-Datenbankmodus befinden sich getrennt in der linken
Seitenleiste „Steuerung / Administration“. Der Datenbankmodus verlangt das Passwort
aus `CED_DATA_PASS`. Beim Wechsel zu OpenAI muss zunächst der Hinweis bestätigt
werden, dass keine personenbezogenen Daten gesendet werden dürfen. Nach
„Dokument auslesen“ erscheint der
ungeprüfte Reintext. Unten rechts ist immer der tatsächlich gewählte API-Provider
sichtbar; der Schlüssel selbst wird nie dargestellt.

## Browserfunktion testen

1. Die von Codespaces bereitgestellte URL für Port 8501 öffnen.
2. Kontrollieren, dass direkt „Nur Dokument einlesen“ aktiv ist.
3. Ein Testbild **ohne echte Patientendaten** auswählen.
4. Unten rechts die grüne Anzeige `UK-API · UK_API_KEY` kontrollieren.
5. „Dokument auslesen“ anklicken.
6. Prüfen, ob rechts ein Reintext erscheint.
7. Optional sechs Testbilder auswählen. Die Anwendung sendet automatisch zwei
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
- **OpenAI soll verwendet werden:** Provider im Administrationsbereich umstellen,
  den Datenschutzhinweis bestätigen und `OPENAI_API_KEY` setzen.
- **PDF lässt sich nicht öffnen:** Prüfen, ob sie beschädigt oder kennwortgeschützt
  ist; die App überspringt fehlerhafte Seiten nicht still.
- **PowerShell findet `python` nicht:** `py -3 nicegui_app.py`
  verwenden und
  kontrollieren, ob die virtuelle Umgebung aktiv ist.
- **`libGL.so.1` in Codespaces:** Die Browseroberfläche mit
  `python nicegui_app.py` starten.
- **`No module named 'nicegui'`:** Zuerst mit genau demselben Python-Interpreter
  `-m pip install -r requirements.txt` ausführen, der danach die Datei startet.
- **`address already in use` / Port 8501 bereits belegt:** Mit `lsof -i :8501`
  den noch laufenden Webserver ermitteln und beenden. Alternativ bewusst mit
  `CED_WEB_PORT=8502 python nicegui_app.py` einen anderen Port starten und genau
  diesen Port in Codespaces freigeben. Die Anwendung wechselt nicht unbemerkt.
- **Port öffnet sich nicht:** Codespaces-Bereich **Ports** öffnen, den verwendeten
  Port manuell hinzufügen und dessen Sichtbarkeit auf „Privat“ belassen.
- **API-Fehler genauer untersuchen:** Nur lokal den HTTP-Status protokollieren.
  Authorization-Header, Anfrageinhalt und Antworttext dürfen wegen Schlüssel- und
  Patientendatenschutz niemals in Debug-Logs geschrieben werden.

## Projektstruktur

```text
ced_document_ai/
├── config/settings.py
├── database/{database.py,models.py}
├── services/ai/providers.py
├── services/documents/converter.py
└── nicegui_app.py
nicegui_app.py
tests/
requirements.txt
```

Die nächsten Phasen ergänzen Patientenverwaltung, strukturierte Freigabe,
Plausibilitätsprüfung und longitudinale Auswertung. Diese Funktionen sind in der
vorliegenden Testversion bewusst noch nicht vorgetäuscht oder vorweggenommen.
