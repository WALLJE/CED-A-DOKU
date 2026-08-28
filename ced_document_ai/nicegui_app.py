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
from dataclasses import dataclass, field
from pathlib import Path

from nicegui import events, ui

from ced_document_ai.config.settings import ConfigurationError, Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.services.ai.providers import (
    AIProviderError,
    CloudAPIProvider,
    LocalAPIProvider,
)
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
          .datenschutz { background: #fff4e5; border-left: 5px solid #d97706;
            padding: 12px; border-radius: 7px; color: #713f12; }
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
            with ui.row().classes("w-full items-center justify-between"):
                modus_status = ui.label(f"● {LESEMODUS}").classes("status-chip")
                ui.label("UK-API ist als sicherer Standard vorausgewählt.").classes(
                    "text-sm text-slate-500"
                )

            ui.label(
                "KI-Ergebnisse sind ungeprüfte Vorschläge und dürfen nicht automatisch "
                "als medizinische Fakten oder Therapieentscheidungen übernommen werden."
            ).classes("w-full bg-blue-50 border border-blue-200 text-blue-900 p-3 rounded-lg")

            datenbank_banner = ui.label(
                "Datenbankmodus aktiv: Die strukturierte Speicherung wird erst in "
                "einer nachfolgenden Phase implementiert."
            ).classes("w-full bg-orange-50 border border-orange-200 p-3 rounded-lg")
            datenbank_banner.set_visibility(False)

            with ui.row().classes("w-full gap-5 items-stretch"):
                with ui.card().classes("arbeitskarte flex-1 min-w-[320px] p-5"):
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

                with ui.card().classes("arbeitskarte flex-1 min-w-[320px] p-5"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("clinical_notes").classes("text-teal-700")
                        ui.label("Ausgelesener Reintext").classes("bereichstitel")
                    ausgabe = ui.textarea(
                        label="Ungeprüfte KI-Ausgabe",
                        placeholder="Nach der KI-Auslesung erscheint der Dokumentinhalt hier.",
                    ).props("outlined readonly").classes("w-full min-h-[430px]")
                    lesen_schalter = ui.button(
                        "Dokument auslesen", icon="document_scanner"
                    ).props("color=teal-8 unelevated").classes("w-full")

    anbieter_hinweis = ui.label("● UK-API · UK_API_KEY").classes("anbieter-hinweis")
    anbieter_hinweis.style("background: #16833b")

    def aktualisiere_anbieter() -> None:
        """Übernimmt die bewusste Auswahl und kennzeichnet sie unübersehbar."""
        zustand.anbieter = str(anbieter_auswahl.value)
        if zustand.anbieter == "uk":
            anbieter_hinweis.text = "● UK-API · UK_API_KEY"
            anbieter_hinweis.style("background: #16833b")
        else:
            anbieter_hinweis.text = "● OpenAI · OPENAI_API_KEY"
            anbieter_hinweis.style("background: #b42318")
            datenschutz_dialog.open()

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

    def uebernehme_datei(ereignis: events.UploadEventArguments) -> None:
        """Konvertiert genau den erhaltenen Upload und meldet Fehler unverfälscht."""
        try:
            wurzel = Path(zustand.temporaerer_ordner.name)
            quellpfad = wurzel / Path(ereignis.name).name
            quellpfad.write_bytes(ereignis.content.read())
            zustand.seiten.extend(DocumentConverter(wurzel / "seiten").convert([quellpfad]))
        except (DocumentConversionError, OSError) as fehler:
            # Debugging: Bei Bedarf lokal Dateityp und Exception-Typ prüfen. Namen
            # oder Inhalte medizinischer Dokumente nie in produktive Logs schreiben.
            ui.notify(f"Dokumentimport fehlgeschlagen: {fehler}", type="negative")
            return
        seiten_auswahl.options = {
            nummer: f"Seite {nummer + 1}" for nummer in range(len(zustand.seiten))
        }
        seiten_auswahl.value = 0
        seiten_auswahl.update()
        vorschau_platzhalter.set_visibility(False)
        vorschau.set_visibility(True)
        zeige_seite()
        ui.notify(f"{len(zustand.seiten)} Seite(n) vorbereitet", type="positive")

    def lese_dokument() -> None:
        """Sendet Seiten ausschließlich an den sichtbar gewählten Anbieter."""
        if not zustand.seiten:
            ui.notify("Bitte zuerst ein Dokument auswählen.", type="warning")
            return
        try:
            ki_anbieter = (
                LocalAPIProvider(einstellungen)
                if zustand.anbieter == "uk"
                else CloudAPIProvider(einstellungen)
            )
            ausgabe.value = ki_anbieter.analyze(
                zustand.seiten, "noch nicht klassifiziert", [], {}
            )
        except (ConfigurationError, AIProviderError, OSError, ValueError) as fehler:
            # Debugging: Endpunkt, Modell und Secret-Verfügbarkeit prüfen. Es gibt
            # absichtlich keinen Fallback; Schlüssel und Dokumentinhalt nie loggen.
            ui.notify(str(fehler), type="negative", timeout=10000)

    anbieter_auswahl.on_value_change(lambda _: aktualisiere_anbieter())
    datenbank_schalter.text = "CED-Datenbank aktivieren"
    datenbank_schalter.on_click(aktualisiere_datenbankmodus)
    seiten_auswahl.on_value_change(lambda _: zeige_seite())
    upload.on_upload(uebernehme_datei)
    lesen_schalter.on_click(lese_dokument)


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
