"""Basis-GUI für Moduswahl, Dokumentimport, Vorschau und Reintext-Ausgabe."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ced_document_ai.config.settings import ConfigurationError, Settings
from ced_document_ai.services.ai.providers import (
    AIProviderError,
    CloudAPIProvider,
    DocumentAI,
    LocalAPIProvider,
)
from ced_document_ai.services.documents.converter import DocumentConverter


class WorkMode(str, Enum):
    READ_ONLY = "Nur Dokument einlesen"
    DATABASE = "Einlesen und in CED-Datenbank verarbeiten"


def choose_work_mode() -> WorkMode | None:
    """Zeigt beim Start die verlangte Modusauswahl und prüft den Datenbankzugang."""
    dialog = QDialog()
    dialog.setWindowTitle("CED-A-DOKU – Arbeitsmodus")
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Bitte wählen Sie den Arbeitsmodus:"))
    read_button = QPushButton(WorkMode.READ_ONLY.value)
    database_button = QPushButton(WorkMode.DATABASE.value)
    layout.addWidget(read_button)
    layout.addWidget(database_button)
    selected: list[WorkMode] = []

    def select_read_only() -> None:
        selected.append(WorkMode.READ_ONLY)
        dialog.accept()

    def select_database() -> None:
        password_dialog = QDialog(dialog)
        password_dialog.setWindowTitle("Geschützter CED-Datenbankzugang")
        password_layout = QVBoxLayout(password_dialog)
        password_layout.addWidget(QLabel("Passwort für den CED-Datenbankmodus:"))
        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        confirm = QPushButton("Zugang prüfen")
        password_layout.addWidget(password_input)
        password_layout.addWidget(confirm)

        def verify() -> None:
            try:
                expected = Settings.from_environment().ced_database_password()
            except ConfigurationError as error:
                QMessageBox.critical(password_dialog, "Konfiguration fehlt", str(error))
                return
            # compare_digest verhindert unnötige zeitliche Unterschiede beim Vergleich.
            import hmac

            if not hmac.compare_digest(password_input.text(), expected):
                QMessageBox.warning(password_dialog, "Zugriff verweigert", "Das Passwort ist falsch.")
                password_input.clear()
                return
            password_dialog.accept()

        confirm.clicked.connect(verify)
        password_input.returnPressed.connect(verify)
        if password_dialog.exec() == QDialog.DialogCode.Accepted:
            selected.append(WorkMode.DATABASE)
            dialog.accept()

    read_button.clicked.connect(select_read_only)
    database_button.clicked.connect(select_database)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return selected[0]


class AnalysisWorker(QObject):
    """Führt Netzwerkzugriffe außerhalb des GUI-Threads aus."""

    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, provider: DocumentAI, pages: list[Path]) -> None:
        super().__init__()
        self.provider = provider
        self.pages = pages

    def run(self) -> None:
        try:
            result = self.provider.analyze(
                self.pages,
                document_type="noch nicht klassifiziert",
                categories=[],
                prompt_config={},
            )
            self.finished.emit(result)
        except (AIProviderError, OSError, ValueError) as error:
            self.failed.emit(str(error))


class DropArea(QListWidget):
    """Liste, die unterstützte Dateien per Drag & Drop an das Hauptfenster meldet."""

    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.files_dropped.emit(paths)
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    """Lauffähige Minimaloberfläche für die erste Dokumentauslesung."""

    def __init__(self, mode: WorkMode) -> None:
        super().__init__()
        self.mode = mode
        self.settings = Settings.from_environment()
        self.converter = DocumentConverter()
        self.pages: list[Path] = []
        self.thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self.setWindowTitle(f"CED-A-DOKU – {mode.value}")
        self.resize(1150, 760)

        central = QWidget()
        root = QVBoxLayout(central)
        toolbar = QHBoxLayout()
        self.import_button = QPushButton("PDF/JPG/PNG auswählen")
        self.clipboard_button = QPushButton("Bild aus Zwischenablage")
        self.analyze_button = QPushButton("Dokument auslesen")
        self.analyze_button.setEnabled(False)
        self.provider_box = QComboBox()
        self.provider_box.addItem("UK-API (gemma4-31b)", "uk")
        self.provider_box.addItem("OpenAI", "openai")
        initial_index = 1 if self.settings.provider == "openai" else 0
        self.provider_box.setCurrentIndex(initial_index)
        toolbar.addWidget(self.import_button)
        toolbar.addWidget(self.clipboard_button)
        toolbar.addWidget(QLabel("KI-Anbieter:"))
        toolbar.addWidget(self.provider_box)
        toolbar.addWidget(self.analyze_button)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Dokumentseiten (Dateien hier ablegen):"))
        self.page_list = DropArea()
        self.preview = QLabel("Noch keine Seite ausgewählt")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(350)
        self.preview.setStyleSheet("QLabel { border: 1px solid #aaa; background: #fafafa; }")
        left_layout.addWidget(self.page_list)
        left_layout.addWidget(self.preview, stretch=1)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Ausgelesener Reintext (noch nicht gespeichert):"))
        self.output = QTextEdit()
        self.output.setPlaceholderText("Nach der KI-Auslesung erscheint der Dokumentinhalt hier.")
        right_layout.addWidget(self.output)
        splitter.addWidget(left)
        splitter.addWidget(right)
        root.addWidget(splitter, stretch=1)

        footer = QHBoxLayout()
        self.mode_label = QLabel(f"Modus: {mode.value}")
        self.provider_indicator = QLabel()
        footer.addWidget(self.mode_label)
        footer.addStretch()
        footer.addWidget(self.provider_indicator)
        root.addLayout(footer)
        self.setCentralWidget(central)

        self.import_button.clicked.connect(self.select_files)
        self.clipboard_button.clicked.connect(self.import_clipboard)
        self.analyze_button.clicked.connect(self.analyze)
        self.page_list.files_dropped.connect(self.add_files)
        self.page_list.currentRowChanged.connect(self.show_page)
        self.provider_box.currentIndexChanged.connect(self.update_provider_indicator)
        self.update_provider_indicator()

        if mode == WorkMode.DATABASE:
            self.statusBar().showMessage(
                "Datenbankmodus freigeschaltet; die strukturierte Verarbeitung folgt in einer späteren Phase."
            )

    def update_provider_indicator(self) -> None:
        """Zeigt nur den Provider, niemals Namen oder Inhalt des Secrets."""
        provider = self.provider_box.currentData()
        if provider == "uk":
            self.provider_indicator.setText("● UK-API · UK_API_KEY")
            self.provider_indicator.setStyleSheet("color: #16833b; font-weight: bold;")
        else:
            self.provider_indicator.setText("● OpenAI · OPEN_AI_KEY")
            self.provider_indicator.setStyleSheet("color: #b42318; font-weight: bold;")

    def select_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Medizinische Dokumente auswählen",
            "",
            "Dokumente (*.pdf *.png *.jpg *.jpeg)",
        )
        if paths:
            self.add_files(paths)

    def add_files(self, raw_paths: list[str]) -> None:
        """Konvertiert die Auswahl vollständig oder zeigt einen klaren Importfehler."""
        try:
            new_pages = self.converter.convert([Path(path) for path in raw_paths])
        except Exception as error:
            # Ein unerwarteter Importfehler wird sichtbar gemacht, nicht durch einen
            # alternativen stillen Verarbeitungsweg verdeckt. Zum Debugging können
            # Entwickler lokal `raise` ergänzen, ohne Patientendaten zu protokollieren.
            QMessageBox.critical(self, "Dokumentimport fehlgeschlagen", str(error))
            return
        self.pages.extend(new_pages)
        for page in new_pages:
            self.page_list.addItem(QListWidgetItem(f"Seite {self.page_list.count() + 1}: {page.name}"))
        self.analyze_button.setEnabled(bool(self.pages))
        if new_pages:
            self.page_list.setCurrentRow(len(self.pages) - len(new_pages))

    def import_clipboard(self) -> None:
        """Speichert ein Zwischenablagebild temporär und hängt es als weitere Seite an."""
        image = QApplication.clipboard().image()
        if image.isNull():
            QMessageBox.information(self, "Zwischenablage", "Die Zwischenablage enthält kein Bild.")
            return
        target = self.converter.temporary_file(f"clipboard_{len(self.pages) + 1}.png")
        if not image.save(str(target), "PNG"):
            QMessageBox.critical(self, "Zwischenablage", "Das Bild konnte nicht übernommen werden.")
            return
        self.add_files([str(target)])

    def show_page(self, row: int) -> None:
        if row < 0 or row >= len(self.pages):
            return
        pixmap = QPixmap(str(self.pages[row]))
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def analyze(self) -> None:
        """Erzeugt den gewählten Provider und startet genau diesen – ohne Fallback."""
        try:
            provider: DocumentAI
            if self.provider_box.currentData() == "uk":
                provider = LocalAPIProvider(self.settings)
            else:
                provider = CloudAPIProvider(self.settings)
        except ConfigurationError as error:
            QMessageBox.critical(self, "API-Konfiguration fehlt", str(error))
            return

        self.analyze_button.setEnabled(False)
        self.output.setPlainText("Dokument wird ausgelesen …")
        self.thread = QThread(self)
        self.worker = AnalysisWorker(provider, list(self.pages))
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.failed.connect(self.analysis_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def analysis_finished(self, text: str) -> None:
        self.output.setPlainText(text)
        self.analyze_button.setEnabled(True)
        self.statusBar().showMessage("Auslesung abgeschlossen. Ergebnis noch nicht bestätigt oder gespeichert.")

    def analysis_failed(self, message: str) -> None:
        self.output.clear()
        self.analyze_button.setEnabled(True)
        QMessageBox.critical(self, "KI-Auslesung fehlgeschlagen", message)
