"""Anbieterunabhängige KI-Schnittstelle und zwei REST-Implementierungen."""

from __future__ import annotations

import base64
import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import requests

from ced_document_ai.config.settings import Settings


class AIProviderError(RuntimeError):
    """Fehler, der ohne Offenlegung von Schlüssel oder Patientendaten angezeigt wird."""


class DocumentAI(ABC):
    """Vertrag für jede aktuelle oder zukünftige Dokument-KI."""

    @abstractmethod
    def analyze(
        self,
        document: Sequence[Path],
        document_type: str,
        categories: Sequence[str],
        prompt_config: dict[str, Any],
    ) -> str:
        """Analysiert Dokumentseiten und liefert die unbearbeitete Textantwort."""


@dataclass
class OpenAICompatibleProvider(DocumentAI):
    """Gemeinsamer Client für OpenAI-kompatible Chat-Completions-Endpunkte."""

    endpoint: str
    model: str
    api_key: str
    provider_name: str
    timeout_seconds: int = 120
    max_images: int = 5

    def analyze(
        self,
        document: Sequence[Path],
        document_type: str,
        categories: Sequence[str],
        prompt_config: dict[str, Any],
    ) -> str:
        if not document:
            raise ValueError("Mindestens eine Dokumentseite ist erforderlich.")

        prompt = str(
            prompt_config.get(
                "prompt",
                "Lies den vollständigen Inhalt der Dokumentseiten aus. Gib das Ergebnis "
                "als schlichten Reintext aus und erfinde keine unleserlichen Angaben.",
            )
        )
        chunks = [document[index : index + self.max_images] for index in range(0, len(document), self.max_images)]
        answers: list[str] = []
        for chunk_number, paths in enumerate(chunks, start=1):
            content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        f"{prompt}\nDokumenttyp: {document_type}. "
                        f"Teil {chunk_number} von {len(chunks)}; Seiten in Reihenfolge ausgeben."
                    ),
                }
            ]
            content.extend(self._image_content(path) for path in paths)
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": content}],
                "temperature": 0,
            }
            try:
                response = requests.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                answers.append(str(data["choices"][0]["message"]["content"]))
            except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
                # Für gezieltes Debugging kann lokal vorübergehend der HTTP-Status
                # protokolliert werden. Niemals Header, Payload oder Antwortinhalt
                # protokollieren, da diese Secrets und Patientendaten enthalten können.
                raise AIProviderError(
                    f"Die Anfrage an {self.provider_name} ist fehlgeschlagen: "
                    f"{type(error).__name__}. Bitte Endpunkt, Modell-ID und Secret prüfen."
                ) from error

        return "\n\n".join(
            f"--- Dokumentteil {index} ---\n{answer}"
            for index, answer in enumerate(answers, start=1)
        )

    @staticmethod
    def _image_content(path: Path) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
        }


class LocalAPIProvider(OpenAICompatibleProvider):
    """UK-Halle-Zugang mit dem verbindlich vorgegebenen Modell gemma4-31b."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            endpoint=settings.uk_api_url,
            model=settings.uk_model,
            api_key=settings.api_key("uk"),
            provider_name="UK-API",
            timeout_seconds=settings.request_timeout_seconds,
            max_images=settings.max_images_per_request,
        )


class CloudAPIProvider(OpenAICompatibleProvider):
    """Manuell wählbarer OpenAI-Zugang; kein stiller automatischer Fallback."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            endpoint=settings.openai_api_url,
            model=settings.openai_model,
            api_key=settings.api_key("openai"),
            provider_name="OpenAI",
            timeout_seconds=settings.request_timeout_seconds,
            max_images=settings.max_images_per_request,
        )

