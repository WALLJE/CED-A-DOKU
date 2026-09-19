"""Atomare Speicherung manuell bestätigter Labor- und Erregerbefunde."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ced_document_ai.database.models import (
    AIResult,
    AuditLog,
    ConfidenceStatus,
    Document,
    DocumentType,
    Finding,
    FindingCategory,
    Patient,
)
from ced_document_ai.services.ced.laboratory_parser import LABORDOKUMENTTYPEN


@dataclass(frozen=True)
class FreigegebenerLaborwert:
    """Ein in der Prüftabelle ausdrücklich ausgewählter Laborwert."""

    kategorie: str
    anzeigewert: str
    numerischer_wert: float | None
    einheit: str | None
    referenzbereich: str | None
    quelltext: str
    fachgruppe: str
    qualitaet: ConfidenceStatus


@dataclass(frozen=True)
class LaborSpeicherauftrag:
    """Vollständiger Auftrag für genau eine atomare Laborübernahme."""

    patient_id: int
    dokumenttyp: str
    befunddatum: date
    original_name: str
    rohe_ki_antwort: str
    kis_vorschlag: str
    provider: str
    modell: str
    befunde: tuple[FreigegebenerLaborwert, ...]


def speichere_laborpruefung(sitzung: Session, auftrag: LaborSpeicherauftrag) -> int:
    """Speichert Dokument, KI-Ergebnis und bestätigte Einzelwerte gemeinsam.

    Neue Kategorien entstehen ausschließlich aus Zeilen, die die Benutzerin oder der
    Benutzer in der Prüftabelle aktiviert hat. Der Referenzbereich bleibt in der
    unveränderten Quellzeile und wird noch nicht in ein separates Datenbankfeld
    übertragen; dadurch wird kein vorhandenes Schema stillschweigend erweitert.
    """

    if auftrag.dokumenttyp not in LABORDOKUMENTTYPEN:
        raise ValueError("Der Dokumenttyp gehört nicht zum Labor-Prüfpfad.")
    if sitzung.get(Patient, auftrag.patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    if not auftrag.befunde:
        raise ValueError("Es wurde kein Laborwert zur Übernahme ausgewählt.")
    if not auftrag.original_name.strip():
        raise ValueError("Der Dokumentname fehlt.")
    for befund in auftrag.befunde:
        if not befund.kategorie.strip() or not befund.anzeigewert.strip():
            raise ValueError("Kategorie und Wert sind für jeden Laborbefund verpflichtend.")
        if befund.fachgruppe not in {"Labor", "Calprotectin"}:
            raise ValueError("Die Befundgruppe ist für den Laborpfad nicht zugelassen.")

    with sitzung.begin_nested():
        dokumenttyp = sitzung.scalar(
            select(DocumentType).where(DocumentType.name == auftrag.dokumenttyp)
        )
        if dokumenttyp is None:
            dokumenttyp = DocumentType(name=auftrag.dokumenttyp, prompt_text=None)
            sitzung.add(dokumenttyp)
            sitzung.flush()
        dokument = Document(
            patient_id=auftrag.patient_id,
            document_type_id=dokumenttyp.id,
            original_name=auftrag.original_name,
            document_date=auftrag.befunddatum,
            confirmed=False,
        )
        sitzung.add(dokument)
        sitzung.flush()
        sitzung.add(
            AIResult(
                document_id=dokument.id,
                raw_ai_response=auftrag.rohe_ki_antwort,
                kis_summary_compact=auftrag.kis_vorschlag,
                kis_summary_detailed=None,
                model=auftrag.modell,
                provider=auftrag.provider,
            )
        )
        for freigegeben in auftrag.befunde:
            kategorie = sitzung.scalar(
                select(FindingCategory).where(
                    FindingCategory.name == freigegeben.kategorie.strip()
                )
            )
            if kategorie is None:
                kategorie = FindingCategory(
                    name=freigegeben.kategorie.strip(),
                    group_name=freigegeben.fachgruppe,
                    typical_unit=(freigegeben.einheit or "").strip() or None,
                )
                sitzung.add(kategorie)
                sitzung.flush()
            elif kategorie.group_name != freigegeben.fachgruppe:
                raise ValueError(
                    "Die bestätigte Kategorie gehört bereits zu einer anderen Befundgruppe."
                )
            sitzung.add(
                Finding(
                    patient_id=auftrag.patient_id,
                    document_id=dokument.id,
                    category_id=kategorie.id,
                    finding_date=auftrag.befunddatum,
                    numeric_value=freigegeben.numerischer_wert,
                    text_value=freigegeben.anzeigewert.strip(),
                    unit=(freigegeben.einheit or "").strip() or None,
                    source_text=freigegeben.quelltext,
                    page=None,
                    confidence_status=freigegeben.qualitaet,
                    confirmed_by_user=True,
                )
            )
        dokument.confirmed = True
        sitzung.add(
            AuditLog(
                action="LABORBEFUND_BESTAETIGT",
                entity_type="Document",
                entity_id=dokument.id,
                details=f"{len(auftrag.befunde)} bestätigte Laborwerte gespeichert",
            )
        )
        sitzung.flush()
        dokument_id = dokument.id
    sitzung.commit()
    return dokument_id
