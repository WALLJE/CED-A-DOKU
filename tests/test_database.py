"""Prüft das vollständige Phase-1-Datenbankschema ohne echte Patientendaten."""

from pathlib import Path
import sqlite3

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
        "patient_ced_attributes",
        "ai_results",
        "ai_warnings",
        "follow_up_items",
        "user_preferences",
        "audit_log",
    }.issubset(set(inspector.get_table_names()))


def test_initialize_database_ergaenzt_getrennte_namensspalten(tmp_path: Path) -> None:
    datenbankpfad = tmp_path / "altbestand.sqlite3"
    with sqlite3.connect(datenbankpfad) as verbindung:
        verbindung.execute(
            "CREATE TABLE patients (id INTEGER PRIMARY KEY, external_id VARCHAR(100), "
            "name VARCHAR(250) NOT NULL, birth_date DATE, created_at DATETIME)"
        )
    fabrik = initialize_database(Settings(database_path=datenbankpfad))
    spalten = {
        spalte["name"] for spalte in inspect(fabrik.kw["bind"]).get_columns("patients")
    }
    assert {"first_name", "last_name"}.issubset(spalten)


def test_initialize_database_ergaenzt_dokumentdatum_ohne_ersatzwert(tmp_path: Path) -> None:
    datenbankpfad = tmp_path / "alte_dokumente.sqlite3"
    with sqlite3.connect(datenbankpfad) as verbindung:
        verbindung.execute(
            "CREATE TABLE documents (id INTEGER PRIMARY KEY, original_name VARCHAR(500) "
            "NOT NULL, imported_at DATETIME, confirmed BOOLEAN)"
        )
    fabrik = initialize_database(Settings(database_path=datenbankpfad))
    spalten = {
        spalte["name"] for spalte in inspect(fabrik.kw["bind"]).get_columns("documents")
    }

    assert "document_date" in spalten
