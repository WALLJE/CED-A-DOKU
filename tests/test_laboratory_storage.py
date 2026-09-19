"""Tests der atomaren Speicherung bestätigter Laborwerte."""

from datetime import date

import pytest
from sqlalchemy import func, select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import (
    AIResult,
    ConfidenceStatus,
    Document,
    Finding,
    FindingCategory,
    Patient,
)
from ced_document_ai.services.ced.laboratory_storage import (
    FreigegebenerLaborwert,
    LaborSpeicherauftrag,
    speichere_laborpruefung,
)


def _auftrag(patient_id: int) -> LaborSpeicherauftrag:
    return LaborSpeicherauftrag(
        patient_id=patient_id,
        dokumenttyp="Virologischer Befund",
        befunddatum=date(2026, 9, 19),
        original_name="virologie.pdf",
        rohe_ki_antwort="Synthetische Rohantwort",
        kis_vorschlag="CMV-PCR negativ.",
        provider="TEST",
        modell="TESTMODELL",
        befunde=(
            FreigegebenerLaborwert(
                kategorie="CMV-PCR",
                anzeigewert="negativ",
                numerischer_wert=None,
                einheit=None,
                referenzbereich="negativ",
                quelltext="| CMV-PCR | negativ | | negativ |",
                fachgruppe="Labor",
                qualitaet=ConfidenceStatus.UNCERTAIN,
            ),
        ),
    )


def test_bestaetigter_virologiewert_wird_atomar_gespeichert(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "labor.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="LAB-1", name="Labor Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        dokument_id = speichere_laborpruefung(sitzung, _auftrag(patient.id))
        dokument = sitzung.get(Document, dokument_id)
        befund = sitzung.scalar(select(Finding))
        kategorie = sitzung.scalar(select(FindingCategory))

        assert dokument is not None and dokument.confirmed
        assert dokument.document_date == date(2026, 9, 19)
        assert befund is not None and befund.text_value == "negativ"
        assert befund.confirmed_by_user
        assert kategorie is not None and kategorie.name == "CMV-PCR"
        assert kategorie.group_name == "Labor"
        assert sitzung.scalar(select(func.count()).select_from(AIResult)) == 1


def test_falsche_kategoriegruppe_verhindert_gesamte_uebernahme(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "konflikt.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="LAB-2", name="Konflikt Beispiel")
        sitzung.add_all(
            [patient, FindingCategory(name="CMV-PCR", group_name="MRT")]
        )
        sitzung.commit()

        with pytest.raises(ValueError, match="anderen Befundgruppe"):
            speichere_laborpruefung(sitzung, _auftrag(patient.id))

        assert sitzung.scalar(select(func.count()).select_from(Document)) == 0
        assert sitzung.scalar(select(func.count()).select_from(Finding)) == 0
        assert sitzung.scalar(select(func.count()).select_from(AIResult)) == 0
