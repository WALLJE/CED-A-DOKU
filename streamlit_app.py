"""Einfacher Einstiegspunkt für Streamlit und GitHub Codespaces.

Die eigentliche Oberfläche liegt im Python-Paket. Diese kleine Startdatei sorgt
dafür, dass Streamlit das Projekt ohne besondere Pfadkonfiguration erkennen kann.
Sie unterstützt sowohl den üblichen Streamlit-Befehl als auch den ▶-Startknopf
„Python-Datei ausführen“ in Visual Studio Code.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from streamlit.runtime import exists as streamlit_server_is_running


def start() -> int:
    """Startet bei Bedarf den Webserver oder zeichnet die Streamlit-Seite."""
    if not streamlit_server_is_running():
        # Beim direkten Aufruf mit `python streamlit_app.py` existiert noch kein
        # Streamlit-Server. Deshalb wird derselbe Python-Interpreter erneut mit
        # `-m streamlit run` gestartet. Es werden bewusst keine Pakete automatisch
        # installiert und keine Fehler verborgen: Schlägt Streamlit fehl, erscheint
        # dessen Originalmeldung im Terminal und der Rückgabecode wird weitergegeben.
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).resolve()),
            "--server.address",
            "0.0.0.0",
        ]
        return subprocess.run(command, check=False).returncode

    # Dieser Import erfolgt erst innerhalb des laufenden Streamlit-Servers. Dadurch
    # wird die Oberfläche nicht einmal vergeblich im sogenannten Bare Mode aufgebaut.
    from ced_document_ai.web_app import main

    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(start())
