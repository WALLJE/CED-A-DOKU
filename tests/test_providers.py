"""Prüft Bildbegrenzung und Antwortverarbeitung ohne externen API-Aufruf."""

from pathlib import Path
from unittest.mock import Mock, patch

from ced_document_ai.services.ai.providers import OpenAICompatibleProvider


def test_provider_sends_at_most_five_images_per_request(tmp_path: Path) -> None:
    pages = []
    for number in range(6):
        page = tmp_path / f"page_{number}.png"
        page.write_bytes(b"testbild")
        pages.append(page)

    provider = OpenAICompatibleProvider(
        endpoint="https://example.invalid/chat/completions",
        model="gemma4-31b",
        api_key="nur-testwert",
        provider_name="Test",
    )
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": "Text"}}]}

    with patch("ced_document_ai.services.ai.providers.requests.post", return_value=response) as post:
        result = provider.analyze(pages, "Test", [], {})

    assert post.call_count == 2
    image_counts = [
        len(call.kwargs["json"]["messages"][0]["content"]) - 1
        for call in post.call_args_list
    ]
    assert image_counts == [5, 1]
    assert result == "Text\n\nText"
    # Die technische Aufteilung darf weder im Prompt als nummerierter Auftrag noch
    # im zurückgegebenen Transkript sichtbare Dokumentteilnummern erzeugen.
    prompts = [call.kwargs["json"]["messages"][0]["content"][0]["text"] for call in post.call_args_list]
    assert all("Teil 1" not in prompt and "Teil 2" not in prompt for prompt in prompts)
    assert all("keine Seitenzahlen, Dokumentnummern" in prompt for prompt in prompts)
