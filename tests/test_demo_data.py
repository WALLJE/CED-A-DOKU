"""Tests der ausschließlich explizit erzeugten synthetischen Verlaufsdaten."""

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


def test_demo_seeder_ist_bei_vollstaendigem_bestand_idempotent(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "doppelt.sqlite3"))
    with fabrik() as sitzung:
        assert erzeuge_demo_daten(sitzung) == 5
        assert erzeuge_demo_daten(sitzung) == 0
        assert sitzung.scalar(select(func.count()).select_from(Patient)) == 5
        assert sitzung.scalar(select(func.count()).select_from(Finding)) == 180


def test_demo_seeder_ergaenzt_fehlende_faelle_ohne_bestand_zu_aendern(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "teilbestand.sqlite3"))
    with fabrik() as sitzung:
        vorhandener_patient = Patient(
            external_id="DEMO-003",
            first_name="Bewusst",
            last_name="Vorhanden",
            name="Vorhanden, Bewusst",
        )
        sitzung.add(vorhandener_patient)
        sitzung.commit()
        vorhandene_id = vorhandener_patient.id

        assert erzeuge_demo_daten(sitzung) == 4
        demo_patienten = list(
            sitzung.scalars(
                select(Patient)
                .where(Patient.external_id.like("DEMO-%"))
                .order_by(Patient.external_id)
            )
        )

        assert [patient.external_id for patient in demo_patienten] == [
            f"DEMO-{nummer:03d}" for nummer in range(1, 6)
        ]
        unveraendert = next(
            patient for patient in demo_patienten if patient.external_id == "DEMO-003"
        )
        assert unveraendert.id == vorhandene_id
        assert unveraendert.display_name == "Vorhanden, Bewusst"
