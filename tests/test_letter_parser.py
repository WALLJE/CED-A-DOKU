"""Tests der deterministischen Abschnittserkennung für Arztbriefe."""

from ced_document_ai.services.ced.letter_parser import parse_arztbrief


def test_gegliederter_arztbrief_wird_abschnittsweise_extrahiert() -> None:
    abschnitte = parse_arztbrief(
        """
        Sehr geehrte Kolleginnen und Kollegen,
        Langzeitdiagnosen:
        Morbus Crohn (ED 06/2024)
        - Befallsmuster: Ileitis terminalis
        Operationen:
        - Ileumperforation mit Ileozökalresektion (07/2024)
        Beruf:
        Studium Geschichte/Englisch
        Familie:
        Vater und Großvater beide M. Crohn
        Diagnostik/Befunde:
        Therapie:
        09/2024-01/2025: Prednisolon
        11/2024-aktuell: Azathioprin
        Endoskopie:
        07/2024: Gastroskopie und Koloskopie
        MRT/CT/Röntgen:
        09/2024: MR Sellink: keine Aktivität
        """
    )

    assert [abschnitt.kategorie for abschnitt in abschnitte] == [
        "Diagnosen",
        "Operationen",
        "Sozialanamnese",
        "Familienanamnese",
        "Therapie/Medikation",
        "Endoskopie",
        "Bildgebung",
    ]
    assert "Morbus Crohn" in abschnitte[0].inhalt
    assert "keine Aktivität" in abschnitte[-1].inhalt


def test_ungegliederter_freitext_wird_nicht_geraten() -> None:
    assert parse_arztbrief("Morbus Crohn und Azathioprin werden erwähnt.") == []
