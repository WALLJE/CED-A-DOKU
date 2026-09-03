"""Tests des strikten Workflows ohne Übertragung medizinischer Dokumente."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ced_document_ai.services.ai.document_workflow import (
    DokumentAntwortFehler,
    Dokumenttyp,
    FORMATVORGABEN,
    WORKFLOW_PROMPT,
    parse_dokumentantwort,
)
from ced_document_ai.services.ai.providers import OpenAICompatibleProvider


def _antwort(typ: Dokumenttyp = Dokumenttyp.ARZTBRIEF) -> str:
    return f"""DOKUMENTTYP:
{typ.value}

AUSGELESENER INHALT:
Kein Fieber, CRP 12 mg/l.

STRUKTURIERTE DARSTELLUNG:
Diagnosen: Colitis ulcerosa

KIS-VORSCHLAG:
Kein Fieber; CRP 12 mg/l.
"""


@pytest.mark.parametrize("dokumenttyp", list(Dokumenttyp))
def test_alle_dokumenttypen_werden_geparst(dokumenttyp: Dokumenttyp) -> None:
    assert parse_dokumentantwort(_antwort(dokumenttyp)).dokumenttyp is dokumenttyp


def test_vier_abschnitte_bleiben_getrennt_und_leerzeilen_sind_erlaubt() -> None:
    ergebnis = parse_dokumentantwort("\n\n" + _antwort() + "\n\n")
    assert ergebnis.ausgelesener_inhalt == "Kein Fieber, CRP 12 mg/l."
    assert ergebnis.strukturierte_darstellung == "Diagnosen: Colitis ulcerosa"
    assert ergebnis.kis_vorschlag == "Kein Fieber; CRP 12 mg/l."


@pytest.mark.parametrize(
    ("abschnitt", "meldung"),
    [
        ("DOKUMENTTYP", "Pflichtabschnitt fehlt: DOKUMENTTYP"),
        ("AUSGELESENER INHALT", "Pflichtabschnitt fehlt: AUSGELESENER INHALT"),
        ("STRUKTURIERTE DARSTELLUNG", "Pflichtabschnitt fehlt: STRUKTURIERTE DARSTELLUNG"),
        ("KIS-VORSCHLAG", "Pflichtabschnitt fehlt: KIS-VORSCHLAG"),
    ],
)
def test_fehlender_abschnitt_ist_fehler(abschnitt: str, meldung: str) -> None:
    text = _antwort()
    start = text.index(abschnitt + ":")
    ende = text.find("\n\n", start)
    if ende == -1:
        ende = len(text)
    with pytest.raises(DokumentAntwortFehler, match=meldung):
        parse_dokumentantwort(text[:start] + text[ende:])


def test_unbekannter_typ_hat_keinen_fallback() -> None:
    with pytest.raises(DokumentAntwortFehler, match="Unbekannter Dokumenttyp"):
        parse_dokumentantwort(_antwort().replace("Arztbrief", "Entlassschein", 1))


def test_leerer_abschnitt_ist_fehler() -> None:
    text = _antwort().replace("Kein Fieber, CRP 12 mg/l.", "", 1)
    with pytest.raises(DokumentAntwortFehler, match="Pflichtabschnitt ist leer"):
        parse_dokumentantwort(text)


def test_doppelte_und_falsche_reihenfolge_sind_fehler() -> None:
    with pytest.raises(DokumentAntwortFehler, match="mehrfach vorhanden"):
        parse_dokumentantwort(_antwort() + "\nDOKUMENTTYP:\nArztbrief")
    teile = _antwort().split("\n\n")
    with pytest.raises(DokumentAntwortFehler, match="widersprüchlich angeordnet"):
        parse_dokumentantwort("\n\n".join([teile[0], teile[2], teile[1], teile[3]]))


def test_prompt_enthaelt_vorlagen_und_sicherheitsregeln() -> None:
    for text in (
        "Diagnosen", "Parameter | Ergebnis | Einheit |", "Medikament/Wirkstoff",
        "Einnahmeschema", "Indikation", "Körperregion", "Beurteilung",
        "Stuhlfrequenz", "Bauchschmerzen VAS", "anatomische Skizzen",
    ):
        assert text in FORMATVORGABEN
    for text in (
        "Keine Angaben ergänzen", "Keine Diagnosen", "Laborwerte nicht interpretieren",
        "Zahlen", "Einheiten", "Negationen", "`kein`, `nicht`, `ohne`",
        "wahrscheinliche Dokumentreihenfolge", "sequentiell zusammengefügtes Dokument",
    ):
        assert text in WORKFLOW_PROMPT


def test_mehrseitiges_dokument_erzeugt_genau_ein_gemeinsames_ergebnis(tmp_path: Path) -> None:
    seiten = []
    for nummer in range(3):
        pfad = tmp_path / f"seite{nummer}.png"
        pfad.write_bytes(b"bild")
        seiten.append(pfad)
    provider = OpenAICompatibleProvider("https://example.invalid", "modell", "key", "Test", max_images=2)
    teilantwort = Mock()
    teilantwort.raise_for_status.return_value = None
    teilantwort.json.return_value = {"choices": [{"message": {"content": "Transkription"}}]}
    finalantwort = Mock()
    finalantwort.raise_for_status.return_value = None
    finalantwort.json.return_value = {"choices": [{"message": {"content": _antwort()}}]}
    with patch(
        "ced_document_ai.services.ai.providers.requests.post",
        side_effect=[teilantwort, teilantwort, finalantwort],
    ) as post:
        ergebnis = provider.process_document(seiten)
    assert post.call_count == 3
    assert ergebnis.dokumenttyp is Dokumenttyp.ARZTBRIEF
    # Nur die letzte Anfrage enthält den Klassifikationsauftrag und damit genau ein Ergebnis.
    prompts = [call.kwargs["json"]["messages"][0]["content"][0]["text"] for call in post.call_args_list]
    assert sum("DOKUMENTTYP:" in prompt for prompt in prompts) == 1
    assert "technischen Upload-Reihenfolge" in prompts[-1]


def test_parserfehler_startet_keine_weitere_anfrage(tmp_path: Path) -> None:
    seite = tmp_path / "seite.png"
    seite.write_bytes(b"bild")
    provider = OpenAICompatibleProvider("https://example.invalid", "modell", "key", "Test")
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": "kaputt"}}]}
    with patch("ced_document_ai.services.ai.providers.requests.post", return_value=response) as post:
        with pytest.raises(DokumentAntwortFehler):
            provider.process_document([seite])
    assert post.call_count == 1
