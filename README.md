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
   OPENAI_API_KEY=hier_den_openai_api_schluessel_eintragen
   ```

   Es sind keine Anführungszeichen erforderlich. Für den in `CED_AI_PROVIDER`
   ausgewählten Anbieter muss der entsprechende Schlüssel gesetzt sein.

   Für die OpenAI-Verbindung zusätzlich den Anbieter aktivieren:

   ```dotenv
   CED_AI_PROVIDER=openai
   CED_OPENAI_MODEL=gpt-4.1-mini
   ```

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

Ein gefundener Patient ist immer nur ein Vorschlag. Die Auswahl im geschützten
Dropdown aktiviert den Patienten unmittelbar für Patientenübersicht und Verläufe.
Davon getrennt prüft „Daten zuordnen“, ob das aktuell eingelesene Dokument neue,
speicherbare Daten für diesen Patienten enthält. Der Schalter ist nur dann aktiv.
Erkannte Patienten-ID, getrennt beschrifteter Vor- und Nachname sowie Geburtsdatum
werden gegen den ausgewählten Datensatz geprüft. Bei einem Widerspruch bleibt der
Patient für bestehende Ansichten aktiv, die Dokumentzuordnung wird jedoch gesperrt.
Ohne aktive Patientenauswahl bleiben Patientenübersicht, klinischer Verlauf, Labor,
Calprotectin, Endoskopie, Sonografie und MRT/CT einheitlich deaktiviert.

Gibt es keinen passenden Bestandspatienten, kann „Neuer Patient“ in der Seitenleiste
die selten benötigte Neuanlage einblenden. Eindeutig beschriftete Patienten-ID,
Vorname, Nachname und Geburtsdatum aus Briefkopf oder Patientenkleber werden dabei
vorbelegt; ein ungetrennter Gesamtname wird nicht geraten. Ein neuer Patient wird erst
durch den zugehörigen Schalter angelegt. Testpatienten können über die Oberfläche
angelegt und anschließend durch Löschen der lokalen Entwicklungsdatenbank
`data/ced_document_ai.sqlite3` vollständig entfernt werden.

> **Debugging-Hinweis:** Wenn trotz sichtbarer Stammdaten kein Vorschlag erscheint,
> zuerst prüfen, ob jede Angabe im Rohtext in einer eigenen, eindeutig beschrifteten
> Zeile wie `Patienten-ID:`, `Name:` und `Geburtsdatum:` steht. Medizinische Inhalte
> oder Stammdaten nicht zur Fehlersuche in Konsolen- oder Server-Logs ausgeben.

Dokumentbilder können weiterhin per **Strg+V** beziehungsweise **Cmd+V** eingefügt
werden. Der Paste-Handler arbeitet in der Capture-Phase, damit ein fokussiertes
Formularfeld oder eine Tabellenzelle das Bildereignis nicht vorher abfängt. Falls ein
Browser kein Bild übergibt, in dessen Entwicklerwerkzeugen ausschließlich `kind` und
MIME-Typ des Clipboard-Eintrags prüfen; Base64- oder Bildinhalte nicht protokollieren.

## CED-Prüftabelle

Nach bestätigter Patientenzuordnung kann ein als `CED-Patientenfragebogen` erkanntes
Dokument in eine vorläufige Prüftabelle übernommen werden. Der dafür verwendete
Reintextparser arbeitet auf der bereits vorhandenen strukturierten Darstellung; die
allgemeine Dokument- und Textextraktion wird dadurch nicht verändert. Erkannter
Wert, Einheit, Qualitätsstatus und unveränderte Quellzeile werden nebeneinander
angezeigt und können vor einer späteren Speicherung geprüft werden.

Die CED-Prüfung wird nach der Patientenauswahl über „Daten zuordnen“ in der linken
geschützten Steuerung geöffnet. Die Arbeitsansicht belegt nur den Bereich rechts neben
der weiterhin bedienbaren Seitenleiste. „Dokument einlesen“ sowie die übrigen
Patientenansichten können direkt in derselben Navigation geöffnet werden; gesonderte
Zurück-Schalter sind nicht erforderlich. Die CED-Felder werden unmittelbar extrahiert
und in der Tabelle angezeigt. Im Kopf stehen der gespeicherte Name und das
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

Nicht lesbare, unsichere oder bewusst von der Übernahme ausgeschlossene Zeilen werden
in roter Schrift dargestellt. Die übrige Tabellenformatierung bleibt identisch.

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
Vor der Speicherung wird geprüft, ob für denselben Patienten am selben Datum bereits
identische Kategorien und Werte bestätigt wurden. Dann wird die erste Speicherung
angehalten und eine Doppelübernahme erfordert einen zweiten Bestätigungsklick. Nach
erfolgreicher Speicherung werden Tabelle und Befunddatum geleert und „Daten zuordnen“
bleibt für dieses Dokument deaktiviert.

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
der Seitenleiste angeboten. Die Dropdownauswahl aktiviert den Patienten ohne weiteren
Klick, sodass die Patientenübersicht auch ohne Dokument geöffnet werden kann. „Daten
zuordnen“ gehört ausschließlich zum getrennten Dokumentimport. Unter dem am unteren Rand
angeordneten Schalter „Datenbankmodus beenden“ bleibt Name und Geburtsdatum des
aktiven Patienten sichtbar. Beim Dokumentwechsel wird die bewusste Dropdownauswahl
beibehalten. Name und Geburtsdatum des aktiven
Patienten stehen auch im Kopf des Einlesebereichs. Nach der Dokumentanalyse werden
erkannte Stammdaten erneut mit dem aktiven Patienten abgeglichen. Ein Widerspruch
hebt die Auswahl nicht auf, sperrt aber weiterhin die Übernahme dieses Dokuments.

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
verlängern. Erstdiagnose, „Symptome seit“, Details zur Diagnose und Befallsmuster
starten als schreibgeschützte Formfelder.
Über „Stammdaten bearbeiten“ können fehlende oder zu korrigierende Angaben bewusst
freigegeben und gespeichert werden. Jede Speicherung legt eine neue bestätigte
Version mit der Quelle „MANUELL“ und einem Audit-Eintrag an; ältere Versionen bleiben
erhalten. Leere Felder löschen keine frühere Angabe und unveränderte Werte werden
nicht erneut versioniert. Die automatische Übernahme solcher Stammdaten aus
Dokumenten bleibt einem späteren, ebenfalls bestätigungspflichtigen Schritt
vorbehalten.

Unter dem Befallsmuster stehen acht häufige extraintestinale Manifestationen als
deutlich sichtbare Mehrfachauswahl zur Verfügung: Arthritis/Arthralgie,
Sakroiliitis/ankylosierende Spondylitis, Uveitis, Episkleritis, Erythema nodosum,
Pyoderma gangraenosum, primär sklerosierende Cholangitis und aphthöse Stomatitis.
Gesetzte Kreuze und zusätzliche manuelle EIM werden versioniert gespeichert. Die
Liste ist ein Eingabekatalog und keine automatische Diagnose oder Interpretation.
Gesetzte EIM werden auch in der schreibgeschützten Patientenübersicht farblich
hervorgehoben.

Das Befallsmuster wird nicht mehr als freier Code eingegeben. Für Morbus Crohn werden
Lokalisation (L1–L3), ein zusätzlicher oberer GI-Befall (L4), Verhalten (B1–B3) und
ein perianaler Zusatz (`p`) ausdrücklich abgefragt; B2 ist als stenosierend und B3
als penetrierend/fistulierend beschriftet. Für Colitis ulcerosa wird die Ausdehnung
E1–E3 ausgewählt. Erst aus der vollständigen, manuell bestätigten Auswahl wird der
sichtbare Code gebildet. Unvollständige Angaben werden nicht geraten.

Hauptdiagnose und Nebendiagnosen besitzen einen eigenen Schalter „Diagnosen
bearbeiten“. Das Feld „Details zur Diagnose“ steht davon getrennt bei Erstdiagnose
und „Symptome seit“ in den CED-Stammdaten. Es nimmt ergänzende bestätigte Angaben
auf, ohne daraus automatisch weitere strukturierte Diagnosen zu erzeugen. Frühere
Diagnosen werden bei einer Speicherung als ersetzt markiert.
Medikamentöser und chirurgischer Therapieverlauf werden davon getrennt über
„Therapien bearbeiten“ freigegeben. Nur geänderte ausgefüllte Therapiefelder werden
als neue Version gespeichert. Beide Vorgänge erhalten getrennte Audit-Einträge ohne
medizinische Inhalte; leere Felder löschen keine frühere Angabe.

> **Debugging-Hinweis:** Bleibt die Übersicht trotz gespeicherter CED-Werte leer,
> zunächst prüfen, ob `confirmed_by_user` gesetzt ist und `patient_id` mit dem oben
> bestätigten Patienten übereinstimmt. In Debug-Ausgaben nur IDs und Trefferanzahlen,
> niemals Namen, Diagnosen oder Befundwerte verwenden.

## Zuordnung weiterer Dokumenttypen

Auch Laborbefunde, Arztbriefe, Medikamentenpläne, bildgebende Befunde und sonstige
medizinische Dokumente können nach dem Einlesen einem Patienten zugeordnet werden.
Die strukturierte Darstellung führt vorhandene Patientenmerkmale und passend
beschriftete Dokumentdaten gesondert auf. Lokal werden Patienten-ID, Name und
Geburtsdatum gegen den Bestand geprüft. Bereits ein einzelnes passendes Merkmal darf
einen klar als unsicher gekennzeichneten Vorschlag erzeugen; die Zuordnung erfolgt
aber niemals automatisch.

Vor der Speicherung zeigt eine Prüfansicht den aktiven Patienten, Dokumenttyp,
erkanntes Datum und die strukturierten Informationen. Das Datum muss bestätigt oder
manuell ergänzt werden. Widersprüchliche Stammdaten sperren die Zuordnung. Allgemeine
Dokumente werden mit Rohantwort und KIS-Text archiviert; Fachwerte wie einzelne
Laborparameter werden ohne eigenen Fachparser nicht als strukturierte Befunde
geraten oder gespeichert.

Sobald Patient, erkannter Dokumenttyp und ausgelesener Inhalt vorliegen und kein
Stammdatenwiderspruch besteht, wird „Daten zuordnen“ auch für Laborbefunde und andere
Nicht-CED-Dokumente aktiv. Die Aktivierung hängt nicht von der CED-spezifischen
Prüftabelle ab. Nach bereits erfolgter Speicherung bleibt der Schalter gesperrt.

### Dokumentarchiv und Befundklassen

Bestätigt zugeordnete Dokumente bleiben nun auch ohne eigenen Fachparser in der
Patientenansicht auffindbar. Die Fachansichten zeigen unterhalb strukturierter
Einzelwerte zusätzlich Dokumentdatum, Befundklasse, Dokumenttyp, gespeicherte
KI-Kurzfassung und Quelldatei. Ein als `Laborbefund` erkanntes virologisches Dokument
erscheint deshalb unter **Labor**, auch wenn noch keine einzelnen Virusparameter als
bestätigte Befunde gespeichert wurden.

Der kontrollierte Katalog unterscheidet derzeit CED-Fragebogen, allgemeines Labor,
Virologie, Mikrobiologie, Calprotectin, Endoskopie, Sonografie, MRT, CT, Röntgen,
Pathologie, Funktionsdiagnostik, Arztbriefe, Medikamentenpläne und sonstige
medizinische Dokumente. Arztbriefe, Pathologie, Funktionsdiagnostik, Medikation und
nicht anderweitig zuordenbare präzise Dokumenttypen erscheinen unter **Weitere
Befunde**. Eine unbekannte präzise Bezeichnung bleibt erhalten und wird nicht
automatisch in „Andere Befunde“ umbenannt. Neue Einzelwerte oder medizinische
Kategorien werden weiterhin erst nach einem dokumenttypspezifischen Parser und einer
manuellen Prüfung als `Finding` gespeichert; die reine Archivierung erfindet keine
Werte.

### Labor, Virologie und Mikrobiologie prüfen

Für `Laborbefund`, `Virologischer Befund`, `Mikrobiologischer Befund` und
`Calprotectin-Befund` wird vor der Speicherung eine editierbare Prüftabelle erzeugt.
Der deterministische Parser verarbeitet ausschließlich klar beschriftete Tabellen-
oder `Parameter: Wert`-Zeilen aus der strukturierten Darstellung. Angezeigt werden
Parameter, Ergebnis, Einheit, Referenzbereich, Quellzeile, Qualitätsstatus und ein
Übernahmeschalter. Werte und Einheiten werden nicht umgerechnet oder medizinisch
interpretiert.

Mehrspaltige Laborverläufe werden ebenfalls unterstützt. Enthält eine Tabelle eine
explizit beschriftete Zeile `Abnahmedatum`, `Entnahmedatum`, `Befunddatum` oder
`Messdatum`, wird jede nicht leere Messzelle als eigener Wert mit genau diesem Datum
in der Prüftabelle angezeigt. Alternativ verarbeitet der Parser das normalisierte
Langformat `Datum | Parameter | Ergebnis | Einheit | Referenzbereich`. Historische
Messspalten werden dadurch nicht als widersprüchliche Doppelwerte behandelt. Das
jüngste ausdrücklich erkannte Messdatum wird lediglich als sichtbarer Vorschlag für
das Dokumentdatum eingesetzt und kann vor der Speicherung korrigiert werden.

Der Parser gleicht Parameter zuerst mit dem festen Anfangskatalog und anschließend
mit bereits bestätigten Kategorien der lokalen Datenbank ab. Ein neuer eindeutig
beschrifteter Parameter bleibt zunächst ausgeschaltet und als **Neue Kategorie ·
prüfen** markiert. Erst ein bewusst gesetzter Übernahmeschalter legt ihn zusammen mit
dem bestätigten Dokument atomar an. Fehlende beziehungsweise abweichende Einheiten,
unleserliche Werte und widersprüchliche Doppelangaben sind ebenfalls nicht
vorausgewählt. Nach erfolgreicher Speicherung öffnet die App direkt den Labor- oder
Calprotectin-Verlauf.

## Synthetische Demo-Daten

Für die visuelle Prüfung können fünf vollständig erfundene Patienten mit Haupt- und
Nebendiagnosen, CED-Stammdaten, medikamentösem und chirurgischem Therapieverlauf
sowie jeweils drei Zeitpunkten für Fragebogen, Labor, Calprotectin, Endoskopie,
Sonografie, MRT und CT angelegt werden:

```bash
PYTHONPATH=. python scripts/seed_demo_data.py
```

Der Seeder läuft niemals automatisch und verwendet ausschließlich die reservierten
Patienten-IDs `DEMO-001` bis `DEMO-005`. Er kann gefahrlos erneut ausgeführt werden:
Er ergänzt nur fehlende IDs und verändert bereits vorhandene Demofälle nicht. Sind
alle fünf vorhanden, meldet er dies ohne Fehler. Ein vorhandener, aber unvollständiger
Demofall wird bewusst nicht automatisch repariert oder überschrieben. Die Werte sind
medizinisch frei erfunden und dürfen nicht als fachliche Referenz verwendet werden.
Zum Entfernen der Testdaten kann – solange garantiert keine realen Daten enthalten
sind – die lokale Entwicklungsdatenbank gelöscht werden.

Die Testfälle liegen **nicht im Git-Repository**, sondern ausschließlich in der lokal
erzeugten SQLite-Datei unter `data/ced_document_ai.sqlite3` beziehungsweise am mit
`CED_DATABASE_PATH` gesetzten Ort. Der Ordner `data/` ist absichtlich von Git
ausgeschlossen, damit weder echte noch synthetische Patientendaten durch `git pull`
übertragen werden. Ein neuer oder neu aufgebauter Codespace besitzt deshalb zunächst
keine Demo-Patienten. In diesem Fall den obigen Seeder einmal im Projektordner
ausführen. Seine Abschlussmeldung nennt den tatsächlich verwendeten absoluten
Datenbankpfad; die App muss mit demselben `CED_DATABASE_PATH` gestartet werden. Ist
das Dropdown leer, zeigt die Oberfläche ebenfalls diesen ausdrücklichen Hinweis an,
statt stillschweigend eine zweite Datenbank oder Testpatienten anzulegen.

## Verbleibende Entwicklungsschritte

Der frühere Arbeitsplan wurde am 18. September 2026 erneut gegen Quellcode und Tests
geprüft. Der geschützte CED-Grundpfad ist weitgehend vorhanden. Fehlende
Standardfelder werden inzwischen als nicht ausgewählte `MISSING`-Zeilen sichtbar
gemacht. Vorhandene numerische Werte und Einheiten werden zusätzlich durch einen
getrennten regelbasierten Dienst geprüft, der ausschließlich Hinweise ergänzt und
keine Werte korrigiert. Als nächstes folgen die gefilterte Längstabelle und danach
die getrennten KIS-Varianten.

Der vollständige Soll-Ist-Abgleich, die noch offenen Punkte der bisherigen drei
Iterationen und die neu priorisierte Roadmap stehen in
[`UMSETZUNGSSTAND.md`](UMSETZUNGSSTAND.md). Der umfassende fachliche Zielkatalog
bleibt unverändert in [`projektplan.md`](projektplan.md) erhalten.
