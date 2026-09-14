"""Lesemodell für die geschützte patientenbezogene CED-Übersicht.

Die Oberfläche erhält bewusst ein kompaktes, unveränderliches Ergebnisobjekt und
führt keine eigenen SQL-Abfragen aus. Angezeigt werden ausschließlich bestätigte
Befunde. Noch nicht strukturierte Stammdaten wie Befallsmuster oder Therapieverlauf
bleiben klar als leer gekennzeichnet, statt aus Freitext geraten zu werden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ced_document_ai.database.models import Diagnosis, Finding, FindingCategory, Patient


@dataclass(frozen=True)
class DiagnoseUebersicht:
    """Eine bereits gespeicherte Diagnose mit ihrem aktuellen Datenbankstatus."""

    bezeichnung: str
    status: str
    erstdiagnose: date | None


@dataclass(frozen=True)
class BefundUebersicht:
    """Ein bestätigter Wert des zuletzt gespeicherten CED-Befunddatums."""

    kategorie: str
    wert: str
    einheit: str | None


@dataclass(frozen=True)
class PatientenUebersicht:
    """Alle im ersten Dashboard-Schritt tatsächlich verfügbaren Patientendaten."""

    patient_id: int
    externe_id: str | None
    name: str
    geburtsdatum: date | None
    alter: int | None
    diagnosen: tuple[DiagnoseUebersicht, ...]
    letztes_befunddatum: date | None
    letzte_befunde: tuple[BefundUebersicht, ...]


def berechne_alter(geburtsdatum: date | None, *, am: date | None = None) -> int | None:
    """Berechnet das vollendete Alter dynamisch und speichert es nicht dauerhaft."""
    if geburtsdatum is None:
        return None
    stichtag = am or date.today()
    if geburtsdatum > stichtag:
        # Ein zukünftiges Geburtsdatum ist ein Datenfehler. Es wird kein negatives
        # oder vermeintlich korrigiertes Alter als Ersatz angezeigt.
        return None
    hatte_geburtstag = (stichtag.month, stichtag.day) >= (
        geburtsdatum.month,
        geburtsdatum.day,
    )
    return stichtag.year - geburtsdatum.year - (0 if hatte_geburtstag else 1)


def lade_patientenuebersicht(
    sitzung: Session,
    patient_id: int,
    *,
    stichtag: date | None = None,
) -> PatientenUebersicht:
    """Lädt bestätigte Daten eines Patienten oder meldet eine fehlende Zuordnung.

    Debugging-Hinweis: Bei Problemen nur Patient-ID, Tabellenname und Trefferanzahl
    untersuchen. Namen, Diagnosen und medizinische Werte nicht in Logs ausgeben.
    """
    patient = sitzung.get(Patient, patient_id)
    if patient is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")

    diagnosen = tuple(
        DiagnoseUebersicht(
            bezeichnung=diagnose.diagnosis_name,
            status=diagnose.status,
            erstdiagnose=diagnose.first_diagnosis_date,
        )
        for diagnose in sitzung.scalars(
            select(Diagnosis)
            .where(Diagnosis.patient_id == patient_id)
            .order_by(Diagnosis.first_diagnosis_date, Diagnosis.diagnosis_name)
        )
    )

    befundzeilen = list(
        sitzung.execute(
            select(Finding, FindingCategory)
            .join(FindingCategory, Finding.category_id == FindingCategory.id)
            .where(
                Finding.patient_id == patient_id,
                Finding.confirmed_by_user.is_(True),
            )
            .order_by(Finding.finding_date.desc(), FindingCategory.name)
        )
    )
    letztes_datum = befundzeilen[0][0].finding_date if befundzeilen else None
    letzte_befunde = tuple(
        BefundUebersicht(
            kategorie=kategorie.name,
            wert=befund.text_value
            or (str(befund.numeric_value) if befund.numeric_value is not None else ""),
            einheit=befund.unit,
        )
        for befund, kategorie in befundzeilen
        if befund.finding_date == letztes_datum
    )
    return PatientenUebersicht(
        patient_id=patient.id,
        externe_id=patient.external_id,
        name=patient.name,
        geburtsdatum=patient.birth_date,
        alter=berechne_alter(patient.birth_date, am=stichtag),
        diagnosen=diagnosen,
        letztes_befunddatum=letztes_datum,
        letzte_befunde=letzte_befunde,
    )
