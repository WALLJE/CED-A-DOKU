"""Tests der ausschließlich explizit erzeugten synthetischen Verlaufsdaten."""

import pytest
from sqlalchemy import func, select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import Finding, Patient
from ced_document_ai.services.ced.demo_data import erzeuge_demo_daten
from ced_document_ai.services.ced.patient_overview import (
    lade_fachverlauf,
    lade_klinischen_verlauf,
    lade_patientenuebersicht,
)


def test_demo_seeder_fuellt_patientenprofil_und_alle_fachverlaeufe(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "demo.sqlite3"))
    with fabrik() as sitzung:
        assert erzeuge_demo_daten(sitzung) == 5
        patient = sitzung.scalar(
            select(Patient).where(Patient.external_id == "DEMO-001")
        )
        assert patient is not None
        assert patient.first_name == "Anna"
        assert patient.last_name == "Muster"
        assert patient.display_name == "Muster, Anna"

        uebersicht = lade_patientenuebersicht(sitzung, patient.id)
        assert uebersicht.name == "Muster, Anna"
        assert uebersicht.therapie_medikamentoes
        assert uebersicht.therapie_chirurgisch
        assert {diagnose.status for diagnose in uebersicht.diagnosen} == {
            "HAUPTDIAGNOSE",
            "NEBENDIAGNOSE",
        }
        assert lade_klinischen_verlauf(sitzung, patient.id).daten
        for gruppen in (
            ("Labor",),
            ("Calprotectin",),
            ("Endoskopie",),
            ("Sonografie",),
            ("MRT", "CT"),
        ):
            fachverlauf = lade_fachverlauf(sitzung, patient.id, gruppen)
            assert len(fachverlauf.daten) == 3
            assert fachverlauf.zeilen
        assert sitzung.scalar(select(func.count()).select_from(Finding)) == 180


def test_demo_seeder_verhindert_doppelte_testpatienten(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "doppelt.sqlite3"))
    with fabrik() as sitzung:
        erzeuge_demo_daten(sitzung)
        with pytest.raises(ValueError, match="DEMO-Patienten-ID"):
            erzeuge_demo_daten(sitzung)
