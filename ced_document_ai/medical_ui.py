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
          .status-chip { background: #e3f2ef; color: #075c5b; border: 1px solid #b7d9d5;
            border-radius: 999px; padding: 5px 12px; font-weight: 600; }
          .admin-drawer { background: #e5efee; border-right: 1px solid #bdd2d0; }
          .admin-trenner { border-top: 1px solid #bed2d0; margin: 18px 0; }
          .anbieter-hinweis { position: fixed; right: 18px; bottom: 12px;
            color: white; padding: 7px 13px; border-radius: 9px; z-index: 9999;
            font-weight: bold; box-shadow: 0 3px 12px #0004; }
          .arbeitsstatus { position: fixed; right: 18px; bottom: 58px;
            background: #183638; color: white; padding: 7px 13px; border-radius: 9px;
            z-index: 9999; box-shadow: 0 3px 12px #0003; max-width: 520px; }
          .datenschutz { background: #fff4e5; border-left: 5px solid #d97706;
            padding: 12px; border-radius: 7px; color: #713f12; }
          .referenzspalte, .ergebnisspalte { min-width: 320px; }
          .ergebnistext textarea { min-height: 330px !important;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
        </style>
    """)

    # Der Dialog ist modal. Damit kann OpenAI nicht unbemerkt ausgewählt werden;
    # die Auswahl bleibt sichtbar, bis der konkrete Datenschutzhinweis bestätigt ist.
    with ui.dialog() as datenschutz_dialog, ui.card().classes("w-full max-w-lg p-6"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("privacy_tip", size="md").classes("text-orange-700")
            ui.label("Datenschutzhinweis").classes("text-xl font-bold text-slate-800")
        ui.label(
            "Bei Verwendung von OpenAI dürfen keine personenbezogenen Daten oder "
            "Dokumente mit identifizierbaren Patientendaten übermittelt werden."
        ).classes("datenschutz my-4")
        ui.button("O. K.", on_click=datenschutz_dialog.close, icon="check").props(
            "color=teal-8 unelevated"
        ).classes("self-end")

    # Diese Elemente werden sowohl aus der Arbeitsfläche als auch aus dem Adminbereich
    # aktualisiert. Sie werden vor den Callback-Funktionen bewusst einmal angelegt.
    with ui.left_drawer(value=True).classes("admin-drawer p-5"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("admin_panel_settings", size="sm").classes("text-teal-800")
            ui.label("Steuerung / Administration").classes(
                "text-lg font-bold text-teal-900"
            )
        ui.label("Zugriff auf sensible Verarbeitungsfunktionen").classes(
            "text-xs text-slate-600 mb-5"
        )

        ui.label("LLM auswählen").classes("font-semibold text-slate-700")
        anbieter_auswahl = ui.select(
            {"uk": "UK-API (Standard)", "openai": "OpenAI"},
            value="uk",
        ).props("outlined dense").classes("w-full mt-1")
        ui.label("Kein automatischer Wechsel zwischen den Anbietern.").classes(
            "text-xs text-slate-500 mt-1"
        )
        ui.label(
            "Die Auswahl kann auch nach einem Upload geändert werden. Mit "
            "„Dokument neu bearbeiten“ wird dasselbe Dokument erneut verarbeitet."
        ).classes("text-xs text-slate-600 mt-2")
        ui.html('<div class="admin-trenner"></div>')
        ui.label("CED-Datenbank").classes("font-semibold text-slate-700")
        datenbank_status = ui.label("Nicht aktiviert · Lesemodus aktiv").classes(
            "text-sm text-slate-600 my-2"
        )
        passwort = ui.input(
            "Administrationspasswort", password=True, password_toggle_button=True
        ).props("outlined dense").classes("w-full")
        datenbank_schalter = ui.button(icon="lock_open").props(
            "color=teal-8 unelevated"
        ).classes("w-full mt-3")

    with ui.column().classes("w-full min-h-screen"):
        with ui.column().classes("medizin-kopf w-full px-8 py-7 gap-1"):
            ui.label("Medizinische Dokumentation").classes("medizin-kicker")
            ui.label("CED-A-DOKU").classes("text-3xl font-bold")
            ui.label("Assistierte Auslesung medizinischer Dokumente").classes(
                "text-teal-50"
            )

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-5"):
            modus_status = ui.label(f"● {LESEMODUS}").classes("status-chip self-start")

            datenbank_banner = ui.label(
                "Datenbankmodus aktiv: Die strukturierte Speicherung wird erst in "
                "einer nachfolgenden Phase implementiert."
            ).classes("w-full bg-orange-50 border border-orange-200 p-3 rounded-lg")
            datenbank_banner.set_visibility(False)

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
                    ).props("outlined dense").classes("w-52")
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
                    ui.label(
                        "Zusätzlich können Sie einen Screenshot mit Strg+V oder "
                        "Win+Umschalt+V aus der Zwischenablage einfügen."
                    ).classes("text-sm text-slate-500")

                with ui.column().classes("ergebnisspalte flex-1 lg:w-1/2 gap-5"):
                    with ui.card().classes("arbeitskarte w-full p-5"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("clinical_notes").classes("text-teal-700")
                            ui.label("Dokumenterkennung").classes("bereichstitel")
                        dokumenttyp_ausgabe = ui.input(
                            "Erkannter Dokumenttyp", value=""
                        ).props("outlined readonly").classes("w-full")
                        fehler_ausgabe = ui.label("").classes(
                            "w-full bg-red-50 border border-red-300 text-red-900 p-3 rounded-lg"
                        )
                        fehler_ausgabe.set_visibility(False)
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

    anbieter_hinweis = ui.label("● UK-API · UK_API_KEY").classes("anbieter-hinweis")
    anbieter_hinweis.style("background: #16833b")
    arbeitsstatus = ui.label("Bereit · noch kein Dokument geladen").classes("arbeitsstatus")

    def setze_status(text: str) -> None:
        """Zeigt den letzten Arbeitsschritt dauerhaft und ohne sensible Inhalte an.

        Für tieferes Debugging kann lokal zusätzlich der Zeitpunkt ergänzt werden.
        Dokumentnamen, Antworttexte und Secrets dürfen hier jedoch nicht erscheinen.
        """
        arbeitsstatus.text = text

    def aktualisiere_anbieter() -> None:
        """Wechselt bewusst den Anbieter, behält aber Dokument und Ergebnis bei."""
        zustand.anbieter = str(anbieter_auswahl.value)
        if zustand.anbieter == "uk":
            anbieter_hinweis.text = "● UK-API · UK_API_KEY"
            anbieter_hinweis.style("background: #16833b")
        else:
            anbieter_hinweis.text = "● OpenAI · OPENAI_API_KEY"
            anbieter_hinweis.style("background: #b42318")
            datenschutz_dialog.open()
        if zustand.seiten:
            neuer_name = "UK-API" if zustand.anbieter == "uk" else "OpenAI"
            lesen_schalter.text = f"Dokument mit {neuer_name} neu bearbeiten"
            setze_status(
                f"Anbieter auf {neuer_name} gewechselt · Dokument bereit zur erneuten Verarbeitung"
            )
            ui.notify(
                f"{neuer_name} ausgewählt. Das hochgeladene Dokument bleibt erhalten; "
                "starten Sie die Bearbeitung erneut.",
                type="info",
                timeout=6000,
            )

    def aktualisiere_datenbankmodus() -> None:
        """Aktiviert oder beendet den geschützten Datenbankmodus."""
        if zustand.arbeitsmodus == DATENBANKMODUS:
            zustand.arbeitsmodus = LESEMODUS
            passwort.value = ""
            passwort.set_visibility(True)
            datenbank_schalter.text = "CED-Datenbank aktivieren"
            datenbank_status.text = "Nicht aktiviert · Lesemodus aktiv"
            modus_status.text = f"● {LESEMODUS}"
            datenbank_banner.set_visibility(False)
            return

        try:
            richtiges_passwort = einstellungen.ced_database_password()
        except ConfigurationError as fehler:
            ui.notify(str(fehler), type="negative", timeout=10000)
            return
        if not hmac.compare_digest(passwort.value or "", richtiges_passwort):
            ui.notify("Das Administrationspasswort ist falsch.", type="negative")
            return
        zustand.arbeitsmodus = DATENBANKMODUS
        passwort.value = ""
        passwort.set_visibility(False)
        datenbank_schalter.text = "Datenbankmodus beenden"
        datenbank_status.text = "Aktiviert · geschützter Datenbankmodus"
        modus_status.text = f"● {DATENBANKMODUS}"
        datenbank_banner.set_visibility(True)

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

    def uebernehme_dokument(dateiname: str, dateiinhalt: bytes) -> None:
        """Konvertiert Upload oder Zwischenablage über denselben Importweg.

        Debugging-Hinweis: Falls ein Browser kein Bild liefert, kann in dessen
        Entwicklerwerkzeugen der MIME-Typ des Clipboard-Items geprüft werden. Der
        medizinische Bildinhalt darf dabei nicht in Konsolen-Logs ausgegeben werden.
        """
        # Ein neuer Upload beginnt zwingend eine neue Ergebnismenge. Auch frühere
        # Fehler verschwinden; Ersatztexte werden in keines der vier Felder geschrieben.
        zustand.seiten.clear()
        zustand.dokumenttyp = ""
        zustand.ausgelesener_inhalt = ""
        zustand.strukturierte_darstellung = ""
        zustand.kis_vorschlag = ""
        zustand.letzter_fehler = ""
        zustand.ergebnis_anbieter = ""
        dokumenttyp_ausgabe.value = ""
        ergebnis_ausgabe.value = ""
        ergebnis_auswahl.value = "rohtext"
        fehler_ausgabe.text = ""
        fehler_ausgabe.set_visibility(False)
        lesen_schalter.text = "Dokument auslesen"
        setze_status("Dokument wird importiert und für die Vorschau vorbereitet …")
        try:
            wurzel = Path(zustand.temporaerer_ordner.name)
            quellpfad = wurzel / Path(dateiname).name
            quellpfad.write_bytes(dateiinhalt)
            zustand.seiten.extend(DocumentConverter(wurzel / "seiten").convert([quellpfad]))
        except (DocumentConversionError, OSError) as fehler:
            # Debugging: Bei Bedarf lokal Dateityp und Exception-Typ prüfen. Namen
            # oder Inhalte medizinischer Dokumente nie in produktive Logs schreiben.
            ui.notify(f"Dokumentimport fehlgeschlagen: {fehler}", type="negative")
            setze_status("Dokumentimport fehlgeschlagen · technischen Hinweis prüfen")
            return
        seiten_auswahl.options = {
            nummer: f"Seite {nummer + 1}" for nummer in range(len(zustand.seiten))
        }
        seiten_auswahl.value = 0
        seiten_auswahl.update()
        vorschau_platzhalter.set_visibility(False)
        vorschau.set_visibility(True)
        zeige_seite()
        setze_status(
            f"{len(zustand.seiten)} Seite(n) vorbereitet · Anbieter wählen und Bearbeitung starten"
        )
        ui.notify(f"{len(zustand.seiten)} Seite(n) vorbereitet", type="positive")

    def uebernehme_datei(ereignis: events.UploadEventArguments) -> None:
        """Reicht den bewährten Datei-Upload unverändert an den Importweg weiter."""
        uebernehme_dokument(ereignis.name, ereignis.content.read())

    def uebernehme_zwischenablage(ereignis: events.GenericEventArguments) -> None:
        """Dekodiert genau das vom Browser übergebene Screenshot-Bild."""
        daten = ereignis.args
        dateiname = f"zwischenablage-{uuid.uuid4().hex}.png"
        uebernehme_dokument(dateiname, base64.b64decode(daten["base64"], validate=True))

    async def lese_dokument() -> None:
        """Bearbeitet erhaltene Seiten erneut mit dem gerade gewählten Anbieter.

        Der Netzwerkaufruf läuft in einem I/O-Worker, damit der Browser den Status
        bereits vor der möglicherweise langen LLM-Anfrage darstellen kann. Ein Fehler
        löst ausdrücklich keinen automatischen Anbieterwechsel aus: Die Oberfläche
        schlägt lediglich die bewusste Alternative vor und bewahrt die Seiten.
        """
        if not zustand.seiten:
            ui.notify("Bitte zuerst ein Dokument auswählen.", type="warning")
            setze_status("Warte auf Dokumentupload")
            return
        anbieter_name = "UK-API" if zustand.anbieter == "uk" else "OpenAI"
        lesen_schalter.disable()
        setze_status(
            f"{anbieter_name}: {len(zustand.seiten)} Seite(n) werden verarbeitet …"
        )
        fehler_ausgabe.set_visibility(False)
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
            fehler_ausgabe.set_visibility(False)
            lesen_schalter.text = f"Dokument mit {anbieter_name} neu bearbeiten"
            setze_status(f"{anbieter_name}: Verarbeitung abgeschlossen · Ergebnis ungeprüft")
            ui.notify(
                f"Verarbeitung mit {anbieter_name} abgeschlossen.",
                type="positive",
                timeout=4000,
            )
        except (ConfigurationError, AIProviderError, DokumentAntwortFehler, OSError, ValueError) as fehler:
            # Debugging: Endpunkt, Modell und Secret-Verfügbarkeit prüfen. Es gibt
            # absichtlich keinen Fallback; Schlüssel und Dokumentinhalt nie loggen.
            zustand.letzter_fehler = str(fehler)
            fehler_ausgabe.text = zustand.letzter_fehler
            fehler_ausgabe.set_visibility(True)
            alternative = "OpenAI" if zustand.anbieter == "uk" else "UK-API"
            setze_status(
                f"{anbieter_name}: Verarbeitung fehlgeschlagen · Dokument bleibt für neuen Versuch erhalten"
            )
            ui.notify(
                f"{fehler} Sie können links {alternative} auswählen und dasselbe "
                "Dokument erneut bearbeiten.",
                type="negative",
                timeout=12000,
            )
        finally:
            lesen_schalter.enable()

    def kopiere_ergebnis() -> None:
        """Kopiert unmittelbar und unverändert die aktuell sichtbare Textvariante."""
        ui.clipboard.write(ergebnis_ausgabe.value or "")
        ui.notify("Angezeigten Text kopiert", type="positive", timeout=1800)

    anbieter_auswahl.on_value_change(lambda _: aktualisiere_anbieter())
    datenbank_schalter.text = "CED-Datenbank aktivieren"
    datenbank_schalter.on_click(aktualisiere_datenbankmodus)
    seiten_auswahl.on_value_change(lambda _: zeige_seite())
    upload.on_upload(uebernehme_datei)
    lesen_schalter.on_click(lese_dokument)
    ergebnis_auswahl.on_value_change(lambda _: aktualisiere_ergebnisanzeige())
    kopieren_schalter.on_click(kopiere_ergebnis)
    ui.on("zwischenablage_bild", uebernehme_zwischenablage)

    # Der Browser liest ausschließlich Bildobjekte aus einem echten Paste-Ereignis.
    # Datei- und Drag-and-drop-Import bleiben davon unabhängig und unverändert aktiv.
    ui.run_javascript("""
        document.addEventListener('paste', event => {
            const bild = [...(event.clipboardData?.items || [])]
                .find(eintrag => eintrag.type.startsWith('image/'));
            if (!bild) return;
            event.preventDefault();
            const leser = new FileReader();
            leser.onload = () => emitEvent('zwischenablage_bild', {
                base64: String(leser.result).split(',', 2)[1],
            });
            leser.readAsDataURL(bild.getAsFile());
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
