"""SQLAlchemy-Verbindung zur lokalen SQLite-Datenbank."""

from __future__ import annotations

from sqlalchemy import create_engine
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
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factory


def get_session() -> Session:
    """Öffnet eine Datenbanksitzung nach vorheriger Initialisierung."""
    if _session_factory is None:
        raise RuntimeError("Die Datenbank wurde noch nicht initialisiert.")
    return _session_factory()

