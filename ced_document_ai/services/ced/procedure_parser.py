"""Regelbasierte Abschnittserkennung für Endoskopie und Sonografie.

Die KI liefert zuvor eine originalnahe, beschriftete Darstellung. Dieses Modul
ordnet ausschließlich vollständig bekannte Feldbezeichnungen zu. Es ergänzt weder
einen Aktivitätsscore noch eine Diagnose und berechnet insbesondere keinen SES-CD
oder UC-EIS aus beschreibendem Freitext. Gleiches gilt für den CDEIS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtrahierterFachabschnitt:
    """Ein einzeln zu bestätigender Abschnitt eines Untersuchungsbefunds."""

    kategorie: str
    inhalt: str
    quelltext: str
    uebernehmen: bool
    pruefhinweis: str = ""


_ENDOSKOPIE_FELDER = {
    "untersuchung": "Untersuchung",
    "befund": "Endoskopischer Befund",
    "beurteilung": "Endoskopische Beurteilung",
    "histologie": "Histologie",
    "ses-cd": "SES-CD",
    "ses cd": "SES-CD",
    "sescd": "SES-CD",
    "cdeis": "CDEIS",
    "cdeis-score": "CDEIS",
    "cdeis score": "CDEIS",
    "uc-eis": "UC-EIS",
    "uc eis": "UC-EIS",
    "uceis": "UC-EIS",
    "empfehlung": "Empfehlung",
}
_SONOGRAFIE_FELDER = {
    "untersuchung": "Untersuchung",
    "körperregion": "Körperregion",
    "koerperregion": "Körperregion",
    "befund": "Sonografischer Befund",
    "beurteilung": "Sonografische Beurteilung",
    "empfehlung": "Empfehlung",
}


def _normalisiere_feldname(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().rstrip(":"))


def parse_fachbefund(
    text: str,
    dokumenttyp: str,
    *,
    erkrankungstyp: str | None = None,
) -> list[ExtrahierterFachabschnitt]:
    """Extrahiert bekannte Endoskopie- oder Sonografiezeilen ohne Fallback.

    Bei einem bekannten CED-Typ wird der jeweils andere endoskopische Score sichtbar
    beanstandet und zunächst nicht ausgewählt. Ein fehlender Score wird nicht ergänzt:
    Nicht jeder Befund enthält eine Aktivitätsbewertung und Freitext genügt nicht zur
    regelbasierten Berechnung.
    """

    if dokumenttyp == "Endoskopiebefund":
        felder = _ENDOSKOPIE_FELDER
    elif dokumenttyp == "Sonografiebefund":
        felder = _SONOGRAFIE_FELDER
    else:
        raise ValueError("Der Fachparser unterstützt nur Endoskopie und Sonografie.")

    ergebnisse: list[ExtrahierterFachabschnitt] = []
    for rohzeile in (text or "").splitlines():
        if ":" not in rohzeile:
            continue
        feldname, inhalt = rohzeile.split(":", 1)
        kategorie = felder.get(_normalisiere_feldname(feldname))
        inhalt = inhalt.strip()
        if kategorie is None or not inhalt:
            continue
        hinweis = ""
        uebernehmen = True
        if kategorie in {"SES-CD", "CDEIS"} and erkrankungstyp == "Colitis ulcerosa":
            hinweis = f"{kategorie} gehört zur Aktivitätsbeurteilung bei Morbus Crohn."
            uebernehmen = False
        elif kategorie == "UC-EIS" and erkrankungstyp == "Morbus Crohn":
            hinweis = "UC-EIS gehört zur Aktivitätsbeurteilung bei Colitis ulcerosa."
            uebernehmen = False
        ergebnisse.append(
            ExtrahierterFachabschnitt(
                kategorie=kategorie,
                inhalt=inhalt,
                quelltext=rohzeile.strip(),
                uebernehmen=uebernehmen,
                pruefhinweis=hinweis,
            )
        )
    return ergebnisse
