"""Startpunkt der Desktop-Anwendung.

Die Datei hält den Programmeinstieg bewusst klein. Dadurch lassen sich Oberfläche,
Datenbank und KI-Anbindung später unabhängig voneinander testen und erweitern.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ced_document_ai.database.database import initialize_database
from ced_document_ai.ui.main_window import MainWindow, choose_work_mode


def main() -> int:
    """Initialisiert Datenbank und GUI und liefert den Prozess-Rückgabecode."""
    application = QApplication(sys.argv)
    application.setApplicationName("CED-A-DOKU")

    # Die Tabellen werden lokal vorbereitet. Medizinische Befunde werden in dieser
    # ersten Version jedoch noch nicht gespeichert; dafür ist später ausdrücklich
    # die Freigabe durch die Benutzerin oder den Benutzer erforderlich.
    initialize_database()

    mode = choose_work_mode()
    if mode is None:
        return 0

    window = MainWindow(mode=mode)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

