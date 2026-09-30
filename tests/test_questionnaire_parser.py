"""Tests des CED-Reintextparsers mit ausschließlich synthetischen Angaben."""

from ced_document_ai.database.models import ConfidenceStatus
from datetime import date

from ced_document_ai.services.ced.questionnaire_parser import (
    STANDARDKATEGORIEN,
    erkenne_befunddatum,
    parse_ced_fragebogen,
)


def _vorhandene_befunde(text: str):
    """Blendet MISSING-Zeilen aus, wenn ein Test nur erkannte Werte untersucht."""
    return [
        befund
        for befund in parse_ced_fragebogen(text)
        if befund.qualitaet is not ConfidenceStatus.MISSING
    ]


def test_bekannte_felder_werden_getrennt_und_originalquelle_bleibt_erhalten() -> None:
    befunde = _vorhandene_befunde(
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
    befunde = _vorhandene_befunde(
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
    [befund] = _vorhandene_befunde("Auffälligkeiten Analregion: unleserlich")

    assert befund.anzeigewert == "unleserlich"
    assert befund.qualitaet is ConfidenceStatus.UNREADABLE
    assert befund.numerischer_wert is None


def test_neue_kategorie_bleibt_als_unbestaetigter_vorschlag_erhalten() -> None:
    [befund] = _vorhandene_befunde("Appetit: vermindert")

    assert befund.kategorie == "Appetit"
    assert befund.neue_kategorie
    assert not befund.uebernehmen
    assert befund.qualitaet is ConfidenceStatus.UNCERTAIN


def test_doppelte_kategorie_wird_als_konflikt_markiert() -> None:
    befunde = _vorhandene_befunde("Gewicht: 74 kg\nGewicht: 75 kg")

    assert len(befunde) == 2
    assert all(befund.qualitaet is ConfidenceStatus.CONFLICT for befund in befunde)
    assert all(not befund.uebernehmen for befund in befunde)


def test_unbeschrifteter_freitext_wird_nicht_geraten() -> None:
    befunde = parse_ced_fragebogen("Heute deutlich besser als gestern.")

    assert [befund.kategorie for befund in befunde] == list(STANDARDKATEGORIEN)
    assert all(befund.qualitaet is ConfidenceStatus.MISSING for befund in befunde)
    assert all(not befund.uebernehmen for befund in befunde)
    assert all(not befund.anzeigewert and not befund.quelltext for befund in befunde)


def test_nicht_genannte_standardfelder_werden_als_missing_ergaenzt() -> None:
    befunde = parse_ced_fragebogen("Gewicht: 74 kg")

    gewicht = next(befund for befund in befunde if befund.kategorie == "Gewicht")
    fehlende = [
        befund
        for befund in befunde
        if befund.qualitaet is ConfidenceStatus.MISSING
    ]

    assert gewicht.qualitaet is ConfidenceStatus.HIGH_CONFIDENCE
    assert gewicht.uebernehmen
    assert len(fehlende) == len(STANDARDKATEGORIEN) - 1
    assert all(not befund.uebernehmen for befund in fehlende)


def test_eindeutig_beschriftetes_befunddatum_wird_vorgeschlagen() -> None:
    erkannt = erkenne_befunddatum(
        "Geburtsdatum: 12.03.1980\nBefunddatum: 13.09.2026\nGewicht: 74 kg"
    )

    assert erkannt == date(2026, 9, 13)


def test_befunddatum_hat_vorrang_vor_allgemeinem_datum() -> None:
    erkannt = erkenne_befunddatum(
        "Datum: 01.09.2026\nBefunddatum: 13.09.2026"
    )

    assert erkannt == date(2026, 9, 13)


def test_labor_entnahmedatum_wird_als_dokumentdatum_erkannt() -> None:
    erkannt = erkenne_befunddatum(
        "Geburtsdatum: 12.03.1980\nEntnahmedatum: 17.09.2026"
    )

    assert erkannt == date(2026, 9, 17)


def test_widerspruechliche_gleichrangige_daten_werden_nicht_geraten() -> None:
    erkannt = erkenne_befunddatum(
        "Fragebogendatum: 12.09.2026\nErhebungsdatum: 13.09.2026"
    )

    assert erkannt is None


def test_geburtsdatum_allein_ist_kein_befunddatum() -> None:
    assert erkenne_befunddatum("Geburtsdatum: 12.03.1980") is None


def test_metadaten_werden_nicht_als_neue_befundkategorien_angeboten() -> None:
    befunde = _vorhandene_befunde(
        "Patient: Erika Beispiel\nBefunddatum: 13.09.2026\nGewicht: 74 kg"
    )

    assert [befund.kategorie for befund in befunde] == ["Gewicht"]
