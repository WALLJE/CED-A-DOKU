"""Direkt ausführbarer Einstiegspunkt für die NiceGUI-Browseroberfläche."""

from ced_document_ai.nicegui_app import starte_anwendung


if __name__ in {"__main__", "__mp_main__"}:
    starte_anwendung()

