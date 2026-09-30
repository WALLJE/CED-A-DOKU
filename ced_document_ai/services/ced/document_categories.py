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
    beschreibung: str
    merkmale: str


# Häufige Dokumentklassen werden ausdrücklich hinterlegt. Eine neue, von einem
# späteren Parser gelieferte präzise Bezeichnung bleibt dennoch als Dokumenttyp in
# der Datenbank erhalten und erscheint unter „Weitere Befunde“. So wird sie nicht
# vorschnell zur unspezifischen Klasse „Andere Befunde“ umbenannt.
DOKUMENTKLASSEN: tuple[Dokumentklasse, ...] = (
    Dokumentklasse("CED-Patientenfragebogen", "CED-Fragebogen", "Strukturierter CED-Fragebogen.", "Stuhlfrequenz; Bauchschmerzen; Allgemeinbefinden; Gewicht"),
    Dokumentklasse("Laborbefund", "Labor", "Allgemeiner medizinischer Laborbefund.", "Parameter; Ergebnis; Einheit; Referenzbereich"),
    Dokumentklasse("Virologischer Befund", "Labor", "Virologische Laboruntersuchung.", "PCR; Viruslast; Virusnachweis; Material; Nachweisgrenze"),
    Dokumentklasse("Mikrobiologischer Befund", "Labor", "Mikrobiologischer Erregerbefund.", "Material; Erreger; Kultur; Resistenz; Antibiogramm"),
    Dokumentklasse("Calprotectin-Befund", "Calprotectin", "Fäkaler Calprotectin-Laborbefund.", "Calprotectin; Stuhlprobe; Ergebnis; Einheit; Referenzbereich"),
    Dokumentklasse("Endoskopiebefund", "Endoskopie", "Bericht einer gastrointestinalen Endoskopie.", "Endoskopie; Schleimhaut; Histologie; SES-CD; CDEIS; UCEIS"),
    Dokumentklasse("Sonografiebefund", "Sonografie", "Sonografischer Untersuchungsbericht.", "Sonografie; Körperregion; Messung; Befund; Beurteilung"),
    Dokumentklasse("MRT-Befund", "MRT", "Magnetresonanztomografischer Befund.", "MRT; MR; Sequenz; Körperregion; Befund; Beurteilung"),
    Dokumentklasse("CT-Befund", "CT", "Computertomografischer Befund.", "CT; Kontrastmittel; Körperregion; Befund; Beurteilung"),
    Dokumentklasse("Röntgenbefund", "Röntgen", "Konventioneller radiologischer Befund.", "Röntgen; Projektion; Körperregion; Befund; Beurteilung"),
    Dokumentklasse("Pathologiebefund", "Pathologie", "Histologischer oder pathologischer Bericht.", "Material; Makroskopie; Mikroskopie; Histologie; Beurteilung"),
    Dokumentklasse("Funktionsdiagnostischer Befund", "Funktionsdiagnostik", "Bericht einer medizinischen Funktionsmessung.", "Untersuchung; Messverfahren; Messwerte; Befund; Beurteilung"),
    Dokumentklasse("Arztbrief", "Arztbriefe", "Ärztlicher Bericht oder Entlassbrief.", "Diagnosen; Anamnese; Verlauf; Therapie; Empfehlung"),
    Dokumentklasse("Medikamentenplan", "Medikation", "Plan der aktuellen Medikation.", "Präparat; Wirkstoff; Stärke; Dosis; Einnahmeschema"),
    Dokumentklasse("Bildgebender Befund", "Bildgebung", "Bildgebender Befund ohne eindeutige Modalität.", "Untersuchung; Körperregion; Technik; Befund; Beurteilung"),
    Dokumentklasse("sonstiges medizinisches Dokument", "Weitere Befunde", "Medizinisches Dokument ohne präzisere Klasse.", "medizinischer Kontext; keine passendere aktive Dokumentklasse"),
)

_FACHGRUPPE_NACH_TYP = {
    dokumentklasse.dokumenttyp: dokumentklasse.fachgruppe
    for dokumentklasse in DOKUMENTKLASSEN
}


def ermittle_dokumentfachgruppe(dokumenttyp: str, *, gespeicherte_fachgruppe: str | None = None) -> str:
    """Ordnet einen gespeicherten Dokumenttyp einer sichtbaren Fachgruppe zu.

    Unbekannte, aber bereits gespeicherte Typen behalten ihre konkrete Bezeichnung
    und werden lediglich in der Sammelansicht sichtbar gemacht. Zum Debuggen sollte
    die unbekannte Bezeichnung lokal gegen ``DOKUMENTKLASSEN`` geprüft werden; eine
    automatische Umbenennung oder medizinische Interpretation findet nicht statt.
    """

    normalisiert = dokumenttyp.strip()
    if not normalisiert:
        raise ValueError("Ein leerer Dokumenttyp kann keiner Fachgruppe zugeordnet werden.")
    if gespeicherte_fachgruppe:
        return gespeicherte_fachgruppe
    return _FACHGRUPPE_NACH_TYP.get(normalisiert, "Weitere Befunde")
