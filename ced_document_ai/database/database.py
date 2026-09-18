"""SQLAlchemy-Verbindung zur lokalen SQLite-Datenbank."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.models import Base

_session_factory: sessionmaker[Session] | None = None


def initialize_database(settings: Settings | None = None) -> sessionmaker[Session]:
    """Erstellt den Datenordner, alle Tabellen und eine wiederverwendbare Session-Fabrik."""
    global _session_factory
    active_settings = settings or Settings.from_environment()
    active_settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{active_settings.database_path}")
    Base.metadata.create_all(engine)
    # ``create_all`` ergänzt keine Spalten in einer vorhandenen SQLite-Tabelle.
    # Diese kleine, explizite Migration bewahrt die bisherige Namensspalte und legt
    # ausschließlich die beiden neuen nullable Spalten an. Namen werden absichtlich
    # nicht automatisch aufgeteilt; dies muss bei Altdaten fachlich geprüft werden.
    patientenspalten = {
        spalte["name"] for spalte in inspect(engine).get_columns("patients")
    }
    with engine.begin() as verbindung:
        if "first_name" not in patientenspalten:
            verbindung.execute(text("ALTER TABLE patients ADD COLUMN first_name VARCHAR(150)"))
        if "last_name" not in patientenspalten:
            verbindung.execute(text("ALTER TABLE patients ADD COLUMN last_name VARCHAR(150)"))
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factory


def get_session() -> Session:
    """Öffnet eine Datenbanksitzung nach vorheriger Initialisierung."""
    if _session_factory is None:
        raise RuntimeError("Die Datenbank wurde noch nicht initialisiert.")
    return _session_factory()
