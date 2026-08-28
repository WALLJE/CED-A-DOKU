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
        st.session_state.work_mode = None
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


def _apply_layout() -> None:
    """Setzt das Seitenlayout und die stets sichtbare Provider-Markierung."""
    st.set_page_config(
        page_title="CED-A-DOKU",
        page_icon="📄",
        layout="wide",
    )
    st.markdown(
        """
        <style>
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


def _show_mode_selection(settings: Settings) -> bool:
    """Fordert vor der Dokumentansicht den gewünschten Arbeitsmodus an."""
    st.title("CED-A-DOKU")
    st.info(
        "KI-Ergebnisse sind ungeprüfte Vorschläge und dürfen nicht automatisch als "
        "medizinische Fakten oder Therapieentscheidungen übernommen werden."
    )
    st.subheader("Arbeitsmodus auswählen")
    selected_mode = st.radio(
        "Wie soll die Anwendung gestartet werden?",
        (READ_MODE, DATABASE_MODE),
        index=0,
    )

    if selected_mode == DATABASE_MODE:
        password = st.text_input(
            "Passwort für den CED-Datenbankmodus",
            type="password",
            help="Das Passwort wird mit CED_DATA_PASS verglichen und nicht gespeichert.",
        )
        if st.button("Datenbankzugang prüfen", type="primary"):
            try:
                expected_password = settings.ced_database_password()
            except ConfigurationError as error:
                st.error(str(error))
                return False
            if not hmac.compare_digest(password, expected_password):
                st.error("Das Passwort ist falsch.")
                return False
            st.session_state.database_unlocked = True
            st.session_state.work_mode = DATABASE_MODE
            st.rerun()
        return False

    if st.button("Nur Einlesen starten", type="primary"):
        st.session_state.work_mode = READ_MODE
        st.rerun()
    return False


def _reset_mode() -> None:
    """Beendet den aktuellen Modus, ohne Zugangsdaten oder Dokumente zu behalten."""
    st.session_state.work_mode = None
    st.session_state.database_unlocked = False
    st.session_state.analysis_result = ""
    st.session_state.page_files = []
    st.session_state.upload_signature = None
    st.rerun()


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
    heading, mode_column = st.columns([4, 1])
    with heading:
        st.title("CED-A-DOKU – Dokument einlesen")
        st.caption(f"Aktiver Modus: {st.session_state.work_mode}")
    with mode_column:
        if st.button("Modus wechseln"):
            _reset_mode()

    if st.session_state.work_mode == DATABASE_MODE:
        st.warning(
            "Der Datenbankmodus ist freigeschaltet. Die strukturierte Verarbeitung "
            "und Speicherung wird erst in einer nachfolgenden Phase implementiert."
        )

    provider = st.selectbox(
        "KI-Anbieter",
        options=("uk", "openai"),
        format_func=lambda value: (
            "UK-API (gemma4-31b)" if value == "uk" else "OpenAI"
        ),
        index=1 if settings.provider == "openai" else 0,
    )
    _show_provider_badge(provider)

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

    if st.session_state.work_mode is None:
        _show_mode_selection(settings)
        return
    if (
        st.session_state.work_mode == DATABASE_MODE
        and not st.session_state.database_unlocked
    ):
        st.session_state.work_mode = None
        st.rerun()
    _show_document_workspace(settings)

