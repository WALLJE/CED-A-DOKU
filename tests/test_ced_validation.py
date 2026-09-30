"""Tests der technischen CED-Prüfregeln mit ausschließlich synthetischen Werten."""

from ced_document_ai.database.models import ConfidenceStatus
from ced_document_ai.services.ced.questionnaire_parser import parse_ced_fragebogen
from ced_document_ai.services.ced.validation import pruefe_technische_plausibilitaet


def _befund(text: str, kategorie: str):
    """Liefert gezielt einen Befund; MISSING-Zeilen bleiben in den Tests sichtbar."""
    befunde = pruefe_technische_plausibilitaet(parse_ced_fragebogen(text))
    return next(befund for befund in befunde if befund.kategorie == kategorie)


def test_plausibler_numerischer_wert_bleibt_unveraendert() -> None:
    befund = _befund("Gewicht: 74 kg", "Gewicht")

    assert befund.numerischer_wert == 74
    assert befund.anzeigewert == "74 kg"
    assert befund.qualitaet is ConfidenceStatus.HIGH_CONFIDENCE
    assert befund.pruefhinweis == ""


def test_wert_ausserhalb_pruefbereich_wird_nur_markiert() -> None:
    befund = _befund("Stuhlfrequenz: 45 pro Tag", "Stuhlfrequenz")

    assert befund.numerischer_wert == 45
    assert befund.anzeigewert == "45 pro Tag"
    assert befund.qualitaet is ConfidenceStatus.UNCERTAIN
    assert "0 bis 40 pro Tag" in befund.pruefhinweis


def test_fehlende_erwartete_einheit_wird_markiert() -> None:
    befund = _befund("Gewicht: 74", "Gewicht")

    assert befund.numerischer_wert == 74
    assert befund.einheit is None
    assert befund.qualitaet is ConfidenceStatus.UNCERTAIN
    assert "Einheit fehlt" in befund.pruefhinweis


def test_nicht_numerischer_wert_wird_nicht_geraten() -> None:
    befund = _befund("Gewicht: nicht angegeben", "Gewicht")

    assert befund.numerischer_wert is None
    assert befund.anzeigewert == "nicht angegeben"
    assert befund.qualitaet is ConfidenceStatus.UNCERTAIN
    assert "Kein numerischer Wert erkannt" in befund.pruefhinweis


def test_missing_und_unleserlich_werden_nicht_zusaetzlich_interpretiert() -> None:
    befunde = pruefe_technische_plausibilitaet(
        parse_ced_fragebogen("Gewicht: unleserlich")
    )
    gewicht = next(befund for befund in befunde if befund.kategorie == "Gewicht")
    stuhlfrequenz = next(
        befund for befund in befunde if befund.kategorie == "Stuhlfrequenz"
    )

    assert gewicht.qualitaet is ConfidenceStatus.UNREADABLE
    assert gewicht.pruefhinweis == ""
    assert stuhlfrequenz.qualitaet is ConfidenceStatus.MISSING
    assert stuhlfrequenz.pruefhinweis == ""


def test_bestehender_konflikt_wird_nicht_abgeschwaecht() -> None:
    befund = _befund("Gewicht: 7 kg\nGewicht: 8 kg", "Gewicht")

    assert befund.qualitaet is ConfidenceStatus.CONFLICT
    assert "20 bis 400 kg" in befund.pruefhinweis
