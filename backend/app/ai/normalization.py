"""Presentation rules for new AI suggestions, independent of provider adapters."""

import re

from app.schemas import ExtractionPayload


# Only unambiguous package units belong here. General product translation is the
# model's responsibility; ambiguous units must remain suggestions for review.
_VIETNAMESE_UNITS = {
    "piece": "cái", "pieces": "cái",
    "box": "hộp", "boxes": "hộp",
    "bag": "túi", "bags": "túi",
    "bottle": "chai", "bottles": "chai",
    "can": "lon", "cans": "lon",
    "pair": "đôi", "pairs": "đôi",
    "roll": "cuộn", "rolls": "cuộn",
}

# Symbols are case-sensitive data even when used as the sales unit. Include
# common SI prefixes without trying to infer or correct a provider's spelling.
_MEASUREMENT_SYMBOLS = {
    prefix + symbol
    for prefix in ("", "p", "n", "µ", "μ", "m", "c", "d", "da", "h", "k", "M", "G", "T")
    for symbol in ("g", "m", "m²", "m³", "s", "L", "l", "A", "V", "W", "Wh", "Ah",
                   "Hz", "Pa", "N", "J", "Ω", "mol", "cd")
} | {"t", "min", "h", "K", "°C", "°F", "%"}


def _is_measurement_unit(value: str) -> bool:
    # Recognize compound symbols, with optional signed integer exponents. Every
    # component must be a known symbol; ordinary unit names still use casing.
    components = re.split(r"\s*(?:/|\*|·|⋅|\s+)\s*", value)
    return bool(components) and all(
        component in _MEASUREMENT_SYMBOLS
        or re.sub(r"(?:\^?-?\d+|[⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+)$", "", component) in _MEASUREMENT_SYMBOLS
        for component in components
    )


def sentence_case(value: str | None) -> str | None:
    """Uppercase the first Unicode letter, including after digits/punctuation."""
    if value is None:
        return None
    text = value.strip().lower()
    for index, character in enumerate(text):
        if character.isalpha():
            return text[:index] + character.upper() + text[index + 1:]
    return text


def normalize_extraction_payload(payload: ExtractionPayload) -> ExtractionPayload:
    """Copy descriptive suggestions without changing source evidence or codes.

    Package measurements and arbitrary attributes can contain case-sensitive SI
    units or identifiers. They are intentionally outside presentation casing.
    This function is never applied to human edits or existing stored records.
    """
    unit = payload.unit_suggestion
    if unit is not None:
        unit = _VIETNAMESE_UNITS.get(unit.strip().casefold(), unit)
        unit = unit.strip() if _is_measurement_unit(unit.strip()) else sentence_case(unit)
    return payload.model_copy(update={
        "product_name": sentence_case(payload.product_name),
        "product_type": sentence_case(payload.product_type),
        "brand": sentence_case(payload.brand),
        "unit_suggestion": unit,
    })
