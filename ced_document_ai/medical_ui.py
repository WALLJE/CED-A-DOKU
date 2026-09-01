"""Medizinische NiceGUI-Oberfläche für den browserbasierten Dokumentimport.

Die normale Arbeitsfläche ist bewusst von der technischen Steuerung getrennt:
Dokumente können sofort eingelesen werden, während LLM-Auswahl und Datenbankzugang
in einer seitlichen Administrationsleiste liegen. Medizinische Dateien verbleiben
im temporären Sitzungsordner und werden noch nicht als Befunde gespeichert.
"""

from __future__ import annotations

import base64
import hmac
import os
import socket
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from nicegui import events, run, ui

from ced_document_ai.config.settings import ConfigurationError, Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.services.ai.providers import (
    AIProviderError,
    CloudAPIProvider,
    LocalAPIProvider,
)
from ced_document_ai.services.ai.document_workflow import DokumentAntwortFehler
from ced_document_ai.services.documents.converter import (
    DocumentConversionError,
    DocumentConverter,
)


LESEMODUS = "Nur Dokument einlesen"
DATENBANKMODUS = "Einlesen und in CED-Datenbank verarbeiten"


@dataclass
class Sitzungszustand:
    """Enthält ausschließlich Daten des aktuell geöffneten Browserfensters."""

    # Der Lesemodus und die UK-API sind absichtlich feste, sichere Startwerte.
    # Eine optionale CED_AI_PROVIDER-Variable verändert die sichtbare Vorauswahl nicht.
    arbeitsmodus: str = LESEMODUS
    anbieter: str = "uk"
    seiten: list[Path] = field(default_factory=list)
    # Die vier Werte gehören immer zu genau demselben Dokument. Sie werden beim
    # nächsten Upload gemeinsam gelöscht, sodass keine alten Ergebnisse stehen bleiben.
    dokumenttyp: str = ""
    ausgelesener_inhalt: str = ""
    strukturierte_darstellung: str = ""
    kis_vorschlag: str = ""
    letzter_fehler: str = ""
    # Der Anbieter des sichtbaren Ergebnisses wird separat festgehalten. So kann
    # eine neue Auswahl als "noch nicht neu verarbeitet" kenntlich gemacht werden,
    # ohne das bereits hochgeladene Dokument oder dessen bisheriges Ergebnis zu löschen.
    ergebnis_anbieter: str = ""
    temporaerer_ordner: tempfile.TemporaryDirectory[str] = field(
        default_factory=lambda: tempfile.TemporaryDirectory(prefix="ced_nicegui_")
    )


def _bildadresse(dateipfad: Path) -> str:
    """Erstellt eine nur im Browser verwendete Datenadresse für die Vorschau."""
    endung = dateipfad.suffix.lower()
    medientyp = "image/jpeg" if endung in {".jpg", ".jpeg"} else "image/png"
    inhalt = base64.b64encode(dateipfad.read_bytes()).decode("ascii")
    return f"data:{medientyp};base64,{inhalt}"


@ui.page("/")
def zeige_hauptseite() -> None:
    """Erzeugt die medizinische Arbeitsfläche mit separater Administration."""
    einstellungen = Settings.from_environment()
    zustand = Sitzungszustand()

    # Die Farben orientieren sich an klinischen Informationssystemen: viel Weiß,
    # zurückhaltendes Grau und Petrol als eindeutige Aktions- und Orientierungsfarbe.
    # Für CSS-Debugging kann im Browser die Elementprüfung aktiviert werden; es wird
    # bewusst kein zweites Ersatz-Stylesheet geladen, das Fehler verdecken könnte.
    ui.add_head_html("""
        <meta name="theme-color" content="#0b6664">
        <style>
          body { background: #f3f7f7; color: #183638; }
          .q-page { background: #f3f7f7; }
          .medizin-kopf { background: linear-gradient(120deg, #075c5b, #16827d);
            color: white; border-radius: 0 0 22px 22px; box-shadow: 0 8px 24px #1234; }
          .medizin-kicker { color: #bde8e4; letter-spacing: .15em;
            text-transform: uppercase; font-size: .75rem; font-weight: 700; }
          .arbeitskarte { background: white; border: 1px solid #d7e4e3;
            border-radius: 14px; box-shadow: 0 3px 14px #163b3b12; }
          .bereichstitel { color: #0b6664; font-weight: 700; font-size: 1.1rem; }
          .admin-drawer { background: #e5efee; border-right: 1px solid #bdd2d0; }
          .admin-drawer .q-drawer__content { display: flex; flex-direction: column; }
          .admin-trenner { border-top: 1px solid #bed2d0; margin: 18px 0; }
          .steuerungs-meldungen { margin-top: auto; background: #d6e5e3;
            border-top: 1px solid #aac6c3; padding: 14px 20px 18px; width: 100%;
            color: #334e50; font-size: .8rem; font-weight: 400; line-height: 1.4; }
          .status-titel { color: #334e50; font-size: .8rem; font-weight: 500; }
          .anbieter-hinweis, .arbeitsstatus { color: #334e50; font: inherit; }
          .meldungsfehler { color: #991b1b; font-weight: 600; }
          .referenzspalte, .ergebnisspalte { min-width: 320px; }
          .ergebnistext textarea { min-height: 330px !important;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
        </style>
    """)

    # Diese Elemente werden sowohl aus der Arbeitsfläche als auch aus dem Adminbereich
    # aktualisiert. Sie werden vor den Callback-Funktionen bewusst einmal angelegt.
    with ui.left_drawer(value=True).classes("admin-drawer p-5"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("admin_panel_settings", size="sm").classes("text-teal-800")
            ui.label("Steuerung / Administration").classes(
                "text-lg font-bold text-teal-900"
            )
        ui.label("LLM auswählen").classes("font-semibold text-slate-700")
        anbieter_auswahl = ui.select(
            {"uk": "UK-API (Standard)", "openai": "OpenAI"},
            value="uk",
        ).props("outlined dense").classes("w-full mt-1")
        ui.html('<div class="admin-trenner"></div>')
        ui.label("CED-Datenbank").classes("font-semibold text-slate-700")
        passwort = ui.input(
            "Administrationspasswort", password=True, password_toggle_button=True
        ).props("outlined dense").classes("w-full")
        datenbank_schalter = ui.button(icon="lock_open").props(
            "color=teal-8 unelevated"
        ).classes("w-full mt-3")

        # Sämtliche Status- und Bedienhinweise stehen gebündelt am unteren linken
        # Rand der Steuerung. So überdecken weder Toasts noch frei schwebende Chips
        # medizinische Dokumente. Zum CSS-Debugging kann im Browser geprüft werden,
        # ob ``margin-top: auto`` innerhalb des Drawer-Flexcontainers wirksam ist.
        with ui.column().classes("steuerungs-meldungen gap-2"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("info", size="xs").classes("text-teal-800")
                ui.label("Status und Hinweise").classes("status-titel")
            anbieter_hinweis = ui.label("● UK-API · UK_API_KEY").classes(
                "anbieter-hinweis"
            )
            datenbank_status = ui.label(
                "Datenbank: nicht aktiviert · Lesemodus aktiv"
            ).classes("arbeitsstatus")
            arbeitsstatus = ui.label(
                "Bereit · noch kein Dokument geladen"
            ).classes("arbeitsstatus")

    with ui.column().classes("w-full min-h-screen"):
        with ui.column().classes("medizin-kopf w-full px-8 py-7 gap-1"):
            ui.label("Medizinische Dokumentation").classes("medizin-kicker")
            ui.label("CED-A-DOKU").classes("text-3xl font-bold")
            ui.label("Assistierte Auslesung medizinischer Dokumente").classes(
                "text-teal-50"
            )

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-5"):
            # Die zwei Spalten bilden einen einzigen, stabilen Arbeitsbereich: Das
            # Referenzbild bleibt links sichtbar, während rechts Erkennung und die
            # umschaltbaren Textvarianten ohne zusätzliche Fenster erreichbar sind.
            with ui.row().classes("w-full gap-5 items-stretch flex-wrap lg:flex-nowrap"):
                with ui.card().classes(
                    "arbeitskarte referenzspalte flex-1 lg:w-1/2 p-5"
                ):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("description").classes("text-teal-700")
                        ui.label("Originaldokument").classes("bereichstitel")
                    seiten_auswahl = ui.select(
                        {}, label="Vorschauseite"
                    ).props("outlined dense").classes("flex-1")
                    with ui.row().classes("w-full items-center gap-2"):
                        seite_hoch = ui.button("Nach oben", icon="arrow_upward").props(
                            "flat dense color=teal-8"
                        )
                        seite_runter = ui.button("Nach unten", icon="arrow_downward").props(
                            "flat dense color=teal-8"
                        )
                    vorschau_platzhalter = ui.label(
                        "Noch kein Dokument ausgewählt."
                    ).classes("text-slate-500 py-12 self-center")
                    vorschau = ui.image().classes(
                        "w-full max-h-[560px] object-contain rounded-lg border"
                    )
                    vorschau.set_visibility(False)
                    upload = ui.upload(
                        label="PDF-, JPG- oder PNG-Dokumente auswählen",
                        multiple=True,
                        auto_upload=True,
                    ).props('accept=".pdf,.png,.jpg,.jpeg" color="teal-8"').classes(
                        "w-full"
                    )
                with ui.column().classes("ergebnisspalte flex-1 lg:w-1/2 gap-5"):
                    with ui.card().classes("arbeitskarte w-full p-5"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("clinical_notes").classes("text-teal-700")
                            ui.label("Dokumenterkennung").classes("bereichstitel")
                        dokumenttyp_ausgabe = ui.input(
                            "Erkannter Dokumenttyp", value=""
                        ).props("outlined readonly").classes("w-full")
                        lesen_schalter = ui.button(
                            "Dokument auslesen", icon="document_scanner"
                        ).props("color=teal-8 unelevated").classes("w-full")

                    with ui.card().classes("arbeitskarte w-full p-5"):
                        ui.label("KI-Ergebnis").classes("bereichstitel")
                        ergebnis_auswahl = ui.select(
                            {
                                "rohtext": "Rohtext",
                                "strukturiert": "Strukturierter, formatierter Text",
                                "zusammenfassung": "KI-Zusammenfassung",
                            },
                            value="rohtext",
                            label="Darstellung",
                        ).props("outlined dense").classes("w-full")
                        ergebnis_ausgabe = ui.textarea(
                            placeholder="Der ausgelesene Rohtext erscheint hier."
                        ).props("outlined readonly").classes("ergebnistext w-full")
                        kopieren_schalter = ui.button(
                            "Angezeigten Text kopieren", icon="content_copy"
                        ).props("color=teal-8 unelevated").classes("w-full")

    def setze_status(text: str, *, fehler: bool = False) -> None:
        """Zeigt den letzten Arbeitsschritt dauerhaft und ohne sensible Inhalte an.

        Für tieferes Debugging kann lokal zusätzlich der Zeitpunkt ergänzt werden.
        Dokumentnamen, Antworttexte und Secrets dürfen hier jedoch nicht erscheinen.
        """
        arbeitsstatus.text = text
        arbeitsstatus.classes(remove="meldungsfehler")
        if fehler:
            arbeitsstatus.classes(add="meldungsfehler")

    def aktualisiere_anbieter() -> None:
        """Wechselt bewusst den Anbieter, behält aber Dokument und Ergebnis bei."""
        zustand.anbieter = str(anbieter_auswahl.value)
        if zustand.anbieter == "uk":
            anbieter_hinweis.text = "● UK-API · UK_API_KEY"
        else:
            anbieter_hinweis.text = "● OpenAI · OPEN_AI_KEY"
        setze_status(
            f"{'UK-API' if zustand.anbieter == 'uk' else 'OpenAI'} ausgewählt"
        )
        if zustand.seiten:
            neuer_name = "UK-API" if zustand.anbieter == "uk" else "OpenAI"
            lesen_schalter.text = f"Dokument mit {neuer_name} neu bearbeiten"
            setze_status(
                f"Anbieter auf {neuer_name} gewechselt · Dokument bereit zur erneuten Verarbeitung"
            )

    def aktualisiere_datenbankmodus() -> None:
        """Aktiviert oder beendet den geschützten Datenbankmodus."""
        if zustand.arbeitsmodus == DATENBANKMODUS:
            zustand.arbeitsmodus = LESEMODUS
            passwort.value = ""
            passwort.set_visibility(True)
            datenbank_schalter.text = "CED-Datenbank aktivieren"
            datenbank_status.text = "Datenbank: nicht aktiviert · Lesemodus aktiv"
            setze_status("Lesemodus aktiviert · Datenbankmodus beendet")
            return

        try:
            richtiges_passwort = einstellungen.ced_database_password()
        except ConfigurationError as fehler:
            setze_status(str(fehler), fehler=True)
            return
        if not hmac.compare_digest(passwort.value or "", richtiges_passwort):
            setze_status("Das Administrationspasswort ist falsch.", fehler=True)
            return
        zustand.arbeitsmodus = DATENBANKMODUS
        passwort.value = ""
        passwort.set_visibility(False)
        datenbank_schalter.text = "Datenbankmodus beenden"
        datenbank_status.text = "Datenbank: aktiviert · geschützter Modus"
        setze_status(
            "Datenbankmodus aktiviert · strukturierte Speicherung ist noch nicht implementiert"
        )

    def zeige_seite() -> None:
        """Wechselt die Vorschau ohne die Originaldatei dauerhaft abzulegen."""
        if seiten_auswahl.value is not None:
            vorschau.set_source(_bildadresse(zustand.seiten[seiten_auswahl.value]))

    def aktualisiere_ergebnisanzeige() -> None:
        """Zeigt exakt die gewählte, bereits geprüfte Antwortvariante an."""
        varianten = {
            "rohtext": zustand.ausgelesener_inhalt,
            "strukturiert": zustand.strukturierte_darstellung,
            "zusammenfassung": zustand.kis_vorschlag,
        }
        ergebnis_ausgabe.value = varianten[str(ergebnis_auswahl.value)]

    def setze_seitenoptionen(auswahl: int | None = None) -> None:
        """Nummeriert die Seiten neu und hält die Vorschauauswahl konsistent."""
        seiten_auswahl.options = {
            nummer: f"Seite {nummer + 1}" for nummer in range(len(zustand.seiten))
        }
        seiten_auswahl.value = auswahl
        seiten_auswahl.update()
        if auswahl is not None:
            zeige_seite()

    def verschiebe_seite(richtung: int) -> None:
        """Verschiebt die ausgewählte Seite zur manuellen Reihenfolgekorrektur."""
        if seiten_auswahl.value is None:
            return
        bisher = int(seiten_auswahl.value)
        neu = bisher + richtung
        if not 0 <= neu < len(zustand.seiten):
            return
        zustand.seiten[bisher], zustand.seiten[neu] = (
            zustand.seiten[neu],
            zustand.seiten[bisher],
        )
        setze_seitenoptionen(neu)
        setze_status(f"Seite {bisher + 1} wurde an Position {neu + 1} verschoben")

    def uebernehme_dokumente(dateien: list[tuple[str, bytes]]) -> None:
        """Hängt mehrere Upload-, Drop- oder Zwischenablagedateien gemeinsam an.

        Debugging-Hinweis: Falls ein Browser kein Bild liefert, kann in dessen
        Entwicklerwerkzeugen der MIME-Typ des Clipboard-Items geprüft werden. Der
        medizinische Bildinhalt darf dabei nicht in Konsolen-Logs ausgegeben werden.
        """
        # Neue Quellen werden in der vom Browser gelieferten Reihenfolge angehängt.
        # Das vorhandene Ergebnis wird zurückgesetzt, weil es nicht mehr zur nun
        # erweiterten Seitenmenge passt; bereits geladene Seiten bleiben erhalten.
        zustand.dokumenttyp = ""
        zustand.ausgelesener_inhalt = ""
        zustand.strukturierte_darstellung = ""
        zustand.kis_vorschlag = ""
        zustand.letzter_fehler = ""
        zustand.ergebnis_anbieter = ""
        dokumenttyp_ausgabe.value = ""
        ergebnis_ausgabe.value = ""
        ergebnis_auswahl.value = "rohtext"
        lesen_schalter.text = "Dokument auslesen"
        setze_status("Dokument wird importiert und für die Vorschau vorbereitet …")
        try:
            wurzel = Path(zustand.temporaerer_ordner.name)
            quellpfade: list[Path] = []
            for dateiname, dateiinhalt in dateien:
                # Die UUID vermeidet Kollisionen, wenn mehrere Screenshots denselben
                # Namen tragen. Der Originalname wird nur lokal als Suffix bewahrt.
                quellpfad = wurzel / f"{uuid.uuid4().hex}-{Path(dateiname).name}"
                quellpfad.write_bytes(dateiinhalt)
                quellpfade.append(quellpfad)
            neue_seiten = DocumentConverter(wurzel / "seiten").convert(quellpfade)
            erster_neuer_index = len(zustand.seiten)
            zustand.seiten.extend(neue_seiten)
        except (DocumentConversionError, OSError) as fehler:
            # Debugging: Bei Bedarf lokal Dateityp und Exception-Typ prüfen. Namen
            # oder Inhalte medizinischer Dokumente nie in produktive Logs schreiben.
            setze_status(f"Dokumentimport fehlgeschlagen: {fehler}", fehler=True)
            return
        setze_seitenoptionen(erster_neuer_index)
        vorschau_platzhalter.set_visibility(False)
        vorschau.set_visibility(True)
        setze_status(
            f"{len(zustand.seiten)} Seite(n) vorbereitet · Anbieter wählen und Bearbeitung starten"
        )

    def uebernehme_datei(ereignis: events.UploadEventArguments) -> None:
        """Hängt jede Datei einer Mehrfachauswahl an die vorhandenen Seiten an."""
        uebernehme_dokumente([(ereignis.name, ereignis.content.read())])

    def uebernehme_abgelegte_dateien(ereignis: events.GenericEventArguments) -> None:
        """Übernimmt Drop- oder Clipboard-Dateien in der gelieferten Reihenfolge."""
        dateien = [
            (eintrag["name"], base64.b64decode(eintrag["base64"], validate=True))
            for eintrag in ereignis.args["dateien"]
        ]
        uebernehme_dokumente(dateien)

    async def lese_dokument() -> None:
        """Bearbeitet erhaltene Seiten erneut mit dem gerade gewählten Anbieter.

        Der Netzwerkaufruf läuft in einem I/O-Worker, damit der Browser den Status
        bereits vor der möglicherweise langen LLM-Anfrage darstellen kann. Ein Fehler
        löst ausdrücklich keinen automatischen Anbieterwechsel aus: Die Oberfläche
        schlägt lediglich die bewusste Alternative vor und bewahrt die Seiten.
        """
        if not zustand.seiten:
            setze_status("Warte auf Dokumentupload")
            return
        anbieter_name = "UK-API" if zustand.anbieter == "uk" else "OpenAI"
        lesen_schalter.disable()
        setze_status(
            f"{anbieter_name}: {len(zustand.seiten)} Seite(n) werden verarbeitet …"
        )
        try:
            ki_anbieter = (
                LocalAPIProvider(einstellungen)
                if zustand.anbieter == "uk"
                else CloudAPIProvider(einstellungen)
            )
            # ``run.io_bound`` hält die Oberfläche reaktionsfähig. Es ist kein
            # Fallback: Aufgerufen wird ausschließlich der oben ausgewählte Provider.
            ergebnis = await run.io_bound(ki_anbieter.process_document, list(zustand.seiten))
            zustand.dokumenttyp = ergebnis.dokumenttyp.value
            zustand.ausgelesener_inhalt = ergebnis.ausgelesener_inhalt
            zustand.strukturierte_darstellung = ergebnis.strukturierte_darstellung
            zustand.kis_vorschlag = ergebnis.kis_vorschlag
            zustand.ergebnis_anbieter = zustand.anbieter
            dokumenttyp_ausgabe.value = zustand.dokumenttyp
            aktualisiere_ergebnisanzeige()
            lesen_schalter.text = f"Dokument mit {anbieter_name} neu bearbeiten"
            setze_status(f"{anbieter_name}: Verarbeitung abgeschlossen · Ergebnis ungeprüft")
        except (ConfigurationError, AIProviderError, DokumentAntwortFehler, OSError, ValueError) as fehler:
            # Debugging: Endpunkt, Modell und Secret-Verfügbarkeit prüfen. Es gibt
            # absichtlich keinen Fallback; Schlüssel und Dokumentinhalt nie loggen.
            zustand.letzter_fehler = str(fehler)
            alternative = "OpenAI" if zustand.anbieter == "uk" else "UK-API"
            setze_status(
                f"{anbieter_name}: {fehler} Dokument bleibt erhalten; Sie können "
                f"{alternative} auswählen und es erneut bearbeiten.",
                fehler=True,
            )
        finally:
            lesen_schalter.enable()

    def kopiere_ergebnis() -> None:
        """Kopiert unmittelbar und unverändert die aktuell sichtbare Textvariante."""
        ui.clipboard.write(ergebnis_ausgabe.value or "")
        setze_status("Angezeigten Text in die Zwischenablage kopiert")

    anbieter_auswahl.on_value_change(lambda _: aktualisiere_anbieter())
    datenbank_schalter.text = "CED-Datenbank aktivieren"
    datenbank_schalter.on_click(aktualisiere_datenbankmodus)
    seiten_auswahl.on_value_change(lambda _: zeige_seite())
    seite_hoch.on_click(lambda: verschiebe_seite(-1))
    seite_runter.on_click(lambda: verschiebe_seite(1))
    upload.on_upload(uebernehme_datei)
    lesen_schalter.on_click(lese_dokument)
    ergebnis_auswahl.on_value_change(lambda _: aktualisiere_ergebnisanzeige())
    kopieren_schalter.on_click(kopiere_ergebnis)
    ui.on("abgelegte_dateien", uebernehme_abgelegte_dateien)

    # Der Browser liest ausschließlich Bildobjekte aus einem echten Paste-Ereignis.
    # Zusätzlich fängt die Seite Datei-Drops außerhalb des sichtbaren Uploaders ab.
    ui.run_javascript(r"""
        // Außerhalb des Upload-Feldes abgelegte Dateien werden als geordnete
        // Gruppe gelesen. Innerhalb des Uploaders übernimmt NiceGUI den Drop, damit
        // dasselbe Dokument nicht doppelt importiert wird.
        document.addEventListener('dragover', event => {
            if (event.dataTransfer?.types.includes('Files')) event.preventDefault();
        });
        document.addEventListener('drop', async event => {
            if (!event.dataTransfer?.files.length || event.target.closest('.q-uploader')) return;
            event.preventDefault();
            const erlaubt = /\.(pdf|png|jpe?g)$/i;
            const dateien = [...event.dataTransfer.files].filter(datei => erlaubt.test(datei.name));
            const gelesen = await Promise.all(dateien.map(datei => new Promise((resolve, reject) => {
                const leser = new FileReader();
                leser.onload = () => resolve({
                    name: datei.name,
                    base64: String(leser.result).split(',', 2)[1],
                });
                leser.onerror = reject;
                leser.readAsDataURL(datei);
            })));
            if (gelesen.length) emitEvent('abgelegte_dateien', {dateien: gelesen});
        });
        document.addEventListener('paste', async event => {
            const bilder = [...(event.clipboardData?.items || [])]
                .filter(eintrag => eintrag.type.startsWith('image/'));
            if (!bilder.length) return;
            event.preventDefault();
            const gelesen = await Promise.all(bilder.map((bild, index) =>
                new Promise((resolve, reject) => {
                    const leser = new FileReader();
                    leser.onload = () => resolve({
                        name: `zwischenablage-${index + 1}.png`,
                        base64: String(leser.result).split(',', 2)[1],
                    });
                    leser.onerror = reject;
                    leser.readAsDataURL(bild.getAsFile());
                })));
            emitEvent('abgelegte_dateien', {dateien: gelesen});
        });
    """)


def _pruefe_port(port: int) -> None:
    """Beendet den Start mit einer verständlichen Hilfe, wenn der Port belegt ist."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as pruefung:
        pruefung.settimeout(0.3)
        if pruefung.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(
                f"CED-A-DOKU wurde nicht gestartet: Port {port} ist bereits belegt.\n"
                f"Prüfen: lsof -i :{port}\n"
                "Den dort angezeigten alten Webserver beenden oder vor dem Start "
                "bewusst einen anderen Port setzen, z. B. CED_WEB_PORT=8502."
            )


def starte_anwendung() -> None:
    """Initialisiert SQLite und startet NiceGUI auf dem ausdrücklich gewählten Port."""
    # Es erfolgt kein automatischer Ausweichport: Dadurch bleibt die in Codespaces
    # freigegebene Adresse vorhersehbar. CED_WEB_PORT erlaubt eine bewusste Änderung.
    port = int(os.getenv("CED_WEB_PORT", "8501"))
    _pruefe_port(port)
    initialize_database()
    ui.run(title="CED-A-DOKU", host="0.0.0.0", port=port, reload=False)
