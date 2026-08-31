"""Prüft die PDF-Konvertierung über den aktuellen PyMuPDF-Modulnamen."""

from pathlib import Path

import pymupdf

from ced_document_ai.services.documents.converter import DocumentConverter


def test_pdf_wird_mit_pymupdf_in_geordnete_bildseiten_konvertiert(
    tmp_path: Path,
) -> None:
    """Sichert Seitenzahl und Reihenfolge ohne ein medizinisches Testdokument."""
    quellpfad = tmp_path / "test.pdf"
    with pymupdf.open() as dokument:
        dokument.new_page().insert_text((72, 72), "Erste Testseite")
        dokument.new_page().insert_text((72, 72), "Zweite Testseite")
        dokument.save(quellpfad)

    zielordner = tmp_path / "bilder"
    seiten = DocumentConverter(zielordner).convert([quellpfad])

    assert [seite.name for seite in seiten] == ["test_1.png", "test_2.png"]
    assert all(seite.is_file() and seite.stat().st_size > 0 for seite in seiten)


def test_gleichnamige_pdf_uploads_ueberschreiben_keine_bereits_erzeugten_seiten(
    tmp_path: Path,
) -> None:
    """Sichert, dass wirklich jedes separat hochgeladene Dokument analysiert wird."""
    quellpfad = tmp_path / "test.pdf"
    with pymupdf.open() as dokument:
        dokument.new_page().insert_text((72, 72), "Testseite")
        dokument.save(quellpfad)

    konverter = DocumentConverter(tmp_path / "bilder")
    erste_seite = konverter.convert([quellpfad])[0]
    zweite_seite = konverter.convert([quellpfad])[0]

    assert erste_seite.name == "test_1.png"
    assert zweite_seite.name == "test_1_2.png"
    assert erste_seite.is_file() and zweite_seite.is_file()
