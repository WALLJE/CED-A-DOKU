"""Tests der bestätigten Zuordnung allgemeiner Dokumente mit synthetischen Daten."""

from datetime import date

from sqlalchemy import func, select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import AIResult, Document, Finding, Patient
from ced_document_ai.services.ced.document_storage import (
    DokumentSpeicherauftrag,
    speichere_allgemeines_dokument,
)


def test_allgemeines_dokument_wird_mit_patient_und_datum_archiviert(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "dokument.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-DOC", name="Dokument Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        dokument_id = speichere_allgemeines_dokument(
            sitzung,
            DokumentSpeicherauftrag(
                patient_id=patient.id,
                dokumenttyp="Laborbefund",
                dokumentdatum=date(2026, 9, 18),
                original_name="synthetisch.pdf",
                rohe_ki_antwort="Synthetische Rohantwort",
                kis_vorschlag="Synthetischer KIS-Text",
                provider="TEST",
                modell="TESTMODELL",
            ),
        )

        dokument = sitzung.get(Document, dokument_id)
        assert dokument is not None
        assert dokument.patient_id == patient.id
        assert dokument.document_date == date(2026, 9, 18)
        assert dokument.confirmed
        assert sitzung.scalar(select(func.count()).select_from(AIResult)) == 1
        # Ohne Fachparser entstehen absichtlich keine geratenen Labor-Findings.
        assert sitzung.scalar(select(func.count()).select_from(Finding)) == 0
