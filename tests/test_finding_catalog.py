"""Tests des persistenten Befundkatalogs und seiner kontrollierten Synonyme."""

from sqlalchemy import select

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database
from ced_document_ai.database.models import FindingCategory, FindingCategoryAlias
from ced_document_ai.services.ced.finding_catalog import stelle_befundkatalog_sicher


def test_standardkategorien_und_aliase_werden_persistent_geseedet(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "befundkatalog.sqlite3"))
    with fabrik() as sitzung:
        stelle_befundkatalog_sicher(sitzung)
        haemoglobin = sitzung.scalar(
            select(FindingCategory).where(FindingCategory.name == "Hämoglobin")
        )
        assert haemoglobin is not None
        assert haemoglobin.display_name == "Hämoglobin"
        assert haemoglobin.sort_order == 20
        assert haemoglobin.active
        aliase = set(sitzung.scalars(
            select(FindingCategoryAlias.alias).where(
                FindingCategoryAlias.category_id == haemoglobin.id
            )
        ))
        assert {"Hb", "Haemoglobin"}.issubset(aliase)


def test_seed_ueberschreibt_bearbeitete_kategorie_nicht(tmp_path) -> None:
    fabrik = initialize_database(Settings(database_path=tmp_path / "befundpflege.sqlite3"))
    with fabrik() as sitzung:
        stelle_befundkatalog_sicher(sitzung)
        crp = sitzung.scalar(select(FindingCategory).where(FindingCategory.name == "CRP"))
        crp.display_name = "CRP (Labor)"
        crp.sort_order = 777
        sitzung.commit()
        stelle_befundkatalog_sicher(sitzung)
        assert crp.display_name == "CRP (Labor)"
        assert crp.sort_order == 777

