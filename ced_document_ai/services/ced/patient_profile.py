"""Speicherung manuell bestätigter CED-Stammdaten mit Versionshistorie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from ced_document_ai.database.models import AuditLog, Patient, PatientCEDAttribute


ERSTDIAGNOSE = "ERSTDIAGNOSE"
BEFALLSMUSTER = "BEFALLSMUSTER"


@dataclass(frozen=True)
class ManuelleCEDStammdaten:
    """Vom Benutzer ausdrücklich bestätigte, optional ausgefüllte Stammdaten."""

    erstdiagnose: date | None
    befallsmuster: str | None


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
