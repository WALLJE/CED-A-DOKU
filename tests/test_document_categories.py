"""Tests des kontrollierten Katalogs medizinischer Dokumentklassen."""

import pytest

from ced_document_ai.services.ced.document_categories import (
    DOKUMENTKLASSEN,
    ermittle_dokumentfachgruppe,
)


def test_haeufige_dokumenttypen_haben_eindeutige_fachgruppen() -> None:
    typen = [eintrag.dokumenttyp for eintrag in DOKUMENTKLASSEN]

    assert len(typen) == len(set(typen))
    assert all(eintrag.beschreibung and eintrag.merkmale for eintrag in DOKUMENTKLASSEN)
    assert ermittle_dokumentfachgruppe("Laborbefund") == "Labor"
    assert ermittle_dokumentfachgruppe("Virologischer Befund") == "Labor"
    assert ermittle_dokumentfachgruppe("MRT-Befund") == "MRT"
    assert ermittle_dokumentfachgruppe("Arztbrief") == "Arztbriefe"


def test_neuer_typ_erhaelt_keinen_stillen_gruppenfallback() -> None:
    with pytest.raises(ValueError, match="keine persistente Fachgruppe"):
        ermittle_dokumentfachgruppe("Humangenetischer Befund")


def test_leerer_dokumenttyp_wird_nicht_stillschweigend_klassifiziert() -> None:
    with pytest.raises(ValueError, match="leerer Dokumenttyp"):
        ermittle_dokumentfachgruppe("   ")
