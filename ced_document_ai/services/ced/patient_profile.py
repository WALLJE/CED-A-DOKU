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
DIAGNOSE_HINWEISE = "DIAGNOSE_HINWEISE"
EIM_AUSWAHL = "EIM_AUSWAHL"
EIM_WEITERE = "EIM_WEITERE"

# Fester initialer Katalog für die sichtbare Mehrfachauswahl. Die Einträge werden
# nicht aus Dokumenttext geraten; weitere Manifestationen bleiben als bewusstes
# Freitextfeld möglich.
EIM_OPTIONEN: tuple[str, ...] = (
    "Arthritis / Arthralgie",
    "Sakroiliitis / ankylosierende Spondylitis",
    "Uveitis",
    "Episkleritis",
    "Erythema nodosum",
    "Pyoderma gangraenosum",
    "Primär sklerosierende Cholangitis (PSC)",
    "Aphthöse Stomatitis",
)


@dataclass(frozen=True)
class ManuelleCEDStammdaten:
    """Vom Benutzer ausdrücklich bestätigte, optional ausgefüllte Stammdaten."""

    erstdiagnose: date | None
    befallsmuster: str | None
    eim_auswahl: tuple[str, ...] | None = None
    eim_weitere: str | None = None


@dataclass(frozen=True)
class DiagnosenEingabe:
    """Manuell geprüfte Diagnosen mit einem getrennten ergänzenden Hinweisfeld."""

    hauptdiagnose: str
    nebendiagnosen: tuple[str, ...]

    # Hinweise sind bewusst kein weiterer Diagnoseeintrag. Sie können ergänzende
    # Zusammenhänge dokumentieren, ohne die strukturierte Diagnosenliste zu verändern.
    hinweise: str | None


@dataclass(frozen=True)
class TherapienEingabe:
    """Manuell geprüfte medikamentöse und chirurgische Therapietexte."""

    therapie_medikamentoes: str | None
    therapie_chirurgisch: str | None


def speichere_diagnosen(
    sitzung: Session,
    patient_id: int,
    eingabe: DiagnosenEingabe,
) -> None:
    """Versioniert Diagnosen und optionale Diagnosehinweise in einer Transaktion."""
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
        hinweise = (eingabe.hinweise or "").strip()
        if hinweise:
            sitzung.add(
                PatientCEDAttribute(
                    patient_id=patient_id,
                    attribute_type=DIAGNOSE_HINWEISE,
                    text_value=hinweise,
                    source_type="MANUELL",
                    confirmed_by_user=True,
                )
            )
        sitzung.add(
            AuditLog(
                action="DIAGNOSEN_MANUELL_BESTAETIGT",
                entity_type="Patient",
                entity_id=patient_id,
                details=f"1 Hauptdiagnose und {len(nebendiagnosen)} Nebendiagnose(n) versioniert",
            )
        )
    sitzung.commit()


def speichere_therapien(
    sitzung: Session,
    patient_id: int,
    eingabe: TherapienEingabe,
) -> int:
    """Versioniert ausschließlich ausgefüllte Therapiefelder und gibt ihre Anzahl zurück."""
    if sitzung.get(Patient, patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    therapien = tuple(
        (attributtyp, (textwert or "").strip())
        for attributtyp, textwert in (
            (THERAPIE_MEDIKAMENTOES, eingabe.therapie_medikamentoes),
            (THERAPIE_CHIRURGISCH, eingabe.therapie_chirurgisch),
        )
        if (textwert or "").strip()
    )
    if not therapien:
        raise ValueError("Bitte mindestens ein Therapiefeld ausfüllen.")
    with sitzung.begin_nested():
        for attributtyp, textwert in therapien:
            sitzung.add(
                PatientCEDAttribute(
                    patient_id=patient_id,
                    attribute_type=attributtyp,
                    text_value=textwert,
                    source_type="MANUELL",
                    confirmed_by_user=True,
                )
            )
        sitzung.add(
            AuditLog(
                action="THERAPIEN_MANUELL_BESTAETIGT",
                entity_type="Patient",
                entity_id=patient_id,
                details=f"{len(therapien)} Therapiefeld(er) versioniert",
            )
        )
    sitzung.commit()
    return len(therapien)


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
    eim_weitere = (stammdaten.eim_weitere or "").strip()
    if (
        stammdaten.erstdiagnose is None
        and not befallsmuster
        and stammdaten.eim_auswahl is None
        and stammdaten.eim_weitere is None
    ):
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
    if stammdaten.eim_auswahl is not None:
        unbekannte_eim = set(stammdaten.eim_auswahl) - set(EIM_OPTIONEN)
        if unbekannte_eim:
            raise ValueError("Die EIM-Auswahl enthält einen unbekannten Katalogeintrag.")
        # Auch eine leere Auswahl wird als neue Version gespeichert. So kann ein
        # zuvor gesetztes Kreuz bewusst und nachvollziehbar entfernt werden.
        neue_eintraege.append(
            PatientCEDAttribute(
                patient_id=patient_id,
                attribute_type=EIM_AUSWAHL,
                text_value="\n".join(stammdaten.eim_auswahl),
                source_type="MANUELL",
                confirmed_by_user=True,
            )
        )
    if stammdaten.eim_weitere is not None:
        neue_eintraege.append(
            PatientCEDAttribute(
                patient_id=patient_id,
                attribute_type=EIM_WEITERE,
                text_value=eim_weitere,
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
