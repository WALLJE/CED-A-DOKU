"""Browseroberfläche für die erste KI-gestützte Dokumentauslesung.

Diese Oberfläche verwendet Streamlit und benötigt deshalb weder PySide6 noch eine
grafische Linux-Desktop-Sitzung. Sie kann in GitHub Codespaces über den automatisch
weitergeleiteten Port 8501 im Browser geöffnet werden.

Wichtig: In dieser ersten Version wird die KI-Antwort nur im Browser angezeigt.
Sie wird weder als bestätigter Befund noch als KIS-Text in SQLite gespeichert.
"""

from __future__ import annotations

import hmac
import tempfile
from pathlib import Path

import streamlit as st

from ced_document_ai.config.settings import ConfigurationError, Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.services.ai.providers import (
    AIProviderError,
    CloudAPIProvider,
    DocumentAI,
    LocalAPIProvider,
)
from ced_document_ai.services.documents.converter import (
    DocumentConversionError,
    DocumentConverter,
)

READ_MODE = "Nur Dokument einlesen"
DATABASE_MODE = "Einlesen und in CED-Datenbank verarbeiten"


def _initialize_session() -> None:
    """Legt ausschließlich technische Zustände für die aktuelle Browsersitzung an."""
    if "work_mode" not in st.session_state:
        # Das sichere reine Einlesen ist der Standard. Der Datenbankmodus kann
        # ausschließlich im gekennzeichneten Administrationsbereich aktiviert werden.
        st.session_state.work_mode = READ_MODE
    if "database_unlocked" not in st.session_state:
        st.session_state.database_unlocked = False
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = ""
    if "page_files" not in st.session_state:
        st.session_state.page_files = []
    if "upload_signature" not in st.session_state:
        st.session_state.upload_signature = None
    if "temporary_directory" not in st.session_state:
        # Der Ordner lebt nur so lange wie die Browsersitzung. Dadurch werden
        # hochgeladene medizinische Dokumente nicht dauerhaft im Projekt abgelegt.
        st.session_state.temporary_directory = tempfile.TemporaryDirectory(
            prefix="ced_web_"
        )
    if "provider" not in st.session_state:
        # Die UK-API ist unabhängig von einer optionalen Umgebungsvariable immer
        # die datenschutzfreundliche Vorauswahl der Oberfläche.
        st.session_state.provider = "uk"
    if "openai_warning_pending" not in st.session_state:
        st.session_state.openai_warning_pending = False


def _apply_layout() -> None:
    """Setzt das Seitenlayout und die stets sichtbare Provider-Markierung."""
    st.set_page_config(
        page_title="CED-A-DOKU",
        page_icon="⚕️",
        layout="wide",
    )
    st.markdown(
        """
        <style>
        .stApp { background: #f4f8f8; }
        [data-testid="stHeader"] { background: rgba(244, 248, 248, 0.92); }
        h1, h2, h3 { color: #123f43; }
        [data-testid="stSidebar"] { background: #e5f0ef; border-right: 1px solid #bdd4d2; }
        .medical-header { border-left: 6px solid #168078; padding: .25rem 0 .25rem 1rem;
          margin-bottom: 1rem; }
        .medical-kicker { color: #168078; font-weight: 700; letter-spacing: .08em;
          text-transform: uppercase; font-size: .76rem; }
        .provider-badge {
            position: fixed;
            right: 1.25rem;
            bottom: 0.8rem;
            z-index: 9999;
            border-radius: 0.5rem;
            padding: 0.35rem 0.65rem;
            color: white;
            font-size: 0.78rem;
            font-weight: 700;
            box-shadow: 0 1px 5px rgba(0, 0, 0, 0.25);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.dialog("Datenschutzhinweis")
def _show_openai_warning() -> None:
    """Verlangt eine bewusste Bestätigung vor der Nutzung von OpenAI."""
    st.warning(
        "Bei Verwendung von OpenAI dürfen keine personenbezogenen Daten oder "
        "Dokumente mit identifizierbaren Patientendaten übermittelt werden."
    )
    if st.button("O. K.", type="primary", use_container_width=True):
        st.session_state.openai_warning_pending = False
        st.rerun()


def _show_provider_badge(provider: str) -> None:
    """Zeigt Provider und Secret-Namen, aber niemals den geheimen Schlüsselwert."""
    if provider == "uk":
        label = "UK-API · UK_API_KEY"
        color = "#16833b"
    else:
        label = "OpenAI · OPENAI_API_KEY"
        color = "#b42318"
    st.markdown(
        f'<div class="provider-badge" style="background:{color}">● {label}</div>',
        unsafe_allow_html=True,
    )


def _show_admin_area(settings: Settings) -> str:
    """Zeigt geschützte Datenbank- und Modellauswahl getrennt in der Seitenleiste."""
    with st.sidebar:
        st.markdown("### ⚙️ Steuerung / Administration")
        st.caption("Zugriff auf sensible Verarbeitungsfunktionen")
        provider = st.selectbox(
            "LLM auswählen",
            options=("uk", "openai"),
            format_func=lambda value: "UK-API (Standard)" if value == "uk" else "OpenAI",
            key="provider",
        )
        if (
            provider == "openai"
            and st.session_state.get("previous_provider") != "openai"
        ):
            st.session_state.openai_warning_pending = True
        st.session_state.previous_provider = provider

        st.divider()
        st.markdown("#### CED-Datenbank")
        if st.session_state.work_mode == DATABASE_MODE:
            st.success("Datenbankmodus aktiv")
            if st.button("Datenbankmodus beenden", use_container_width=True):
                st.session_state.work_mode = READ_MODE
                st.session_state.database_unlocked = False
                st.rerun()
        else:
            st.caption("Nur für autorisierte Mitarbeitende")
            password = st.text_input(
                "Administrationspasswort",
                type="password",
                help="Das Passwort wird mit CED_DATA_PASS verglichen und nicht gespeichert.",
            )
            if st.button("CED-Datenbank aktivieren", use_container_width=True):
                try:
                    expected_password = settings.ced_database_password()
                except ConfigurationError as error:
                    st.error(str(error))
                else:
                    if hmac.compare_digest(password, expected_password):
                        st.session_state.database_unlocked = True
                        st.session_state.work_mode = DATABASE_MODE
                        st.rerun()
                    st.error("Das Passwort ist falsch.")
    return provider


def _prepare_uploaded_pages(uploaded_files: list) -> list[Path]:
    """Speichert Browser-Uploads temporär und konvertiert PDFs in Bildseiten."""
    signature = tuple((item.name, item.size) for item in uploaded_files)
    if signature == st.session_state.upload_signature:
        return list(st.session_state.page_files)

    temporary_root = Path(st.session_state.temporary_directory.name)
    upload_root = temporary_root / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    source_paths: list[Path] = []

    for index, uploaded_file in enumerate(uploaded_files, start=1):
        # Path(...).name entfernt etwaige Verzeichnisanteile aus dem Browsernamen.
        # Der Index verhindert, dass gleichnamige Uploads einander überschreiben.
        safe_name = Path(uploaded_file.name).name
        target = upload_root / f"{index}_{safe_name}"
        target.write_bytes(uploaded_file.getvalue())
        source_paths.append(target)

    converter = DocumentConverter(output_directory=temporary_root / "pages")
    pages = converter.convert(source_paths)
    st.session_state.upload_signature = signature
    st.session_state.page_files = pages
    st.session_state.analysis_result = ""
    return pages


def _create_provider(provider: str, settings: Settings) -> DocumentAI:
    """Erstellt ausschließlich den sichtbar gewählten Provider, ohne Fallback."""
    if provider == "uk":
        return LocalAPIProvider(settings)
    return CloudAPIProvider(settings)


def _show_document_workspace(settings: Settings) -> None:
    """Zeigt Upload, Seitenvorschau und KI-Reintext nebeneinander."""
    provider = _show_admin_area(settings)
    st.markdown(
        '<div class="medical-header"><div class="medical-kicker">Medizinische Dokumentation</div>'
        '<h1>CED-A-DOKU</h1><div>Assistierte Dokumentauslesung</div></div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Aktiver Bereich: {st.session_state.work_mode}")
    st.info(
        "KI-Ergebnisse sind ungeprüfte Vorschläge und dürfen nicht automatisch als "
        "medizinische Fakten oder Therapieentscheidungen übernommen werden."
    )

    if st.session_state.work_mode == DATABASE_MODE:
        st.warning(
            "Der Datenbankmodus ist freigeschaltet. Die strukturierte Verarbeitung "
            "und Speicherung wird erst in einer nachfolgenden Phase implementiert."
        )

    _show_provider_badge(provider)
    if st.session_state.openai_warning_pending:
        _show_openai_warning()

    uploaded_files = st.file_uploader(
        "PDF-, JPG- oder PNG-Dokumente auswählen",
        type=("pdf", "png", "jpg", "jpeg"),
        accept_multiple_files=True,
        help=(
            "Mehrere Bilder können gemeinsam ausgewählt werden. Die Reihenfolge "
            "entspricht der Upload-Reihenfolge. Pro KI-Anfrage werden höchstens "
            "fünf Bilder gesendet."
        ),
    )

    pages: list[Path] = []
    if uploaded_files:
        try:
            pages = _prepare_uploaded_pages(uploaded_files)
        except (DocumentConversionError, OSError) as error:
            st.error(f"Dokumentimport fehlgeschlagen: {error}")
            # Debugging-Hinweis: Bei Bedarf lokal den Exception-Typ untersuchen.
            # Dateiinhalte und Dateinamen niemals in produktive Logs schreiben.
            return

    original_column, result_column = st.columns(2, gap="large")
    with original_column:
        st.subheader("Originaldokument")
        if not pages:
            st.info("Noch kein Dokument ausgewählt.")
        else:
            selected_page = st.selectbox(
                "Seite anzeigen",
                range(len(pages)),
                format_func=lambda index: f"Seite {index + 1}",
            )
            st.image(str(pages[selected_page]), use_container_width=True)
            st.caption(f"{len(pages)} Seite(n) für die Auslesung vorbereitet")

    with result_column:
        st.subheader("Ausgelesener Reintext")
        if st.button(
            "Dokument auslesen",
            type="primary",
            disabled=not pages,
            use_container_width=True,
        ):
            try:
                ai_provider = _create_provider(provider, settings)
                with st.spinner("Dokument wird ausgelesen …"):
                    st.session_state.analysis_result = ai_provider.analyze(
                        pages,
                        document_type="noch nicht klassifiziert",
                        categories=[],
                        prompt_config={},
                    )
            except (ConfigurationError, AIProviderError, OSError, ValueError) as error:
                st.error(str(error))
                # Es erfolgt bewusst kein automatischer Wechsel des Providers. Zum
                # Debugging Endpunkt, Modell-ID und Secret-Verfügbarkeit prüfen;
                # niemals Authorization-Header oder Dokumentinhalt protokollieren.

        if st.session_state.analysis_result:
            st.text_area(
                "Ungeprüfte KI-Ausgabe",
                value=st.session_state.analysis_result,
                height=520,
            )
            st.caption("Dieses Ergebnis wurde noch nicht bestätigt oder gespeichert.")
        else:
            st.info("Nach der KI-Auslesung erscheint der Dokumentinhalt hier.")


def main() -> None:
    """Initialisiert die Browseranwendung und steuert den aktuellen Arbeitsmodus."""
    _apply_layout()
    _initialize_session()
    settings = Settings.from_environment()
    initialize_database(settings)

    _show_document_workspace(settings)
