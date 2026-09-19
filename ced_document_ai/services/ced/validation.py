"""Deterministische technische Plausibilitätsprüfung für CED-Prüfwerte.

Die Regeln in diesem Modul bewerten ausschließlich formale Wertebereiche und
Einheiten. Sie stellen keine Diagnose, ändern keinen erkannten Wert und erzeugen
keinen Ersatzwert. Auffälligkeiten werden nur als Prüfhinweis an die Oberfläche
zurückgegeben und müssen dort von einem Menschen beurteilt werden.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from ced_document_ai.database.models import ConfidenceStatus
from ced_document_ai.services.ced.questionnaire_parser import ExtrahierterBefund


# Diese Grenzen sind bewusst als technische Prüfgrenzen formuliert. Ein Wert
# außerhalb des üblichen Prüfbereichs wird nicht verworfen oder korrigiert. Bei
# einer fachlichen Änderung müssen Regel, Begründung und Tests gemeinsam angepasst
# werden; versteckte patientenbezogene Sonderregeln sind hier nicht zulässig.
_NUMERISCHE_REGELN: dict[str, tuple[float, float, str]] = {
    "Stuhlfrequenz": (0, 40, "0 bis 40 pro Tag"),
    "Gewicht": (20, 400, "20 bis 400 kg"),
    "Bauchschmerzen VAS": (0, 6, "0 bis 6"),
    "Allgemeinbefinden Skalenwert": (0, 6, "0 bis 6"),
}

_ERLAUBTE_EINHEITEN: dict[str, frozenset[str]] = {
    "Stuhlfrequenz": frozenset({"pro tag", "/ tag", "/tag"}),
    "Gewicht": frozenset({"kg", "kilogramm"}),
    "Bauchschmerzen VAS": frozenset({"von 6", "/ 6", "/6"}),
    "Allgemeinbefinden Skalenwert": frozenset({"von 6", "/ 6", "/6"}),
}


def _normalisiere_einheit(einheit: str | None) -> str:
    """Normalisiert nur den Einheitenvergleich, niemals den sichtbaren Originalwert."""
    ohne_akzente = unicodedata.normalize("NFKD", einheit or "")
    basis = "".join(
        zeichen for zeichen in ohne_akzente if not unicodedata.combining(zeichen)
    ).casefold()
    return re.sub(r"\s+", " ", basis).strip()


def _status_mit_warnung(aktueller_status: ConfidenceStatus) -> ConfidenceStatus:
    """Verschärft nur sichere Werte; bestehende Problemzustände bleiben erhalten."""
    if aktueller_status is ConfidenceStatus.HIGH_CONFIDENCE:
        return ConfidenceStatus.UNCERTAIN
    return aktueller_status


def pruefe_technische_plausibilitaet(
    befunde: list[ExtrahierterBefund],
) -> list[ExtrahierterBefund]:
    """Ergänzt Hinweise zu Zahlenbereichen und Einheiten ohne automatische Korrektur.

    ``MISSING``- und ``UNREADABLE``-Zeilen werden nicht interpretiert. Für numerisch
    erwartete Kategorien wird ein fehlender Zahlenwert sichtbar beanstandet. Werte
    außerhalb der festgelegten Prüfgrenzen sowie unbekannte Einheiten werden als
    ``UNCERTAIN`` markiert, sofern nicht bereits ein strengerer Status vorliegt.

    Debugging-Hinweis: Bei einer unerwarteten Markierung dürfen Kategoriename,
    Regelname und resultierender Status protokolliert werden. Numerische Werte,
    Quelltexte und andere medizinische Inhalte gehören nicht in dauerhafte Logs.
    """
    ergebnis: list[ExtrahierterBefund] = []
    for befund in befunde:
        if befund.qualitaet in {
            ConfidenceStatus.MISSING,
            ConfidenceStatus.UNREADABLE,
        }:
            ergebnis.append(befund)
            continue

        regel = _NUMERISCHE_REGELN.get(befund.kategorie)
        if regel is None:
            ergebnis.append(befund)
            continue

        minimum, maximum, bereichstext = regel
        hinweise: list[str] = []
        if befund.numerischer_wert is None:
            hinweise.append("Kein numerischer Wert erkannt; bitte Originalangabe prüfen.")
        elif not minimum <= befund.numerischer_wert <= maximum:
            hinweise.append(
                f"Außerhalb des technischen Prüfbereichs {bereichstext}; bitte prüfen."
            )

        erlaubte_einheiten = _ERLAUBTE_EINHEITEN[befund.kategorie]
        if _normalisiere_einheit(befund.einheit) not in erlaubte_einheiten:
            hinweise.append("Einheit fehlt oder entspricht nicht der erwarteten Schreibweise.")

        if not hinweise:
            ergebnis.append(befund)
            continue
        ergebnis.append(
            replace(
                befund,
                qualitaet=_status_mit_warnung(befund.qualitaet),
                pruefhinweis=" ".join(hinweise),
            )
        )
    return ergebnis
