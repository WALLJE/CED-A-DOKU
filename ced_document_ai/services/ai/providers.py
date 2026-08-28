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
from ced_document_ai.services.ai.document_workflow import (
    DokumentErgebnis,
    WORKFLOW_PROMPT,
    parse_dokumentantwort,
)


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

    @abstractmethod
    def process_document(self, document: Sequence[Path]) -> DokumentErgebnis:
        """Verarbeitet alle Seiten zu genau einem gemeinsamen Ergebnis."""


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

    def process_document(self, document: Sequence[Path]) -> DokumentErgebnis:
        """Führt den Workflow aus, bei vielen Seiten bewusst in zwei Phasen.

        Passt das Dokument in eine Anfrage, erhält das Modell direkt den zentralen
        Auftrag. Andernfalls werden zunächst ausschließlich Transkriptionen der
        Seitenblöcke erstellt. Erst danach erzeugt eine einzige Textanfrage Typ,
        Struktur und KIS-Vorschlag für das Gesamtdokument. Es gibt weder einen
        Anbieterwechsel noch eine Ersatzantwort bei einem Parserfehler.
        """
        if not document:
            raise ValueError("Mindestens eine Dokumentseite ist erforderlich.")
        if self.max_images < 1:
            raise AIProviderError("Die maximale Bildanzahl des Anbieters muss mindestens 1 sein.")

        if len(document) <= self.max_images:
            rohantwort = self._request(WORKFLOW_PROMPT, document)
        else:
            transkriptionen: list[str] = []
            teile = [
                document[index : index + self.max_images]
                for index in range(0, len(document), self.max_images)
            ]
            for nummer, seiten in enumerate(teile, start=1):
                erster_index = (nummer - 1) * self.max_images + 1
                letzter_index = erster_index + len(seiten) - 1
                # Diese Phase darf ausdrücklich noch nicht klassifizieren oder
                # zusammenfassen, damit technische Blöcke kein eigenes Ergebnis bilden.
                auftrag = (
                    "Lies ausschließlich die bereitgestellten Seiten vollständig und "
                    "originalgetreu aus. Nicht klassifizieren, strukturieren oder kürzen. "
                    "Keine Angaben ergänzen. Unleserliches als `unleserlich` markieren. "
                    f"Kennzeichne die Seiten {erster_index} bis {letzter_index} einzeln "
                    "und erhalte ihre Reihenfolge."
                )
                transkriptionen.append(self._request(auftrag, seiten))
            gesamtauslesung = "\n\n".join(
                f"--- Seitenblock {nummer} ---\n{text}"
                for nummer, text in enumerate(transkriptionen, start=1)
            )
            rohantwort = self._request(
                WORKFLOW_PROMPT
                + "\n\nNachfolgend steht die bereits in korrekter Seitenreihenfolge erfasste "
                "Auslesung des gesamten Dokuments. Verarbeite alle Blöcke gemeinsam:\n\n"
                + gesamtauslesung,
                (),
            )
        return parse_dokumentantwort(rohantwort)

    # Alias für Aufrufer, die eine explizit benannte Workflow-Methode bevorzugen.
    analyze_workflow = process_document

    def _request(self, prompt: str, paths: Sequence[Path]) -> str:
        """Sendet genau eine Anfrage; sensible Payloads werden nie protokolliert."""
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
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
            return str(response.json()["choices"][0]["message"]["content"])
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
            # Zum lokalen Debuggen nur Exception-Typ und HTTP-Status prüfen. Niemals
            # Prompt, Antwort, Bilder, Authorization-Header oder Patientendaten loggen.
            raise AIProviderError(
                f"Die Anfrage an {self.provider_name} ist fehlgeschlagen: "
                f"{type(error).__name__}. Bitte Endpunkt, Modell-ID und Secret prüfen."
            ) from error

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
