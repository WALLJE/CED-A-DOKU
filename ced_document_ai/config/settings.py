"""Zentrale, sichere Anwendungskonfiguration.

Secrets werden ausschließlich aus Umgebungsvariablen gelesen. Für einen lokalen
Start lädt dieses Modul die Variablen einmalig aus der ``.env`` im Projektordner.
Bereits gesetzte Umgebungsvariablen werden dabei bewusst nicht überschrieben.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Der explizite Pfad macht unabhängig davon, aus welchem Arbeitsverzeichnis das
# Programm gestartet wird. ``override=False`` schützt beispielsweise Secrets, die
# in einer Entwicklungsumgebung bereits als echte Umgebungsvariablen gesetzt sind.
# Bei Problemen kann zum lokalen Debuggen vorübergehend ``verbose=True`` ergänzt
# werden; Schlüsselwerte selbst dürfen dabei niemals ausgegeben werden.
DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=DOTENV_PATH, override=False)


@dataclass(frozen=True)
class Settings:
    """Unveränderliche Einstellungen für einen Programmlauf."""

    uk_api_url: str = "https://chatbot-diz.uk-halle.de/api/chat/completions"
    uk_model: str = "gemma4-31b"
    openai_api_url: str = "https://api.openai.com/v1/chat/completions"
    openai_model: str = "gpt-4.1-mini"
    provider: str = "uk"
    database_path: Path = Path("data/ced_document_ai.sqlite3")
    request_timeout_seconds: int = 120
    max_images_per_request: int = 5

    @classmethod
    def from_environment(cls) -> "Settings":
        """Liest nur nicht geheime Optionen; Schlüssel werden bei Bedarf geladen."""
        return cls(
            uk_api_url=os.getenv(
                "CED_UK_API_URL",
                "https://chatbot-diz.uk-halle.de/api/chat/completions",
            ),
            uk_model=os.getenv("CED_UK_MODEL", "gemma4-31b"),
            openai_api_url=os.getenv(
                "CED_OPENAI_API_URL",
                "https://api.openai.com/v1/chat/completions",
            ),
            openai_model=os.getenv("CED_OPENAI_MODEL", "gpt-4.1-mini"),
            provider=os.getenv("CED_AI_PROVIDER", "uk").strip().lower(),
            database_path=Path(
                os.getenv("CED_DATABASE_PATH", "data/ced_document_ai.sqlite3")
            ),
        )

    def api_key(self, provider: str) -> str:
        """Gibt den Schlüssel des gewählten Providers zurück oder erklärt den Fehler."""
        variable = "UK_API_KEY" if provider == "uk" else "OPEN_AI_KEY"
        value = os.getenv(variable, "").strip()
        if not value:
            raise ConfigurationError(
                f"Die Umgebungsvariable {variable} fehlt oder ist leer. "
                "Bitte das Secret setzen und die Anwendung neu starten."
            )
        return value

    def ced_database_password(self) -> str:
        """Liest das Passwort für den geschützten Verarbeitungsmodus."""
        value = os.getenv("CED_DATA_PASS", "")
        if not value:
            raise ConfigurationError(
                "Die Umgebungsvariable CED_DATA_PASS fehlt oder ist leer."
            )
        return value


class ConfigurationError(RuntimeError):
    """Verständliche Fehlermeldung für fehlende oder falsche Konfiguration."""
