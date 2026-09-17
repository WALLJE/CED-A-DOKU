"""Tests der versionierten manuellen CED-Stammdaten mit Testpatienten."""

from datetime import date

import pytest
from sqlalchemy import func, select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import AuditLog, Patient, PatientCEDAttribute
from ced_document_ai.services.ced.patient_overview import lade_patientenuebersicht
from ced_document_ai.services.ced.patient_profile import (
    ManuelleCEDStammdaten,
    speichere_manuelle_stammdaten,
)


def test_manuelle_stammdaten_werden_versioniert_und_angezeigt(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "profil.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-01", name="Erika Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        anzahl = speichere_manuelle_stammdaten(
            sitzung,
            patient.id,
            ManuelleCEDStammdaten(
                erstdiagnose=date(2020, 4, 3),
                befallsmuster="synthetisches Testmuster",
            ),
        )
        speichere_manuelle_stammdaten(
            sitzung,
            patient.id,
            ManuelleCEDStammdaten(
                erstdiagnose=None,
                befallsmuster="aktualisiertes Testmuster",
            ),
        )
        uebersicht = lade_patientenuebersicht(sitzung, patient.id)

        assert anzahl == 2
        assert uebersicht.erstdiagnose == date(2020, 4, 3)
        assert uebersicht.befallsmuster == "aktualisiertes Testmuster"
        assert (
            sitzung.scalar(select(func.count()).select_from(PatientCEDAttribute)) == 3
        )
        assert sitzung.scalar(select(func.count()).select_from(AuditLog)) == 2


def test_leerer_auftrag_erzeugt_keine_daten(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "leer.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-02", name="Max Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        with pytest.raises(ValueError, match="mindestens ein"):
            speichere_manuelle_stammdaten(
                sitzung,
                patient.id,
                ManuelleCEDStammdaten(erstdiagnose=None, befallsmuster="  "),
            )

        assert (
            sitzung.scalar(select(func.count()).select_from(PatientCEDAttribute)) == 0
        )
        assert sitzung.scalar(select(func.count()).select_from(AuditLog)) == 0
