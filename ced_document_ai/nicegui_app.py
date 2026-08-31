"""NiceGUI-Oberfläche für den browserbasierten Dokumentimport.

Alle Bezeichner der Oberfläche sind bewusst deutsch gewählt. Medizinische Dateien
werden nur in einem temporären Sitzungsordner abgelegt und noch nicht als Befunde
in die CED-Datenbank übernommen.
"""

from __future__ import annotations

import base64
import hmac
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
from ced_document_ai.services.documents.converter import DocumentConversionError
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
        .seitenvorschau { width: 110px; height: 145px; object-fit: contain;
          background: #f8fafc; }
        .warte-sanduhr { animation: sanduhr-drehen 1.2s ease-in-out infinite; }
        @keyframes sanduhr-drehen { 0%, 45% { transform: rotate(0deg); }
          55%, 100% { transform: rotate(180deg); } }
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

                ui.label("Dokumente laden").classes("text-xl font-semibold mt-4")
                ui.label(
                    "PDF-, JPG- oder PNG-Dateien hier ablegen, auswählen oder aus der "
                    "Zwischenablage einfügen (Strg+V / Cmd+V)."
                ).classes("text-slate-600")

                vorschau_bereich = ui.column().classes("w-full gap-2")

                def aktualisiere_vorschauen() -> None:
                    """Zeigt alle Seiten; die Schaltflächen verändern die KI-Reihenfolge."""
                    vorschau_bereich.clear()
                    with vorschau_bereich:
                        if not zustand.seiten:
                            ui.label("Noch keine Dokumentseiten übernommen.").classes(
                                "text-slate-500 italic"
                            )
                        for index, seite in enumerate(zustand.seiten):
                            with ui.card().classes("w-full"):
                                with ui.row().classes("items-center no-wrap w-full"):
                                    ui.image(_bildadresse(seite)).classes("seitenvorschau")
                                    ui.label(f"Seite {index + 1} · {seite.name}").classes(
                                        "grow font-medium"
                                    )

                                    def verschiebe(von: int, nach: int) -> None:
                                        zustand.seiten.insert(nach, zustand.seiten.pop(von))
                                        aktualisiere_vorschauen()

                                    ui.button(
                                        icon="arrow_upward",
                                        on_click=lambda _, i=index: verschiebe(i, i - 1),
                                    ).props("flat round").set_enabled(index > 0)
                                    ui.button(
                                        icon="arrow_downward",
                                        on_click=lambda _, i=index: verschiebe(i, i + 1),
                                    ).props("flat round").set_enabled(
                                        index < len(zustand.seiten) - 1
                                    )

                def speichere_und_konvertiere(dateiname: str, inhalt: bytes) -> None:
                    """Speichert jeden Upload eindeutig, damit gleiche Namen nichts ersetzen."""
                    wurzel = Path(zustand.temporaerer_ordner.name)
                    upload_ordner = wurzel / "uploads" / uuid.uuid4().hex
                    upload_ordner.mkdir(parents=True)
                    quellpfad = upload_ordner / Path(dateiname).name
                    quellpfad.write_bytes(inhalt)
                    konverter = DocumentConverter(wurzel / "seiten")
                    zustand.seiten.extend(konverter.convert([quellpfad]))
                    aktualisiere_vorschauen()
                    ui.notify(f"{len(zustand.seiten)} Seite(n) vorbereitet", type="positive")

                def uebernehme_datei(ereignis: events.UploadEventArguments) -> None:
                    try:
                        speichere_und_konvertiere(ereignis.name, ereignis.content.read())
                    except (DocumentConversionError, OSError) as fehler:
                        # Zum Debugging kann lokal der Dateiname geprüft werden; den
                        # Dokumentinhalt niemals in Protokolle schreiben.
                        ui.notify(str(fehler), type="negative", timeout=10000)

                ui.upload(
                    label="Dokumente auswählen oder hier ablegen",
                    on_upload=uebernehme_datei,
                    multiple=True,
                    auto_upload=True,
                ).props('accept=".pdf,.png,.jpg,.jpeg" color="teal"').classes("w-full")

                def uebernehme_zwischenablage(ereignis: events.GenericEventArguments) -> None:
                    daten = dict(ereignis.args)
                    try:
                        kopf, codiert = str(daten["data_url"]).split(",", 1)
                        if not kopf.startswith("data:image/"):
                            raise ValueError("Die Zwischenablage enthält kein unterstütztes Bild.")
                        speichere_und_konvertiere(str(daten["name"]), base64.b64decode(codiert))
                    except (KeyError, ValueError, DocumentConversionError, OSError) as fehler:
                        # Bei Bedarf lokal nur MIME-Typ und Bytelänge inspizieren.
                        ui.notify(str(fehler), type="negative", timeout=10000)

                ui.on("clipboard_upload", uebernehme_zwischenablage)
                ui.run_javascript("""
                    if (!window.cedClipboardListener) {
                      window.cedClipboardListener = true;
                      document.addEventListener('paste', event => {
                        for (const item of event.clipboardData.items) {
                          if (!item.type.startsWith('image/')) continue;
                          const file = item.getAsFile();
                          const reader = new FileReader();
                          reader.onload = () => emitEvent('clipboard_upload', {
                            name: file.name || `zwischenablage.${item.type.split('/')[1]}`,
                            data_url: reader.result,
                          });
                          reader.readAsDataURL(file);
                        }
                      });
                    }
                """)

                ui.label("Übernommene Dokumentseiten").classes("text-xl font-semibold mt-4")
                aktualisiere_vorschauen()

                ausgabe = ui.markdown().classes("w-full border rounded p-4 bg-slate-50")
                statuszeile = ui.row().classes("items-center gap-2")
                with statuszeile:
                    sanduhr = ui.icon("hourglass_top").classes(
                        "warte-sanduhr text-amber-700 text-2xl"
                    )
                    statustext = ui.label("Warte auf die Antwort der KI …")
                statuszeile.set_visibility(False)

                async def lese_dokument() -> None:
                    if not zustand.seiten:
                        ui.notify("Bitte zuerst ein Dokument auswählen.", type="warning")
                        return
                    analyse_knopf.disable()
                    statuszeile.set_visibility(True)
                    ausgabe.content = ""
                    try:
                        if zustand.anbieter == "uk":
                            ki_anbieter = LocalAPIProvider(einstellungen)
                        else:
                            ki_anbieter = CloudAPIProvider(einstellungen)
                        # io_bound hält die Ereignisschleife frei, sodass die animierte
                        # Sanduhr während der gesamten Netzwerkanfrage sichtbar bleibt.
                        ergebnis = await run.io_bound(
                            ki_anbieter.process_document, tuple(zustand.seiten)
                        )
                        ausgabe.content = (
                            f"## {ergebnis.dokumenttyp.value}\n\n"
                            "### Strukturierte Darstellung\n\n"
                            f"{ergebnis.strukturierte_darstellung}\n\n"
                            "### KIS-Vorschlag (ungeprüft)\n\n"
                            f"{ergebnis.kis_vorschlag}\n\n"
                            "<details><summary>Originalgetreue Auslesung anzeigen</summary>\n\n"
                            f"{ergebnis.ausgelesener_inhalt}\n\n</details>"
                        )
                    except (
                        ConfigurationError,
                        AIProviderError,
                        DokumentAntwortFehler,
                        OSError,
                        ValueError,
                    ) as fehler:
                        # Zum Debugging Endpunkt, Modell und Secret-Verfügbarkeit prüfen.
                        # Niemals Schlüssel oder Dokumentinhalt in Protokolle schreiben.
                        ui.notify(str(fehler), type="negative", timeout=10000)
                    finally:
                        statuszeile.set_visibility(False)
                        analyse_knopf.enable()

                analyse_knopf = ui.button(
                    "Alle Dokumentseiten analysieren", on_click=lese_dokument
                ).props("color=primary")

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
