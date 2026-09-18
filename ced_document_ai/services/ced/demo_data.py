"""Explizit aufrufbare, vollständig synthetische Testdaten für Fachansichten.

Dieses Modul wird beim normalen Anwendungsstart bewusst nicht ausgeführt. Dadurch
gelangen Demo-Einträge niemals unbemerkt in eine reale Datenbank. Der separate
Seeder bricht ab, sobald eine seiner reservierten ``DEMO-*``-IDs bereits existiert.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ced_document_ai.database.models import (
    ConfidenceStatus,
    Diagnosis,
    Document,
    Finding,
    FindingCategory,
    Patient,
    PatientCEDAttribute,
)
from ced_document_ai.services.ced.patient_profile import (
    BEFALLSMUSTER,
    ERSTDIAGNOSE,
    THERAPIE_CHIRURGISCH,
    THERAPIE_MEDIKAMENTOES,
)


KATEGORIEN = (
    ("Stuhlfrequenz", "CED-Fragebogen", "pro Tag"),
    ("Bauchschmerzen", "CED-Fragebogen", None),
    ("CRP", "Labor", "mg/l"),
    ("Hämoglobin", "Labor", "g/dl"),
    ("Leukozyten", "Labor", "Gpt/l"),
    ("Fäkales Calprotectin", "Calprotectin", "µg/g"),
    ("SES-CD", "Endoskopie", "Punkte"),
    ("Endoskopischer Befund", "Endoskopie", None),
    ("Darmwanddicke terminales Ileum", "Sonografie", "mm"),
    ("Sonografische Aktivität", "Sonografie", None),
    ("MRT Aktivitätszeichen", "MRT", None),
    ("CT Komplikation", "CT", None),
)


def erzeuge_demo_daten(sitzung: Session) -> int:
    """Legt fünf Patienten mit longitudinalen, fachlich getrennten Testwerten an."""
    demo_ids = tuple(f"DEMO-{nummer:03d}" for nummer in range(1, 6))
    vorhanden = sitzung.scalar(
        select(Patient.id).where(Patient.external_id.in_(demo_ids)).limit(1)
    )
    if vorhanden is not None:
        raise ValueError(
            "Demo-Daten wurden nicht angelegt: Mindestens eine DEMO-Patienten-ID existiert bereits."
        )

    kategorien: dict[str, FindingCategory] = {}
    for name, gruppe, einheit in KATEGORIEN:
        kategorie = sitzung.scalar(
            select(FindingCategory).where(FindingCategory.name == name)
        )
        if kategorie is None:
            kategorie = FindingCategory(
                name=name, group_name=gruppe, typical_unit=einheit
            )
            sitzung.add(kategorie)
        elif kategorie.group_name != gruppe:
            raise ValueError(
                f"Demo-Kategorie {name!r} gehört nicht zur erwarteten Fachgruppe {gruppe!r}."
            )
        kategorien[name] = kategorie
    sitzung.flush()

    patienten = (
        ("Muster", "Anna", date(1987, 2, 14), "Morbus Crohn", "L3, B1"),
        ("Beispiel", "Bernd", date(1974, 7, 3), "Colitis ulcerosa", "E3"),
        ("Testperson", "Clara", date(1992, 11, 21), "Morbus Crohn", "L1, B2"),
        ("Demofall", "David", date(1968, 5, 9), "Colitis ulcerosa", "E2"),
        ("Prüfpatient", "Eva", date(2001, 1, 30), "Morbus Crohn", "L2, B1"),
    )
    zeitpunkte = (date(2025, 1, 15), date(2025, 7, 15), date(2026, 1, 15))

    for index, (nachname, vorname, geburt, diagnose, befall) in enumerate(patienten):
        patient = Patient(
            external_id=demo_ids[index],
            first_name=vorname,
            last_name=nachname,
            name=f"{nachname}, {vorname}",
            birth_date=geburt,
        )
        sitzung.add(patient)
        sitzung.flush()
        sitzung.add_all(
            [
                Diagnosis(
                    patient_id=patient.id,
                    diagnosis_name=diagnose,
                    diagnosis_code="K50.8" if diagnose == "Morbus Crohn" else "K51.8",
                    first_diagnosis_date=date(2015 + index, 3, 1),
                    status="HAUPTDIAGNOSE",
                ),
                Diagnosis(
                    patient_id=patient.id,
                    diagnosis_name="Vitamin-D-Mangel",
                    diagnosis_code="E55.9",
                    first_diagnosis_date=date(2022, 6, 1),
                    status="NEBENDIAGNOSE",
                ),
                PatientCEDAttribute(
                    patient_id=patient.id,
                    attribute_type=ERSTDIAGNOSE,
                    date_value=date(2015 + index, 3, 1),
                    source_type="DEMO",
                ),
                PatientCEDAttribute(
                    patient_id=patient.id,
                    attribute_type=BEFALLSMUSTER,
                    text_value=befall,
                    source_type="DEMO",
                ),
                PatientCEDAttribute(
                    patient_id=patient.id,
                    attribute_type=THERAPIE_MEDIKAMENTOES,
                    text_value="Vedolizumab seit 2024; zuvor Mesalazin",
                    source_type="DEMO",
                ),
                PatientCEDAttribute(
                    patient_id=patient.id,
                    attribute_type=THERAPIE_CHIRURGISCH,
                    text_value=(
                        "Ileozökalresektion 2020" if index % 2 == 0 else "keine Operation"
                    ),
                    source_type="DEMO",
                ),
            ]
        )

        for messung, datum in enumerate(zeitpunkte):
            dokument = Document(
                patient_id=patient.id,
                original_name=f"demo-{demo_ids[index]}-{datum.isoformat()}.pdf",
                confirmed=True,
            )
            sitzung.add(dokument)
            sitzung.flush()
            # Die Werte sind ausgedacht und dienen ausschließlich dazu, Tabellen,
            # Zeitachsen, Einheiten und Fachgruppen visuell prüfen zu können.
            werte = (
                ("Stuhlfrequenz", 7 - messung, f"{7 - messung} pro Tag", "pro Tag"),
                ("Bauchschmerzen", None, ("stark", "mittel", "leicht")[messung], None),
                ("CRP", 18 - 5 * messung + index, None, "mg/l"),
                ("Hämoglobin", 11.5 + 0.4 * messung, None, "g/dl"),
                ("Leukozyten", 10.2 - 0.8 * messung, None, "Gpt/l"),
                ("Fäkales Calprotectin", 620 - 190 * messung + 10 * index, None, "µg/g"),
                ("SES-CD", 12 - 3 * messung, None, "Punkte"),
                ("Endoskopischer Befund", None, ("deutlich aktiv", "mäßig aktiv", "milde Restaktivität")[messung], None),
                ("Darmwanddicke terminales Ileum", 6.5 - messung, None, "mm"),
                ("Sonografische Aktivität", None, ("hoch", "mittel", "gering")[messung], None),
                ("MRT Aktivitätszeichen", None, ("ausgeprägt", "rückläufig", "gering")[messung], None),
                ("CT Komplikation", None, "keine Fistel oder Abszess", None),
            )
            for name, numerisch, textwert, einheit in werte:
                sitzung.add(
                    Finding(
                        patient_id=patient.id,
                        document_id=dokument.id,
                        category_id=kategorien[name].id,
                        finding_date=datum,
                        numeric_value=numerisch,
                        text_value=textwert,
                        unit=einheit,
                        source_text="Synthetischer Demo-Datensatz",
                        confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                        confirmed_by_user=True,
                    )
                )
    sitzung.commit()
    return len(patienten)
