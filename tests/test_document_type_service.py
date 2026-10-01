"""Tests für den persistenten, ausschließlich nutzerbestätigten Klassenkatalog."""

from sqlalchemy import func, select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import DocumentType, DocumentTypeExample, FindingCategory
from ced_document_ai.services.ced.document_type_service import (
    ergaenze_bestaetigtes_beispiel,
    erstelle_patientenfreie_lernmerkmale,
    finde_aehnliche_klassen,
    lege_dokumentklasse_an,
    liste_dokumentklassen,
    liste_fachgruppen,
)


def test_neue_klasse_und_lernbeispiele_bleiben_persistent(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "klassen.sqlite3"))
    with fabrik() as sitzung:
        assert any(k.name == "Laborbefund" for k in liste_dokumentklassen(sitzung))
        klasse = lege_dokumentklasse_an(
            sitzung,
            name="Gefäßdiagnostischer Befund",
            fachgruppe="Funktionsdiagnostik",
            beschreibung="Bericht einer vaskulären Funktionsuntersuchung.",
            klassifikationsmerkmale="Explizite Gefäßregion und Untersuchungstechnik.",
            beispielmerkmale="Überschrift Gefäßdiagnostik und gegliederter Befund.",
        )
        ergaenze_bestaetigtes_beispiel(
            sitzung,
            dokumenttyp_name=klasse.name,
            beispielmerkmale="Enthält Untersuchung, Befund und Beurteilung.",
        )

    with fabrik() as sitzung:
        geladen = next(k for k in liste_dokumentklassen(sitzung) if k.name == klasse.name)
        assert geladen.fachgruppe == "Funktionsdiagnostik"
        assert len(geladen.beispiele) == 2
        assert sitzung.scalar(select(func.count(FindingCategory.id))) > 0
        assert sitzung.scalar(select(func.count(DocumentTypeExample.id))) == 2
        assert "Gefäßdiagnostischer Befund" in finde_aehnliche_klassen(
            sitzung, "Gefässdiagnostischer Befund"
        )


def test_klasse_wird_nicht_automatisch_ueberschrieben_oder_doppelt_angelegt(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "konflikt.sqlite3"))
    with fabrik() as sitzung:
        lege_dokumentklasse_an(
            sitzung,
            name="Spezialbefund",
            fachgruppe="Weitere Befunde",
            beschreibung="Bestätigte Beschreibung.",
            klassifikationsmerkmale="Bestätigte Merkmale.",
            beispielmerkmale="Erstes Beispiel.",
        )
        try:
            lege_dokumentklasse_an(
                sitzung,
                name="Spezialbefund",
                fachgruppe="Labor",
                beschreibung="Andere Beschreibung.",
                klassifikationsmerkmale="Andere Merkmale.",
                beispielmerkmale="Anderes Beispiel.",
            )
        except ValueError as fehler:
            assert "existiert bereits" in str(fehler)
        else:
            raise AssertionError("Eine bestehende Klasse darf nicht überschrieben werden.")
        gespeichert = sitzung.scalar(select(DocumentType).where(DocumentType.name == "Spezialbefund"))
        assert gespeichert.group_name == "Weitere Befunde"


def test_standardklassen_besitzen_definition_und_merkmale(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "standard.sqlite3"))
    with fabrik() as sitzung:
        klassen = liste_dokumentklassen(sitzung)
        assert klassen
        assert all(klasse.beschreibung and klasse.merkmale for klasse in klassen)
        gruppen = liste_fachgruppen(sitzung)
        assert gruppen[0].anzeigename == "CED-Fragebogen"
        assert gruppen[-1].anzeigename == "Weitere Befunde"


def test_lernmerkmale_enthalten_ueberschriften_aber_keine_patientenwerte() -> None:
    merkmale = erstelle_patientenfreie_lernmerkmale(
        """Patient: Max Beispiel
Geburtsdatum: 01.02.1980
Diagnosen: Morbus Crohn
Anamnese: Bauchschmerzen seit drei Tagen
Parameter | Ergebnis | Einheit | Referenzbereich
CRP | 12 | mg/l | < 5
"""
    )
    assert "Diagnosen" in merkmale
    assert "Anamnese" in merkmale
    assert "Parameter" in merkmale
    assert "Max Beispiel" not in merkmale
    assert "01.02.1980" not in merkmale
    assert "Morbus Crohn" not in merkmale
    assert "12" not in merkmale
