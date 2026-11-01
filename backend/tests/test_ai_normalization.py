import pytest

from app.ai.normalization import normalize_extraction_payload, sentence_case
from app.ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT, USER_PROMPT
from app.schemas import ExtractionPayload


@pytest.mark.parametrize(("value", "expected"), [
    (None, None), ("", ""), ("  ĐÈN LED ÂM TRẦN  ", "Đèn led âm trần"),
    ('123 "ỐNG NƯỚC"', '123 "Ống nước"'),
    ("  đe\u0300n ĐIỆN", "Đe\u0300n điện"), ("123", "123"),
])
def test_sentence_case_uses_first_unicode_letter(value, expected):
    assert sentence_case(value) == expected


@pytest.mark.parametrize(("unit", "expected"), [
    ("BOX", "Hộp"), ("pieces", "Cái"), ("bottles", "Chai"),
    ("  HỘP  ", "Hộp"), ("unknown sales unit", "Unknown sales unit"),
    ("kg", "kg"), ("mL", "mL"), ("kW", "kW"), ("m²", "m²"),
    ("µg", "µg"), ("MHz", "MHz"),
    ("m/s", "m/s"), ("kg/m³", "kg/m³"), ("kWh/m²", "kWh/m²"),
    ("N·m", "N·m"), ("kg m^-3", "kg m^-3"), ("m s⁻¹", "m s⁻¹"),
    (None, None),
])
def test_unit_suggestions_use_bounded_vietnamese_aliases(unit, expected):
    result = normalize_extraction_payload(ExtractionPayload(unit_suggestion=unit))
    assert result.unit_suggestion == expected


def test_normalization_copies_payload_and_preserves_structured_facts():
    payload = ExtractionPayload(
        product_name="ĐÈN CHIẾU SÁNG", product_type="ĐÈN", brand="ACME",
        model_number="LED-XyZ", barcode="AbC0123", category_suggestion="CAT_LED",
        unit_suggestion="box", package_size="10 kW / 220 V",
        attributes={"serial": "aBcD", "spec": {"voltage": "220 mV"}, "count": 2},
        confidence={"product_name": 0.9},
    )
    original = payload.model_dump()
    result = normalize_extraction_payload(payload)
    assert result.product_name == "Đèn chiếu sáng"
    assert result.product_type == "Đèn"
    assert result.brand == "Acme"
    assert result.unit_suggestion == "Hộp"
    for field in ("model_number", "barcode", "category_suggestion", "package_size",
                  "attributes", "confidence"):
        assert getattr(result, field) == getattr(payload, field)
    assert payload.model_dump() == original
    assert normalize_extraction_payload(result) == result
    assert normalize_extraction_payload(ExtractionPayload()) == ExtractionPayload()


def test_prompt_requests_vietnamese_names_and_retains_uncertainty_rules():
    assert PROMPT_VERSION == "catalog-v5"
    for prompt in (SYSTEM_PROMPT, USER_PROMPT):
        assert "product_type, product_name, and unit_suggestion in Vietnamese" in prompt
        assert "null" in prompt
    assert "Never guess" in SYSTEM_PROMPT
    assert "preserve manufacturer and brand names" in SYSTEM_PROMPT
