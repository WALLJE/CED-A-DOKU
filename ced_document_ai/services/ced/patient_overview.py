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


@dataclass(frozen=True)
class Verlaufszeile:
    """Ein klinischer Parameter mit seinen bestätigten Werten je Befunddatum."""

    kategorie: str
    werte: tuple[tuple[date, str], ...]


@dataclass(frozen=True)
class KlinischerVerlauf:
    """Dynamische Pivot-Grundlage ohne fest verdrahtete Datums- oder Feldspalten."""

    daten: tuple[date, ...]
    zeilen: tuple[Verlaufszeile, ...]


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
                FindingCategory.group_name == "CED-Fragebogen",
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


def lade_klinischen_verlauf(sitzung: Session, patient_id: int) -> KlinischerVerlauf:
    """Lädt alle bestätigten CED-Fragebogenparameter als kumulative Zeitansicht.

    Mehrere Werte derselben Kategorie am selben Tag werden nicht überschrieben,
    sondern sichtbar mit `` | `` verbunden. So bleibt ein möglicher Datenkonflikt
    prüfbar. Labor- oder Bildgebungswerte gelangen nur dann in diese Ansicht, wenn
    ihre Kategorie ausdrücklich zur Gruppe ``CED-Fragebogen`` gehört.
    """
    if sitzung.get(Patient, patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    eintraege = list(
        sitzung.execute(
            select(Finding, FindingCategory)
            .join(FindingCategory, Finding.category_id == FindingCategory.id)
            .where(
                Finding.patient_id == patient_id,
                Finding.confirmed_by_user.is_(True),
                FindingCategory.group_name == "CED-Fragebogen",
            )
            .order_by(FindingCategory.name, Finding.finding_date)
        )
    )
    daten = tuple(sorted({befund.finding_date for befund, _ in eintraege}))
    sammlung: dict[str, dict[date, list[str]]] = {}
    for befund, kategorie in eintraege:
        wert = befund.text_value or (
            str(befund.numeric_value) if befund.numeric_value is not None else ""
        )
        if befund.unit and befund.unit not in wert:
            wert = f"{wert} {befund.unit}".strip()
        sammlung.setdefault(kategorie.name, {}).setdefault(
            befund.finding_date, []
        ).append(wert)
    zeilen = tuple(
        Verlaufszeile(
            kategorie=kategorie,
            werte=tuple(
                (datum, " | ".join(werte))
                for datum, werte in sorted(werte_nach_datum.items())
            ),
        )
        for kategorie, werte_nach_datum in sorted(sammlung.items())
    )
    return KlinischerVerlauf(daten=daten, zeilen=zeilen)
