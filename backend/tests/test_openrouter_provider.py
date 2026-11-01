import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.ai.openrouter import (
    OpenRouterVisionProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from app.ai.providers import MockVisionProvider
from app.ai.prompts import PROMPT_VERSION
from app.core.config import Settings


SECRET = "test-secret-that-must-not-leak"


def make_image(path: Path) -> None:
    Image.new("RGB", (160, 80), "white").save(path, format="PNG")


def completion(content: str, **extra):
    return {
        "id": "chatcmpl-test",
        "model": "nvidia/nemotron-3.5-super-vl:free",
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
        **extra,
    }


def test_openrouter_sends_bounded_image_and_preserves_trace_metadata(tmp_path, caplog):
    path = tmp_path / "original.png"
    make_image(path)
    original = path.read_bytes()
    captured = {}

    def handler(request: httpx.Request):
        captured["request"] = request
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=completion(json.dumps({
            "product_name": "Visible item", "brand": None, "model_number": None,
            "barcode": None, "category_suggestion": None, "unit_suggestion": None,
            "package_size": None, "attributes": {}, "confidence": {},
        })))

    provider = OpenRouterVisionProvider(SECRET, "nvidia/nemotron-3.5-super-vl:free", transport=httpx.MockTransport(handler))
    result = provider.extract(path)

    request = captured["request"]
    body = captured["body"]
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert body["model"] == "nvidia/nemotron-3.5-super-vl:free"
    assert body["max_tokens"] == 700
    assert body["reasoning"] == {"enabled": False}
    assert "Never guess" in body["messages"][0]["content"]
    image_url = body["messages"][1]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    assert result.payload.product_name == "Visible item"
    assert result.payload.barcode is None
    assert result.provider == "openrouter"
    assert result.model == "nvidia/nemotron-3.5-super-vl:free"
    assert result.raw_response["usage"]["total_tokens"] == 130
    assert result.raw_response["prompt_version"] == PROMPT_VERSION
    assert SECRET not in repr(result)
    assert SECRET not in caplog.text
    assert path.read_bytes() == original


@pytest.mark.parametrize("content", [
    "not json",
    '{"product_name":"x","unexpected":"extra"}',
    '{"product_name":"x","confidence":{"product_name":2}}',
])
def test_openrouter_rejects_malformed_or_invalid_payload_without_secret(tmp_path, content):
    path = tmp_path / "label.png"
    make_image(path)
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=completion(content)))
    provider = OpenRouterVisionProvider(SECRET, "nvidia/nemotron-3.5-super-vl:free", transport=transport)
    with pytest.raises(ProviderPermanentError) as error:
        provider.extract(path)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("content", [None, "", "   ", [], 17])
def test_openrouter_empty_or_non_text_message_content_has_distinct_failure_classification(tmp_path, content):
    path = tmp_path / "label.png"
    make_image(path)
    body = completion("")
    body["choices"][0]["message"]["content"] = content
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=body))
    provider = OpenRouterVisionProvider(SECRET, "nvidia/nemotron-3.5-super-vl:free", transport=transport)

    with pytest.raises(ProviderPermanentError) as error:
        provider.extract(path)

    assert str(error.value) == "OpenRouter returned empty message content"
    assert error.value.public_message == "OpenRouter returned empty message content"


@pytest.mark.parametrize(("status", "error_type"), [(401, ProviderPermanentError),
                                                       (429, ProviderTransientError),
                                                       (503, ProviderTransientError)])
def test_openrouter_classifies_http_errors_without_echoing_response(tmp_path, status, error_type):
    path = tmp_path / "label.png"
    make_image(path)
    transport = httpx.MockTransport(lambda _request: httpx.Response(status, text=SECRET))
    provider = OpenRouterVisionProvider(SECRET, "nvidia/nemotron-3.5-super-vl:free", transport=transport)
    with pytest.raises(error_type) as error:
        provider.extract(path)
    assert SECRET not in str(error.value)


def test_openrouter_timeout_is_retryable_and_mock_remains_default(tmp_path, monkeypatch):
    path = tmp_path / "label.png"
    make_image(path)
    def timeout(_request):
        raise httpx.ReadTimeout("transport timeout")

    provider = OpenRouterVisionProvider(SECRET, "nvidia/nemotron-3.5-super-vl:free", transport=httpx.MockTransport(timeout))
    with pytest.raises(ProviderTransientError) as error:
        provider.extract(path)
    assert SECRET not in str(error.value)
    assert Settings().ai_provider == "mock"
    monkeypatch.delenv("AI_MODEL", raising=False)
    assert Settings(_env_file=None).ai_model == "nvidia/nemotron-3.5-super-vl:free"
    assert MockVisionProvider().extract(Path("unused")).payload.product_name is None
