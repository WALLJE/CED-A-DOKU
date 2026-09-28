"""Tests des Sitzungszustands und kritischer UI-Referenzen ohne Browser."""

import inspect

from ced_document_ai.medical_ui import DATENBANKMODUS, Sitzungszustand, zeige_hauptseite


def test_ausgelesenes_labor_mit_patient_aktiviert_datenzuordnung() -> None:
    zustand = Sitzungszustand(
        arbeitsmodus=DATENBANKMODUS,
        patient_id=7,
        dokumenttyp="Laborbefund",
        ausgelesener_inhalt="Synthetischer Laborinhalt",
        # Der Test bildet ausdrücklich den gemeldeten Fall ab: Die allgemeine
        # Zuordnung darf nicht von der CED-spezifischen Tabellenansicht abhängen.
        strukturierte_darstellung="",
        patientenabgleich_erlaubt=True,
    )

    assert zustand.datenzuordnung_moeglich


def test_widerspruch_oder_bereits_gespeichertes_dokument_sperrt_zuordnung() -> None:
    widerspruch = Sitzungszustand(
        arbeitsmodus=DATENBANKMODUS,
        patient_id=7,
        dokumenttyp="Laborbefund",
        ausgelesener_inhalt="Synthetischer Laborinhalt",
        patientenabgleich_erlaubt=False,
    )
    gespeichert = Sitzungszustand(
        arbeitsmodus=DATENBANKMODUS,
        patient_id=7,
        dokumenttyp="Laborbefund",
        ausgelesener_inhalt="Synthetischer Laborinhalt",
        patientenabgleich_erlaubt=True,
        gespeichertes_dokument_id=11,
    )

    assert not widerspruch.datenzuordnung_moeglich
    assert not gespeichert.datenzuordnung_moeglich


def test_diagnosedetails_verwendet_keine_veraltete_ui_referenz() -> None:
    """Sichert die vollständige Umbenennung des Diagnosedetail-Feldes ab.

    NiceGUI erzeugt die verschachtelten Rücksetzfunktionen erst beim Seitenaufbau.
    Der frühere Bezeichner würde daher trotz erfolgreichem Import erst nach dem Klick
    auf „CED-Datenbank aktivieren“ einen NameError auslösen. Die Quelltextprüfung ist
    hier bewusst eng auf diesen regressionsanfälligen UI-Bezeichner begrenzt.
    """
    quelltext = inspect.getsource(zeige_hauptseite)

    assert "diagnose_details_ausgabe" in quelltext
    assert "diagnose_hinweise_ausgabe" not in quelltext
