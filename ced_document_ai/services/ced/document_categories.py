"""Kontrollierter Katalog für patientenbezogene medizinische Dokumentklassen.

Die Dokumentklasse bestimmt, in welchem Bereich ein bestätigtes Dokument später
sichtbar ist. Sie ist absichtlich von einzelnen Befundparametern getrennt: Ein
Virologiebefund kann beispielsweise unter ``Labor`` angezeigt werden, ohne dass aus
seinem Freitext ungeprüfte Laborwerte erzeugt werden.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StandardFachgruppe:
    """Einmalige Seed-Definition; zur Laufzeit gilt die Datenbanktabelle."""

    schluessel: str
    anzeigename: str
    reihenfolge: int


STANDARD_FACHGRUPPEN: tuple[StandardFachgruppe, ...] = (
    StandardFachgruppe("ced", "CED-Fragebogen", 10),
    StandardFachgruppe("labor", "Labor", 20),
    StandardFachgruppe("calprotectin", "Calprotectin", 30),
    StandardFachgruppe("endoskopie", "Endoskopie", 40),
    StandardFachgruppe("sonografie", "Sonografie", 50),
    StandardFachgruppe("mrt", "MRT", 60),
    StandardFachgruppe("ct", "CT", 70),
    StandardFachgruppe("roentgen", "Röntgen", 80),
    StandardFachgruppe("bildgebung", "Bildgebung", 90),
    StandardFachgruppe("pathologie", "Pathologie", 100),
    StandardFachgruppe("funktionsdiagnostik", "Funktionsdiagnostik", 110),
    StandardFachgruppe("arztbriefe", "Arztbriefe", 120),
    StandardFachgruppe("medikation", "Medikation", 130),
    StandardFachgruppe("weitere", "Weitere Befunde", 999),
)


@dataclass(frozen=True)
class Dokumentklasse:
    """Eine erlaubte Dokumentbezeichnung und ihre sichtbare Fachgruppe."""

    dokumenttyp: str
    fachgruppe: str
    beschreibung: str
    merkmale: str
    parser_schluessel: str | None
    reihenfolge: int


# Häufige Dokumentklassen werden ausdrücklich hinterlegt. Eine neue, von einem
# späteren Parser gelieferte präzise Bezeichnung bleibt dennoch als Dokumenttyp in
# der Datenbank erhalten und erscheint unter „Weitere Befunde“. So wird sie nicht
# vorschnell zur unspezifischen Klasse „Andere Befunde“ umbenannt.
DOKUMENTKLASSEN: tuple[Dokumentklasse, ...] = (
    Dokumentklasse("CED-Patientenfragebogen", "CED-Fragebogen", "Strukturierter CED-Fragebogen.", "Stuhlfrequenz; Bauchschmerzen; Allgemeinbefinden; Gewicht", "ced_questionnaire", 10),
    Dokumentklasse("Laborbefund", "Labor", "Allgemeiner medizinischer Laborbefund.", "Parameter; Ergebnis; Einheit; Referenzbereich", "laboratory", 10),
    Dokumentklasse("Virologischer Befund", "Labor", "Virologische Laboruntersuchung.", "PCR; Viruslast; Virusnachweis; Material; Nachweisgrenze", "laboratory", 20),
    Dokumentklasse("Mikrobiologischer Befund", "Labor", "Mikrobiologischer Erregerbefund.", "Material; Erreger; Kultur; Resistenz; Antibiogramm", "laboratory", 30),
    Dokumentklasse("Calprotectin-Befund", "Calprotectin", "Fäkaler Calprotectin-Laborbefund.", "Calprotectin; Stuhlprobe; Ergebnis; Einheit; Referenzbereich", "laboratory", 10),
    Dokumentklasse("Endoskopiebefund", "Endoskopie", "Bericht einer gastrointestinalen Endoskopie.", "Endoskopie; Schleimhaut; Histologie; SES-CD; CDEIS; UCEIS", "endoscopy", 10),
    Dokumentklasse("Sonografiebefund", "Sonografie", "Sonografischer Untersuchungsbericht.", "Sonografie; Körperregion; Messung; Befund; Beurteilung", "sonography", 10),
    Dokumentklasse("MRT-Befund", "MRT", "Magnetresonanztomografischer Befund.", "MRT; MR; Sequenz; Körperregion; Befund; Beurteilung", None, 10),
    Dokumentklasse("CT-Befund", "CT", "Computertomografischer Befund.", "CT; Kontrastmittel; Körperregion; Befund; Beurteilung", None, 10),
    Dokumentklasse("Röntgenbefund", "Röntgen", "Konventioneller radiologischer Befund.", "Röntgen; Projektion; Körperregion; Befund; Beurteilung", None, 10),
    Dokumentklasse("Pathologiebefund", "Pathologie", "Histologischer oder pathologischer Bericht.", "Material; Makroskopie; Mikroskopie; Histologie; Beurteilung", None, 10),
    Dokumentklasse("Funktionsdiagnostischer Befund", "Funktionsdiagnostik", "Bericht einer medizinischen Funktionsmessung.", "Untersuchung; Messverfahren; Messwerte; Befund; Beurteilung", None, 10),
    Dokumentklasse("Arztbrief", "Arztbriefe", "Ärztlicher Bericht oder Entlassbrief.", "Diagnosen; Anamnese; Verlauf; Therapie; Empfehlung", "letter", 10),
    Dokumentklasse("Medikamentenplan", "Medikation", "Plan der aktuellen Medikation.", "Präparat; Wirkstoff; Stärke; Dosis; Einnahmeschema", None, 10),
    Dokumentklasse("Bildgebender Befund", "Bildgebung", "Bildgebender Befund ohne eindeutige Modalität.", "Untersuchung; Körperregion; Technik; Befund; Beurteilung", None, 10),
    Dokumentklasse("sonstiges medizinisches Dokument", "Weitere Befunde", "Medizinisches Dokument ohne präzisere Klasse.", "medizinischer Kontext; keine passendere aktive Dokumentklasse", None, 999),
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
    if normalisiert in _FACHGRUPPE_NACH_TYP:
        return _FACHGRUPPE_NACH_TYP[normalisiert]
    raise ValueError(
        "Der Dokumenttyp besitzt keine persistente Fachgruppe. "
        "Bitte den Katalogeintrag prüfen; es gibt keinen Sammelgruppen-Fallback."
    )
