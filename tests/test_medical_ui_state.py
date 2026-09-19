"""Tests des reinen Sitzungszustands ohne Browser- oder NiceGUI-Interaktion."""

from ced_document_ai.medical_ui import DATENBANKMODUS, Sitzungszustand


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
