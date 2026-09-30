"""Persistenter, kontrollierter Katalog medizinischer Dokumentklassen.

Das Modul trennt eine Dokumentklasse strikt von einzelnen Befundkategorien. Eine
Klasse darf archiviert werden, auch wenn noch kein Fachparser existiert. Lernsignale
werden ausschließlich nach einer ausdrücklichen Benutzerbestätigung ergänzt; die
KI darf weder Klassen noch Beispiele selbständig dauerhaft anlegen.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from ced_document_ai.database.models import AuditLog, DocumentType, DocumentTypeExample
from ced_document_ai.services.ced.document_categories import DOKUMENTKLASSEN


ERLAUBTE_FACHGRUPPEN = (
    "CED-Fragebogen", "Labor", "Calprotectin", "Endoskopie", "Sonografie",
    "MRT", "CT", "Röntgen", "Bildgebung", "Pathologie",
    "Funktionsdiagnostik", "Arztbriefe", "Medikation", "Weitere Befunde",
)


@dataclass(frozen=True)
class Dokumentklassendaten:
    """Unveränderliche, für UI und KI freigegebene Katalogansicht."""

    name: str
    anzeigename: str
    fachgruppe: str
    beschreibung: str
    merkmale: str
    nutzererstellt: bool
    beispiele: tuple[str, ...] = ()


def stelle_standardklassen_sicher(sitzung: Session) -> None:
    """Legt fehlende Standardklassen an, ohne bestehende Definitionen zu ändern."""

    vorhandene = set(sitzung.scalars(select(DocumentType.name)))
    for standard in DOKUMENTKLASSEN:
        if standard.dokumenttyp not in vorhandene:
            sitzung.add(DocumentType(
                name=standard.dokumenttyp,
                display_name=standard.dokumenttyp,
                group_name=standard.fachgruppe,
                active=True,
                user_created=False,
                prompt_text=None,
                description=None,
                classification_hints=None,
            ))
    sitzung.commit()


def liste_dokumentklassen(sitzung: Session, *, nur_aktive: bool = True) -> tuple[Dokumentklassendaten, ...]:
    """Liest den persistenten Katalog samt bestätigten Lernbeispielen."""

    # Erst der tatsächliche Katalogzugriff materialisiert die Standardklassen. Das
    # vermeidet Seiteneffekte beim reinen Datenbankaufbau und hält Tests/Importe, die
    # eigene Dokumenttypen anlegen, unabhängig von der Anwendungsinitialisierung.
    stelle_standardklassen_sicher(sitzung)
    abfrage = select(DocumentType).order_by(DocumentType.name)
    if nur_aktive:
        abfrage = abfrage.where(DocumentType.active.is_(True))
    ergebnis: list[Dokumentklassendaten] = []
    for dokumenttyp in sitzung.scalars(abfrage):
        beispiele = tuple(sitzung.scalars(
            select(DocumentTypeExample.feature_description)
            .where(
                DocumentTypeExample.document_type_id == dokumenttyp.id,
                DocumentTypeExample.confirmed_by_user.is_(True),
            )
            .order_by(DocumentTypeExample.id)
        ))
        ergebnis.append(Dokumentklassendaten(
            name=dokumenttyp.name,
            anzeigename=dokumenttyp.display_name or dokumenttyp.name,
            fachgruppe=dokumenttyp.group_name or "Weitere Befunde",
            beschreibung=dokumenttyp.description or "",
            merkmale=dokumenttyp.classification_hints or "",
            nutzererstellt=bool(dokumenttyp.user_created),
            beispiele=beispiele,
        ))
    return tuple(ergebnis)


def finde_aehnliche_klassen(sitzung: Session, name: str) -> tuple[str, ...]:
    """Liefert nur eine Dublettenwarnung; sie entscheidet niemals automatisch."""

    vergleich = name.strip().casefold()
    if not vergleich:
        return ()
    treffer = []
    for vorhanden in sitzung.scalars(select(DocumentType.name)):
        if vergleich in vorhanden.casefold() or vorhanden.casefold() in vergleich or SequenceMatcher(
            None, vergleich, vorhanden.casefold()
        ).ratio() >= 0.72:
            treffer.append(vorhanden)
    return tuple(sorted(treffer))


def lege_dokumentklasse_an(
    sitzung: Session,
    *,
    name: str,
    fachgruppe: str,
    beschreibung: str,
    klassifikationsmerkmale: str,
    beispielmerkmale: str,
) -> DocumentType:
    """Legt eine vom Benutzer bestätigte Klasse samt erstem Beispiel atomar an."""

    bereinigt = " ".join(name.split())
    if len(bereinigt) < 3:
        raise ValueError("Der Name der neuen Dokumentklasse ist zu kurz.")
    if fachgruppe not in ERLAUBTE_FACHGRUPPEN:
        raise ValueError("Die gewählte Fachgruppe ist nicht im kontrollierten Katalog enthalten.")
    if sitzung.scalar(select(DocumentType).where(DocumentType.name == bereinigt)):
        raise ValueError("Eine Dokumentklasse mit diesem Namen existiert bereits.")
    if not beschreibung.strip() or not klassifikationsmerkmale.strip():
        raise ValueError("Beschreibung und erkennbare Klassenmerkmale sind verpflichtend.")
    if not beispielmerkmale.strip():
        raise ValueError("Für eine neue Klasse ist ein bestätigtes Beispielmerkmal erforderlich.")

    with sitzung.begin_nested():
        dokumenttyp = DocumentType(
            name=bereinigt,
            display_name=bereinigt,
            group_name=fachgruppe,
            active=True,
            user_created=True,
            description=beschreibung.strip(),
            classification_hints=klassifikationsmerkmale.strip(),
            prompt_text=None,
        )
        sitzung.add(dokumenttyp)
        sitzung.flush()
        sitzung.add(DocumentTypeExample(
            document_type_id=dokumenttyp.id,
            feature_description=beispielmerkmale.strip(),
            confirmed_by_user=True,
        ))
        sitzung.add(AuditLog(
            action="DOKUMENTKLASSE_ANGELEGT",
            entity_type="DocumentType",
            entity_id=dokumenttyp.id,
            details=f"Neue Dokumentklasse in Fachgruppe {fachgruppe} bestätigt",
        ))
    sitzung.commit()
    return dokumenttyp


def ergaenze_bestaetigtes_beispiel(
    sitzung: Session, *, dokumenttyp_name: str, beispielmerkmale: str, dokument_id: int | None = None
) -> None:
    """Erweitert Lernmerkmale additiv; Definitionen werden nicht automatisch umgeschrieben."""

    dokumenttyp = sitzung.scalar(select(DocumentType).where(
        DocumentType.name == dokumenttyp_name, DocumentType.active.is_(True)
    ))
    if dokumenttyp is None:
        raise ValueError("Die bestätigte Dokumentklasse ist nicht vorhanden oder inaktiv.")
    merkmal = beispielmerkmale.strip()
    if not merkmal:
        raise ValueError("Ein leeres Lernbeispiel wird nicht gespeichert.")
    bereits = sitzung.scalar(select(DocumentTypeExample.id).where(
        DocumentTypeExample.document_type_id == dokumenttyp.id,
        DocumentTypeExample.feature_description == merkmal,
    ))
    if bereits is not None:
        return
    sitzung.add(DocumentTypeExample(
        document_type_id=dokumenttyp.id,
        feature_description=merkmal,
        source_document_id=dokument_id,
        confirmed_by_user=True,
    ))
    sitzung.add(AuditLog(
        action="DOKUMENTKLASSE_BEISPIEL_ERGAENZT",
        entity_type="DocumentType",
        entity_id=dokumenttyp.id,
        details="Benutzerbestätigtes Klassifikationsbeispiel ergänzt",
    ))
    sitzung.commit()
