"""Bestätigte patientenbezogene Archivierung allgemeiner medizinischer Dokumente."""

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
from ced_document_ai.services.ced.document_categories import DOKUMENTKLASSEN


@dataclass(frozen=True)
class VorhandeneDokumentzuordnung:
    """Bereits gespeicherte exakte KI-Rohantwort mit ihrer Patientenzuordnung."""

    dokument_id: int
    patient_id: int | None


def finde_vorhandene_dokumentzuordnungen(
    sitzung: Session, rohe_ki_antwort: str
) -> tuple[VorhandeneDokumentzuordnung, ...]:
    """Findet nur bytegenau gleiche archivierte Antworten, ohne Ähnlichkeit zu raten."""

    if not rohe_ki_antwort.strip():
        return ()
    return tuple(
        VorhandeneDokumentzuordnung(dokument_id=dokument.id, patient_id=dokument.patient_id)
        for dokument in sitzung.scalars(
            select(Document)
            .join(AIResult, AIResult.document_id == Document.id)
            .where(AIResult.raw_ai_response == rohe_ki_antwort)
            .order_by(Document.id)
        )
    )


@dataclass(frozen=True)
class DokumentSpeicherauftrag:
    """Vollständiger, zuvor in der Oberfläche bestätigter Dokumentauftrag."""

    patient_id: int
    dokumenttyp: str
    dokumentdatum: date
    original_name: str
    rohe_ki_antwort: str
    kis_vorschlag: str
    provider: str
    modell: str
    befunde: tuple["FreigegebenerDokumentbefund", ...] = ()
    kis_vorschlag_ausfuehrlich: str = ""


@dataclass(frozen=True)
class FreigegebenerDokumentbefund:
    """Ein bewusst ausgewählter strukturierter Abschnitt eines Dokuments."""

    kategorie: str
    inhalt: str
    quelltext: str
    fachgruppe: str


def speichere_allgemeines_dokument(
    sitzung: Session, auftrag: DokumentSpeicherauftrag
) -> int:
    """Archiviert Dokument und KI-Rohantwort atomar, aber erzeugt keine Befundwerte.

    Die Funktion ist bewusst kein universeller Befundparser. Labor- oder andere
    Fachwerte werden erst durch einen eigenen Prüfschritt als strukturierte Findings
    gespeichert. Zum Debugging nur Tabellenname und Exception-Typ protokollieren,
    niemals Dokument- oder Patientendaten.
    """
    if sitzung.get(Patient, auftrag.patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    if not auftrag.dokumenttyp.strip() or not auftrag.original_name.strip():
        raise ValueError("Dokumenttyp und Dokumentname sind verpflichtend.")
    with sitzung.begin_nested():
        dokumenttyp = sitzung.scalar(
            select(DocumentType).where(DocumentType.name == auftrag.dokumenttyp)
        )
        if dokumenttyp is None:
            standard = next(
                (eintrag for eintrag in DOKUMENTKLASSEN if eintrag.dokumenttyp == auftrag.dokumenttyp),
                None,
            )
            if standard is not None:
                dokumenttyp = DocumentType(
                    name=standard.dokumenttyp,
                    display_name=standard.dokumenttyp,
                    group_name=standard.fachgruppe,
                    active=True,
                    user_created=False,
                )
                sitzung.add(dokumenttyp)
                sitzung.flush()
        if dokumenttyp is None or not dokumenttyp.active:
            raise ValueError(
                "Die Dokumentklasse ist nicht bestätigt oder nicht aktiv. "
                "Bitte die Klasse vor der Archivierung im Klassifikationsdialog bestätigen."
            )
        dokument = Document(
            patient_id=auftrag.patient_id,
            document_type_id=dokumenttyp.id,
            original_name=auftrag.original_name,
            document_date=auftrag.dokumentdatum,
            confirmed=True,
        )
        sitzung.add(dokument)
        sitzung.flush()
        sitzung.add(
            AIResult(
                document_id=dokument.id,
                raw_ai_response=auftrag.rohe_ki_antwort,
                kis_summary_compact=auftrag.kis_vorschlag,
                kis_summary_detailed=auftrag.kis_vorschlag_ausfuehrlich or None,
                model=auftrag.modell,
                provider=auftrag.provider,
            )
        )
        for freigegeben in auftrag.befunde:
            if not freigegeben.kategorie.strip() or not freigegeben.inhalt.strip():
                raise ValueError("Kategorie und Inhalt sind für jeden Abschnitt verpflichtend.")
            kategorie = sitzung.scalar(
                select(FindingCategory).where(
                    FindingCategory.name == freigegeben.kategorie.strip()
                )
            )
            if kategorie is None:
                kategorie = FindingCategory(
                    name=freigegeben.kategorie.strip(),
                    group_name=freigegeben.fachgruppe,
                    typical_unit=None,
                )
                sitzung.add(kategorie)
                sitzung.flush()
            elif kategorie.group_name != freigegeben.fachgruppe:
                raise ValueError(
                    "Die bestätigte Dokumentkategorie gehört bereits zu einer anderen Befundgruppe."
                )
            sitzung.add(
                Finding(
                    patient_id=auftrag.patient_id,
                    document_id=dokument.id,
                    category_id=kategorie.id,
                    finding_date=auftrag.dokumentdatum,
                    numeric_value=None,
                    text_value=freigegeben.inhalt.strip(),
                    unit=None,
                    source_text=freigegeben.quelltext,
                    page=None,
                    confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                    confirmed_by_user=True,
                )
            )
        sitzung.add(
            AuditLog(
                action="DOKUMENT_PATIENT_ZUGEORDNET",
                entity_type="Document",
                entity_id=dokument.id,
                details=(
                    "Allgemeines Dokument mit bestätigtem Patient und Datum archiviert"
                    + (
                        f"; {len(auftrag.befunde)} bestätigte Abschnitte gespeichert"
                        if auftrag.befunde
                        else ""
                    )
                ),
            )
        )
    sitzung.commit()
    return dokument.id
