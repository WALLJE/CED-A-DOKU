"""Speicherung manuell bestätigter CED-Stammdaten mit Versionshistorie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from sqlalchemy import select

from ced_document_ai.database.models import (
    AuditLog,
    Diagnosis,
    Patient,
    PatientCEDAttribute,
)


ERSTDIAGNOSE = "ERSTDIAGNOSE"
BEFALLSMUSTER = "BEFALLSMUSTER"
THERAPIE_MEDIKAMENTOES = "THERAPIE_MEDIKAMENTOES"
THERAPIE_CHIRURGISCH = "THERAPIE_CHIRURGISCH"


@dataclass(frozen=True)
class ManuelleCEDStammdaten:
    """Vom Benutzer ausdrücklich bestätigte, optional ausgefüllte Stammdaten."""

    erstdiagnose: date | None
    befallsmuster: str | None


@dataclass(frozen=True)
class PatientenfallEingabe:
    """Manuell geprüfte Diagnose- und Therapiefelder der Patientenübersicht."""

    hauptdiagnose: str
    nebendiagnosen: tuple[str, ...]
    therapie_medikamentoes: str | None
    therapie_chirurgisch: str | None


def speichere_patientenfall(
    sitzung: Session,
    patient_id: int,
    eingabe: PatientenfallEingabe,
) -> None:
    """Versioniert Diagnosen und geänderte Therapietexte in einer Transaktion."""
    if sitzung.get(Patient, patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    hauptdiagnose = eingabe.hauptdiagnose.strip()
    if not hauptdiagnose:
        raise ValueError("Eine Hauptdiagnose muss angegeben werden.")
    nebendiagnosen = tuple(
        dict.fromkeys(wert.strip() for wert in eingabe.nebendiagnosen if wert.strip())
    )
    with sitzung.begin_nested():
        # Frühere Diagnoseversionen bleiben erhalten und werden klar als ersetzt
        # markiert. So gibt es kein stilles Löschen medizinischer Angaben.
        for diagnose in sitzung.scalars(
            select(Diagnosis).where(
                Diagnosis.patient_id == patient_id,
                Diagnosis.status.in_(("HAUPTDIAGNOSE", "NEBENDIAGNOSE")),
            )
        ):
            diagnose.status = "ERSETZT"
        sitzung.add(
            Diagnosis(
                patient_id=patient_id,
                diagnosis_name=hauptdiagnose,
                status="HAUPTDIAGNOSE",
            )
        )
        sitzung.add_all(
            Diagnosis(
                patient_id=patient_id,
                diagnosis_name=wert,
                status="NEBENDIAGNOSE",
            )
            for wert in nebendiagnosen
        )
        for attributtyp, textwert in (
            (THERAPIE_MEDIKAMENTOES, eingabe.therapie_medikamentoes),
            (THERAPIE_CHIRURGISCH, eingabe.therapie_chirurgisch),
        ):
            bereinigt = (textwert or "").strip()
            if bereinigt:
                sitzung.add(
                    PatientCEDAttribute(
                        patient_id=patient_id,
                        attribute_type=attributtyp,
                        text_value=bereinigt,
                        source_type="MANUELL",
                        confirmed_by_user=True,
                    )
                )
        sitzung.add(
            AuditLog(
                action="PATIENTENFALL_MANUELL_BESTAETIGT",
                entity_type="Patient",
                entity_id=patient_id,
                details=f"1 Hauptdiagnose und {len(nebendiagnosen)} Nebendiagnose(n) versioniert",
            )
        )
    sitzung.commit()


def speichere_manuelle_stammdaten(
    sitzung: Session,
    patient_id: int,
    stammdaten: ManuelleCEDStammdaten,
) -> int:
    """Legt neue Versionen ausgefüllter Werte atomar an und gibt deren Anzahl zurück.

    Leere Felder löschen keine früheren Angaben. Soll ein Wert später ausdrücklich
    aufgehoben werden, benötigt dies einen eigenen fachlichen Vorgang. Es gibt keinen
    Fallback auf Freitext. Zum Debugging nur Exception-Typ und Anzahl der angelegten
    Versionen verwenden, niemals die medizinischen Werte selbst.
    """
    if sitzung.get(Patient, patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    befallsmuster = (stammdaten.befallsmuster or "").strip()
    if stammdaten.erstdiagnose is None and not befallsmuster:
        raise ValueError("Bitte mindestens ein CED-Stammdatenfeld ausfüllen.")

    neue_eintraege: list[PatientCEDAttribute] = []
    if stammdaten.erstdiagnose is not None:
        neue_eintraege.append(
            PatientCEDAttribute(
                patient_id=patient_id,
                attribute_type=ERSTDIAGNOSE,
                date_value=stammdaten.erstdiagnose,
                text_value=None,
                source_type="MANUELL",
                confirmed_by_user=True,
            )
        )
    if befallsmuster:
        neue_eintraege.append(
            PatientCEDAttribute(
                patient_id=patient_id,
                attribute_type=BEFALLSMUSTER,
                text_value=befallsmuster,
                date_value=None,
                source_type="MANUELL",
                confirmed_by_user=True,
            )
        )

    with sitzung.begin_nested():
        sitzung.add_all(neue_eintraege)
        sitzung.flush()
        sitzung.add(
            AuditLog(
                action="CED_STAMMDATEN_MANUELL_BESTAETIGT",
                entity_type="Patient",
                entity_id=patient_id,
                details=f"{len(neue_eintraege)} Stammdatenfeld(er) versioniert",
            )
        )
    sitzung.commit()
    return len(neue_eintraege)
