"""Tests des CED-Reintextparsers mit ausschließlich synthetischen Angaben."""

from ced_document_ai.database.models import ConfidenceStatus
from ced_document_ai.services.ced.questionnaire_parser import parse_ced_fragebogen


def test_bekannte_felder_werden_getrennt_und_originalquelle_bleibt_erhalten() -> None:
    befunde = parse_ced_fragebogen(
        "Stuhlfrequenz: 4 pro Tag\nGewicht: 74,5 kg\nBlut im Stuhl: nein"
    )

    assert [befund.kategorie for befund in befunde] == [
        "Stuhlfrequenz",
        "Gewicht",
        "Blut im Stuhl",
    ]
    assert befunde[0].numerischer_wert == 4
    assert befunde[0].einheit == "pro Tag"
    assert befunde[1].numerischer_wert == 74.5
    assert befunde[1].einheit == "kg"
    assert befunde[2].quelltext == "Blut im Stuhl: nein"


def test_skalenwert_wird_aus_beschreibung_zusaetzlich_abgeleitet() -> None:
    befunde = parse_ced_fragebogen(
        "Bauchschmerzen: moderat (VAS 3 von 6)\nAllgemeinbefinden: 2 / 6"
    )

    assert [befund.kategorie for befund in befunde] == [
        "Bauchschmerzen",
        "Bauchschmerzen VAS",
        "Allgemeinbefinden",
        "Allgemeinbefinden Skalenwert",
    ]
    assert befunde[1].numerischer_wert == 3
    assert befunde[3].numerischer_wert == 2


def test_unleserlicher_wert_wird_nicht_ersetzt() -> None:
    [befund] = parse_ced_fragebogen("Auffälligkeiten Analregion: unleserlich")

    assert befund.anzeigewert == "unleserlich"
    assert befund.qualitaet is ConfidenceStatus.UNREADABLE
    assert befund.numerischer_wert is None


def test_neue_kategorie_bleibt_als_unbestaetigter_vorschlag_erhalten() -> None:
    [befund] = parse_ced_fragebogen("Appetit: vermindert")

    assert befund.kategorie == "Appetit"
    assert befund.neue_kategorie
    assert not befund.uebernehmen
    assert befund.qualitaet is ConfidenceStatus.UNCERTAIN


def test_doppelte_kategorie_wird_als_konflikt_markiert() -> None:
    befunde = parse_ced_fragebogen("Gewicht: 74 kg\nGewicht: 75 kg")

    assert len(befunde) == 2
    assert all(befund.qualitaet is ConfidenceStatus.CONFLICT for befund in befunde)
    assert all(not befund.uebernehmen for befund in befunde)


def test_unbeschrifteter_freitext_wird_nicht_geraten() -> None:
    assert parse_ced_fragebogen("Heute deutlich besser als gestern.") == []
