"""Legt bewusst fünf synthetische Patienten in der konfigurierten Datenbank an."""

from ced_document_ai.database.database import get_session, initialize_database
from ced_document_ai.services.ced.demo_data import erzeuge_demo_daten


if __name__ == "__main__":
    initialize_database()
    with get_session() as sitzung:
        anzahl = erzeuge_demo_daten(sitzung)
    print(f"{anzahl} synthetische Demo-Patienten wurden angelegt.")
