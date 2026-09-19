"""Kontrollierter Katalog für patientenbezogene medizinische Dokumentklassen.

Die Dokumentklasse bestimmt, in welchem Bereich ein bestätigtes Dokument später
sichtbar ist. Sie ist absichtlich von einzelnen Befundparametern getrennt: Ein
Virologiebefund kann beispielsweise unter ``Labor`` angezeigt werden, ohne dass aus
seinem Freitext ungeprüfte Laborwerte erzeugt werden.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dokumentklasse:
    """Eine erlaubte Dokumentbezeichnung und ihre sichtbare Fachgruppe."""

    dokumenttyp: str
    fachgruppe: str


# Häufige Dokumentklassen werden ausdrücklich hinterlegt. Eine neue, von einem
# späteren Parser gelieferte präzise Bezeichnung bleibt dennoch als Dokumenttyp in
# der Datenbank erhalten und erscheint unter „Weitere Befunde“. So wird sie nicht
# vorschnell zur unspezifischen Klasse „Andere Befunde“ umbenannt.
DOKUMENTKLASSEN: tuple[Dokumentklasse, ...] = (
    Dokumentklasse("CED-Patientenfragebogen", "CED-Fragebogen"),
    Dokumentklasse("Laborbefund", "Labor"),
    Dokumentklasse("Virologischer Befund", "Labor"),
    Dokumentklasse("Mikrobiologischer Befund", "Labor"),
    Dokumentklasse("Calprotectin-Befund", "Calprotectin"),
    Dokumentklasse("Endoskopiebefund", "Endoskopie"),
    Dokumentklasse("Sonografiebefund", "Sonografie"),
    Dokumentklasse("MRT-Befund", "MRT"),
    Dokumentklasse("CT-Befund", "CT"),
    Dokumentklasse("Röntgenbefund", "Röntgen"),
    Dokumentklasse("Pathologiebefund", "Pathologie"),
    Dokumentklasse("Funktionsdiagnostischer Befund", "Funktionsdiagnostik"),
    Dokumentklasse("Arztbrief", "Arztbriefe"),
    Dokumentklasse("Medikamentenplan", "Medikation"),
    Dokumentklasse("Bildgebender Befund", "Bildgebung"),
    Dokumentklasse("sonstiges medizinisches Dokument", "Weitere Befunde"),
)

_FACHGRUPPE_NACH_TYP = {
    dokumentklasse.dokumenttyp: dokumentklasse.fachgruppe
    for dokumentklasse in DOKUMENTKLASSEN
}


def ermittle_dokumentfachgruppe(dokumenttyp: str) -> str:
    """Ordnet einen gespeicherten Dokumenttyp einer sichtbaren Fachgruppe zu.

    Unbekannte, aber bereits gespeicherte Typen behalten ihre konkrete Bezeichnung
    und werden lediglich in der Sammelansicht sichtbar gemacht. Zum Debuggen sollte
    die unbekannte Bezeichnung lokal gegen ``DOKUMENTKLASSEN`` geprüft werden; eine
    automatische Umbenennung oder medizinische Interpretation findet nicht statt.
    """

    normalisiert = dokumenttyp.strip()
    if not normalisiert:
        raise ValueError("Ein leerer Dokumenttyp kann keiner Fachgruppe zugeordnet werden.")
    return _FACHGRUPPE_NACH_TYP.get(normalisiert, "Weitere Befunde")
