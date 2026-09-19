"""Tests des deterministischen Labor-/Virologie-/Mikrobiologie-Parsers."""

import pytest

from ced_document_ai.database.models import ConfidenceStatus
from ced_document_ai.services.ced.laboratory_parser import parse_laborbefund


def test_markdown_laborwerte_werden_ohne_interpretation_gelesen() -> None:
    befunde = parse_laborbefund(
        """
        Patient: Beispiel, Erika
        Entnahmedatum: 19.09.2026
        | Parameter | Ergebnis | Einheit | Referenzbereich |
        | --- | --- | --- | --- |
        | CRP | 12,4 | mg/l | < 5 |
        | Hämoglobin | 11.8 | g/dl | 12-16 |
        """,
        "Laborbefund",
    )

    assert [(befund.kategorie, befund.anzeigewert) for befund in befunde] == [
        ("CRP", "12,4"),
        ("Hämoglobin", "11.8"),
    ]
    assert befunde[0].numerischer_wert == 12.4
    assert befunde[0].referenzbereich == "< 5"
    assert befunde[0].qualitaet is ConfidenceStatus.HIGH_CONFIDENCE
    assert befunde[0].uebernehmen


def test_qualitativer_virologiewert_bleibt_text_und_bekannte_gruppe_labor() -> None:
    befunde = parse_laborbefund(
        "| CMV-PCR | negativ |  | negativ |",
        "Virologischer Befund",
    )

    assert len(befunde) == 1
    assert befunde[0].kategorie == "CMV-PCR"
    assert befunde[0].anzeigewert == "negativ"
    assert befunde[0].numerischer_wert is None
    assert befunde[0].fachgruppe == "Labor"
    assert befunde[0].neue_kategorie
    assert not befunde[0].uebernehmen


def test_neuer_parameter_bleibt_ausgeschaltet_bis_zur_bestaetigung() -> None:
    befunde = parse_laborbefund("Neuer Marker: 7 U/ml", "Laborbefund")

    assert len(befunde) == 1
    assert befunde[0].kategorie == "Neuer Marker"
    assert befunde[0].einheit == "U/ml"
    assert befunde[0].neue_kategorie
    assert befunde[0].qualitaet is ConfidenceStatus.UNCERTAIN
    assert not befunde[0].uebernehmen


def test_bereits_bestaetigte_dynamische_kategorie_wird_wiedererkannt() -> None:
    befunde = parse_laborbefund(
        "| CMV-PCR | negativ |  | negativ |",
        "Virologischer Befund",
        bestehende_kategorien=(("CMV-PCR", None, "Labor"),),
    )

    assert len(befunde) == 1
    assert befunde[0].kategorie == "CMV-PCR"
    assert not befunde[0].neue_kategorie
    assert befunde[0].uebernehmen


def test_widerspruechliche_doppelangabe_wird_nicht_vorausgewaehlt() -> None:
    befunde = parse_laborbefund(
        "| CRP | 5 | mg/l | < 5 |\n| CRP | 12 | mg/l | < 5 |",
        "Laborbefund",
    )

    assert len(befunde) == 2
    assert all(befund.qualitaet is ConfidenceStatus.CONFLICT for befund in befunde)
    assert all(not befund.uebernehmen for befund in befunde)


def test_fehlende_oder_abweichende_einheit_wird_nicht_korrigiert() -> None:
    ohne_einheit = parse_laborbefund("| CRP | 12 |  | |", "Laborbefund")[0]
    andere_einheit = parse_laborbefund("| CRP | 1.2 | mg/dl | |", "Laborbefund")[0]

    assert ohne_einheit.einheit is None
    assert ohne_einheit.qualitaet is ConfidenceStatus.UNCERTAIN
    assert not ohne_einheit.uebernehmen
    assert andere_einheit.einheit == "mg/dl"
    assert andere_einheit.qualitaet is ConfidenceStatus.UNCERTAIN
    assert not andere_einheit.uebernehmen


def test_unterstuetzter_dokumenttyp_ist_verpflichtend() -> None:
    with pytest.raises(ValueError, match="kein unterstützter Laborpfad"):
        parse_laborbefund("CRP: 12 mg/l", "Arztbrief")
