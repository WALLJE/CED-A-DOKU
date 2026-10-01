"""Persistenter Katalog für sortierbare medizinische Befundkategorien.

Die Konstanten in diesem Modul sind ausschließlich einmalige Seed-Daten. Nach der
Initialisierung lesen Oberfläche und Speicherpfade Namen, Gruppen, Reihenfolge,
Einheiten und Synonyme aus SQLite. Die eigentliche Parserlogik bleibt weiterhin in
den getesteten Fachparsern und wird nicht durch frei editierbare Datenbankregeln
ersetzt.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ced_document_ai.database.models import FindingCategory, FindingCategoryAlias


@dataclass(frozen=True)
class StandardBefundkategorie:
    name: str
    gruppe: str
    einheit: str | None
    reihenfolge: int
    aliase: tuple[str, ...] = ()


_CED_NAMEN = (
    "Stuhlfrequenz", "Stuhlgang nachts", "Blut im Stuhl", "Schleim im Stuhl",
    "Bauchschmerzen", "Bauchschmerzen VAS", "Allgemeinbefinden",
    "Allgemeinbefinden Skalenwert", "Gewicht", "Gewichtsverlust", "Fieber",
    "Nachtschweiß", "Gelenkschmerzen", "Hautveränderungen",
    "Auffälligkeiten Analregion", "Aktuelle Medikamente", "Neue Aspekte",
    "Fragen des Patienten",
)

STANDARD_BEFUNDKATEGORIEN: tuple[StandardBefundkategorie, ...] = tuple(
    StandardBefundkategorie(name, "CED-Fragebogen", None, index * 10)
    for index, name in enumerate(_CED_NAMEN, start=1)
) + (
    StandardBefundkategorie("CRP", "Labor", "mg/l", 10, ("C-reaktives Protein",)),
    StandardBefundkategorie("Hämoglobin", "Labor", "g/dl", 20, ("Haemoglobin", "Hb")),
    StandardBefundkategorie("Leukozyten", "Labor", "Gpt/l", 30, ("Leukos",)),
    StandardBefundkategorie("Thrombozyten", "Labor", "Gpt/l", 40, ("Thrombos",)),
    StandardBefundkategorie("Ferritin", "Labor", "µg/l", 50),
    StandardBefundkategorie("Vitamin B12", "Labor", "pg/ml", 60, ("Cobalamin",)),
    StandardBefundkategorie("Folsäure", "Labor", "ng/ml", 70, ("Folsaeure",)),
    StandardBefundkategorie("Albumin", "Labor", "g/l", 80),
    StandardBefundkategorie("Kreatinin", "Labor", "mg/dl", 90),
    StandardBefundkategorie("ALT", "Labor", "U/l", 100, ("GPT",)),
    StandardBefundkategorie("AST", "Labor", "U/l", 110, ("GOT",)),
    StandardBefundkategorie("Gamma-GT", "Labor", "U/l", 120, ("GGT",)),
    StandardBefundkategorie(
        "Fäkales Calprotectin", "Calprotectin", "µg/g", 10,
        ("Calprotectin", "Calprotectin im Stuhl"),
    ),
)


def stelle_befundkatalog_sicher(sitzung: Session) -> None:
    """Seedet fehlende Kategorien und Aliase, ohne vorhandene Werte zu überschreiben."""

    vorhandene = {
        kategorie.name: kategorie
        for kategorie in sitzung.scalars(select(FindingCategory))
    }
    for standard in STANDARD_BEFUNDKATEGORIEN:
        kategorie = vorhandene.get(standard.name)
        if kategorie is None:
            kategorie = FindingCategory(
                name=standard.name,
                display_name=standard.name,
                group_name=standard.gruppe,
                typical_unit=standard.einheit,
                sort_order=standard.reihenfolge,
                active=True,
            )
            sitzung.add(kategorie)
            sitzung.flush()
            vorhandene[standard.name] = kategorie
        else:
            if not kategorie.display_name:
                kategorie.display_name = standard.name
        vorhandene_aliase = set(sitzung.scalars(
            select(FindingCategoryAlias.alias).where(
                FindingCategoryAlias.category_id == kategorie.id
            )
        ))
        for alias in standard.aliase:
            if alias not in vorhandene_aliase:
                sitzung.add(FindingCategoryAlias(category_id=kategorie.id, alias=alias))
    sitzung.commit()

