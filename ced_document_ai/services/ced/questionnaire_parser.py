"""Toleranter Reintextparser für CED-Fragebogendaten und neue Kategorien.

Der Parser arbeitet ausschließlich auf der bereits erzeugten strukturierten
Darstellung. Er verändert weder die allgemeine Textextraktion noch ruft er selbst
einen KI-Anbieter auf. Bekannte Kategorien werden über einen kontrollierten Katalog
zugeordnet. Weitere klar beschriftete Zeilen bleiben als prüfpflichtige Vorschläge
erhalten, damit neue Kategorien später bewusst in die Tabelle aufgenommen werden
können, ohne sie schon dauerhaft im Befundkatalog anzulegen.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace

from ced_document_ai.database.models import ConfidenceStatus


STANDARDKATEGORIEN: tuple[str, ...] = (
    "Stuhlfrequenz",
    "Stuhlgang nachts",
    "Blut im Stuhl",
    "Schleim im Stuhl",
    "Bauchschmerzen",
    "Bauchschmerzen VAS",
    "Allgemeinbefinden",
    "Allgemeinbefinden Skalenwert",
    "Gewicht",
    "Gewichtsverlust",
    "Fieber",
    "Nachtschweiß",
    "Gelenkschmerzen",
    "Hautveränderungen",
    "Auffälligkeiten Analregion",
    "Aktuelle Medikamente",
    "Neue Aspekte",
    "Fragen des Patienten",
)


@dataclass(frozen=True)
class ExtrahierterBefund:
    """Ein noch nicht gespeicherter Tabellenwert mit seiner unveränderten Quelle."""

    kategorie: str
    anzeigewert: str
    numerischer_wert: float | None
    einheit: str | None
    quelltext: str
    qualitaet: ConfidenceStatus
    neue_kategorie: bool = False
    uebernehmen: bool = True


def _normalisiere(wert: str) -> str:
    """Vereinheitlicht nur für den Feldvergleich, niemals für die spätere Anzeige."""
    ohne_akzente = unicodedata.normalize("NFKD", wert)
    basis = "".join(
        zeichen for zeichen in ohne_akzente if not unicodedata.combining(zeichen)
    ).casefold()
    return re.sub(r"[^a-z0-9]+", " ", basis).strip()


_ALIASE = {
    _normalisiere(alias): kategorie
    for kategorie, aliase in {
        "Stuhlfrequenz": ("Stuhlfrequenz", "Stühle pro Tag", "Stuhlgaenge pro Tag"),
        "Stuhlgang nachts": ("Stuhlgang nachts", "Nächtlicher Stuhlgang"),
        "Blut im Stuhl": ("Blut im Stuhl", "Blutbeimengung"),
        "Schleim im Stuhl": ("Schleim im Stuhl", "Schleimbeimengung"),
        "Bauchschmerzen": ("Bauchschmerzen", "Bauchschmerz"),
        "Bauchschmerzen VAS": ("Bauchschmerzen VAS", "Bauchschmerz VAS"),
        "Allgemeinbefinden": ("Allgemeinbefinden",),
        "Allgemeinbefinden Skalenwert": (
            "Allgemeinbefinden Skalenwert",
            "Allgemeinbefinden Skala",
        ),
        "Gewicht": ("Gewicht", "Körpergewicht"),
        "Gewichtsverlust": ("Gewichtsverlust",),
        "Fieber": ("Fieber",),
        "Nachtschweiß": ("Nachtschweiß", "Nachtschweiss"),
        "Gelenkschmerzen": ("Gelenkschmerzen", "Arthralgien"),
        "Hautveränderungen": ("Hautveränderungen", "Hautveraenderungen"),
        "Auffälligkeiten Analregion": (
            "Auffälligkeiten Analregion",
            "Analregion",
            "Perianale Auffälligkeiten",
        ),
        "Aktuelle Medikamente": ("Aktuelle Medikamente", "Medikamente"),
        "Neue Aspekte": ("Neue Aspekte", "Was sollten wir wissen"),
        "Fragen des Patienten": ("Fragen des Patienten", "Patientenfragen"),
    }.items()
    for alias in aliase
}

_ZEILE = re.compile(r"^\s*([^:|]{2,100})\s*:\s*(.*?)\s*$")
_ZAHL = re.compile(r"(?<!\d)(-?\d+(?:[.,]\d+)?)(?!\d)")
_QUALITAET = re.compile(r"\s*(?:✓\s*sicher|\?\s*unsicher|!\s*prüfen)\s*$", re.I)


def _qualitaet_und_wert(wert: str) -> tuple[ConfidenceStatus, str]:
    """Entfernt nur explizite Qualitätsmarker und bewahrt den medizinischen Wert."""
    klein = wert.casefold().strip()
    if klein in {"unleserlich", "nicht lesbar"}:
        return ConfidenceStatus.UNREADABLE, wert.strip()
    if re.search(r"(?:\?|unsicher|!\s*prüfen)\s*$", wert, re.I):
        return ConfidenceStatus.UNCERTAIN, _QUALITAET.sub("", wert).strip()
    return ConfidenceStatus.HIGH_CONFIDENCE, _QUALITAET.sub("", wert).strip()


def _numerik(kategorie: str, wert: str) -> tuple[float | None, str | None]:
    """Trennt Zahlen nur bei dafür vorgesehenen Kategorien von ihrer Einheit."""
    numerische_kategorien = {
        "Stuhlfrequenz",
        "Bauchschmerzen VAS",
        "Allgemeinbefinden Skalenwert",
        "Gewicht",
    }
    if kategorie not in numerische_kategorien:
        return None, None
    treffer = _ZAHL.search(wert)
    if treffer is None:
        return None, None
    zahl = float(treffer.group(1).replace(",", "."))
    rest = (wert[: treffer.start()] + wert[treffer.end() :]).strip(" ()")
    einheit = re.sub(r"\s+", " ", rest) or None
    return zahl, einheit


def _skalenwert_ableiten(
    kategorie: str, wert: str, quelltext: str
) -> ExtrahierterBefund | None:
    """Erhält einen ausdrücklich genannten Skalenwert zusätzlich zum Beschreibungstext."""
    ziel = {
        "Bauchschmerzen": "Bauchschmerzen VAS",
        "Allgemeinbefinden": "Allgemeinbefinden Skalenwert",
    }.get(kategorie)
    if ziel is None:
        return None
    treffer = re.search(
        r"(?:VAS|Skala)?\s*\(?\s*(\d+(?:[.,]\d+)?)\s*(?:von|/)\s*6\s*\)?",
        wert,
        re.I,
    )
    if treffer is None:
        return None
    zahl = float(treffer.group(1).replace(",", "."))
    qualitaet = (
        ConfidenceStatus.HIGH_CONFIDENCE
        if 0 <= zahl <= 6
        else ConfidenceStatus.CONFLICT
    )
    return ExtrahierterBefund(
        kategorie=ziel,
        anzeigewert=f"{treffer.group(1)} von 6",
        numerischer_wert=zahl,
        einheit="von 6",
        quelltext=quelltext,
        qualitaet=qualitaet,
    )


def parse_ced_fragebogen(text: str) -> list[ExtrahierterBefund]:
    """Parst bekannte Felder und behält neue Kategorien als Vorschläge bei.

    Debugging-Hinweis: Bei einer nicht erkannten Zeile dürfen lokal Feldname und
    Parserstatus geprüft werden. Den vollständigen Wert oder Patiententext nicht in
    dauerhafte Logs schreiben. Nicht beschriftete Freitextzeilen werden bewusst nicht
    geraten und deshalb nicht als Befund übernommen.
    """
    gefundene: list[ExtrahierterBefund] = []
    for zeile in (text or "").splitlines():
        treffer = _ZEILE.match(zeile)
        if treffer is None:
            continue
        feldname, rohwert = treffer.groups()
        if not rohwert.strip():
            continue
        kategorie = _ALIASE.get(_normalisiere(feldname), feldname.strip())
        ist_neu = kategorie not in STANDARDKATEGORIEN
        qualitaet, wert = _qualitaet_und_wert(rohwert)
        if ist_neu:
            qualitaet = ConfidenceStatus.UNCERTAIN
        numerischer_wert, einheit = _numerik(kategorie, wert)
        gefundene.append(
            ExtrahierterBefund(
                kategorie=kategorie,
                anzeigewert=wert,
                numerischer_wert=numerischer_wert,
                einheit=einheit,
                quelltext=zeile.strip(),
                qualitaet=qualitaet,
                neue_kategorie=ist_neu,
                uebernehmen=not ist_neu,
            )
        )
        skalenwert = _skalenwert_ableiten(kategorie, wert, zeile.strip())
        if skalenwert is not None:
            gefundene.append(skalenwert)

    # Doppelte Kategorien dürfen nicht still auf einen Wert reduziert werden. Alle
    # betroffenen Zeilen bleiben sichtbar und werden für die Prüfung markiert.
    anzahl = {
        kategorie: sum(befund.kategorie == kategorie for befund in gefundene)
        for kategorie in {befund.kategorie for befund in gefundene}
    }
    return [
        replace(befund, qualitaet=ConfidenceStatus.CONFLICT, uebernehmen=False)
        if anzahl[befund.kategorie] > 1
        else befund
        for befund in gefundene
    ]
