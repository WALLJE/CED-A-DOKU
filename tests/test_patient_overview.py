"""Tests der Patientenübersicht mit ausschließlich synthetischen Testdaten."""

from datetime import date

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import (
    ConfidenceStatus,
    Diagnosis,
    Document,
    Finding,
    FindingCategory,
    Patient,
)
from ced_document_ai.services.ced.patient_overview import (
    berechne_alter,
    lade_klinischen_verlauf,
    lade_patientenuebersicht,
)


def test_alter_wird_am_stichtag_korrekt_berechnet() -> None:
    assert berechne_alter(date(1980, 9, 14), am=date(2026, 9, 14)) == 46
    assert berechne_alter(date(1980, 9, 15), am=date(2026, 9, 14)) == 45
    assert berechne_alter(None, am=date(2026, 9, 14)) is None
    assert berechne_alter(date(2030, 1, 1), am=date(2026, 9, 14)) is None


def test_uebersicht_zeigt_nur_letztes_befunddatum_und_bestaetigte_werte(
    tmp_path,
) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "uebersicht.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(
            external_id="TEST-01",
            name="Erika Beispiel",
            birth_date=date(1980, 3, 12),
        )
        dokument = Document(patient_id=None, original_name="test.pdf", confirmed=True)
        gewicht = FindingCategory(name="Gewicht", group_name="CED-Fragebogen")
        blut = FindingCategory(name="Blut im Stuhl", group_name="CED-Fragebogen")
        sitzung.add_all([patient, dokument, gewicht, blut])
        sitzung.flush()
        dokument.patient_id = patient.id
        sitzung.add(
            Diagnosis(
                patient_id=patient.id,
                diagnosis_name="Synthetische Testdiagnose",
                first_diagnosis_date=date(2020, 1, 1),
                status="AKTIV",
            )
        )
        sitzung.add_all(
            [
                Finding(
                    patient_id=patient.id,
                    document_id=dokument.id,
                    category_id=gewicht.id,
                    finding_date=date(2026, 1, 1),
                    numeric_value=70,
                    text_value="70 kg",
                    unit="kg",
                    confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                    confirmed_by_user=True,
                ),
                Finding(
                    patient_id=patient.id,
                    document_id=dokument.id,
                    category_id=gewicht.id,
                    finding_date=date(2026, 9, 13),
                    numeric_value=74,
                    text_value="74 kg",
                    unit="kg",
                    confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                    confirmed_by_user=True,
                ),
                Finding(
                    patient_id=patient.id,
                    document_id=dokument.id,
                    category_id=blut.id,
                    finding_date=date(2026, 9, 13),
                    text_value="ungeprüft",
                    confidence_status=ConfidenceStatus.UNCERTAIN,
                    confirmed_by_user=False,
                ),
            ]
        )
        sitzung.commit()

        uebersicht = lade_patientenuebersicht(
            sitzung, patient.id, stichtag=date(2026, 9, 14)
        )

    assert uebersicht.name == "Erika Beispiel"
    assert uebersicht.alter == 46
    assert uebersicht.letztes_befunddatum == date(2026, 9, 13)
    assert [(wert.kategorie, wert.wert) for wert in uebersicht.letzte_befunde] == [
        ("Gewicht", "74 kg")
    ]
    assert uebersicht.diagnosen[0].bezeichnung == "Synthetische Testdiagnose"


def test_klinischer_verlauf_pivotiert_bestaetigte_ced_parameter(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "verlauf.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-02", name="Max Beispiel", birth_date=None)
        dokument = Document(patient_id=None, original_name="test.pdf", confirmed=True)
        stuhl = FindingCategory(name="Stuhlfrequenz", group_name="CED-Fragebogen")
        labor = FindingCategory(name="CRP", group_name="Labor")
        sitzung.add_all([patient, dokument, stuhl, labor])
        sitzung.flush()
        dokument.patient_id = patient.id
        for datum, wert in (
            (date(2026, 1, 1), "6 pro Tag"),
            (date(2026, 9, 13), "3 pro Tag"),
        ):
            sitzung.add(
                Finding(
                    patient_id=patient.id,
                    document_id=dokument.id,
                    category_id=stuhl.id,
                    finding_date=datum,
                    text_value=wert,
                    confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                    confirmed_by_user=True,
                )
            )
        sitzung.add(
            Finding(
                patient_id=patient.id,
                document_id=dokument.id,
                category_id=labor.id,
                finding_date=date(2026, 9, 13),
                numeric_value=12,
                unit="mg/l",
                confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                confirmed_by_user=True,
            )
        )
        sitzung.commit()

        verlauf = lade_klinischen_verlauf(sitzung, patient.id)

    assert verlauf.daten == (date(2026, 1, 1), date(2026, 9, 13))
    assert len(verlauf.zeilen) == 1
    assert verlauf.zeilen[0].kategorie == "Stuhlfrequenz"
    assert verlauf.zeilen[0].werte == (
        (date(2026, 1, 1), "6 pro Tag"),
        (date(2026, 9, 13), "3 pro Tag"),
    )


def test_mehrere_werte_am_selben_tag_werden_nicht_ueberschrieben(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "doppelt.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-03", name="Doppel Beispiel", birth_date=None)
        dokument = Document(patient_id=None, original_name="test.pdf", confirmed=True)
        kategorie = FindingCategory(name="Gewicht", group_name="CED-Fragebogen")
        sitzung.add_all([patient, dokument, kategorie])
        sitzung.flush()
        dokument.patient_id = patient.id
        for wert in ("70 kg", "71 kg"):
            sitzung.add(
                Finding(
                    patient_id=patient.id,
                    document_id=dokument.id,
                    category_id=kategorie.id,
                    finding_date=date(2026, 9, 13),
                    text_value=wert,
                    confidence_status=ConfidenceStatus.CONFLICT,
                    confirmed_by_user=True,
                )
            )
        sitzung.commit()

        verlauf = lade_klinischen_verlauf(sitzung, patient.id)

    assert verlauf.zeilen[0].werte == ((date(2026, 9, 13), "70 kg | 71 kg"),)
