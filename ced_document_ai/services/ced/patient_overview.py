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

from ced_document_ai.database.models import (
    AIResult,
    Diagnosis,
    Document,
    DocumentType,
    Finding,
    FindingCategory,
    Patient,
    PatientCEDAttribute,
)
from ced_document_ai.services.ced.document_categories import ermittle_dokumentfachgruppe
from ced_document_ai.services.ced.patient_profile import (
    BEFALLSMUSTER,
    CED_ERKRANKUNGSTYP,
    CU_AUSDEHNUNG,
    DIAGNOSE_DETAILS,
    EIM_AUSWAHL,
    EIM_WEITERE,
    MC_LOKALISATION,
    MC_OBERER_GI,
    MC_PERIANAL,
    MC_VERHALTEN,
    SYMPTOME_SEIT,
    ERSTDIAGNOSE,
    THERAPIE_CHIRURGISCH,
    THERAPIE_MEDIKAMENTOES,
)


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
    erstdiagnose: date | None
    befallsmuster: str | None
    therapie_medikamentoes: str | None
    therapie_chirurgisch: str | None
    diagnose_details: str | None
    symptome_seit: date | None
    erkrankungstyp: str | None
    mc_lokalisation: str | None
    mc_oberer_gi: bool
    mc_verhalten: str | None
    mc_perianal: bool
    cu_ausdehnung: str | None
    eim_auswahl: tuple[str, ...]
    eim_weitere: str | None
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


@dataclass(frozen=True)
class ArchiviertesDokument:
    """Ein bestätigtes Dokument, das auch ohne einzelne Findings sichtbar bleibt."""

    dokument_id: int
    dokumentdatum: date | None
    dokumenttyp: str
    fachgruppe: str
    dateiname: str
    kurzfassung: str


def lade_dokumentenarchiv(
    sitzung: Session,
    patient_id: int,
    *,
    fachgruppen: tuple[str, ...] | None = None,
) -> tuple[ArchiviertesDokument, ...]:
    """Lädt bestätigte Dokumente mit ihrer gespeicherten KI-Kurzfassung.

    Das Archiv zeigt auch Dokumente ohne strukturierten Fachparser. Dadurch bleibt
    etwa ein zugeordneter Virologiebefund unter Labor auffindbar, obwohl noch keine
    einzelnen Virusparameter als bestätigte Findings vorliegen. Leere Kurzfassungen
    werden sichtbar leer gelassen und nicht aus der Rohantwort ersetzt.
    """

    if sitzung.get(Patient, patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    zeilen = sitzung.execute(
        select(Document, DocumentType, AIResult)
        .join(DocumentType, Document.document_type_id == DocumentType.id)
        .outerjoin(AIResult, AIResult.document_id == Document.id)
        .where(Document.patient_id == patient_id, Document.confirmed.is_(True))
        .order_by(Document.document_date.desc(), Document.id.desc())
    )
    dokumente: list[ArchiviertesDokument] = []
    erlaubte_gruppen = set(fachgruppen) if fachgruppen is not None else None
    for dokument, dokumenttyp, ki_ergebnis in zeilen:
        fachgruppe = ermittle_dokumentfachgruppe(dokumenttyp.name)
        if erlaubte_gruppen is not None and fachgruppe not in erlaubte_gruppen:
            continue
        dokumente.append(
            ArchiviertesDokument(
                dokument_id=dokument.id,
                dokumentdatum=dokument.document_date,
                dokumenttyp=dokumenttyp.name,
                fachgruppe=fachgruppe,
                dateiname=dokument.original_name,
                kurzfassung=(ki_ergebnis.kis_summary_compact or "")
                if ki_ergebnis is not None
                else "",
            )
        )
    return tuple(dokumente)


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
    # Die Stammdaten werden versioniert gespeichert. Für die kompakte Übersicht ist
    # jeweils nur die jüngste ausdrücklich bestätigte Version relevant. Die ID dient
    # bei identischen Zeitstempeln als stabile Reihenfolge.
    attribute = {
        attributtyp: sitzung.scalar(
            select(PatientCEDAttribute)
            .where(
                PatientCEDAttribute.patient_id == patient_id,
                PatientCEDAttribute.attribute_type == attributtyp,
                PatientCEDAttribute.confirmed_by_user.is_(True),
            )
            .order_by(
                PatientCEDAttribute.created_at.desc(), PatientCEDAttribute.id.desc()
            )
            .limit(1)
        )
        for attributtyp in (
            ERSTDIAGNOSE,
            BEFALLSMUSTER,
            THERAPIE_MEDIKAMENTOES,
            THERAPIE_CHIRURGISCH,
            DIAGNOSE_DETAILS,
            SYMPTOME_SEIT,
            CED_ERKRANKUNGSTYP,
            MC_LOKALISATION,
            MC_OBERER_GI,
            MC_VERHALTEN,
            MC_PERIANAL,
            CU_AUSDEHNUNG,
            EIM_AUSWAHL,
            EIM_WEITERE,
        )
    }
    return PatientenUebersicht(
        patient_id=patient.id,
        externe_id=patient.external_id,
        name=patient.display_name,
        geburtsdatum=patient.birth_date,
        alter=berechne_alter(patient.birth_date, am=stichtag),
        erstdiagnose=(
            attribute[ERSTDIAGNOSE].date_value if attribute[ERSTDIAGNOSE] else None
        ),
        befallsmuster=(
            attribute[BEFALLSMUSTER].text_value if attribute[BEFALLSMUSTER] else None
        ),
        therapie_medikamentoes=(
            attribute[THERAPIE_MEDIKAMENTOES].text_value
            if attribute[THERAPIE_MEDIKAMENTOES]
            else None
        ),
        therapie_chirurgisch=(
            attribute[THERAPIE_CHIRURGISCH].text_value
            if attribute[THERAPIE_CHIRURGISCH]
            else None
        ),
        diagnose_details=(
            attribute[DIAGNOSE_DETAILS].text_value
            if attribute[DIAGNOSE_DETAILS]
            else None
        ),
        symptome_seit=(
            attribute[SYMPTOME_SEIT].date_value if attribute[SYMPTOME_SEIT] else None
        ),
        erkrankungstyp=(
            attribute[CED_ERKRANKUNGSTYP].text_value
            if attribute[CED_ERKRANKUNGSTYP]
            else None
        ),
        mc_lokalisation=(
            attribute[MC_LOKALISATION].text_value if attribute[MC_LOKALISATION] else None
        ),
        mc_oberer_gi=bool(
            attribute[MC_OBERER_GI] and attribute[MC_OBERER_GI].text_value == "JA"
        ),
        mc_verhalten=(
            attribute[MC_VERHALTEN].text_value if attribute[MC_VERHALTEN] else None
        ),
        mc_perianal=bool(
            attribute[MC_PERIANAL] and attribute[MC_PERIANAL].text_value == "JA"
        ),
        cu_ausdehnung=(
            attribute[CU_AUSDEHNUNG].text_value if attribute[CU_AUSDEHNUNG] else None
        ),
        eim_auswahl=(
            tuple(
                zeile
                for zeile in (attribute[EIM_AUSWAHL].text_value or "").splitlines()
                if zeile
            )
            if attribute[EIM_AUSWAHL]
            else ()
        ),
        eim_weitere=(
            attribute[EIM_WEITERE].text_value if attribute[EIM_WEITERE] else None
        ),
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


def lade_fachverlauf(
    sitzung: Session,
    patient_id: int,
    gruppen: tuple[str, ...],
) -> KlinischerVerlauf:
    """Lädt bestätigte Werte ausgewählter Fachgruppen als gemeinsame Zeitmatrix.

    Die aufrufende Ansicht benennt ihre erlaubten Gruppen ausdrücklich. Dadurch
    geraten beispielsweise Laborwerte nicht versehentlich in eine Bildgebungsansicht.
    Debugging-Hinweis: Bei leeren Ansichten Gruppenname und Trefferanzahl prüfen,
    niemals medizinische Werte in ein Log schreiben.
    """
    if not gruppen:
        raise ValueError("Mindestens eine Fachgruppe muss angegeben werden.")
    if sitzung.get(Patient, patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    eintraege = list(
        sitzung.execute(
            select(Finding, FindingCategory)
            .join(FindingCategory, Finding.category_id == FindingCategory.id)
            .where(
                Finding.patient_id == patient_id,
                Finding.confirmed_by_user.is_(True),
                FindingCategory.group_name.in_(gruppen),
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
    return KlinischerVerlauf(
        daten=daten,
        zeilen=tuple(
            Verlaufszeile(
                kategorie=kategorie,
                werte=tuple(
                    (datum, " | ".join(werte))
                    for datum, werte in sorted(werte_nach_datum.items())
                ),
            )
            for kategorie, werte_nach_datum in sorted(sammlung.items())
        ),
    )
