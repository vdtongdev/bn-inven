"""OpenRouter chat-completions adapter. All HTTP is injected/testable; never logs inputs."""

import base64
import io
import json
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from app.ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT, USER_PROMPT
from app.ai.providers import ProviderResult
from app.schemas import ExtractionPayload

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_IMAGE_DIMENSION = 1600
JPEG_QUALITY = 84
MAX_OUTPUT_TOKENS = 700


class ProviderError(RuntimeError):
    public_message = "Vision provider request failed"


class ProviderPermanentError(ProviderError):
    """Request cannot succeed unchanged; do not spend another worker attempt."""


class ProviderEmptyContentError(ProviderPermanentError):
    """The provider completed the HTTP request without returning parseable content."""

    public_message = "OpenRouter returned empty message content"


class ProviderTransientError(ProviderError):
    """Network, rate-limit, or provider failure eligible for bounded retry."""


def _encode_inference_image(image_path: Path) -> str:
    try:
        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
            if image.mode in ("RGBA", "LA"):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    except (OSError, ValueError, UnidentifiedImageError):
        raise ProviderPermanentError("Uploaded image could not be prepared for recognition") from None
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


class OpenRouterVisionProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        transport: httpx.BaseTransport | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 45.0,
    ) -> None:
        if not api_key:
            raise ProviderPermanentError("OpenRouter API key is not configured")
        self._api_key = api_key
        self.model = model
        self._transport = transport
        self._timeout = httpx.Timeout(read_timeout, connect=connect_timeout)

    def extract(self, image_path: Path) -> ProviderResult:
        data_url = _encode_inference_image(image_path)
        request_body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "reasoning": {"enabled": False},
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
        }
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                response = client.post(
                    ENDPOINT,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request_body,
                )
        except (httpx.TimeoutException, httpx.NetworkError):
            raise ProviderTransientError("OpenRouter request timed out or could not reach the service") from None
        except httpx.HTTPError:
            raise ProviderTransientError("OpenRouter transport failed") from None

        if response.status_code in (408, 429) or response.status_code >= 500:
            raise ProviderTransientError(f"OpenRouter temporary HTTP failure ({response.status_code})")
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderPermanentError(f"OpenRouter rejected the request ({response.status_code})")
        try:
            raw_response = response.json()
            content = raw_response["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ProviderEmptyContentError("OpenRouter returned empty message content")
            payload_data = json.loads(content)
            payload = ExtractionPayload.model_validate(payload_data)
        except ProviderEmptyContentError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, ValidationError):
            raise ProviderPermanentError("OpenRouter returned an invalid extraction response") from None

        returned_model = raw_response.get("model")
        return ProviderResult(
            payload=payload,
            provider="openrouter",
            model=returned_model if isinstance(returned_model, str) else self.model,
            raw_response={
                "provider_response": raw_response,
                "prompt_version": PROMPT_VERSION,
                "usage": raw_response.get("usage"),
            },
        )
