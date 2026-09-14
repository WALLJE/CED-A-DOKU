"""Tests der lokalen Patientenerkennung ohne echte medizinische Daten."""

from dataclasses import dataclass
from datetime import date

from ced_document_ai.services.ced.patient_matching import (
    erkenne_patientendaten,
    ermittle_patiententreffer,
)


@dataclass
class BeispielPatient:
    """Kleiner Testdatensatz mit derselben Abgleichschnittstelle wie das ORM-Modell."""

    id: int
    external_id: str | None
    name: str
    birth_date: date | None


def test_erkennt_eindeutig_beschriftete_stammdaten() -> None:
    erkannt = erkenne_patientendaten(
        "Patienten-ID: TEST-001\nPatient: Erika Beispiel\nGeburtsdatum: 12.03.1980"
    )

    assert erkannt.externe_id == "TEST-001"
    assert erkannt.name == "Erika Beispiel"
    assert erkannt.geburtsdatum == date(1980, 3, 12)
    assert erkannt.ausreichend_fuer_vorschlag


def test_name_allein_erzeugt_keinen_patientenvorschlag() -> None:
    erkannt = erkenne_patientendaten("Patient: Erika Beispiel")
    patienten = [BeispielPatient(1, "TEST-001", "Erika Beispiel", date(1980, 3, 12))]

    assert not erkannt.ausreichend_fuer_vorschlag
    assert ermittle_patiententreffer(erkannt, patienten) == []


def test_id_name_und_geburtsdatum_erzeugen_eindeutigen_treffer() -> None:
    erkannt = erkenne_patientendaten(
        "Patienten-ID: TEST-001\nName: Erika Beispiel\nGeburtsdatum: 12.03.1980"
    )
    patienten = [BeispielPatient(7, "test-001", "Erika Beispiel", date(1980, 3, 12))]

    treffer = ermittle_patiententreffer(erkannt, patienten)

    assert len(treffer) == 1
    assert treffer[0].patient_id == 7
    assert treffer[0].status == "Eindeutiger Treffer"
    assert not treffer[0].widerspruch


def test_identische_id_mit_abweichendem_geburtsdatum_wird_nicht_verschwiegen() -> None:
    erkannt = erkenne_patientendaten(
        "Patienten-ID: TEST-001\nName: Erika Beispiel\nGeburtsdatum: 12.03.1980"
    )
    patienten = [BeispielPatient(7, "TEST-001", "Erika Beispiel", date(1981, 3, 12))]

    treffer = ermittle_patiententreffer(erkannt, patienten)

    assert treffer[0].status == "Widerspruch"
    assert treffer[0].widerspruch
    assert "Stammdaten widersprechen" in treffer[0].begruendung[-1]


def test_mehrere_verschiedene_namenszeilen_werden_nicht_geraten() -> None:
    erkannt = erkenne_patientendaten(
        "Name: Erika Beispiel\nName: Erna Beispiel\nGeburtsdatum: 12.03.1980"
    )

    assert erkannt.name is None
    assert not erkannt.ausreichend_fuer_vorschlag
