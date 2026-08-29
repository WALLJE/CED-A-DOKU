#!/usr/bin/env python3
"""Diagnose der Verbindung zur Open-WebUI-API der UK Halle.

Dieses bewusst eigenstaendige Skript veraendert weder die Anwendung noch deren
Konfiguration. Es verwendet ausschliesslich ``UK_API_KEY`` und synthetische
Testdaten. Dadurch gelangen bei der Diagnose keine Patientendaten an die API.

Aufruf::

    export UK_API_KEY="..."
    python connection-test.py

Optional koennen Basis-URL und Modelle als Argumente angegeben werden. Der
API-Key wird absichtlich weder als Kommandozeilenargument akzeptiert noch
ausgegeben, weil beides den Schluessel leicht in Prozesslisten oder Logs
offenlegen wuerde.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import ssl
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests


STANDARD_BASIS_URL = "https://chatbot-diz.uk-halle.de/api"
STANDARD_MODELLE = ("gemma4-31b", "google/medgemma-27b-it")

# Ein fest eingebettetes, synthetisches PNG (1 x 1 Pixel). Das Bild enthaelt
# garantiert keine Patientendaten und prueft lediglich, ob Endpunkt und Modell
# das OpenAI-Format ``image_url`` mit einer Data-URL akzeptieren.
TEST_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@dataclass
class Ergebnis:
    """Ein einzelnes Diagnoseergebnis fuer die abschliessende Zusammenfassung."""

    test: str
    erfolgreich: bool
    detail: str


def ausgabe(status: str, test: str, detail: str) -> None:
    """Gibt ein Ergebnis sofort und gut lesbar im Terminal aus."""

    print(f"[{status}] {test}: {detail}", flush=True)


def exception_kette(fehler: BaseException) -> str:
    """Zeigt Exception-Typen ohne Request, Header oder API-Key an.

    ``str(fehler)`` wird bewusst nicht verwendet: Requests-Exceptions koennen
    die URL und in seltenen Faellen weitere Request-Details enthalten. Die
    Typenkette reicht meist aus, um DNS-, Proxy-, TLS- und Timeout-Probleme zu
    unterscheiden.
    """

    teile: list[str] = []
    aktuell: BaseException | None = fehler
    while aktuell is not None and len(teile) < 8:
        name = type(aktuell).__name__
        if name not in teile:
            teile.append(name)
        aktuell = aktuell.__cause__ or aktuell.__context__
    return " -> ".join(teile)


def sichere_http_details(response: requests.Response) -> str:
    """Liefert Status und eine kurze, bereinigte API-Fehlermeldung.

    Die Tests verwenden nur synthetische Inhalte. Trotzdem werden Antworttexte
    begrenzt und der API-Key vorsorglich ersetzt. Authorization-Header und der
    Request-Payload werden niemals ausgegeben.
    """

    text = response.text.strip().replace("\n", " ")[:500]
    api_key = os.getenv("UK_API_KEY", "")
    if api_key:
        text = text.replace(api_key, "<ENTFERNTER_API_KEY>")
    return f"HTTP {response.status_code}" + (f"; Antwort: {text}" if text else "")


def pruefe_dns(host: str) -> Ergebnis:
    """Prueft die Namensaufloesung unabhaengig von Requests."""

    try:
        adressen = sorted({eintrag[4][0] for eintrag in socket.getaddrinfo(host, 443)})
    except OSError as fehler:
        return Ergebnis("DNS", False, exception_kette(fehler))
    return Ergebnis("DNS", True, f"{host} wurde zu {', '.join(adressen)} aufgeloest")


def pruefe_tls(host: str, timeout: float) -> Ergebnis:
    """Prueft TCP und die lokale TLS-Zertifikatsvalidierung ohne API-Key."""

    start = time.monotonic()
    try:
        kontext = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as verbindung:
            with kontext.wrap_socket(verbindung, server_hostname=host) as tls:
                version = tls.version() or "unbekannte TLS-Version"
    except (OSError, ssl.SSLError) as fehler:
        return Ergebnis("TCP/TLS", False, exception_kette(fehler))
    dauer = time.monotonic() - start
    return Ergebnis("TCP/TLS", True, f"{version}; Verbindungsaufbau {dauer:.2f} s")


def request_details(fehler: requests.RequestException) -> str:
    """Ordnet Requests-Fehler einer hilfreichen, geheimnisfreien Diagnose zu."""

    if isinstance(fehler, requests.exceptions.SSLError):
        hinweis = "TLS-Zertifikate beziehungsweise lokale CA-Konfiguration pruefen"
    elif isinstance(fehler, requests.exceptions.ProxyError):
        hinweis = "HTTPS_PROXY und NO_PROXY pruefen"
    elif isinstance(fehler, requests.exceptions.ConnectTimeout):
        hinweis = "Firewall, VPN, Proxy oder Erreichbarkeit des Servers pruefen"
    elif isinstance(fehler, requests.exceptions.ReadTimeout):
        hinweis = "Server antwortet zu langsam; Anbieterstatus pruefen"
    elif isinstance(fehler, requests.exceptions.ConnectionError):
        hinweis = "DNS, Firewall, VPN, Proxy und Server-Erreichbarkeit pruefen"
    else:
        hinweis = "Netzwerkverbindung pruefen"
    return f"{exception_kette(fehler)}; {hinweis}"


def pruefe_modelle(
    session: requests.Session, basis_url: str, headers: dict[str, str], timeout: float
) -> tuple[Ergebnis, set[str]]:
    """Prueft Authentifizierung und liest die angebotenen Modell-IDs aus."""

    try:
        response = session.get(f"{basis_url}/models", headers=headers, timeout=timeout)
    except requests.RequestException as fehler:
        return Ergebnis("GET /models", False, request_details(fehler)), set()

    if response.status_code in (401, 403):
        return Ergebnis(
            "GET /models",
            False,
            f"HTTP {response.status_code}; UK_API_KEY wurde abgelehnt oder ist nicht berechtigt",
        ), set()
    if not response.ok:
        return Ergebnis("GET /models", False, sichere_http_details(response)), set()

    try:
        daten = response.json()
        eintraege = daten["data"] if isinstance(daten, dict) and "data" in daten else daten
        if not isinstance(eintraege, list):
            raise TypeError("Modellliste ist keine Liste")
        ids = {
            str(eintrag.get("id") or eintrag.get("name"))
            for eintrag in eintraege
            if isinstance(eintrag, dict) and (eintrag.get("id") or eintrag.get("name"))
        }
    except (requests.JSONDecodeError, TypeError, ValueError, KeyError) as fehler:
        return Ergebnis("GET /models", False, f"Unerwartetes JSON-Format: {type(fehler).__name__}"), set()

    detail = f"{len(ids)} Modell-ID(s): " + (", ".join(sorted(ids)) if ids else "keine IDs gefunden")
    return Ergebnis("GET /models", bool(ids), detail), ids


def pruefe_chat(
    session: requests.Session,
    basis_url: str,
    headers: dict[str, str],
    timeout: float,
    modell: str,
    mit_bild: bool,
) -> Ergebnis:
    """Sendet einen synthetischen Text- oder Bildtest an genau ein Modell."""

    if mit_bild:
        content: str | list[dict[str, Any]] = [
            {"type": "text", "text": "Welche Farbe hat dieses Testbild? Antworte kurz."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{TEST_PNG_BASE64}"},
            },
        ]
        bezeichnung = f"Bild-Chat ({modell})"
    else:
        content = "Antworte exakt mit: Verbindung erfolgreich"
        bezeichnung = f"Text-Chat ({modell})"

    payload = {"model": modell, "messages": [{"role": "user", "content": content}]}
    try:
        response = session.post(
            f"{basis_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as fehler:
        return Ergebnis(bezeichnung, False, request_details(fehler))

    if response.status_code in (401, 403):
        return Ergebnis(
            bezeichnung,
            False,
            f"HTTP {response.status_code}; UK_API_KEY wurde abgelehnt oder ist nicht berechtigt",
        )
    if not response.ok:
        return Ergebnis(bezeichnung, False, sichere_http_details(response))

    try:
        antwort = response.json()["choices"][0]["message"]["content"]
    except (requests.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as fehler:
        return Ergebnis(bezeichnung, False, f"Unerwartetes JSON-Format: {type(fehler).__name__}")
    return Ergebnis(bezeichnung, True, f"Antwortformat gueltig; {len(str(antwort))} Zeichen empfangen")


def argumente() -> argparse.Namespace:
    """Definiert nur nicht geheime Kommandozeilenoptionen."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=STANDARD_BASIS_URL, help="API-Basis inklusive /api")
    parser.add_argument(
        "--model",
        action="append",
        dest="modelle",
        help="Zu testende Modell-ID; mehrfach moeglich (Standard: gemma und medgemma)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout je Test in Sekunden")
    parser.add_argument(
        "--skip-image",
        action="store_true",
        help="Nur DNS, TLS, Modelle und Text testen",
    )
    return parser.parse_args()


def main() -> int:
    """Fuehrt alle Tests nacheinander aus; es gibt keinen automatischen Fallback."""

    args = argumente()
    basis_url = args.base_url.rstrip("/")
    parsed = urlparse(basis_url)
    if parsed.scheme != "https" or not parsed.hostname:
        ausgabe("FEHLER", "Konfiguration", "--base-url muss eine gueltige HTTPS-URL sein")
        return 2
    if args.timeout <= 0:
        ausgabe("FEHLER", "Konfiguration", "--timeout muss groesser als null sein")
        return 2

    api_key = os.getenv("UK_API_KEY", "").strip()
    if not api_key:
        ausgabe("FEHLER", "API-Key", "Umgebungsvariable UK_API_KEY fehlt oder ist leer")
        return 2
    ausgabe("OK", "API-Key", "UK_API_KEY ist gesetzt (Wert wird nicht angezeigt)")

    # Nur die Existenz von Proxy-Variablen wird genannt. Ihre Werte koennen
    # Zugangsdaten enthalten und duerfen deshalb nicht ausgegeben werden.
    proxy_variablen = [name for name in ("HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy") if os.getenv(name)]
    ausgabe("INFO", "Proxy", ", ".join(proxy_variablen) + " gesetzt" if proxy_variablen else "keine HTTPS-Proxy-Variable gesetzt")

    ergebnisse: list[Ergebnis] = [pruefe_dns(parsed.hostname), pruefe_tls(parsed.hostname, args.timeout)]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Eine Session verwendet dieselbe TLS-/Proxy-Konfiguration fuer alle HTTP-
    # Tests. ``trust_env`` bleibt absichtlich aktiv, damit betriebliche Proxies
    # genauso beruecksichtigt werden wie in der eigentlichen Anwendung.
    with requests.Session() as session:
        modell_ergebnis, angebotene_modelle = pruefe_modelle(session, basis_url, headers, args.timeout)
        ergebnisse.append(modell_ergebnis)
        for modell in args.modelle or list(STANDARD_MODELLE):
            if angebotene_modelle and modell not in angebotene_modelle:
                ergebnisse.append(Ergebnis(f"Modell vorhanden ({modell})", False, "nicht in GET /models enthalten"))
            else:
                ergebnisse.append(Ergebnis(f"Modell vorhanden ({modell})", True, "angeboten oder Modellliste nicht auswertbar"))
            ergebnisse.append(pruefe_chat(session, basis_url, headers, args.timeout, modell, False))
            if not args.skip_image:
                ergebnisse.append(pruefe_chat(session, basis_url, headers, args.timeout, modell, True))

    print("\n--- Diagnoseergebnisse ---")
    for ergebnis in ergebnisse:
        ausgabe("OK" if ergebnis.erfolgreich else "FEHLER", ergebnis.test, ergebnis.detail)

    fehlerzahl = sum(not ergebnis.erfolgreich for ergebnis in ergebnisse)
    print(f"\nAbschluss: {len(ergebnisse) - fehlerzahl} erfolgreich, {fehlerzahl} fehlgeschlagen.")
    print("Ein fehlgeschlagener Bildtest bei erfolgreichem Texttest weist auf fehlende Vision-Unterstuetzung hin.")
    return 1 if fehlerzahl else 0


if __name__ == "__main__":
    sys.exit(main())
