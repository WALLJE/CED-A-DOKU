"""Lokale Erkennung und Zuordnung von Patientenstammdaten.

Die KI-Ausgabe enthält bereits den möglichst originalgetreu gelesenen Dokumenttext.
Dieses Modul wertet ausschließlich ausdrücklich beschriftete Stammdatenzeilen daraus
aus. Das Patientenverzeichnis wird dabei niemals an einen KI-Anbieter übertragen.

Wichtig: Ein Treffer ist stets nur ein Vorschlag. Die Oberfläche muss ihn vor jeder
patientenbezogenen Verarbeitung durch einen Menschen bestätigen lassen. Unklare oder
widersprüchliche Daten werden nicht durch Annahmen oder Ersatzwerte vervollständigt.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Protocol


class PatientMitStammdaten(Protocol):
    """Kleinste für den lokalen Abgleich benötigte Patientenschnittstelle."""

    id: int
    external_id: str | None
    name: str
    birth_date: date | None


def _patientenname(patient: PatientMitStammdaten) -> str:
    """Verwendet getrennte Namen, ohne einen bestehenden Gesamtnamen zu zerlegen."""
    vorname = getattr(patient, "first_name", None)
    nachname = getattr(patient, "last_name", None)
    if nachname and vorname:
        return f"{nachname}, {vorname}"
    return patient.name


def _namen_fuer_abgleich(patient: PatientMitStammdaten) -> tuple[str, ...]:
    """Erlaubt nur explizit gespeicherte Schreibweisen beim lokalen Vergleich."""
    vorname = getattr(patient, "first_name", None)
    nachname = getattr(patient, "last_name", None)
    werte = [patient.name]
    if nachname and vorname:
        werte.extend((f"{vorname} {nachname}", f"{nachname}, {vorname}"))
    return tuple(werte)


@dataclass(frozen=True)
class ErkanntePatientendaten:
    """Unveränderte, ausdrücklich beschriftete Stammdaten aus einem Dokument."""

    externe_id: str | None = None
    name: str | None = None
    vorname: str | None = None
    nachname: str | None = None
    geburtsdatum: date | None = None

    @property
    def ausreichend_fuer_vorschlag(self) -> bool:
        """Verhindert einen Patientenvorschlag allein aufgrund eines Namens."""
        return bool(self.externe_id or (self.name and self.geburtsdatum))


@dataclass(frozen=True)
class Patiententreffer:
    """Nachvollziehbarer lokaler Treffer ohne automatische Zuordnungsentscheidung."""

    patient_id: int
    bezeichnung: str
    status: str
    begruendung: tuple[str, ...]
    widerspruch: bool = False


# Die Muster sind absichtlich eng gefasst: Nur eine klar beschriftete Zeile wird
# übernommen. Für lokales Debugging kann die Liste der erkannten Feldnamen ausgegeben
# werden; vollständige Dokumenttexte oder Patientenwerte gehören nicht in Logs.
_FELDMUSTER = {
    "externe_id": re.compile(
        r"(?im)^\s*(?:patient(?:en)?[- ]?(?:id|nr\.?|nummer)|pat\.?[- ]?nr\.?)\s*:\s*(\S.*?)\s*$"
    ),
    "name": re.compile(
        r"(?im)^\s*(?:patient(?:in)?|name|patientenname)\s*:\s*([^\n\r]+?)\s*$"
    ),
    "vorname": re.compile(r"(?im)^\s*(?:vorname[n]?)\s*:\s*([^\n\r]+?)\s*$"),
    "nachname": re.compile(
        r"(?im)^\s*(?:nachname|familienname)\s*:\s*([^\n\r]+?)\s*$"
    ),
    "geburtsdatum": re.compile(
        r"(?im)^\s*(?:geburtsdatum|geb\.?\s*(?:am|datum)?)\s*:\s*([^\n\r]+?)\s*$"
    ),
}


def _erster_wert(text: str, feld: str) -> str | None:
    """Liefert den ersten eindeutigen Wert; mehrere verschiedene Werte sind unklar."""
    werte = [treffer.group(1).strip() for treffer in _FELDMUSTER[feld].finditer(text)]
    eindeutige_werte = list(dict.fromkeys(wert for wert in werte if wert))
    return eindeutige_werte[0] if len(eindeutige_werte) == 1 else None


def _parse_datum(wert: str | None) -> date | None:
    """Akzeptiert nur geläufige vollständige Datumsformate, ohne das Datum zu raten."""
    if not wert:
        return None
    for formatierung in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(wert.strip(), formatierung).date()
        except ValueError:
            continue
    return None


def erkenne_patientendaten(text: str) -> ErkanntePatientendaten:
    """Extrahiert nur eindeutig beschriftete Patientenmerkmale aus dem Rohtext."""
    vorname = _erster_wert(text or "", "vorname")
    nachname = _erster_wert(text or "", "nachname")
    gesamtname = _erster_wert(text or "", "name")
    if gesamtname is None and vorname and nachname:
        # Beide Bestandteile sind ausdrücklich beschriftet; ihre Kombination ist
        # daher keine geratenen Namensaufteilung.
        gesamtname = f"{vorname} {nachname}"
    return ErkanntePatientendaten(
        externe_id=_erster_wert(text or "", "externe_id"),
        name=gesamtname,
        vorname=vorname,
        nachname=nachname,
        geburtsdatum=_parse_datum(_erster_wert(text or "", "geburtsdatum")),
    )


def _normalisiere(wert: str | None) -> str:
    """Normalisiert Schreibweise für Vergleiche, verändert aber keinen Speicherwert."""
    ohne_akzente = unicodedata.normalize("NFKD", wert or "")
    return " ".join(
        "".join(zeichen for zeichen in ohne_akzente if not unicodedata.combining(zeichen))
        .casefold()
        .split()
    )


def ermittle_patiententreffer(
    erkannt: ErkanntePatientendaten,
    patienten: Iterable[PatientMitStammdaten],
) -> list[Patiententreffer]:
    """Ermittelt lokale Vorschläge und kennzeichnet Stammdatenwidersprüche deutlich."""
    if not erkannt.ausreichend_fuer_vorschlag:
        return []

    treffer: list[tuple[int, Patiententreffer]] = []
    for patient in patienten:
        id_gleich = bool(
            erkannt.externe_id
            and _normalisiere(erkannt.externe_id) == _normalisiere(patient.external_id)
        )
        name_gleich = bool(
            erkannt.name
            and any(
                _normalisiere(erkannt.name) == _normalisiere(name)
                for name in _namen_fuer_abgleich(patient)
            )
        )
        geburt_gleich = bool(
            erkannt.geburtsdatum and erkannt.geburtsdatum == patient.birth_date
        )
        id_widerspruch = bool(
            id_gleich
            and (
                (erkannt.name and not name_gleich)
                or (erkannt.geburtsdatum and not geburt_gleich)
            )
        )

        gruende: list[str] = []
        if id_gleich:
            gruende.append("Patienten-ID stimmt überein")
        if name_gleich:
            gruende.append("Name stimmt überein")
        if geburt_gleich:
            gruende.append("Geburtsdatum stimmt überein")
        if id_widerspruch:
            gruende.append("Stammdaten widersprechen der identischen Patienten-ID")

        # Ein Name allein erzeugt absichtlich keinen Vorschlag. Entweder stimmt die
        # eindeutige ID oder die Kombination aus Name und Geburtsdatum überein.
        if not id_gleich and not (name_gleich and geburt_gleich):
            continue
        status = (
            "Widerspruch"
            if id_widerspruch
            else "Eindeutiger Treffer"
            if id_gleich and name_gleich and geburt_gleich
            else "Sehr wahrscheinlicher Treffer"
        )
        prioritaet = 0 if id_widerspruch else 1 if status == "Eindeutiger Treffer" else 2
        treffer.append(
            (
                prioritaet,
                Patiententreffer(
                    patient_id=patient.id,
                    bezeichnung=f"{patient.external_id or 'ohne ID'} · {_patientenname(patient)} · "
                    f"{patient.birth_date.strftime('%d.%m.%Y') if patient.birth_date else 'ohne Geburtsdatum'}",
                    status=status,
                    begruendung=tuple(gruende),
                    widerspruch=id_widerspruch,
                ),
            )
        )
    return [eintrag for _, eintrag in sorted(treffer, key=lambda element: element[0])]
