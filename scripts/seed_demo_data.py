"""Legt bewusst fünf synthetische Patienten in der konfigurierten Datenbank an."""

from ced_document_ai.config.settings import Settings
from ced_document_ai.database.database import get_session, initialize_database
from ced_document_ai.services.ced.demo_data import erzeuge_demo_daten


if __name__ == "__main__":
    # Derselbe explizit ermittelte Pfad wird sowohl für die Initialisierung als auch
    # für die Abschlussmeldung verwendet. Das ist insbesondere in Codespaces eine
    # wichtige Debugging-Hilfe: Ein relativer Standardpfad gehört zum aktuellen
    # Arbeitsverzeichnis, während CED_DATABASE_PATH bewusst ein anderes Ziel wählen
    # kann. Die Datenbank wird nicht automatisch an einen zweiten Ort kopiert.
    einstellungen = Settings.from_environment()
    initialize_database(einstellungen)
    with get_session() as sitzung:
        anzahl = erzeuge_demo_daten(sitzung)
    datenbankpfad = einstellungen.database_path.resolve()
    if anzahl:
        print(
            f"{anzahl} fehlende synthetische Demo-Patienten wurden angelegt in: "
            f"{datenbankpfad}"
        )
    else:
        print(
            "Alle fünf synthetischen Demo-Patienten waren bereits vorhanden in: "
            f"{datenbankpfad}"
        )
