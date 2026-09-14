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
from datetime import date
from pathlib import Path

from nicegui import events, run, ui
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ced_document_ai.config.settings import ConfigurationError, Settings
from ced_document_ai.database.database import get_session, initialize_database
from ced_document_ai.database.models import ConfidenceStatus, Patient
from ced_document_ai.services.ai.providers import (
    AIProviderError,
    CloudAPIProvider,
    LocalAPIProvider,
)
from ced_document_ai.services.ai.document_workflow import DokumentAntwortFehler, Dokumenttyp
from ced_document_ai.services.ced.patient_matching import (
    ErkanntePatientendaten,
    erkenne_patientendaten,
    ermittle_patiententreffer,
)
from ced_document_ai.services.ced.patient_overview import lade_patientenuebersicht
from ced_document_ai.services.ced.questionnaire_parser import (
    ExtrahierterBefund,
    erkenne_befunddatum,
    parse_ced_fragebogen,
)
from ced_document_ai.services.ced.storage import (
    CEDSpeicherauftrag,
    FreigegebenerBefund,
    speichere_ced_pruefung,
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
    dokumentnamen: list[str] = field(default_factory=list)
    # Die vier Werte gehören immer zu genau demselben Dokument. Sie werden beim
    # nächsten Upload gemeinsam gelöscht, sodass keine alten Ergebnisse stehen bleiben.
    dokumenttyp: str = ""
    ausgelesener_inhalt: str = ""
    strukturierte_darstellung: str = ""
    kis_vorschlag: str = ""
    rohe_ki_antwort: str = ""
    letzter_fehler: str = ""
    # Die Zuordnung wird nur als Datenbank-ID in dieser Browser-Sitzung gehalten.
    # Ein erkannter Vorschlag setzt diesen Wert niemals automatisch.
    patient_id: int | None = None
    erkannte_patientendaten: ErkanntePatientendaten = field(
        default_factory=ErkanntePatientendaten
    )
    # CED-Befunde bleiben bis zu einer späteren ausdrücklichen Freigabe rein
    # temporär. Dieser Umsetzungsschritt schreibt noch keinen Befund in SQLite.
    ced_befunde: list[ExtrahierterBefund] = field(default_factory=list)
    gespeichertes_dokument_id: int | None = None
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
          .upload-hervorgehoben { background: #edfafa; border: 2px dashed #16827d;
            border-radius: 12px; padding: 14px; }
          .upload-hinweis { color: #37817e; font-size: .86rem; font-weight: 500; }
          /* Nach dem Upload zeigt NiceGUI standardmäßig noch einmal eine Datei-/
             Bildvorschau. Sie ist hier redundant, weil jedes Dokumentteil bereits
             oberhalb im sortierbaren Raster erscheint. Bei CSS-Problemen kann im
             Browser geprüft werden, ob NiceGUI weiterhin ``q-uploader__list`` nutzt. */
          .datei-upload .q-uploader__list { display: none; }
          .vorschau-raster { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px; width: 100%; }
          .vorschau-karte { border: 1px solid #cfe0df; border-radius: 10px;
            background: #f9fcfc; padding: 9px; min-width: 0; }
          .vorschau-bild { width: 100%; height: 190px; object-fit: contain;
            background: white; border-radius: 7px; }
          .ki-dreher { animation: ki-drehen 1.1s linear infinite; }
          @keyframes ki-drehen { to { transform: rotate(360deg); } }
          @media (max-width: 680px) {
            .vorschau-raster { grid-template-columns: minmax(0, 1fr); }
          }
          .ergebnistext textarea { min-height: 330px !important;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
          /* Die CED-Prüfung besitzt einen eigenen Vollbild-Arbeitsbereich. Die feste
             Tabellenhöhe hält Kopf, Befunddatum und Speicherschalter erreichbar;
             umfangreiche Befundlisten scrollen ausschließlich innerhalb des Rasters. */
          .ced-pruefdialog .q-dialog__inner { padding: 0; }
          .ced-pruefseite { width: 100vw; max-width: none !important; min-height: 100vh;
            border-radius: 0; margin: 0; background: #f3f7f7; }
          .ced-tabellenrahmen { height: min(58vh, 680px); min-height: 320px; }
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
        ced_navigation = ui.button(
            "CED-Daten einlesen", icon="fact_check"
        ).props("outline color=teal-8").classes("w-full mt-3")
        patientenansicht_navigation = ui.button(
            "Patientenübersicht", icon="person"
        ).props("outline color=teal-8").classes("w-full mt-2")
        # Der Menüpunkt darf vor der Passwortfreigabe keine Rückschlüsse auf
        # Patientendaten oder vorbereitete Befunde ermöglichen.
        ced_navigation.set_visibility(False)
        ced_navigation.disable()
        patientenansicht_navigation.set_visibility(False)
        patientenansicht_navigation.disable()

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
            with ui.row().classes("items-center gap-2 no-wrap"):
                ki_statussymbol = ui.icon("progress_activity", size="sm").classes(
                    "ki-dreher text-amber-700"
                )
                arbeitsstatus = ui.label(
                    "Bereit · noch kein Dokument geladen"
                ).classes("arbeitsstatus")
            ki_statussymbol.set_visibility(False)

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
                    vorschau_platzhalter = ui.label(
                        "Noch keine Dokumentseiten übernommen."
                    ).classes("text-slate-500 italic py-5 self-center")
                    vorschau_bereich = ui.element("div").classes("vorschau-raster")
                    with ui.column().classes("upload-hervorgehoben w-full gap-2"):
                        ui.label("Befunde und Dokumente hier hineinziehen").classes(
                            "upload-hinweis"
                        )
                        upload = ui.upload(
                            label="PDF-, JPG- oder PNG-Dateien auswählen",
                            multiple=True,
                            auto_upload=True,
                        ).props(
                            'accept=".pdf,.png,.jpg,.jpeg" color="teal-8" flat bordered'
                        ).classes("datei-upload w-full bg-white rounded-lg")
                        ui.label(
                            "Auch Einfügen aus der Zwischenablage ist mit Strg+V / Cmd+V möglich."
                        ).classes("upload-hinweis")
                    with ui.row().classes("w-full gap-2"):
                        neu_schalter = ui.button(
                            "Neues Dokument einlesen", icon="note_add"
                        ).props("outline color=teal-8")
                        alles_loeschen_schalter = ui.button(
                            "Alles löschen / neu beginnen", icon="delete_sweep"
                        ).props("outline color=negative")
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

                    # Der Bereich bleibt nicht nur deaktiviert, sondern vollständig
                    # verborgen, bis das Administrationspasswort bestätigt wurde.
                    # Seine Auswahlliste wird erst beim Entsperren aus SQLite gefüllt,
                    # damit Patientendaten vorher nicht an den Browser gelangen.
                    with ui.card().classes("arbeitskarte w-full p-5") as patienten_karte:
                        ui.label("Patientenzuordnung").classes("bereichstitel")
                        patienten_hinweis = ui.label(
                            "Nach dem Auslesen werden mögliche Patienten vorgeschlagen."
                        ).classes("text-slate-600")
                        patienten_auswahl = ui.select(
                            options={}, label="Patient aus Verzeichnis auswählen"
                        ).props("outlined dense clearable").classes("w-full")
                        patient_bestaetigen = ui.button(
                            "Ausgewählten Patienten bestätigen", icon="person_check"
                        ).props("color=teal-8 unelevated").classes("w-full")
                        ui.separator()
                        ui.label("Oder neuen Patienten anlegen").classes(
                            "font-semibold text-slate-700"
                        )
                        neue_patienten_id = ui.input("Patienten-ID").props(
                            "outlined dense"
                        ).classes("w-full")
                        neuer_patientenname = ui.input("Name").props(
                            "outlined dense"
                        ).classes("w-full")
                        neues_geburtsdatum = ui.input("Geburtsdatum").props(
                            "outlined dense type=date"
                        ).classes("w-full")
                        patient_anlegen = ui.button(
                            "Patient anlegen und bestätigen", icon="person_add"
                        ).props("outline color=teal-8").classes("w-full")
                    patienten_karte.set_visibility(False)

                    # Die Prüfung liegt in einem maximierten Dialog und damit auf
                    # einem eigenen Arbeitsbildschirm. Der Einlesebereich bleibt im
                    # Hintergrund unverändert erhalten und kann über "Zurück" ohne
                    # erneute Bildanalyse wieder geöffnet werden.
                    with ui.dialog().props("maximized").classes(
                        "ced-pruefdialog"
                    ) as ced_dialog:
                        with ui.card().classes(
                            "ced-pruefseite p-6 md:p-8 gap-4"
                        ):
                            with ui.row().classes("w-full items-center justify-between gap-3"):
                                with ui.column().classes("gap-0"):
                                    ui.label("CED-Daten prüfen").classes(
                                        "text-2xl font-bold text-teal-900"
                                    )
                                    ced_patientenkopf = ui.label(
                                        "Noch kein Patient bestätigt"
                                    ).classes("text-slate-600")
                                ui.button(
                                    "Zurück zum Einlesen",
                                    icon="arrow_back",
                                    on_click=ced_dialog.close,
                                ).props("outline color=teal-8")
                            ced_pruefung_hinweis = ui.label(
                                "Bitte zuerst einen Patienten bestätigen."
                            ).classes("text-slate-600")
                            befunddatum = ui.input("Befunddatum").props(
                                "outlined dense type=date"
                            ).classes("w-full")
                            ced_tabelle = ui.aggrid(
                                {
                                    "defaultColDef": {
                                        "resizable": True,
                                        "sortable": True,
                                        "filter": True,
                                    },
                                    "columnDefs": [
                                        {"headerName": "Status", "field": "status", "width": 125},
                                        {
                                            "headerName": "Kategorie",
                                            "field": "kategorie",
                                            "editable": True,
                                            "minWidth": 190,
                                        },
                                        {
                                            "headerName": "Wert",
                                            "field": "wert",
                                            "editable": True,
                                            "minWidth": 180,
                                        },
                                        {
                                            "headerName": "Einheit",
                                            "field": "einheit",
                                            "editable": True,
                                            "width": 120,
                                        },
                                        {
                                            "headerName": "Übernehmen",
                                            "field": "uebernehmen",
                                            "editable": True,
                                            "cellEditor": "agCheckboxCellEditor",
                                            "cellRenderer": "agCheckboxCellRenderer",
                                            "width": 135,
                                        },
                                        {
                                            "headerName": "Quelle",
                                            "field": "quelle",
                                            "minWidth": 260,
                                        },
                                    ],
                                    "rowData": [],
                                    # Beendet eine Zellbearbeitung beim Verlassen der
                                    # Zelle, damit ``get_client_data`` beim Speichern
                                    # garantiert den sichtbaren letzten Wert erhält.
                                    "stopEditingWhenCellsLoseFocus": True,
                                }
                            ).classes("ced-tabellenrahmen w-full")
                            ced_speichern = ui.button(
                                "Geprüfte CED-Daten speichern", icon="save"
                            ).props("color=teal-8 unelevated").classes("w-full")
                            ced_speichern.disable()

                    # Die erste Patientenansicht ist bewusst eine kompakte lesende
                    # Übersicht. Noch nicht strukturierte Bereiche bleiben sichtbar
                    # leer, damit keine medizinischen Inhalte aus Freitext geraten
                    # oder vermeintlich vollständig dargestellt werden.
                    with ui.dialog().props("maximized").classes(
                        "ced-pruefdialog"
                    ) as patientenansicht_dialog:
                        with ui.card().classes("ced-pruefseite p-6 md:p-8 gap-5"):
                            with ui.row().classes(
                                "w-full items-start justify-between gap-3"
                            ):
                                with ui.column().classes("gap-0"):
                                    patientenansicht_name = ui.label(
                                        "Patientenübersicht"
                                    ).classes("text-2xl font-bold text-teal-900")
                                    patientenansicht_stammdaten = ui.label("").classes(
                                        "text-slate-600"
                                    )
                                ui.button(
                                    "Zurück zum Einlesen",
                                    icon="arrow_back",
                                    on_click=patientenansicht_dialog.close,
                                ).props("outline color=teal-8")

                            with ui.row().classes(
                                "w-full gap-4 items-stretch flex-wrap lg:flex-nowrap"
                            ):
                                with ui.card().classes("arbeitskarte flex-1 p-5"):
                                    ui.label("Diagnosen").classes("bereichstitel")
                                    hauptdiagnose_ausgabe = ui.label(
                                        "Hauptdiagnose: noch nicht klassifiziert"
                                    )
                                    ui.label("Weitere gespeicherte Diagnosen").classes(
                                        "font-semibold text-slate-700 mt-2"
                                    )
                                    diagnosen_liste = ui.column().classes("gap-1")
                                with ui.card().classes("arbeitskarte flex-1 p-5"):
                                    ui.label("CED-Stammdaten").classes("bereichstitel")
                                    erstdiagnose_ausgabe = ui.label(
                                        "Erstdiagnose: noch nicht hinterlegt"
                                    )
                                    befallsmuster_ausgabe = ui.label(
                                        "Befallsmuster: noch nicht hinterlegt"
                                    )

                            with ui.row().classes(
                                "w-full gap-4 items-stretch flex-wrap lg:flex-nowrap"
                            ):
                                with ui.card().classes("arbeitskarte flex-1 p-5"):
                                    ui.label("Therapieverlauf").classes("bereichstitel")
                                    ui.label(
                                        "Medikamentös: noch kein bestätigter Verlauf"
                                    )
                                    ui.label(
                                        "Chirurgisch: noch kein bestätigter Verlauf"
                                    )
                                with ui.card().classes("arbeitskarte flex-1 p-5"):
                                    ui.label("Fachansichten").classes("bereichstitel")
                                    ui.label(
                                        "Die Fachbereiche werden schrittweise an bestätigte Dokumentdaten angebunden."
                                    ).classes("text-slate-600")
                                    with ui.row().classes("gap-2 flex-wrap"):
                                        for titel in (
                                            "Labor",
                                            "Calprotectin",
                                            "Endoskopie",
                                            "Sonografie",
                                            "MRT / CT",
                                        ):
                                            ui.button(titel).props(
                                                "outline color=teal-8 disable"
                                            )

                            with ui.card().classes("arbeitskarte w-full p-5"):
                                letzte_befunde_titel = ui.label(
                                    "Letzter bestätigter CED-Befund"
                                ).classes("bereichstitel")
                                letzte_befunde_hinweis = ui.label("").classes(
                                    "text-slate-600"
                                )
                                letzte_befunde_tabelle = ui.aggrid(
                                    {
                                        "columnDefs": [
                                            {
                                                "headerName": "Kategorie",
                                                "field": "kategorie",
                                                "flex": 1,
                                            },
                                            {
                                                "headerName": "Wert",
                                                "field": "wert",
                                                "flex": 1,
                                            },
                                            {
                                                "headerName": "Einheit",
                                                "field": "einheit",
                                                "width": 130,
                                            },
                                        ],
                                        "rowData": [],
                                        "domLayout": "autoHeight",
                                    }
                                ).classes("w-full")

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
            anbieter_hinweis.text = "● OpenAI · OPENAI_API_KEY"
        setze_status(
            f"{'UK-API' if zustand.anbieter == 'uk' else 'OpenAI'} ausgewählt"
        )
        if zustand.seiten:
            neuer_name = "UK-API" if zustand.anbieter == "uk" else "OpenAI"
            lesen_schalter.text = f"Dokument mit {neuer_name} neu bearbeiten"
            setze_status(
                f"Anbieter auf {neuer_name} gewechselt · Dokument bereit zur erneuten Verarbeitung"
            )

    def setze_ced_pruefung_zurueck() -> None:
        """Entfernt temporäre CED-Werte, wenn Dokument oder Patient wechselt."""
        zustand.ced_befunde.clear()
        zustand.gespeichertes_dokument_id = None
        ced_tabelle.options["rowData"] = []
        ced_tabelle.update()
        befunddatum.value = ""
        ced_speichern.disable()
        ced_navigation.disable()
        ced_patientenkopf.text = "Noch kein Patient bestätigt"
        ced_dialog.close()

    def setze_patientenansicht_zurueck() -> None:
        """Entfernt sichtbare Patientendaten unmittelbar bei aufgehobener Zuordnung."""
        patientenansicht_navigation.disable()
        patientenansicht_dialog.close()
        patientenansicht_name.text = "Patientenübersicht"
        patientenansicht_stammdaten.text = ""
        diagnosen_liste.clear()
        letzte_befunde_tabelle.options["rowData"] = []
        letzte_befunde_tabelle.update()

    def oeffne_patientenansicht() -> None:
        """Lädt eine aktuelle lesende Übersicht des ausdrücklich bestätigten Patienten."""
        if zustand.arbeitsmodus != DATENBANKMODUS or zustand.patient_id is None:
            setze_status("Bitte zuerst einen Patienten ausdrücklich bestätigen.", fehler=True)
            return
        try:
            with get_session() as sitzung:
                uebersicht = lade_patientenuebersicht(sitzung, zustand.patient_id)
        except (SQLAlchemyError, ValueError) as fehler:
            # Kein Fallback auf alte Sitzungsdaten: Bei einem Abfragefehler bleibt die
            # Ansicht geschlossen. Zum Debugging nur Exception-Typ und Tabellenname,
            # niemals medizinische Inhalte oder Stammdaten protokollieren.
            setze_status(f"Patientenübersicht konnte nicht geladen werden: {fehler}", fehler=True)
            return

        patientenansicht_name.text = uebersicht.name
        geburtsdatum_text = (
            uebersicht.geburtsdatum.strftime("%d.%m.%Y")
            if uebersicht.geburtsdatum
            else "nicht hinterlegt"
        )
        alter_text = f"{uebersicht.alter} Jahre" if uebersicht.alter is not None else "nicht berechenbar"
        patientenansicht_stammdaten.text = (
            f"Geburtsdatum: {geburtsdatum_text} · Alter: {alter_text} · "
            f"Patienten-ID: {uebersicht.externe_id or 'nicht hinterlegt'}"
        )

        # Haupt- und Nebendiagnosen können mit dem aktuellen Schema noch nicht sicher
        # unterschieden werden. Vorhandene Einträge werden deshalb gemeinsam und mit
        # Status gezeigt, statt willkürlich eine Hauptdiagnose zu bestimmen.
        hauptdiagnose_ausgabe.text = "Hauptdiagnose: noch nicht klassifiziert"
        diagnosen_liste.clear()
        with diagnosen_liste:
            if not uebersicht.diagnosen:
                ui.label("Noch keine bestätigte Diagnose vorhanden").classes(
                    "text-slate-500 italic"
                )
            for diagnose in uebersicht.diagnosen:
                datum = (
                    diagnose.erstdiagnose.strftime("%d.%m.%Y")
                    if diagnose.erstdiagnose
                    else "Datum offen"
                )
                ui.label(f"• {diagnose.bezeichnung} · {diagnose.status} · {datum}")

        erstdiagnosen = [
            diagnose.erstdiagnose
            for diagnose in uebersicht.diagnosen
            if diagnose.erstdiagnose is not None
        ]
        erstdiagnose_ausgabe.text = (
            f"Erstdiagnose: {min(erstdiagnosen).strftime('%d.%m.%Y')}"
            if erstdiagnosen
            else "Erstdiagnose: noch nicht hinterlegt"
        )
        befallsmuster_ausgabe.text = "Befallsmuster: noch nicht hinterlegt"

        letzte_befunde_tabelle.options["rowData"] = [
            {
                "kategorie": befund.kategorie,
                "wert": befund.wert,
                "einheit": befund.einheit or "",
            }
            for befund in uebersicht.letzte_befunde
        ]
        letzte_befunde_tabelle.update()
        if uebersicht.letztes_befunddatum:
            letztes_datum = uebersicht.letztes_befunddatum.strftime("%d.%m.%Y")
            letzte_befunde_titel.text = f"Letzter bestätigter CED-Befund · {letztes_datum}"
            letzte_befunde_hinweis.text = (
                f"{len(uebersicht.letzte_befunde)} bestätigte Feld(er)"
            )
        else:
            letzte_befunde_titel.text = "Letzter bestätigter CED-Befund"
            letzte_befunde_hinweis.text = "Noch keine bestätigten Befunde vorhanden"
        patientenansicht_dialog.open()
        setze_status("Patientenübersicht geöffnet")

    def aktualisiere_ced_bereitschaft() -> None:
        """Öffnet die CED-Prüfung nur bei bestätigtem Patient und passendem Dokument."""
        if zustand.arbeitsmodus != DATENBANKMODUS or zustand.patient_id is None:
            ced_navigation.disable()
            patientenansicht_navigation.disable()
            return
        patientenansicht_navigation.enable()
        ist_ced_fragebogen = zustand.dokumenttyp == Dokumenttyp.CED_FRAGEBOGEN.value
        ced_navigation.set_enabled(ist_ced_fragebogen)
        if ist_ced_fragebogen:
            ced_pruefung_hinweis.text = (
                "Die Werte werden aus der vorhandenen strukturierten Darstellung gelesen. "
                "Befunddatum und jede neue Kategorie müssen vor einer späteren Übernahme geprüft werden."
            )
        elif zustand.dokumenttyp:
            ced_pruefung_hinweis.text = (
                f"CED-Extraktion nicht gestartet: Dokumenttyp ist {zustand.dokumenttyp}."
            )
        else:
            ced_pruefung_hinweis.text = "Bitte zunächst das Dokument auslesen."

    def oeffne_ced_pruefung() -> None:
        """Schlägt das Datum vor, extrahiert die Werte und öffnet den Prüfscreen."""
        if zustand.patient_id is None:
            setze_status("Bitte zuerst einen Patienten ausdrücklich bestätigen.", fehler=True)
            return
        if zustand.dokumenttyp != Dokumenttyp.CED_FRAGEBOGEN.value:
            setze_status("Die CED-Extraktion ist nur für CED-Patientenfragebögen verfügbar.", fehler=True)
            return
        datumsvorschlag = erkenne_befunddatum(
            zustand.ausgelesener_inhalt,
            zustand.strukturierte_darstellung,
        )
        # Ein bereits manuell korrigiertes Datum wird beim erneuten Öffnen nicht
        # überschrieben. Ohne eindeutigen Vorschlag bleibt das Pflichtfeld leer.
        if datumsvorschlag is not None and not befunddatum.value:
            befunddatum.value = datumsvorschlag.isoformat()
        zustand.ced_befunde = parse_ced_fragebogen(zustand.strukturierte_darstellung)
        prioritaet = {
            "CONFLICT": 0,
            "UNREADABLE": 1,
            "UNCERTAIN": 2,
            "MISSING": 3,
            "HIGH_CONFIDENCE": 4,
        }
        sortierte_befunde = sorted(
            zustand.ced_befunde,
            key=lambda befund: (prioritaet[befund.qualitaet.value], befund.kategorie),
        )
        ced_tabelle.options["rowData"] = [
            {
                "status": (
                    "Neue Kategorie · prüfen"
                    if befund.neue_kategorie
                    else befund.qualitaet.value
                ),
                "kategorie": befund.kategorie,
                "wert": befund.anzeigewert,
                "einheit": befund.einheit or "",
                "uebernehmen": befund.uebernehmen,
                "quelle": befund.quelltext,
            }
            for befund in sortierte_befunde
        ]
        ced_tabelle.update()
        ced_speichern.set_enabled(bool(zustand.ced_befunde))
        neue_anzahl = sum(befund.neue_kategorie for befund in zustand.ced_befunde)
        if not zustand.ced_befunde:
            ced_pruefung_hinweis.text = (
                "Keine beschrifteten CED-Felder erkannt. Bitte die strukturierte Darstellung prüfen; "
                "es werden keine Werte geraten oder automatisch ersetzt."
            )
            setze_status("Keine CED-Felder für die Prüftabelle erkannt", fehler=True)
            ced_dialog.open()
            return
        datumshinweis = (
            "Befunddatum aus dem Dokument vorgeschlagen"
            if datumsvorschlag is not None
            else "kein eindeutiges Befunddatum erkannt · manuelle Eingabe erforderlich"
        )
        ced_pruefung_hinweis.text = (
            f"{len(zustand.ced_befunde)} Feld(er) erkannt"
            + (
                f" · {neue_anzahl} neue Kategorie(n) sind zunächst von der Übernahme ausgeschlossen"
                if neue_anzahl
                else ""
            )
            + f" · {datumshinweis}. Bitte alle Angaben vor der Speicherung prüfen."
        )
        setze_status("CED-Daten wurden zur manuellen Prüfung vorbereitet")
        ced_dialog.open()

    async def speichere_gepruefte_ced_daten() -> None:
        """Liest den sichtbaren Tabellenstand und speichert nur markierte Zeilen.

        AG Grid verwaltet Änderungen zunächst im Browser. Deshalb wird unmittelbar
        vor der Transaktion der aktuelle Client-Stand abgefragt. Für Debugging darf
        nur die Zeilenanzahl betrachtet werden; Tabellenwerte gehören nicht in Logs.
        """
        if zustand.patient_id is None:
            setze_status("Bitte zuerst einen Patienten ausdrücklich bestätigen.", fehler=True)
            return
        if zustand.gespeichertes_dokument_id is not None:
            setze_status("Diese Prüfung wurde bereits gespeichert.", fehler=True)
            return
        try:
            datum = date.fromisoformat(befunddatum.value or "")
        except ValueError:
            setze_status("Bitte vor der Speicherung ein vollständiges Befunddatum eingeben.", fehler=True)
            return
        try:
            tabellenzeilen = await ced_tabelle.get_client_data()
        except TimeoutError:
            setze_status(
                "Tabellenwerte konnten nicht aus dem Browser gelesen werden. "
                "Bitte die letzte Zelle verlassen und erneut speichern.",
                fehler=True,
            )
            return
        freigegebene: list[FreigegebenerBefund] = []
        for zeile in tabellenzeilen:
            if not zeile.get("uebernehmen"):
                continue
            kategorie = str(zeile.get("kategorie") or "").strip()
            wert = str(zeile.get("wert") or "").strip()
            einheit = str(zeile.get("einheit") or "").strip() or None
            quelle = str(zeile.get("quelle") or "").strip()
            status = str(zeile.get("status") or "")
            try:
                qualitaet = ConfidenceStatus(status)
            except ValueError:
                # Eine ausdrücklich aktivierte neue Kategorie bleibt bis zu einer
                # späteren Katalogprüfung als unsicher gekennzeichnet.
                qualitaet = ConfidenceStatus.UNCERTAIN
            erneut_geparst = parse_ced_fragebogen(f"{kategorie}: {wert}")
            passender_befund = next(
                (befund for befund in erneut_geparst if befund.kategorie == kategorie),
                None,
            )
            numerischer_wert = (
                passender_befund.numerischer_wert if passender_befund else None
            )
            freigegebene.append(
                FreigegebenerBefund(
                    kategorie=kategorie,
                    anzeigewert=wert,
                    numerischer_wert=numerischer_wert,
                    einheit=einheit,
                    quelltext=quelle,
                    qualitaet=qualitaet,
                )
            )
        if zustand.ergebnis_anbieter not in {"uk", "openai"}:
            setze_status(
                "Der Anbieter des sichtbaren Ergebnisses ist nicht eindeutig. "
                "Bitte das Dokument erneut auslesen.",
                fehler=True,
            )
            return
        provider_name = "UK-API" if zustand.ergebnis_anbieter == "uk" else "OpenAI"
        modell = (
            einstellungen.uk_model
            if zustand.ergebnis_anbieter == "uk"
            else einstellungen.openai_model
        )
        auftrag = CEDSpeicherauftrag(
            patient_id=zustand.patient_id,
            befunddatum=datum,
            original_name=" + ".join(zustand.dokumentnamen) or "CED-Fragebogen",
            rohe_ki_antwort=zustand.rohe_ki_antwort,
            kis_vorschlag=zustand.kis_vorschlag,
            provider=provider_name,
            modell=modell,
            befunde=tuple(freigegebene),
        )
        try:
            with get_session() as sitzung:
                dokument_id = speichere_ced_pruefung(sitzung, auftrag)
        except (OSError, SQLAlchemyError, ValueError) as fehler:
            # Es gibt keinen zweiten Speicherweg. Bei SQL-Problemen kann lokal der
            # Exception-Typ ergänzt werden, ohne Werte oder Patientendaten auszugeben.
            setze_status(f"CED-Daten konnten nicht gespeichert werden: {fehler}", fehler=True)
            return
        zustand.gespeichertes_dokument_id = dokument_id
        ced_speichern.disable()
        ced_pruefung_hinweis.text = (
            f"Testdaten als bestätigtes Dokument {dokument_id} gespeichert. "
            "Für Änderungen bitte ein neues Dokument einlesen."
        )
        setze_status("Geprüfte CED-Daten wurden vollständig gespeichert")

    def aktualisiere_patientenvorschlaege() -> None:
        """Erkennt Stammdaten und lädt passende Patienten ausschließlich lokal.

        Die Funktion wird nur im entsperrten Datenbankmodus aufgerufen. Für die
        Fehlersuche können lokal Trefferanzahl und erkannte Feldnamen geprüft werden;
        Namen, Geburtsdaten, IDs oder Dokumenttexte dürfen nicht geloggt werden.
        """
        if zustand.arbeitsmodus != DATENBANKMODUS:
            return
        patienten_karte.set_visibility(True)
        zustand.patient_id = None
        setze_ced_pruefung_zurueck()
        setze_patientenansicht_zurueck()
        zustand.erkannte_patientendaten = erkenne_patientendaten(
            zustand.ausgelesener_inhalt
        )
        erkannt = zustand.erkannte_patientendaten
        neue_patienten_id.value = erkannt.externe_id or ""
        neuer_patientenname.value = erkannt.name or ""
        neues_geburtsdatum.value = (
            erkannt.geburtsdatum.isoformat() if erkannt.geburtsdatum else ""
        )

        with get_session() as sitzung:
            patienten = list(
                sitzung.scalars(select(Patient).order_by(Patient.name, Patient.id))
            )
            trefferliste = ermittle_patiententreffer(erkannt, patienten)

        optionen: dict[int, str] = {}
        for patiententreffer in trefferliste:
            kennzeichnung = "⚠" if patiententreffer.widerspruch else "Vorschlag"
            optionen[patiententreffer.patient_id] = (
                f"{kennzeichnung}: {patiententreffer.bezeichnung} · {patiententreffer.status}"
            )
        for patient in patienten:
            if patient.id not in optionen:
                optionen[patient.id] = (
                    f"{patient.external_id or 'ohne ID'} · {patient.name} · "
                    f"{patient.birth_date.strftime('%d.%m.%Y') if patient.birth_date else 'ohne Geburtsdatum'}"
                )
        patienten_auswahl.options = optionen
        patienten_auswahl.value = None
        patienten_auswahl.update()

        if not zustand.ausgelesener_inhalt:
            patienten_hinweis.text = (
                "Bitte zunächst ein Dokument auslesen. Alternativ kann ein Patient "
                "bewusst aus dem lokalen Verzeichnis ausgewählt werden."
            )
        elif trefferliste:
            erster = trefferliste[0]
            details = ", ".join(erster.begruendung)
            patienten_hinweis.text = (
                f"{erster.status}: {details}. Bitte den Patienten ausdrücklich auswählen und bestätigen."
            )
        elif not erkannt.name:
            patienten_hinweis.text = (
                "Kein Patientenname wurde eingelesen oder erkannt. Bitte einen Patienten "
                "aus dem Verzeichnis auswählen oder alle Stammdaten für eine Neuanlage eingeben."
            )
        else:
            patienten_hinweis.text = (
                "Kein eindeutig passender Patient gefunden. Bitte einen Patienten aus "
                "dem Verzeichnis auswählen oder die vorbelegten Stammdaten prüfen und neu anlegen."
            )

    def bestaetige_patient() -> None:
        """Übernimmt genau die bewusst gewählte Datenbank-ID in die aktuelle Sitzung."""
        if zustand.arbeitsmodus != DATENBANKMODUS:
            setze_status("Patientenzuordnung erfordert den geschützten Datenbankmodus.", fehler=True)
            return
        if patienten_auswahl.value is None:
            setze_status("Bitte zuerst einen Patienten aus dem Verzeichnis auswählen.", fehler=True)
            return
        patient_id = int(patienten_auswahl.value)
        with get_session() as sitzung:
            patient = sitzung.get(Patient, patient_id)
            if patient is None:
                setze_status("Der ausgewählte Patient ist nicht mehr vorhanden.", fehler=True)
                return
            bezeichnung = f"{patient.external_id} · {patient.name}"
        zustand.patient_id = patient_id
        patienten_hinweis.text = f"Bestätigter Patient: {bezeichnung}"
        ced_patientenkopf.text = f"Bestätigter Patient: {bezeichnung}"
        aktualisiere_ced_bereitschaft()
        setze_status("Patientenzuordnung wurde ausdrücklich bestätigt")

    def lege_patient_an() -> None:
        """Legt nach vollständiger manueller Prüfung einen neuen Patienten an."""
        if zustand.arbeitsmodus != DATENBANKMODUS:
            setze_status("Patientenneuanlage erfordert den geschützten Datenbankmodus.", fehler=True)
            return
        externe_id = (neue_patienten_id.value or "").strip()
        name = (neuer_patientenname.value or "").strip()
        try:
            geburtsdatum = date.fromisoformat(neues_geburtsdatum.value or "")
        except ValueError:
            setze_status("Bitte ein vollständiges Geburtsdatum eingeben.", fehler=True)
            return
        if not externe_id or not name:
            setze_status("Patienten-ID, Name und Geburtsdatum sind verpflichtend.", fehler=True)
            return
        with get_session() as sitzung:
            vorhanden = sitzung.scalar(
                select(Patient).where(Patient.external_id == externe_id)
            )
            if vorhanden is not None:
                setze_status(
                    "Diese Patienten-ID ist bereits vorhanden. Bitte den vorhandenen Patienten auswählen.",
                    fehler=True,
                )
                return
            patient = Patient(
                external_id=externe_id,
                name=name,
                birth_date=geburtsdatum,
            )
            sitzung.add(patient)
            sitzung.commit()
            neue_id = patient.id
        aktualisiere_patientenvorschlaege()
        patienten_auswahl.value = neue_id
        patienten_auswahl.update()
        # ``aktualisiere_patientenvorschlaege`` setzt die Zuordnung absichtlich
        # zurück. Deshalb wird der neue, gerade manuell bestätigte Datensatz danach
        # ausdrücklich wieder als Sitzungszuordnung gesetzt.
        zustand.patient_id = neue_id
        patienten_hinweis.text = f"Neuer Patient bestätigt: {externe_id} · {name}"
        ced_patientenkopf.text = f"Bestätigter Patient: {externe_id} · {name}"
        aktualisiere_ced_bereitschaft()
        setze_status("Patient wurde angelegt und für dieses Dokument bestätigt")

    def aktualisiere_datenbankmodus() -> None:
        """Aktiviert oder beendet den geschützten Datenbankmodus."""
        if zustand.arbeitsmodus == DATENBANKMODUS:
            zustand.arbeitsmodus = LESEMODUS
            passwort.value = ""
            passwort.set_visibility(True)
            datenbank_schalter.text = "CED-Datenbank aktivieren"
            datenbank_status.text = "Datenbank: nicht aktiviert · Lesemodus aktiv"
            zustand.patient_id = None
            patienten_auswahl.options = {}
            patienten_auswahl.value = None
            patienten_auswahl.update()
            patienten_karte.set_visibility(False)
            ced_navigation.set_visibility(False)
            patientenansicht_navigation.set_visibility(False)
            setze_ced_pruefung_zurueck()
            setze_patientenansicht_zurueck()
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
        ced_navigation.set_visibility(True)
        patientenansicht_navigation.set_visibility(True)
        setze_status(
            "Datenbankmodus aktiviert · Patientenzuordnung ist verfügbar"
        )
        aktualisiere_patientenvorschlaege()

    def aktualisiere_ergebnisanzeige() -> None:
        """Zeigt exakt die gewählte, bereits geprüfte Antwortvariante an."""
        varianten = {
            "rohtext": zustand.ausgelesener_inhalt,
            "strukturiert": zustand.strukturierte_darstellung,
            "zusammenfassung": zustand.kis_vorschlag,
        }
        ergebnis_ausgabe.value = varianten[str(ergebnis_auswahl.value)]

    def verschiebe_seite(index: int, richtung: int) -> None:
        """Verschiebt eine sichtbare Vorschau zur manuellen Reihenfolgekorrektur."""
        neu = index + richtung
        if not 0 <= neu < len(zustand.seiten):
            return
        zustand.seiten[index], zustand.seiten[neu] = (
            zustand.seiten[neu], zustand.seiten[index],
        )
        aktualisiere_vorschauen()
        setze_status(f"Teil {index + 1} wurde an Position {neu + 1} verschoben")

    def loesche_seite(index: int) -> None:
        """Entfernt genau das auf der Vorschau bezeichnete Teil aus der Sitzung."""
        zustand.seiten.pop(index)
        aktualisiere_vorschauen()
        setze_status(
            f"Teil gelöscht · {len(zustand.seiten)} Teil(e) verbleiben"
            if zustand.seiten else "Alle Dokumentteile wurden gelöscht"
        )

    def aktualisiere_vorschauen() -> None:
        """Zeigt jedes übernommene Teil gleichzeitig in einem zweispaltigen Raster."""
        vorschau_bereich.clear()
        vorschau_platzhalter.set_visibility(not zustand.seiten)
        with vorschau_bereich:
            for index, seite in enumerate(zustand.seiten):
                with ui.column().classes("vorschau-karte gap-1"):
                    ui.image(_bildadresse(seite)).classes("vorschau-bild")
                    ui.label(f"Teil {index + 1}").classes(
                        "text-sm font-semibold text-teal-900"
                    )
                    with ui.row().classes("w-full justify-between gap-0"):
                        ui.button(
                            icon="arrow_upward",
                            on_click=lambda _, i=index: verschiebe_seite(i, -1),
                        ).props("flat round dense color=teal-8").set_enabled(index > 0)
                        ui.button(
                            icon="arrow_downward",
                            on_click=lambda _, i=index: verschiebe_seite(i, 1),
                        ).props("flat round dense color=teal-8").set_enabled(
                            index < len(zustand.seiten) - 1
                        )
                        ui.button(
                            icon="delete",
                            on_click=lambda _, i=index: loesche_seite(i),
                        ).props("flat round dense color=negative")

    def setze_leeren_zustand(status: str) -> None:
        """Löscht Seiten und Ergebnis gemeinsam für ein eindeutig neues Dokument."""
        zustand.seiten.clear()
        zustand.dokumentnamen.clear()
        zustand.dokumenttyp = ""
        zustand.ausgelesener_inhalt = ""
        zustand.strukturierte_darstellung = ""
        zustand.kis_vorschlag = ""
        zustand.rohe_ki_antwort = ""
        zustand.letzter_fehler = ""
        zustand.ergebnis_anbieter = ""
        zustand.patient_id = None
        dokumenttyp_ausgabe.value = ""
        ergebnis_ausgabe.value = ""
        ergebnis_auswahl.value = "rohtext"
        lesen_schalter.text = "Dokument auslesen"
        upload.reset()
        aktualisiere_vorschauen()
        if zustand.arbeitsmodus == DATENBANKMODUS:
            aktualisiere_patientenvorschlaege()
        setze_status(status)

    def beginne_neues_dokument() -> None:
        """Bereitet eine leere Sitzung vor; die hervorgehobene Ablage bleibt sichtbar."""
        setze_leeren_zustand("Bereit für ein neues Dokument · Dateien unten ablegen")

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
        zustand.rohe_ki_antwort = ""
        zustand.letzter_fehler = ""
        zustand.ergebnis_anbieter = ""
        zustand.patient_id = None
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
            zustand.seiten.extend(neue_seiten)
            zustand.dokumentnamen.extend(dateiname for dateiname, _ in dateien)
        except (DocumentConversionError, OSError) as fehler:
            # Debugging: Bei Bedarf lokal Dateityp und Exception-Typ prüfen. Namen
            # oder Inhalte medizinischer Dokumente nie in produktive Logs schreiben.
            setze_status(f"Dokumentimport fehlgeschlagen: {fehler}", fehler=True)
            return
        aktualisiere_vorschauen()
        if zustand.arbeitsmodus == DATENBANKMODUS:
            aktualisiere_patientenvorschlaege()
        setze_status(
            f"{len(zustand.seiten)} Teil(e) vorbereitet · Anbieter wählen und Bearbeitung starten"
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
        ki_statussymbol.set_visibility(True)
        setze_status(
            f"{anbieter_name}: KI analysiert und ordnet {len(zustand.seiten)} Teil(e) …"
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
            zustand.rohe_ki_antwort = ergebnis.rohe_ki_antwort
            zustand.ergebnis_anbieter = zustand.anbieter
            dokumenttyp_ausgabe.value = zustand.dokumenttyp
            aktualisiere_ergebnisanzeige()
            if zustand.arbeitsmodus == DATENBANKMODUS:
                aktualisiere_patientenvorschlaege()
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
            ki_statussymbol.set_visibility(False)
            lesen_schalter.enable()

    def kopiere_ergebnis() -> None:
        """Kopiert unmittelbar und unverändert die aktuell sichtbare Textvariante."""
        ui.clipboard.write(ergebnis_ausgabe.value or "")
        setze_status("Angezeigten Text in die Zwischenablage kopiert")

    anbieter_auswahl.on_value_change(lambda _: aktualisiere_anbieter())
    datenbank_schalter.text = "CED-Datenbank aktivieren"
    datenbank_schalter.on_click(aktualisiere_datenbankmodus)
    patient_bestaetigen.on_click(bestaetige_patient)
    patient_anlegen.on_click(lege_patient_an)
    ced_speichern.on_click(speichere_gepruefte_ced_daten)
    ced_navigation.on_click(oeffne_ced_pruefung)
    patientenansicht_navigation.on_click(oeffne_patientenansicht)
    upload.on_upload(uebernehme_datei)
    neu_schalter.on_click(beginne_neues_dokument)
    alles_loeschen_schalter.on_click(
        lambda: setze_leeren_zustand("Alle Dokumente und Ergebnisse wurden gelöscht")
    )
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
