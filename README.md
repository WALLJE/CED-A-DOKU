# CED-A-DOKU lokal starten

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
   OPENAI_API_KEY=hier_den_openai_api_schluessel_eintragen
   ```

   Es sind keine Anführungszeichen erforderlich. Für den in `CED_AI_PROVIDER`
   ausgewählten Anbieter muss der entsprechende Schlüssel gesetzt sein.

4. Die Browseranwendung aus dem Projektstamm starten:

   ```bash
   python main.py
   ```

Die `.env` ist in `.gitignore` ausgeschlossen. `.env.example` bleibt dagegen als
leere, sichere Vorlage versioniert. Bereits außerhalb der Datei gesetzte
Umgebungsvariablen haben Vorrang vor Einträgen aus `.env`.

In GitHub Codespaces werden die Repository-Secrets `UK_API_KEY` und
`OPENAI_API_KEY` direkt als Umgebungsvariablen verwendet. Nach dem Anlegen oder
Ändern eines Secrets muss der Codespace neu gestartet werden. Eine `.env` ist dort
nicht erforderlich.

> **Debugging-Hinweis:** Falls eine Variable angeblich fehlt, zuerst prüfen, ob
> die Datei wirklich `.env` heißt, im selben Ordner wie `main.py` liegt und kein
> Leerzeichen vor dem Variablennamen enthält. Schlüsselwerte nicht in Logs oder
> Screenshots ausgeben. In Codespaces zusätzlich prüfen, ob die Secret-Namen exakt
> `UK_API_KEY` und `OPENAI_API_KEY` geschrieben sind.
