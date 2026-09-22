"""Deterministischer Reintextparser für Labor, Virologie und Mikrobiologie.

Der Parser verarbeitet ausschließlich klar beschriftete Tabellenzeilen oder
``Parameter: Wert``-Zeilen aus der bereits vorhandenen strukturierten Darstellung.
Er interpretiert keine Befunde, ergänzt keine Referenzbereiche und normalisiert
keine medizinischen Aussagen. Unbekannte Parameter bleiben als ausgeschaltete
Kategorievorschläge für die manuelle Prüfung sichtbar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime

from ced_document_ai.database.models import ConfidenceStatus


LABORDOKUMENTTYPEN = frozenset(
    {
        "Laborbefund",
        "Virologischer Befund",
        "Mikrobiologischer Befund",
        "Calprotectin-Befund",
    }
)


@dataclass(frozen=True)
class ExtrahierterLaborwert:
    """Ein temporärer Laborwert vor jeder dauerhaften Speicherung."""

    kategorie: str
    anzeigewert: str
    numerischer_wert: float | None
    einheit: str | None
    referenzbereich: str | None
    befunddatum: date | None
    quelltext: str
    fachgruppe: str
    qualitaet: ConfidenceStatus
    neue_kategorie: bool
    uebernehmen: bool
    pruefhinweis: str = ""


def _normalisiere(text: str) -> str:
    """Normalisiert ausschließlich zum Katalogvergleich, nie zur Anzeige."""

    zerlegt = unicodedata.normalize("NFKD", text)
    ohne_akzente = "".join(
        zeichen for zeichen in zerlegt if not unicodedata.combining(zeichen)
    )
    return re.sub(r"[^a-z0-9]+", " ", ohne_akzente.casefold()).strip()


# Der initiale Katalog bleibt bewusst klein und technisch. Weitere eindeutig
# beschriftete Parameter erscheinen als Vorschlag, statt einem ähnlich klingenden
# Eintrag zugeordnet zu werden. Die typische Einheit dient nur als Prüfhinweis.
_KATALOGDATEN: dict[str, tuple[tuple[str, ...], str | None, str]] = {
    "CRP": (("CRP", "C-reaktives Protein"), "mg/l", "Labor"),
    "Hämoglobin": (("Hämoglobin", "Haemoglobin", "Hb"), "g/dl", "Labor"),
    "Leukozyten": (("Leukozyten", "Leukos"), "Gpt/l", "Labor"),
    "Thrombozyten": (("Thrombozyten", "Thrombos"), "Gpt/l", "Labor"),
    "Ferritin": (("Ferritin",), "µg/l", "Labor"),
    "Vitamin B12": (("Vitamin B12", "Cobalamin"), "pg/ml", "Labor"),
    "Folsäure": (("Folsäure", "Folsaeure"), "ng/ml", "Labor"),
    "Albumin": (("Albumin",), "g/l", "Labor"),
    "Kreatinin": (("Kreatinin",), "mg/dl", "Labor"),
    "ALT": (("ALT", "GPT"), "U/l", "Labor"),
    "AST": (("AST", "GOT"), "U/l", "Labor"),
    "Gamma-GT": (("Gamma-GT", "GGT"), "U/l", "Labor"),
    "Fäkales Calprotectin": (
        ("Fäkales Calprotectin", "Calprotectin", "Calprotectin im Stuhl"),
        "µg/g",
        "Calprotectin",
    ),
}

_ALIASDATEN = {
    _normalisiere(alias): (name, einheit, gruppe)
    for name, (aliase, einheit, gruppe) in _KATALOGDATEN.items()
    for alias in aliase
}

_METADATEN = {
    _normalisiere(name)
    for name in (
        "Patient",
        "Patienten-ID",
        "Vorname",
        "Nachname",
        "Name",
        "Geburtsdatum",
        "Befunddatum",
        "Entnahmedatum",
        "Auftragsdatum",
        "Auftragsnummer",
        "Berichtsdatum",
        "Probeneingang",
        "Abnahmezeit",
        "Fall-Nr",
        "Methode",
        "Material",
        "Kommentar",
        "Kommentare",
        "Technische Hinweise",
    )
}

_UNLESERLICH = {"unleserlich", "nicht lesbar", "nicht erkennbar"}
_ZAHL = re.compile(r"(?<![\w])([<>≤≥]?\s*-?\d+(?:[.,]\d+)?)")
_WERT_MIT_EINHEIT = re.compile(
    r"^\s*(?P<wert>[<>≤≥]?\s*-?\d+(?:[.,]\d+)?)\s*(?P<einheit>[^\d\s].*?)?\s*$"
)
_DATUM = re.compile(r"(?<!\d)(\d{1,2}[./]\d{1,2}[./]\d{4}|\d{4}-\d{2}-\d{2})(?!\d)")


def _fachgruppe_fuer_unbekannten_parameter(dokumenttyp: str) -> str:
    """Bestimmt nur die Dokumentgruppe, nicht die medizinische Bedeutung."""

    if dokumenttyp == "Calprotectin-Befund":
        return "Calprotectin"
    return "Labor"


def _zerlege_tabellenzeile(zeile: str) -> tuple[str, str, str, str] | None:
    """Liest eine Markdown-/Texttabelle ohne Spalteninhalte zu erraten."""

    if "|" not in zeile:
        return None
    zellen = [zelle.strip() for zelle in zeile.strip().strip("|").split("|")]
    if len(zellen) < 2:
        return None
    if all(not zelle or set(zelle) <= {"-", ":"} for zelle in zellen):
        return None
    if _normalisiere(zellen[0]) in {"parameter", "analyt", "untersuchung", "test"}:
        return None
    zellen.extend([""] * (4 - len(zellen)))
    return zellen[0], zellen[1], zellen[2], zellen[3]


def _tabellenzellen(zeile: str) -> list[str] | None:
    """Gibt alle Zellen einer echten Tabellenzeile unverändert zurück."""

    if "|" not in zeile:
        return None
    zellen = [zelle.strip() for zelle in zeile.strip().strip("|").split("|")]
    if len(zellen) < 2:
        return None
    if all(not zelle or set(zelle) <= {"-", ":"} for zelle in zellen):
        return None
    return zellen


def _parse_datum(text: str) -> date | None:
    """Liest genau ein vorhandenes Datum aus einer Tabellenzelle."""

    treffer = _DATUM.search(text)
    if treffer is None:
        return None
    rohdatum = treffer.group(1)
    formatierung = (
        "%Y-%m-%d"
        if "-" in rohdatum
        else "%d.%m.%Y"
        if "." in rohdatum
        else "%d/%m/%Y"
    )
    try:
        return datetime.strptime(rohdatum, formatierung).date()
    except ValueError:
        return None


def _zerlege_beschriftete_zeile(zeile: str) -> tuple[str, str, str, str] | None:
    """Liest ausschließlich Zeilen mit einem eindeutigen Doppelpunkt-Trenner."""

    if ":" not in zeile:
        return None
    parameter, wert = (teil.strip() for teil in zeile.split(":", 1))
    if not parameter or not wert:
        return None
    treffer = _WERT_MIT_EINHEIT.match(wert)
    if treffer:
        return parameter, treffer.group("wert").strip(), (treffer.group("einheit") or "").strip(), ""
    return parameter, wert, "", ""


def _numerischer_wert(wert: str) -> float | None:
    """Extrahiert eine vorhandene Zahl, ohne Grenzzeichen oder Anzeige zu verändern."""

    treffer = _ZAHL.search(wert)
    if treffer is None:
        return None
    zahl = re.sub(r"^[<>≤≥]\s*", "", treffer.group(1)).replace(",", ".")
    try:
        return float(zahl)
    except ValueError:
        return None


def parse_laborbefund(
    text: str,
    dokumenttyp: str,
    *,
    bestehende_kategorien: tuple[tuple[str, str | None, str], ...] = (),
) -> list[ExtrahierterLaborwert]:
    """Parst beschriftete Laborzeilen und markiert Konflikte nachvollziehbar.

    Der Dokumenttyp muss bereits durch den allgemeinen Workflow bestätigt sein.
    Für andere Dokumenttypen wird bewusst nicht versuchsweise geparst.
    """

    if dokumenttyp not in LABORDOKUMENTTYPEN:
        raise ValueError(f"Dokumenttyp {dokumenttyp!r} ist kein unterstützter Laborpfad.")
    # Bereits bestätigte dynamische Kategorien werden zusätzlich zum festen
    # Anfangskatalog berücksichtigt. Erwartet werden Name, typische Einheit und
    # Fachgruppe. Andere Gruppen werden nicht in den Laborpfad hineingezogen.
    vorhandene_aliasdaten = {
        _normalisiere(name): (name, einheit, gruppe)
        for name, einheit, gruppe in bestehende_kategorien
        if gruppe in {"Labor", "Calprotectin"} and name.strip()
    }
    ergebnisse: list[ExtrahierterLaborwert] = []
    positionen: dict[tuple[str, date | None], list[int]] = {}
    # Manche Laborblätter enthalten mehrere historische Messspalten. Die explizit
    # beschriftete Zeile „Abnahme-/Entnahmedatum“ ordnet jede Ergebnisspalte ihrem
    # eigenen Datum zu. Ohne eine solche Zeile bleibt der bisherige vier-spaltige
    # Einzelwertparser aktiv; es wird nicht anhand der Spaltenposition geraten.
    messdaten_nach_spalte: dict[int, date] = {}
    for rohzeile in text.splitlines():
        zeile = rohzeile.strip()
        if not zeile:
            continue
        zellen = _tabellenzellen(zeile)
        if (
            zellen is not None
            and _normalisiere(zellen[0]) == "datum"
            and len(zellen) > 1
            and _normalisiere(zellen[1]) in {"parameter", "analyt", "untersuchung", "test"}
        ):
            continue
        if zellen is not None and _normalisiere(zellen[0]) in {
            "abnahmedatum",
            "entnahmedatum",
            "befunddatum",
            "messdatum",
        }:
            messdaten_nach_spalte = {
                index: datum
                for index, zelle in enumerate(zellen[1:], start=1)
                if (datum := _parse_datum(zelle)) is not None
            }
            continue
        matrixwerte: list[tuple[str, str, str, str, date | None]] = []
        zeilendatum = _parse_datum(zellen[0]) if zellen is not None else None
        if zellen is not None and zeilendatum is not None and len(zellen) >= 5:
            # Bevorzugtes Langformat aus dem aktuellen KI-Prompt: jeder Messwert
            # trägt sein Datum direkt in derselben Zeile.
            matrixwerte = [(zellen[1], zellen[2], zellen[3], zellen[4], zeilendatum)]
        elif zellen is not None and messdaten_nach_spalte:
            if len(zellen) < 4:
                continue
            parameter = zellen[0]
            referenzbereich = zellen[1]
            einheit = zellen[2]
            matrixwerte = [
                (parameter, zellen[index], einheit, referenzbereich, datum)
                for index, datum in sorted(messdaten_nach_spalte.items())
                if index < len(zellen) and zellen[index].strip()
            ]
        else:
            zerlegt = _zerlege_tabellenzeile(zeile) or _zerlege_beschriftete_zeile(zeile)
            if zerlegt is None:
                continue
            parameter, wert, einheit, referenzbereich = zerlegt
            matrixwerte = [(parameter, wert, einheit, referenzbereich, None)]

        for parameter, wert, einheit, referenzbereich, befunddatum in matrixwerte:
            _ergaenze_laborwert(
                ergebnisse,
                positionen,
                parameter=parameter,
                wert=wert,
                einheit=einheit,
                referenzbereich=referenzbereich,
                befunddatum=befunddatum,
                quelltext=zeile,
                dokumenttyp=dokumenttyp,
                vorhandene_aliasdaten=vorhandene_aliasdaten,
            )

    for indizes in positionen.values():
        if len(indizes) < 2:
            continue
        unterschiedliche_werte = {
            (ergebnisse[index].anzeigewert, ergebnisse[index].einheit)
            for index in indizes
        }
        if len(unterschiedliche_werte) < 2:
            continue
        for index in indizes:
            vorhanden = ergebnisse[index]
            ergebnisse[index] = replace(
                vorhanden,
                qualitaet=ConfidenceStatus.CONFLICT,
                uebernehmen=False,
                pruefhinweis=(
                    vorhanden.pruefhinweis + " Widersprüchliche Doppelangabe im Dokument."
                ).strip(),
            )
    return ergebnisse


def _ergaenze_laborwert(
    ergebnisse: list[ExtrahierterLaborwert],
    positionen: dict[tuple[str, date | None], list[int]],
    *,
    parameter: str,
    wert: str,
    einheit: str,
    referenzbereich: str,
    befunddatum: date | None,
    quelltext: str,
    dokumenttyp: str,
    vorhandene_aliasdaten: dict[str, tuple[str, str | None, str]],
) -> None:
    """Erzeugt genau einen Laborwert aus bereits eindeutig getrennten Zellen."""

    normalisiert = _normalisiere(parameter)
    if normalisiert in _METADATEN:
        return
    katalog = _ALIASDATEN.get(normalisiert) or vorhandene_aliasdaten.get(normalisiert)
    if katalog is None:
        kategorie = parameter
        typische_einheit = None
        fachgruppe = _fachgruppe_fuer_unbekannten_parameter(dokumenttyp)
        neue_kategorie = True
    else:
        kategorie, typische_einheit, fachgruppe = katalog
        neue_kategorie = False
    qualitaet = ConfidenceStatus.HIGH_CONFIDENCE
    uebernehmen = not neue_kategorie
    hinweise: list[str] = []
    if _normalisiere(wert) in _UNLESERLICH:
        qualitaet = ConfidenceStatus.UNREADABLE
        uebernehmen = False
        hinweise.append("Wert ist als unleserlich gekennzeichnet.")
    if neue_kategorie:
        qualitaet = ConfidenceStatus.UNCERTAIN
        hinweise.append("Neue Kategorie: Bezeichnung vor Übernahme ausdrücklich prüfen.")
    if typische_einheit and not einheit:
        qualitaet = ConfidenceStatus.UNCERTAIN
        uebernehmen = False
        hinweise.append(f"Erwartete Einheit {typische_einheit!r} fehlt.")
    elif typische_einheit and _normalisiere(einheit) != _normalisiere(typische_einheit):
        qualitaet = ConfidenceStatus.UNCERTAIN
        uebernehmen = False
        hinweise.append(
            f"Einheit {einheit!r} weicht von der hinterlegten Einheit {typische_einheit!r} ab."
        )
    ergebnis = ExtrahierterLaborwert(
        kategorie=kategorie,
        anzeigewert=wert,
        numerischer_wert=_numerischer_wert(wert),
        einheit=einheit or None,
        referenzbereich=referenzbereich or None,
        befunddatum=befunddatum,
        quelltext=quelltext,
        fachgruppe=fachgruppe,
        qualitaet=qualitaet,
        neue_kategorie=neue_kategorie,
        uebernehmen=uebernehmen,
        pruefhinweis=" ".join(hinweise),
    )
    positionen.setdefault((_normalisiere(kategorie), befunddatum), []).append(len(ergebnisse))
    ergebnisse.append(ergebnis)
