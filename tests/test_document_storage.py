"""Tests der bestätigten Zuordnung allgemeiner Dokumente mit synthetischen Daten."""

from datetime import date

import pytest

from sqlalchemy import func, select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import (
    AIResult,
    Document,
    Finding,
    FindingCategory,
    Patient,
)
from ced_document_ai.services.ced.document_storage import (
    DokumentSpeicherauftrag,
    FreigegebenerDokumentbefund,
    finde_vorhandene_dokumentzuordnungen,
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
                kis_vorschlag_ausfuehrlich="Ausführlicher synthetischer KIS-Text",
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
        assert sitzung.scalar(select(AIResult.kis_summary_detailed)) == (
            "Ausführlicher synthetischer KIS-Text"
        )
        # Ohne Fachparser entstehen absichtlich keine geratenen Labor-Findings.
        assert sitzung.scalar(select(func.count()).select_from(Finding)) == 0


def test_arztbriefabschnitt_wird_nur_nach_freigabe_gespeichert(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "arztbrief.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-BRIEF", name="Brief Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        dokument_id = speichere_allgemeines_dokument(
            sitzung,
            DokumentSpeicherauftrag(
                patient_id=patient.id,
                dokumenttyp="Arztbrief",
                dokumentdatum=date(2026, 9, 28),
                original_name="arztbrief.pdf",
                rohe_ki_antwort="Synthetische Briefantwort",
                kis_vorschlag="Synthetische Zusammenfassung",
                provider="TEST",
                modell="TEST",
                befunde=(
                    FreigegebenerDokumentbefund(
                        kategorie="Diagnosen",
                        inhalt="Morbus Crohn (ED 06/2024)",
                        quelltext="Morbus Crohn (ED 06/2024)",
                        fachgruppe="Arztbriefe",
                    ),
                ),
            ),
        )

        befund = sitzung.scalar(select(Finding))
        kategorie = sitzung.scalar(
            select(FindingCategory).where(FindingCategory.name == "Diagnosen")
        )
        assert befund is not None and befund.document_id == dokument_id
        assert befund.text_value == "Morbus Crohn (ED 06/2024)"
        assert kategorie is not None and kategorie.group_name == "Arztbriefe"


def test_exakt_gleiche_rohantwort_findet_bestehende_patientenzuordnung(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "duplikat.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-DUP", name="Duplikat Beispiel")
        sitzung.add(patient)
        sitzung.commit()
        dokument_id = speichere_allgemeines_dokument(
            sitzung,
            DokumentSpeicherauftrag(
                patient_id=patient.id,
                dokumenttyp="Arztbrief",
                dokumentdatum=date(2026, 9, 28),
                original_name="gleich.pdf",
                rohe_ki_antwort="Exakt identische Antwort",
                kis_vorschlag="Kurz",
                provider="TEST",
                modell="TEST",
            ),
        )

        treffer = finde_vorhandene_dokumentzuordnungen(
            sitzung, "Exakt identische Antwort"
        )

        assert [(eintrag.dokument_id, eintrag.patient_id) for eintrag in treffer] == [
            (dokument_id, patient.id)
        ]


def test_unbestaetigte_neue_dokumentklasse_wird_nicht_implizit_angelegt(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "unbestaetigt.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-NEU", name="Klasse Beispiel")
        sitzung.add(patient)
        sitzung.commit()
        with pytest.raises(ValueError, match="nicht bestätigt"):
            speichere_allgemeines_dokument(
                sitzung,
                DokumentSpeicherauftrag(
                    patient_id=patient.id,
                    dokumenttyp="Von der KI erfundene Klasse",
                    dokumentdatum=date(2026, 9, 30),
                    original_name="unbekannt.pdf",
                    rohe_ki_antwort="Antwort",
                    kis_vorschlag="Kurz",
                    provider="TEST",
                    modell="TEST",
                ),
            )
        assert sitzung.scalar(select(func.count()).select_from(Document)) == 0
        assert sitzung.scalar(
            select(func.count()).select_from(FindingCategory).where(
                FindingCategory.name == "Von der KI erfundene Klasse"
            )
        ) == 0
