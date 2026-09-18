"""Tests der versionierten manuellen CED-Stammdaten mit Testpatienten."""

from datetime import date

import pytest
from sqlalchemy import func, select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import AuditLog, Diagnosis, Patient, PatientCEDAttribute
from ced_document_ai.services.ced.patient_overview import lade_patientenuebersicht
from ced_document_ai.services.ced.patient_profile import (
    DIAGNOSE_DETAILS,
    DiagnosenEingabe,
    ManuelleCEDStammdaten,
    TherapienEingabe,
    bilde_befallsmuster_code,
    speichere_diagnosen,
    speichere_manuelle_stammdaten,
    speichere_therapien,
)


def test_manuelle_stammdaten_werden_versioniert_und_angezeigt(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "profil.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-01", name="Erika Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        anzahl = speichere_manuelle_stammdaten(
            sitzung,
            patient.id,
            ManuelleCEDStammdaten(
                erstdiagnose=date(2020, 4, 3),
                befallsmuster="synthetisches Testmuster",
                eim_auswahl=("Uveitis", "Erythema nodosum"),
                eim_weitere="Synthetische weitere EIM",
                diagnose_details="Synthetische Details",
                symptome_seit=date(2019, 1, 2),
            ),
        )
        speichere_manuelle_stammdaten(
            sitzung,
            patient.id,
            ManuelleCEDStammdaten(
                erstdiagnose=None,
                befallsmuster="aktualisiertes Testmuster",
            ),
        )
        uebersicht = lade_patientenuebersicht(sitzung, patient.id)

        assert anzahl == 6
        assert uebersicht.erstdiagnose == date(2020, 4, 3)
        assert uebersicht.befallsmuster == "aktualisiertes Testmuster"
        assert uebersicht.eim_auswahl == ("Uveitis", "Erythema nodosum")
        assert uebersicht.eim_weitere == "Synthetische weitere EIM"
        assert uebersicht.diagnose_details == "Synthetische Details"
        assert uebersicht.symptome_seit == date(2019, 1, 2)
        assert (
            sitzung.scalar(select(func.count()).select_from(PatientCEDAttribute)) == 7
        )
        assert sitzung.scalar(select(func.count()).select_from(AuditLog)) == 2


def test_leerer_auftrag_erzeugt_keine_daten(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "leer.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-02", name="Max Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        with pytest.raises(ValueError, match="mindestens ein"):
            speichere_manuelle_stammdaten(
                sitzung,
                patient.id,
                ManuelleCEDStammdaten(erstdiagnose=None, befallsmuster="  "),
            )

        assert (
            sitzung.scalar(select(func.count()).select_from(PatientCEDAttribute)) == 0
        )
        assert sitzung.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_diagnosen_und_hinweise_werden_getrennt_versioniert(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "fall.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-03", name="Fall Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        eingabe = DiagnosenEingabe(
            hauptdiagnose="Synthetische Hauptdiagnose",
            nebendiagnosen=("Test-Nebendiagnose",),
        )
        speichere_diagnosen(sitzung, patient.id, eingabe)
        speichere_diagnosen(sitzung, patient.id, eingabe)

        statuswerte = list(sitzung.scalars(select(Diagnosis.status)))
        assert statuswerte.count("HAUPTDIAGNOSE") == 1
        assert statuswerte.count("NEBENDIAGNOSE") == 1
        assert statuswerte.count("ERSETZT") == 2
        uebersicht = lade_patientenuebersicht(sitzung, patient.id)
        assert uebersicht.diagnose_details is None
        assert uebersicht.therapie_medikamentoes is None
        assert uebersicht.therapie_chirurgisch is None
        details = list(
            sitzung.scalars(
                select(PatientCEDAttribute).where(
                    PatientCEDAttribute.attribute_type == DIAGNOSE_DETAILS
                )
            )
        )
        assert details == []


def test_befallsmustercode_entsteht_nur_aus_vollstaendiger_auswahl() -> None:
    crohn = ManuelleCEDStammdaten(
        erstdiagnose=None,
        befallsmuster=None,
        erkrankungstyp="Morbus Crohn",
        mc_lokalisation="L3",
        mc_oberer_gi=True,
        mc_verhalten="B3",
        mc_perianal=True,
    )
    colitis = ManuelleCEDStammdaten(
        erstdiagnose=None,
        befallsmuster=None,
        erkrankungstyp="Colitis ulcerosa",
        cu_ausdehnung="E2",
    )

    assert bilde_befallsmuster_code(crohn) == "L3, L4, B3p"
    assert bilde_befallsmuster_code(colitis) == "E2"


def test_befallsmusterparameter_werden_versioniert_und_code_angezeigt(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "muster.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-05", name="Muster Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        speichere_manuelle_stammdaten(
            sitzung,
            patient.id,
            ManuelleCEDStammdaten(
                erstdiagnose=None,
                befallsmuster=None,
                erkrankungstyp="Morbus Crohn",
                mc_lokalisation="L2",
                mc_oberer_gi=False,
                mc_verhalten="B2",
                mc_perianal=False,
            ),
        )
        uebersicht = lade_patientenuebersicht(sitzung, patient.id)

        assert uebersicht.befallsmuster == "L2, B2"
        assert uebersicht.erkrankungstyp == "Morbus Crohn"
        assert uebersicht.mc_lokalisation == "L2"
        assert uebersicht.mc_verhalten == "B2"


def test_therapien_koennen_ohne_diagnoseaenderung_versioniert_werden(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "therapie.sqlite3"))
    with fabrik() as sitzung:
        patient = Patient(external_id="TEST-04", name="Therapie Beispiel")
        sitzung.add(patient)
        sitzung.commit()

        anzahl = speichere_therapien(
            sitzung,
            patient.id,
            TherapienEingabe(
                therapie_medikamentoes="Synthetische Medikation",
                therapie_chirurgisch="Keine Operation",
            ),
        )
        uebersicht = lade_patientenuebersicht(sitzung, patient.id)

        assert anzahl == 2
        assert list(sitzung.scalars(select(Diagnosis))) == []
        assert uebersicht.therapie_medikamentoes == "Synthetische Medikation"
        assert uebersicht.therapie_chirurgisch == "Keine Operation"
