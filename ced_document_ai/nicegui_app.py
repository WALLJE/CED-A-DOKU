"""NiceGUI-Oberfläche für den browserbasierten Dokumentimport.

Alle Bezeichner der Oberfläche sind bewusst deutsch gewählt. Medizinische Dateien
werden nur in einem temporären Sitzungsordner abgelegt und noch nicht als Befunde
in die CED-Datenbank übernommen.
"""

from __future__ import annotations

import base64
import hmac
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
from ced_document_ai.services.documents.converter import DocumentConverter


@dataclass
class Sitzungszustand:
    """Enthält ausschließlich Daten des aktuell geöffneten Browserfensters."""

    arbeitsmodus: str = ""
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
    """Erzeugt für jeden Browseraufruf einen getrennten Oberflächenzustand."""
    einstellungen = Settings.from_environment()
    zustand = Sitzungszustand(anbieter=einstellungen.provider)

    ui.add_css("""
        .anbieter-hinweis { position: fixed; right: 18px; bottom: 12px;
          color: white; padding: 6px 12px; border-radius: 8px; z-index: 9999;
          font-weight: bold; }
    """)

    with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
        ui.label("CED-A-DOKU").classes("text-3xl font-bold")
        ui.label(
            "Assistenzsystem: KI-Ausgaben müssen medizinisch geprüft werden und "
            "werden in dieser Testversion nicht als Befund gespeichert."
        ).classes("text-red-700")

        modusbereich = ui.column().classes("w-full")
        arbeitsbereich = ui.column().classes("w-full")

        def zeige_arbeitsbereich() -> None:
            modusbereich.set_visibility(False)
            arbeitsbereich.set_visibility(True)
            arbeitsbereich.clear()
            with arbeitsbereich:
                ui.label(f"Modus: {zustand.arbeitsmodus}").classes("text-lg")
                if zustand.arbeitsmodus == "CED-Datenbank":
                    ui.label(
                        "Der Zugang ist freigeschaltet; strukturierte Speicherung "
                        "folgt in einer späteren Phase."
                    ).classes("text-orange-700")

                anbieter_auswahl = ui.select(
                    {"uk": "UK-API (gemma4-31b)", "openai": "OpenAI"},
                    value=zustand.anbieter,
                    label="KI-Anbieter",
                ).classes("w-80")
                hinweis = ui.label().classes("anbieter-hinweis")

                def aktualisiere_anbieter() -> None:
                    zustand.anbieter = anbieter_auswahl.value
                    if zustand.anbieter == "uk":
                        hinweis.text = "● UK-API · UK_API_KEY"
                        hinweis.style("background: #16833b")
                    else:
                        hinweis.text = "● OpenAI · OPENAI_API_KEY"
                        hinweis.style("background: #b42318")

                anbieter_auswahl.on_value_change(lambda _: aktualisiere_anbieter())
                aktualisiere_anbieter()

                seiten_auswahl = ui.select({}, label="Vorschauseite").classes("w-64")
                vorschau = ui.image().classes("w-full max-w-2xl border")
                ausgabe = ui.textarea(label="Ungeprüfte KI-Ausgabe").props(
                    "outlined readonly"
                ).classes("w-full")

                def zeige_seite() -> None:
                    if seiten_auswahl.value is not None:
                        vorschau.set_source(_bildadresse(zustand.seiten[seiten_auswahl.value]))

                seiten_auswahl.on_value_change(lambda _: zeige_seite())

                def uebernehme_datei(ereignis: events.UploadEventArguments) -> None:
                    wurzel = Path(zustand.temporaerer_ordner.name)
                    quellpfad = wurzel / Path(ereignis.name).name
                    quellpfad.write_bytes(ereignis.content.read())
                    konverter = DocumentConverter(wurzel / "seiten")
                    zustand.seiten.extend(konverter.convert([quellpfad]))
                    seiten_auswahl.options = {
                        nummer: f"Seite {nummer + 1}"
                        for nummer in range(len(zustand.seiten))
                    }
                    seiten_auswahl.value = 0
                    seiten_auswahl.update()
                    zeige_seite()
                    ui.notify(f"{len(zustand.seiten)} Seite(n) vorbereitet", type="positive")

                ui.upload(
                    label="PDF-, JPG- oder PNG-Dokumente auswählen",
                    on_upload=uebernehme_datei,
                    multiple=True,
                    auto_upload=True,
                ).props('accept=".pdf,.png,.jpg,.jpeg"').classes("w-full")

                def lese_dokument() -> None:
                    if not zustand.seiten:
                        ui.notify("Bitte zuerst ein Dokument auswählen.", type="warning")
                        return
                    try:
                        if zustand.anbieter == "uk":
                            ki_anbieter = LocalAPIProvider(einstellungen)
                        else:
                            ki_anbieter = CloudAPIProvider(einstellungen)
                        ausgabe.value = ki_anbieter.analyze(
                            zustand.seiten, "noch nicht klassifiziert", [], {}
                        )
                    except (ConfigurationError, AIProviderError, OSError, ValueError) as fehler:
                        # Zum Debugging Endpunkt, Modell und Secret-Verfügbarkeit prüfen.
                        # Niemals Schlüssel oder Dokumentinhalt in Protokolle schreiben.
                        ui.notify(str(fehler), type="negative", timeout=10000)

                ui.button("Dokument auslesen", on_click=lese_dokument).props("color=primary")

        arbeitsbereich.set_visibility(False)
        with modusbereich:
            ui.label("Arbeitsmodus auswählen").classes("text-xl font-semibold")
            passwort = ui.input("Passwort für CED-Datenbank", password=True).classes("w-80")

            def starte_nur_lesen() -> None:
                zustand.arbeitsmodus = "Nur Dokument einlesen"
                zeige_arbeitsbereich()

            def starte_datenbank() -> None:
                try:
                    richtiges_passwort = einstellungen.ced_database_password()
                except ConfigurationError as fehler:
                    ui.notify(str(fehler), type="negative")
                    return
                if not hmac.compare_digest(passwort.value or "", richtiges_passwort):
                    ui.notify("Das Passwort ist falsch.", type="negative")
                    return
                zustand.arbeitsmodus = "CED-Datenbank"
                zeige_arbeitsbereich()

            with ui.row():
                ui.button("Nur Einlesen", on_click=starte_nur_lesen)
                ui.button("CED-Datenbank", on_click=starte_datenbank)


def starte_anwendung() -> None:
    """Initialisiert SQLite und startet den NiceGUI-Server auf Port 8501."""
    initialize_database()
    ui.run(title="CED-A-DOKU", host="0.0.0.0", port=8501, reload=False)
