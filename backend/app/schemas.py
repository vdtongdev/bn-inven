from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExtractionPayload(BaseModel):
    """Versioned AI contract; uncertain observations must be null."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_name: str | None = Field(default=None, max_length=240)
    product_type: str | None = Field(default=None, max_length=160)
    brand: str | None = Field(default=None, max_length=160)
    model_number: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=80)
    category_suggestion: str | None = Field(default=None, max_length=80)
    unit_suggestion: str | None = Field(default=None, max_length=40)
    package_size: str | None = Field(default=None, max_length=120)
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, float | None] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, value):
        if any(score is not None and not 0 <= score <= 1 for score in value.values()):
            raise ValueError("confidence values must be between 0 and 1")
        return value


class BatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    created_at: datetime
    photo_count: int = 0
    draft_count: int = 0


class DraftPatch(BaseModel):
    product_name: str | None = Field(default=None, max_length=240)
    brand: str | None = Field(default=None, max_length=160)
    model_number: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=80)
    item_type: str | None = Field(default=None, max_length=40)
    category_code: str | None = Field(default=None, max_length=80)
    primary_unit: str | None = Field(default=None, max_length=40)
    package_size: str | None = Field(default=None, max_length=120)
    review_status: str | None = None


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    batch_id: str
    item_code: str
    product_name: str | None
    brand: str | None
    model_number: str | None
    barcode: str | None
    item_type: str | None
    category_code: str | None
    primary_unit: str | None
    package_size: str | None
    review_status: str
    matched_catalog_item_id: str | None
    duplicate_suggestion: dict | None = None
    created_at: datetime
    updated_at: datetime
    extraction: dict | None = None
    photo_id: str | None = None
    photo_ids: list[str] = Field(default_factory=list)


class DraftAuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action: str
    created_at: datetime
    changes: dict[str, dict[str, Any]]


class ExportCreate(BaseModel):
    profile_id: str
    draft_ids: list[str] = Field(min_length=1)


class ExportOut(BaseModel):
    id: str
    status: str
    item_count: int
    created_at: datetime
    filename: str


class JobOut(BaseModel):
    id: str
    status: str
    attempts: int
    last_error: str | None
    draft_id: str | None = None
