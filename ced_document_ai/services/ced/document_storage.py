"""Bestätigte patientenbezogene Archivierung allgemeiner medizinischer Dokumente."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ced_document_ai.database.models import AIResult, AuditLog, Document, DocumentType, Patient


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
            dokumenttyp = DocumentType(name=auftrag.dokumenttyp, prompt_text=None)
            sitzung.add(dokumenttyp)
            sitzung.flush()
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
                kis_summary_detailed=None,
                model=auftrag.modell,
                provider=auftrag.provider,
            )
        )
        sitzung.add(
            AuditLog(
                action="DOKUMENT_PATIENT_ZUGEORDNET",
                entity_type="Document",
                entity_id=dokument.id,
                details="Allgemeines Dokument mit bestätigtem Patient und Datum archiviert",
            )
        )
    sitzung.commit()
    return dokument.id
