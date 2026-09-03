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
        """Verarbeitet alle Dokumentteile zu genau einem gemeinsamen Ergebnis."""


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
        for paths in chunks:
            content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        f"{prompt}\nDokumenttyp: {document_type}. "
                        "Die bereitgestellten Bilder in ihrer Reihenfolge lesen. "
                        "In der Transkription keine Seitenzahlen, Dokumentnummern, "
                        "Teilnummern, Trennüberschriften oder sonstigen technischen "
                        "Kennzeichnungen ausgeben. Ausschließlich den übrigen Text des "
                        "Originaldokuments ohne Ergänzungen ausgeben."
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

        # Die Antworten werden ohne künstliche Überschrift verbunden. Für die
        # Fehlersuche kann lokal die Länge der einzelnen ``answers`` geprüft werden;
        # Nummern oder Antworttexte dürfen nicht in dauerhafte Logs geschrieben werden.
        return "\n\n".join(answers)

    def process_document(self, document: Sequence[Path]) -> DokumentErgebnis:
        """Führt den Workflow für mehrere Dokumentteile in zwei Phasen aus.

        Ein einzelnes Bild kann unmittelbar ausgewertet werden. Bei mehreren Bildern
        wird dagegen jedes Teil in einer eigenen Bildanfrage transkribiert. Das ist
        absichtlich unabhängig vom technischen Bildlimit des Anbieters: Manche
        kompatiblen Endpunkte akzeptieren mehrere Bilder, berücksichtigen inhaltlich
        aber nur das letzte. Erst danach erzeugt eine einzige Textanfrage Typ,
        Struktur und KIS-Vorschlag aus *allen* Transkriptionen. Es gibt weder einen
        Anbieterwechsel noch eine Ersatzantwort bei einem Parserfehler.
        """
        if not document:
            raise ValueError("Mindestens eine Dokumentseite ist erforderlich.")
        if self.max_images < 1:
            raise AIProviderError("Die maximale Bildanzahl des Anbieters muss mindestens 1 sein.")

        if len(document) == 1:
            rohantwort = self._request(WORKFLOW_PROMPT, document)
        else:
            transkriptionen: list[str] = []
            for dokumentteil in document:
                # Diese Phase darf ausdrücklich noch nicht klassifizieren oder
                # zusammenfassen. Genau ein Bild je Anfrage macht außerdem im
                # Debugging anhand der Anfragenanzahl sichtbar, ob ein Teil fehlte,
                # ohne Patientendaten oder Bildinhalte protokollieren zu müssen.
                auftrag = (
                    "Lies ausschließlich das bereitgestellte Dokumentteil vollständig und "
                    "originalgetreu aus. Nicht klassifizieren, strukturieren oder kürzen. "
                    "Keine Angaben, Platzhalter oder Hinweise ergänzen. Unleserliche Stellen "
                    "auslassen, statt sie mit einer eigenen Kennzeichnung zu ersetzen. "
                    "Keine Seitenzahl, Dokumentnummer, Teilnummer, Trennüberschrift oder "
                    "sonstige technische Kennzeichnung ausgeben. Gib ausschließlich den "
                    "übrigen Text aus dem Originaldokument aus."
                )
                transkriptionen.append(self._request(auftrag, (dokumentteil,)))
            # Auch die interne Zusammenführung erhält keine künstlichen Nummern, damit
            # sie nicht versehentlich in den ausgegebenen Transkripttext gelangen.
            gesamtauslesung = "\n\n".join(transkriptionen)
            rohantwort = self._request(
                WORKFLOW_PROMPT
                + "\n\nNachfolgend stehen die einzeln erfassten Teile des gesamten "
                "Dokuments. Ihre Reihenfolge entspricht zunächst der technischen "
                "Upload-Reihenfolge. Prüfe anhand der sichtbaren Inhalte die logische "
                "Dokumentreihenfolge und verarbeite alle Teile anschließend gemeinsam. "
                "Kein Dokumentteil darf ausgelassen werden:\n\n"
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
