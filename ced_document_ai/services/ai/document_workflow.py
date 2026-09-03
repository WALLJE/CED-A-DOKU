"""Zentraler, anbieterunabhängiger Arbeitsablauf für medizinische Dokumente.

Dieses Modul enthält bewusst sowohl den Arbeitsauftrag als auch dessen strikten
Parser. Dadurch verwenden Oberfläche, Provider und Tests dieselben Begriffe. Der
Parser repariert keine Antworten: Ein Formatfehler muss sichtbar werden, statt
medizinischen Inhalt unbemerkt einem falschen Feld zuzuordnen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Dokumenttyp(str, Enum):
    """Die einzigen Dokumenttypen, die der Workflow akzeptiert."""

    CED_FRAGEBOGEN = "CED-Patientenfragebogen"
    ARZTBRIEF = "Arztbrief"
    LABORBEFUND = "Laborbefund"
    MEDIKAMENTENPLAN = "Medikamentenplan"
    BILDGEBENDER_BEFUND = "Bildgebender Befund"
    SONSTIGES = "sonstiges medizinisches Dokument"


@dataclass(frozen=True)
class DokumentErgebnis:
    """Unveränderliches Ergebnis genau eines vollständig verarbeiteten Dokuments."""

    dokumenttyp: Dokumenttyp
    ausgelesener_inhalt: str
    strukturierte_darstellung: str
    kis_vorschlag: str


class DokumentAntwortFehler(ValueError):
    """Konkreter Formatfehler einer KI-Antwort (ohne medizinische Ersatzantwort)."""


FORMATVORGABEN = """
Dokumenttypspezifische strukturierte Darstellung:
- Arztbrief: Nur vorhandene Bereiche aus Diagnosen, Anamnese, klinische Befunde,
  Diagnostik, Verlauf, Therapie, Medikation und Empfehlungen/weiteres Vorgehen.
  Diagnosen stehen in einem eigenen klar gegliederten Bereich, nie versteckt im
  Fließtext. Haupt- und Nebendiagnosen nur unterscheiden, wenn das Original dies tut.
- Laborbefund: nach Möglichkeit Tabelle „Parameter | Ergebnis | Einheit |
  Referenzbereich“. Fehlende Zellen bleiben leer. Nur im Original vorhandene
  Referenzbereiche und Kennzeichnungen übernehmen. Kommentare, Materialangaben,
  Probenhinweise und technische Hinweise getrennt unterhalb der Tabelle ausgeben.
- Medikamentenplan: nach Möglichkeit Tabelle „Medikament/Wirkstoff | Stärke |
  Dosis | Einnahmeschema | Indikation | Bemerkung“. Handelsname und Wirkstoff nicht
  gegenseitig ergänzen; Freitext und Bedarfsmedikation nur wie im Original kennzeichnen.
- Bildgebender Befund: vorhandene Angaben gliedern in Untersuchung,
  Untersuchungsdatum, Körperregion, Technik, Befund, Beurteilung und Empfehlung.
  Beurteilung nur übernehmen, wenn sie im Dokument enthalten ist.
- CED-Patientenfragebogen: vorhandene Angaben strukturieren nach Stuhlfrequenz,
  Stuhlgang nachts, Blut im Stuhl, Schleim im Stuhl, Bauchschmerzen,
  Bauchschmerzen VAS, Allgemeinbefinden, Allgemeinbefinden Skalenwert, Gewicht,
  Gewichtsverlust, Fieber, Nachtschweiß, Gelenkschmerzen, Hautveränderungen,
  Auffälligkeiten Analregion, aktuelle Medikamente, neue Aspekte und Fragen des
  Patienten. Visuelle Markierungen, Skalen und anatomische Skizzen berücksichtigen.
  Strukturierte Fragebogendaten und KIS-Vorschlag strikt getrennt halten.
- sonstiges medizinisches Dokument: Überschriften und Gliederung möglichst
  beibehalten und keine unpassende medizinische Standardschablone erzwingen.
""".strip()


WORKFLOW_PROMPT = f"""
Bearbeite das gesamte Dokument strikt in dieser Reihenfolge:
1. Prüfe bei mehreren übergebenen Seiten oder separaten Dateien zuerst deren
   wahrscheinliche Dokumentreihenfolge. Nutze ausschließlich sichtbare Merkmale wie
   Seitenzahlen, Datumsangaben, fortlaufende Sätze, Überschriften und Briefaufbau.
   Die technische Upload-Reihenfolge ist nur ein Hinweis. Ordne Seiten bei eindeutigen
   Indizien logisch; bei uneindeutiger Lage behalte ihre technische Reihenfolge bei.
2. Lies danach alle Seiten vollständig, in der ermittelten Reihenfolge und möglichst
   originalgetreu als ein sequentiell zusammengefügtes Dokument aus.
3. Bestimme genau einen der folgenden Dokumenttypen: {', '.join(t.value for t in Dokumenttyp)}.
4. Strukturiere den ausgelesenen Inhalt passend zu diesem Dokumenttyp.
5. Erstelle ausschließlich aus dem ausgelesenen Inhalt einen gekürzten KIS-Vorschlag.

{FORMATVORGABEN}

Verbindliche Regeln:
- Keine Angaben ergänzen, die nicht im Dokument stehen.
- Keine Diagnosen aus Symptomen oder Befunden ableiten und keine Diagnose präzisieren oder vereinheitlichen.
- Keine Normalbefunde ergänzen und Laborwerte nicht interpretieren.
- Keine Referenzbereiche aus medizinischem Wissen ergänzen.
- Keine Medikamentenindikation aus dem Präparat ableiten.
- Keine Dosierungen berechnen oder verändern und keine Einheiten umrechnen.
- Keine Abkürzungen ausschreiben, wenn die Langform nicht im Dokument steht.
- Keine Widersprüche selbstständig auflösen; unleserliche Stellen als `unleserlich` kennzeichnen.
- Zahlen, Datumsangaben, Einheiten, Medikamentennamen, Diagnosen und Negationen unverändert übernehmen.
- Insbesondere `kein`, `nicht`, `ohne` und vergleichbare Negationen nicht verändern oder entfernen.
- Umformulierungen dürfen die medizinische Aussage weder erweitern noch verändern.
- Der KIS-Vorschlag darf nur durch Auswahl, Ordnung, sprachliche Verdichtung und Kürzung entstehen.

Antworte ausschließlich in diesem eindeutig trennbaren Reintextformat:
DOKUMENTTYP:
[genau ein unterstützter Dokumenttyp]

AUSGELESENER INHALT:
[möglichst vollständige und originalgetreue Auslesung]

STRUKTURIERTE DARSTELLUNG:
[dokumenttypspezifische Darstellung]

KIS-VORSCHLAG:
[gekürzter und geordneter Dokumentationstext]
""".strip()


ABSCHNITTE = (
    "DOKUMENTTYP",
    "AUSGELESENER INHALT",
    "STRUKTURIERTE DARSTELLUNG",
    "KIS-VORSCHLAG",
)
_UEBERSCHRIFT = re.compile(
    r"(?m)^\s*(DOKUMENTTYP|AUSGELESENER INHALT|STRUKTURIERTE DARSTELLUNG|KIS-VORSCHLAG)\s*:\s*$"
)


def parse_dokumentantwort(antwort: str) -> DokumentErgebnis:
    """Parst alle vier Pflichtabschnitte oder meldet den exakten Formatfehler.

    Debugging-Hinweis: Lokal dürfen Entwickler bei Bedarf ausschließlich
    ``[m.group(1) for m in _UEBERSCHRIFT.finditer(antwort)]`` und die Längen der
    ausgeschnittenen Abschnitte ansehen. Die vollständige Antwort, Patientendaten
    oder Schlüssel dürfen niemals automatisch in dauerhafte Logs geschrieben werden.
    """
    trefferliste = list(_UEBERSCHRIFT.finditer(antwort or ""))
    namen = [treffer.group(1) for treffer in trefferliste]
    for name in ABSCHNITTE:
        anzahl = namen.count(name)
        if anzahl == 0:
            raise DokumentAntwortFehler(f"Pflichtabschnitt fehlt: {name}.")
        if anzahl > 1:
            raise DokumentAntwortFehler(f"Pflichtabschnitt mehrfach vorhanden: {name}.")
    if namen != list(ABSCHNITTE):
        raise DokumentAntwortFehler(
            "Pflichtabschnitte sind widersprüchlich angeordnet; erwartet wird: "
            + ", ".join(ABSCHNITTE)
            + "."
        )

    inhalte: dict[str, str] = {}
    for index, treffer in enumerate(trefferliste):
        ende = (
            trefferliste[index + 1].start()
            if index + 1 < len(trefferliste)
            else len(antwort)
        )
        inhalt = antwort[treffer.end() : ende].strip()
        if not inhalt:
            raise DokumentAntwortFehler(f"Pflichtabschnitt ist leer: {treffer.group(1)}.")
        inhalte[treffer.group(1)] = inhalt

    typtext = inhalte["DOKUMENTTYP"].strip()
    try:
        dokumenttyp = Dokumenttyp(typtext)
    except ValueError as fehler:
        raise DokumentAntwortFehler(f"Unbekannter Dokumenttyp: {typtext!r}.") from fehler
    return DokumentErgebnis(
        dokumenttyp=dokumenttyp,
        ausgelesener_inhalt=inhalte["AUSGELESENER INHALT"],
        strukturierte_darstellung=inhalte["STRUKTURIERTE DARSTELLUNG"],
        kis_vorschlag=inhalte["KIS-VORSCHLAG"],
    )


# Englischer Alias erleichtert die anbieterunabhängige Nutzung, ohne eine zweite
# Parserimplementierung oder abweichende Fehlerbehandlung einzuführen.
parse_document_response = parse_dokumentantwort
