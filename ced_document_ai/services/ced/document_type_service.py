"""Persistenter, kontrollierter Katalog medizinischer Dokumentklassen.

Das Modul trennt eine Dokumentklasse strikt von einzelnen Befundkategorien. Eine
Klasse darf archiviert werden, auch wenn noch kein Fachparser existiert. Lernsignale
werden ausschließlich nach einer ausdrücklichen Benutzerbestätigung ergänzt; die
KI darf weder Klassen noch Beispiele selbständig dauerhaft anlegen.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ced_document_ai.database.models import (
    AuditLog,
    DocumentGroup,
    DocumentType,
    DocumentTypeExample,
)
from ced_document_ai.services.ced.document_categories import (
    DOKUMENTKLASSEN,
    STANDARD_FACHGRUPPEN,
)
from ced_document_ai.services.ced.finding_catalog import stelle_befundkatalog_sicher


# Kompatibilitätswert für externe Aufrufer. Die Anwendung selbst lädt Fachgruppen
# über ``liste_fachgruppen`` aus SQLite; diese Seed-Namen entscheiden nicht mehr über
# Sichtbarkeit oder Reihenfolge zur Laufzeit.
ERLAUBTE_FACHGRUPPEN = tuple(gruppe.anzeigename for gruppe in STANDARD_FACHGRUPPEN)


@dataclass(frozen=True)
class Fachgruppendaten:
    id: int
    schluessel: str
    anzeigename: str
    reihenfolge: int


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

    vorhandene_gruppen = {
        gruppe.display_name: gruppe
        for gruppe in sitzung.scalars(select(DocumentGroup))
    }
    for standardgruppe in STANDARD_FACHGRUPPEN:
        if standardgruppe.anzeigename not in vorhandene_gruppen:
            gruppe = DocumentGroup(
                key=standardgruppe.schluessel,
                display_name=standardgruppe.anzeigename,
                sort_order=standardgruppe.reihenfolge,
                active=True,
            )
            sitzung.add(gruppe)
            sitzung.flush()
            vorhandene_gruppen[gruppe.display_name] = gruppe

    vorhandene = {
        dokumenttyp.name: dokumenttyp
        for dokumenttyp in sitzung.scalars(select(DocumentType))
    }
    for standard in DOKUMENTKLASSEN:
        dokumenttyp = vorhandene.get(standard.dokumenttyp)
        if dokumenttyp is None:
            sitzung.add(DocumentType(
                name=standard.dokumenttyp,
                display_name=standard.dokumenttyp,
                group_name=standard.fachgruppe,
                group_id=vorhandene_gruppen[standard.fachgruppe].id,
                parser_key=standard.parser_schluessel,
                sort_order=standard.reihenfolge,
                active=True,
                user_created=False,
                prompt_text=None,
                description=standard.beschreibung,
                classification_hints=standard.merkmale,
            ))
        else:
            # Bestehende individuelle Definitionen werden nicht überschrieben.
            # Lediglich historisch leere Standardfelder erhalten die kontrollierte
            # Projektdefinition, damit der Klassifikator nicht nur Namen sieht.
            if not dokumenttyp.display_name:
                dokumenttyp.display_name = standard.dokumenttyp
            if not dokumenttyp.group_name:
                dokumenttyp.group_name = standard.fachgruppe
            if dokumenttyp.group_id is None:
                dokumenttyp.group_id = vorhandene_gruppen[standard.fachgruppe].id
            if not dokumenttyp.parser_key:
                dokumenttyp.parser_key = standard.parser_schluessel
            if not dokumenttyp.description:
                dokumenttyp.description = standard.beschreibung
            if not dokumenttyp.classification_hints:
                dokumenttyp.classification_hints = standard.merkmale
    stelle_befundkatalog_sicher(sitzung)
    sitzung.commit()


def liste_fachgruppen(sitzung: Session, *, nur_aktive: bool = True) -> tuple[Fachgruppendaten, ...]:
    """Liest Navigation und Reihenfolge ausschließlich aus der Katalogtabelle."""

    stelle_standardklassen_sicher(sitzung)
    abfrage = select(DocumentGroup).order_by(DocumentGroup.sort_order, DocumentGroup.display_name)
    if nur_aktive:
        abfrage = abfrage.where(DocumentGroup.active.is_(True))
    return tuple(
        Fachgruppendaten(
            id=gruppe.id,
            schluessel=gruppe.key,
            anzeigename=gruppe.display_name,
            reihenfolge=gruppe.sort_order,
        )
        for gruppe in sitzung.scalars(abfrage)
    )


def liste_dokumentklassen(sitzung: Session, *, nur_aktive: bool = True) -> tuple[Dokumentklassendaten, ...]:
    """Liest den persistenten Katalog samt bestätigten Lernbeispielen."""

    # Erst der tatsächliche Katalogzugriff materialisiert die Standardklassen. Das
    # vermeidet Seiteneffekte beim reinen Datenbankaufbau und hält Tests/Importe, die
    # eigene Dokumenttypen anlegen, unabhängig von der Anwendungsinitialisierung.
    stelle_standardklassen_sicher(sitzung)
    abfrage = select(DocumentType).order_by(DocumentType.sort_order, DocumentType.name)
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

    stelle_standardklassen_sicher(sitzung)
    bereinigt = " ".join(name.split())
    if len(bereinigt) < 3:
        raise ValueError("Der Name der neuen Dokumentklasse ist zu kurz.")
    gruppe = sitzung.scalar(
        select(DocumentGroup).where(
            DocumentGroup.display_name == fachgruppe,
            DocumentGroup.active.is_(True),
        )
    )
    if gruppe is None:
        raise ValueError("Die gewählte Fachgruppe ist nicht im aktiven Katalog enthalten.")
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
            group_id=gruppe.id,
            parser_key=None,
            sort_order=100,
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


_SENSIBLE_UEBERSCHRIFTEN = {
    "patient", "patienten-id", "name", "vorname", "nachname", "geburtsdatum",
    "adresse", "anschrift", "telefon", "versichertennummer", "fallnummer",
}


def erstelle_patientenfreie_lernmerkmale(text: str) -> str:
    """Gewinnt ausschließlich strukturelle Überschriften aus bestätigtem Text.

    Der Dienst speichert absichtlich keine Werte hinter einem Doppelpunkt und keine
    vollständigen Sätze. Damit werden Namen, Datumsangaben, Messwerte und Diagnosen
    nicht als Trainingsbeispiel dupliziert. Ergibt die konservative Extraktion kein
    Merkmal, wird leer zurückgegeben; es gibt keinen Freitext-Fallback.
    """

    merkmale: list[str] = []
    for rohe_zeile in (text or "").splitlines():
        zeile = rohe_zeile.strip().strip("|#*- ")
        if not zeile:
            continue
        kandidaten: list[str] = []
        if ":" in zeile:
            kandidaten.append(zeile.split(":", 1)[0].strip())
        elif "|" in rohe_zeile:
            kandidaten.extend(zelle.strip() for zelle in rohe_zeile.split("|") if zelle.strip())
        elif len(zeile) <= 40 and not re.search(r"\d", zeile):
            kandidaten.append(zeile)
        for kandidat in kandidaten:
            normalisiert = kandidat.casefold().strip()
            if (
                2 <= len(kandidat) <= 60
                and normalisiert not in _SENSIBLE_UEBERSCHRIFTEN
                and not re.search(r"\d|@", kandidat)
                and kandidat not in merkmale
            ):
                merkmale.append(kandidat)
    return "; ".join(merkmale[:12])
