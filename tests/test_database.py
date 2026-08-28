"""Prüft das vollständige Phase-1-Datenbankschema ohne echte Patientendaten."""

from pathlib import Path

from sqlalchemy import inspect

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import initialize_database


def test_initialize_database_creates_required_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "test.sqlite3"
    factory = initialize_database(Settings(database_path=database_path))
    inspector = inspect(factory.kw["bind"])
    assert {
        "patients",
        "documents",
        "document_types",
        "finding_categories",
        "findings",
        "diagnoses",
        "ai_results",
        "ai_warnings",
        "follow_up_items",
        "user_preferences",
        "audit_log",
    }.issubset(set(inspector.get_table_names()))

