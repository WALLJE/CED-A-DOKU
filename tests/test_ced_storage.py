"""Prüft die atomare Speicherung ausschließlich mit synthetischen Testdaten."""

from datetime import date

import pytest
from sqlalchemy import func, select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import (
    AIResult,
    AuditLog,
    ConfidenceStatus,
    Document,
    Finding,
    FindingCategory,
    Patient,
)
from ced_document_ai.services.ced.storage import (
    CEDSpeicherauftrag,
    FreigegebenerBefund,
    speichere_ced_pruefung,
)


def _auftrag(patient_id: int) -> CEDSpeicherauftrag:
    """Erzeugt einen klar als Test gekennzeichneten vollständigen Speicherauftrag."""
    return CEDSpeicherauftrag(
        patient_id=patient_id,
        befunddatum=date(2026, 1, 1),
        original_name="synthetischer-testbogen.pdf",
        rohe_ki_antwort="Ausschließlich synthetische KI-Testantwort",
        kis_vorschlag="Synthetischer KIS-Testtext",
        provider="Test-Provider",
        modell="Test-Modell",
        befunde=(
            FreigegebenerBefund(
                kategorie="Gewicht",
                anzeigewert="74 kg",
                numerischer_wert=74,
                einheit="kg",
                quelltext="Gewicht: 74 kg",
                qualitaet=ConfidenceStatus.HIGH_CONFIDENCE,
            ),
            FreigegebenerBefund(
                kategorie="Appetit",
                anzeigewert="vermindert",
                numerischer_wert=None,
                einheit=None,
                quelltext="Appetit: vermindert",
                qualitaet=ConfidenceStatus.UNCERTAIN,
            ),
        ),
    )


def test_bestaetigte_befunde_und_neue_kategorie_werden_gemeinsam_gespeichert(
    tmp_path,
) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "speicher.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(
            external_id="TEST-001", name="Erika Beispiel", birth_date=date(1980, 3, 12)
        )
        sitzung.add(patient)
        sitzung.commit()

        dokument_id = speichere_ced_pruefung(sitzung, _auftrag(patient.id))

        dokument = sitzung.get(Document, dokument_id)
        assert dokument is not None and dokument.confirmed
        assert dokument.patient_id == patient.id
        assert sitzung.scalar(select(func.count(Finding.id))) == 2
        assert set(sitzung.scalars(select(FindingCategory.name))) >= {"Gewicht", "Appetit"}
        assert sitzung.scalar(select(AIResult.raw_ai_response)) == (
            "Ausschließlich synthetische KI-Testantwort"
        )
        assert sitzung.scalar(select(func.count(AuditLog.id))) == 1


def test_leerer_auftrag_speichert_keine_teildaten(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "leer.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-002", name="Max Beispiel", birth_date=None)
        sitzung.add(patient)
        sitzung.commit()
        leer = CEDSpeicherauftrag(
            patient_id=patient.id,
            befunddatum=date(2026, 1, 1),
            original_name="test.pdf",
            rohe_ki_antwort="Test",
            kis_vorschlag="Test",
            provider="Test",
            modell="Test",
            befunde=(),
        )

        with pytest.raises(ValueError, match="kein Befund"):
            speichere_ced_pruefung(sitzung, leer)

        assert sitzung.scalar(select(func.count(Document.id))) == 0
        assert sitzung.scalar(select(func.count(FindingCategory.id))) == 0
