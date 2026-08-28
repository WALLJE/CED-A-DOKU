"""Konvertiert unterstützte Dokumente in geordnete Bildseiten für die KI."""

from __future__ import annotations

import tempfile
from pathlib import Path

import fitz

SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}


class DocumentConversionError(RuntimeError):
    """Verständlicher Importfehler ohne stilles Überspringen von Seiten."""


class DocumentConverter:
    """Erzeugt geordnete Bildseiten in einem temporären oder vorgegebenen Ordner."""

    def __init__(self, output_directory: Path | None = None) -> None:
        # Ohne Zielangabe wird ein eigener temporärer Ordner verwaltet. Die NiceGUI-
        # Oberfläche übergibt ihren sitzungsgebundenen Ordner, damit die Dateien
        # während der geöffneten Browserseite verfügbar bleiben.
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        if output_directory is None:
            self._temporary_directory = tempfile.TemporaryDirectory(prefix="ced_doku_")
            self.output_directory = Path(self._temporary_directory.name)
        else:
            self.output_directory = output_directory
            self.output_directory.mkdir(parents=True, exist_ok=True)

    def temporary_file(self, filename: str) -> Path:
        """Liefert einen sicheren Zielpfad für ein temporäres Zwischenablagebild."""
        safe_filename = Path(filename).name
        return self.output_directory / safe_filename

    def convert(self, source_paths: list[Path]) -> list[Path]:
        """Übernimmt Bilder direkt und rendert jede PDF-Seite als PNG."""
        pages: list[Path] = []
        for source in source_paths:
            suffix = source.suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                raise DocumentConversionError(f"Nicht unterstütztes Dateiformat: {source.name}")
            if suffix != ".pdf":
                pages.append(source)
                continue
            try:
                with fitz.open(source) as pdf:
                    for page_index, page in enumerate(pdf):
                        target = self.output_directory / f"{source.stem}_{page_index + 1}.png"
                        # 144 dpi liefern lesbaren Text, ohne Anfragen unnötig groß zu machen.
                        page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(target)
                        pages.append(target)
            except (fitz.FileDataError, OSError) as error:
                raise DocumentConversionError(
                    f"Die PDF-Datei {source.name} konnte nicht gelesen werden."
                ) from error
        return pages
