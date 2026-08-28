"""Einziger Startpunkt für die medizinische CED-A-DOKU-Browseranwendung.

Die eigentliche NiceGUI-Oberfläche liegt im Python-Paket. Diese Datei enthält
bewusst keine eigene Oberflächenlogik, damit der Startweg eindeutig bleibt und
die medizinische Benutzeroberfläche unabhängig davon weiterentwickelt werden kann.
"""

from ced_document_ai.medical_ui import starte_anwendung


if __name__ in {"__main__", "__mp_main__"}:
    # NiceGUI kann beim Start zusätzliche Prozesse erzeugen. ``__mp_main__`` stellt
    # sicher, dass der Einstieg auch in diesen von Python verwalteten Prozessen
    # korrekt erkannt wird. Es wird ausdrücklich kein alternativer Server gestartet.
    starte_anwendung()
