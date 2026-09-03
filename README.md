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

Die `.env` ist in `.gitignore` ausgeschlossen. `.env.example` bleibt dagegen als
leere, sichere Vorlage versioniert. Bereits außerhalb der Datei gesetzte
Umgebungsvariablen haben Vorrang vor Einträgen aus `.env`.

> **Debugging-Hinweis:** Falls eine Variable angeblich fehlt, zuerst prüfen, ob
> die Datei wirklich `.env` heißt, im selben Ordner wie `main.py` liegt und kein
> Leerzeichen vor dem Variablennamen enthält. Schlüsselwerte nicht in Logs oder
> Screenshots ausgeben.
