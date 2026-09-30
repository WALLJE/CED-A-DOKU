"""Deterministische Abschnittserkennung für Arztbriefe.

Der Parser übernimmt ausschließlich Text unter ausdrücklich vorhandenen Überschriften.
Er leitet keine Diagnosen aus Befunden ab und verändert weder Negationen noch Daten,
Medikamente oder Operationsbezeichnungen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtrahierterArztbriefabschnitt:
    """Ein vor der Speicherung manuell zu bestätigender Briefabschnitt."""

    kategorie: str
    inhalt: str
    quelltext: str
    uebernehmen: bool = True


_UEBERSCHRIFTEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:langzeit)?diagnosen?\s*:?$", re.I), "Diagnosen"),
    (re.compile(r"^(?:operationen?|operation)\s*:?$", re.I), "Operationen"),
    (re.compile(r"^(?:therapie(?:/medikation)?|medikation)\s*:?$", re.I), "Therapie/Medikation"),
    (re.compile(r"^(?:endoskopie|gastro-?/?koloskopie)\s*:?$", re.I), "Endoskopie"),
    (re.compile(r"^(?:bildgebung|mrt|ct|röntgen|roentgen)(?:\s*/\s*[^:]*)?\s*:?$", re.I), "Bildgebung"),
    (re.compile(r"^(?:weitere diagnostik|diagnostik(?:/befunde)?|befunde)\s*:?$", re.I), "Weitere Diagnostik"),
    (re.compile(r"^(?:beruf|sozialanamnese)\s*:?$", re.I), "Sozialanamnese"),
    (re.compile(r"^(?:familie|familienanamnese)\s*:?$", re.I), "Familienanamnese"),
    (re.compile(r"^(?:anamnese|vorgeschichte)\s*:?$", re.I), "Anamnese"),
    (re.compile(r"^(?:empfehlungen?|weiteres vorgehen|procedere)\s*:?$", re.I), "Empfehlungen"),
)


def _kategorie_fuer_ueberschrift(zeile: str) -> str | None:
    """Ordnet nur vollständige Überschriften, nicht ähnlich klingende Sätze zu."""

    bereinigt = zeile.strip().strip("*_# ")
    for muster, kategorie in _UEBERSCHRIFTEN:
        if muster.fullmatch(bereinigt):
            return kategorie
    return None


def parse_arztbrief(text: str) -> list[ExtrahierterArztbriefabschnitt]:
    """Extrahiert vorhandene gegliederte Abschnitte ohne Freitext-Fallback."""

    ergebnisse: list[ExtrahierterArztbriefabschnitt] = []
    aktuelle_kategorie: str | None = None
    aktuelle_zeilen: list[str] = []

    def abschliessen() -> None:
        if aktuelle_kategorie is None:
            return
        inhalt = "\n".join(zeile for zeile in aktuelle_zeilen if zeile).strip()
        if not inhalt:
            return
        ergebnisse.append(
            ExtrahierterArztbriefabschnitt(
                kategorie=aktuelle_kategorie,
                inhalt=inhalt,
                quelltext=inhalt,
            )
        )

    for rohzeile in (text or "").splitlines():
        zeile = rohzeile.strip()
        kategorie = _kategorie_fuer_ueberschrift(zeile)
        if kategorie is not None:
            abschliessen()
            aktuelle_kategorie = kategorie
            aktuelle_zeilen = []
            continue
        if aktuelle_kategorie is not None:
            aktuelle_zeilen.append(zeile)
    abschliessen()
    return ergebnisse
