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
    dokument_spalten = {
        spalte["name"] for spalte in inspect(engine).get_columns("documents")
    }
    dokumenttyp_spalten = {
        spalte["name"] for spalte in inspect(engine).get_columns("document_types")
    }
    befundkategorie_spalten = {
        spalte["name"] for spalte in inspect(engine).get_columns("finding_categories")
    }
    with engine.begin() as verbindung:
        if "first_name" not in patientenspalten:
            verbindung.execute(text("ALTER TABLE patients ADD COLUMN first_name VARCHAR(150)"))
        if "last_name" not in patientenspalten:
            verbindung.execute(text("ALTER TABLE patients ADD COLUMN last_name VARCHAR(150)"))
        if "document_date" not in dokument_spalten:
            # Das medizinische Dokumentdatum wird nie durch das Importdatum ersetzt.
            # Bestehende Dokumente bleiben daher bewusst ohne Datum, bis sie geprüft
            # wurden; es gibt keinen stillen Fallback auf den aktuellen Tag.
            verbindung.execute(text("ALTER TABLE documents ADD COLUMN document_date DATE"))
        # Die expliziten ALTER-Anweisungen halten vorhandene lokale Datenbanken
        # nutzbar. Defaults werden auch auf Altdaten angewandt; medizinische Inhalte
        # werden bei dieser rein technischen Migration nicht abgeleitet.
        dokumenttyp_migrationen = {
            "display_name": "VARCHAR(150)",
            "group_name": "VARCHAR(150)",
            "active": "BOOLEAN NOT NULL DEFAULT 1",
            "user_created": "BOOLEAN NOT NULL DEFAULT 0",
            "description": "TEXT",
            "classification_hints": "TEXT",
            "created_at": "DATETIME",
            "group_id": "INTEGER",
            "parser_key": "VARCHAR(100)",
            "sort_order": "INTEGER NOT NULL DEFAULT 100",
        }
        for spaltenname, sql_typ in dokumenttyp_migrationen.items():
            if spaltenname not in dokumenttyp_spalten:
                verbindung.execute(
                    text(f"ALTER TABLE document_types ADD COLUMN {spaltenname} {sql_typ}")
                )
        # Auch Befundkategorien erhalten reine Darstellungsmetadaten. Medizinische
        # Werte oder Einheiten werden bei der Migration nicht ergänzt oder geraten.
        befundkategorie_migrationen = {
            "display_name": "VARCHAR(200)",
            "sort_order": "INTEGER NOT NULL DEFAULT 100",
            "active": "BOOLEAN NOT NULL DEFAULT 1",
        }
        for spaltenname, sql_typ in befundkategorie_migrationen.items():
            if spaltenname not in befundkategorie_spalten:
                verbindung.execute(
                    text(f"ALTER TABLE finding_categories ADD COLUMN {spaltenname} {sql_typ}")
                )
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factory


def get_session() -> Session:
    """Öffnet eine Datenbanksitzung nach vorheriger Initialisierung."""
    if _session_factory is None:
        raise RuntimeError("Die Datenbank wurde noch nicht initialisiert.")
    return _session_factory()
