"""Tests für Endoskopie- und Sonografieabschnitte mit synthetischen Angaben."""

import pytest

from ced_document_ai.services.ced.procedure_parser import parse_fachbefund


def test_endoskopie_uebernimmt_ses_cd_fuer_morbus_crohn() -> None:
    abschnitte = parse_fachbefund(
        """
        Untersuchung: Ileokoloskopie
        Befund: Aphthen im terminalen Ileum
        SES-CD: 5
        CDEIS: 3
        UCEIS: 2
        Beurteilung: geringe Aktivität
        """,
        "Endoskopiebefund",
        erkrankungstyp="Morbus Crohn",
    )

    nach_kategorie = {abschnitt.kategorie: abschnitt for abschnitt in abschnitte}
    assert nach_kategorie["SES-CD"].uebernehmen
    assert not nach_kategorie["SES-CD"].pruefhinweis
    assert nach_kategorie["CDEIS"].uebernehmen
    assert not nach_kategorie["UC-EIS"].uebernehmen
    assert "Colitis ulcerosa" in nach_kategorie["UC-EIS"].pruefhinweis


def test_endoskopie_uebernimmt_uc_eis_fuer_colitis_ulcerosa() -> None:
    abschnitte = parse_fachbefund(
        "UC-EIS: 3\nSES-CD: 7\nCDEIS: 4",
        "Endoskopiebefund",
        erkrankungstyp="Colitis ulcerosa",
    )

    nach_kategorie = {abschnitt.kategorie: abschnitt for abschnitt in abschnitte}
    assert nach_kategorie["UC-EIS"].uebernehmen
    assert not nach_kategorie["SES-CD"].uebernehmen
    assert not nach_kategorie["CDEIS"].uebernehmen


def test_sonografie_verarbeitet_nur_bekannte_beschriftete_felder() -> None:
    abschnitte = parse_fachbefund(
        """
        Untersuchung: Abdomensonografie
        Körperregion: terminales Ileum
        Befund: Wandverdickung 4 mm
        Freitext ohne Zuordnung
        Unbekannt: nicht zuordnen
        """,
        "Sonografiebefund",
    )

    assert [abschnitt.kategorie for abschnitt in abschnitte] == [
        "Untersuchung",
        "Körperregion",
        "Sonografischer Befund",
    ]


def test_fachparser_lehnt_andere_dokumenttypen_ab() -> None:
    with pytest.raises(ValueError, match="nur Endoskopie und Sonografie"):
        parse_fachbefund("Befund: Text", "MRT-Befund")
