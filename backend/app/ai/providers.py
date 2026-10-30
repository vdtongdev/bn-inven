from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.ai.prompts import PROMPT_VERSION
from app.schemas import ExtractionPayload


@dataclass
class ProviderResult:
    payload: ExtractionPayload
    provider: str
    model: str
    raw_response: dict


class VisionProvider(Protocol):
    def extract(self, image_path: Path) -> ProviderResult: ...


class MockVisionProvider:
    """Deterministic local adapter; intentionally returns no invented label facts."""

    def extract(self, image_path: Path) -> ProviderResult:
        payload = ExtractionPayload()
        return ProviderResult(payload, "mock", "mock-empty-v1", payload.model_dump())


class ConfiguredVisionProvider:
    """Integration seam for a future selected provider; fails closed without a real adapter."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def extract(self, image_path: Path) -> ProviderResult:
        from app.ai.openrouter import ProviderPermanentError

        raise ProviderPermanentError(f"Vision provider '{self.provider_name}' has no adapter configured")


def get_provider(name: str) -> VisionProvider:
    if name == "mock":
        return MockVisionProvider()
    if name == "openrouter":
        from app.ai.openrouter import OpenRouterVisionProvider
        from app.core.config import get_settings

        settings = get_settings()
        key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else None
        if not key:
            from app.ai.openrouter import ProviderPermanentError

            raise ProviderPermanentError("OpenRouter API key is not configured")
        return OpenRouterVisionProvider(key, settings.ai_model)
    return ConfiguredVisionProvider(name)
