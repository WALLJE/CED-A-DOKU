"""Atomare Speicherung ausdrücklich freigegebener CED-Fragebogendaten.

Dieses Modul kennt keine Oberfläche und trifft keine medizinischen Entscheidungen.
Es speichert ausschließlich die Werte, die die Benutzerin oder der Benutzer in der
Prüftabelle zur Übernahme markiert hat. Neue Kategorien werden nur dann angelegt,
wenn die betreffende Tabellenzeile ebenfalls ausdrücklich ausgewählt wurde.
"""

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


@dataclass(frozen=True)
class FreigegebenerBefund:
    """Ein nach der Tabellenprüfung bewusst zur Speicherung gewählter Wert."""

    kategorie: str
    anzeigewert: str
    numerischer_wert: float | None
    einheit: str | None
    quelltext: str
    qualitaet: ConfidenceStatus


@dataclass(frozen=True)
class CEDSpeicherauftrag:
    """Alle Daten, die gemeinsam in genau einer Transaktion gespeichert werden."""

    patient_id: int
    befunddatum: date
    original_name: str
    rohe_ki_antwort: str
    kis_vorschlag: str
    provider: str
    modell: str
    befunde: tuple[FreigegebenerBefund, ...]


def finde_befundduplikate(
    sitzung: Session,
    patient_id: int,
    befunddatum: date,
    befunde: tuple[FreigegebenerBefund, ...],
) -> tuple[str, ...]:
    """Nennt Kategorien mit gleichem Datum und identischem bestätigtem Wert.

    Der Vergleich erfolgt nach getrimmtem Textwert und – sofern vorhanden – zusätzlich
    nach numerischem Wert. Die Funktion speichert nichts; die Oberfläche muss vor
    einer bewussten Doppelübernahme ausdrücklich nachfragen.
    """
    doppelte: list[str] = []
    for befund in befunde:
        kandidaten = sitzung.scalars(
            select(Finding)
            .join(FindingCategory, Finding.category_id == FindingCategory.id)
            .where(
                Finding.patient_id == patient_id,
                Finding.finding_date == befunddatum,
                Finding.confirmed_by_user.is_(True),
                FindingCategory.name == befund.kategorie.strip(),
            )
        )
        for vorhanden in kandidaten:
            text_gleich = (vorhanden.text_value or "").strip() == befund.anzeigewert.strip()
            numerisch_gleich = (
                befund.numerischer_wert is None
                or vorhanden.numeric_value == befund.numerischer_wert
            )
            if text_gleich and numerisch_gleich:
                doppelte.append(befund.kategorie.strip())
                break
    return tuple(dict.fromkeys(doppelte))


def _ermittle_oder_erstelle_dokumenttyp(sitzung: Session) -> DocumentType:
    """Legt den festen CED-Dokumenttyp idempotent, aber keinen Ersatztyp an."""
    name = "CED-Patientenfragebogen"
    dokumenttyp = sitzung.scalar(select(DocumentType).where(DocumentType.name == name))
    if dokumenttyp is None:
        dokumenttyp = DocumentType(name=name, prompt_text=None)
        sitzung.add(dokumenttyp)
        sitzung.flush()
    return dokumenttyp


def _ermittle_oder_erstelle_kategorie(
    sitzung: Session, name: str, einheit: str | None
) -> FindingCategory:
    """Erstellt nur eine vom Prüfauftrag tatsächlich übernommene Kategorie."""
    kategorie = sitzung.scalar(
        select(FindingCategory).where(FindingCategory.name == name)
    )
    if kategorie is None:
        kategorie = FindingCategory(
            name=name,
            group_name="CED-Fragebogen",
            typical_unit=einheit,
        )
        sitzung.add(kategorie)
        sitzung.flush()
    return kategorie


def speichere_ced_pruefung(sitzung: Session, auftrag: CEDSpeicherauftrag) -> int:
    """Speichert Dokument und Befunde atomar und gibt die Dokument-ID zurück.

    Der Aufrufer ist für die Anzeige von Fehlern zuständig. Es gibt bewusst keinen
    Fallback und keine Teilübernahme. Zum Debugging dürfen lediglich Exception-Typ,
    Tabellenname und Transaktionsstatus protokolliert werden; keine Patientenwerte,
    Quelltexte oder KI-Antworten.
    """
    if not auftrag.befunde:
        raise ValueError("Es wurde kein Befund zur Übernahme ausgewählt.")
    if not auftrag.original_name.strip():
        raise ValueError("Der Dokumentname fehlt.")
    if sitzung.get(Patient, auftrag.patient_id) is None:
        raise ValueError("Der bestätigte Patient ist nicht mehr vorhanden.")
    for befund in auftrag.befunde:
        if not befund.kategorie.strip() or not befund.anzeigewert.strip():
            raise ValueError("Kategorie und Wert müssen für jede übernommene Zeile gefüllt sein.")

    # ``begin_nested`` ist auch dann sicher nutzbar, wenn SQLAlchemy durch die
    # vorherige Patientenprüfung bereits eine Lesetransaktion begonnen hat. Ein
    # Fehler rollt sämtliche hier erzeugten Datensätze gemeinsam zurück.
    with sitzung.begin_nested():
        dokumenttyp = _ermittle_oder_erstelle_dokumenttyp(sitzung)
        dokument = Document(
            patient_id=auftrag.patient_id,
            document_type_id=dokumenttyp.id,
            original_name=auftrag.original_name,
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
            kategorie = _ermittle_oder_erstelle_kategorie(
                sitzung, freigegeben.kategorie.strip(), freigegeben.einheit
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
                action="CED_BEFUND_BESTAETIGT",
                entity_type="Document",
                entity_id=dokument.id,
                details=f"{len(auftrag.befunde)} bestätigte Befundfelder gespeichert",
            )
        )
        sitzung.flush()
        dokument_id = dokument.id
    sitzung.commit()
    return dokument_id
