import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index,
                        Integer, JSON, String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class ReviewStatus(str, enum.Enum):
    pending = "Pending"
    needs_correction = "NeedsCorrection"
    approved = "Approved"
    excluded = "Excluded"


class JobStatus(str, enum.Enum):
    queued = "Queued"
    running = "Running"
    succeeded = "Succeeded"
    failed = "Failed"


class CaptureBatch(Base):
    __tablename__ = "capture_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    photos: Mapped[list["ProductPhoto"]] = relationship(back_populates="batch", cascade="all, delete-orphan")
    drafts: Mapped[list["ProductDraft"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class ProductPhoto(Base):
    __tablename__ = "product_photos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("capture_batches.id", ondelete="CASCADE"), index=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("product_drafts.id", ondelete="SET NULL"), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    batch: Mapped[CaptureBatch] = relationship(back_populates="photos")
    jobs: Mapped[list["ExtractionJob"]] = relationship(back_populates="photo", cascade="all, delete-orphan")
    draft: Mapped["ProductDraft | None"] = relationship(back_populates="additional_photos", foreign_keys=[draft_id])


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    photo_id: Mapped[str] = mapped_column(ForeignKey("product_photos.id", ondelete="CASCADE"), index=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    photo: Mapped[ProductPhoto] = relationship(back_populates="jobs")
    result: Mapped["ExtractionResult | None"] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")
    __table_args__ = (Index("ix_job_claim", "status", "next_attempt_at"),)


class ExtractionResult(Base):
    __tablename__ = "extraction_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("extraction_jobs.id", ondelete="CASCADE"), unique=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("product_photos.id", ondelete="CASCADE"), index=True)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_response: Mapped[dict] = mapped_column(JSON, nullable=False)
    observed: Mapped[dict] = mapped_column(JSON, nullable=False)
    suggestions: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    job: Mapped[ExtractionJob] = relationship(back_populates="result")


class CatalogItem(Base):
    __tablename__ = "catalog_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    item_code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(160))
    model_number: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(80), index=True)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False)
    category_code: Mapped[str | None] = mapped_column(String(80))
    primary_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    package_size: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class ProductDraft(Base):
    __tablename__ = "product_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("capture_batches.id", ondelete="CASCADE"), index=True)
    extraction_result_id: Mapped[str | None] = mapped_column(ForeignKey("extraction_results.id", ondelete="SET NULL"), unique=True)
    item_code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    product_name: Mapped[str | None] = mapped_column(String(240), index=True)
    brand: Mapped[str | None] = mapped_column(String(160))
    model_number: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(80), index=True)
    item_type: Mapped[str | None] = mapped_column(String(40))
    category_code: Mapped[str | None] = mapped_column(String(80))
    primary_unit: Mapped[str | None] = mapped_column(String(40))
    package_size: Mapped[str | None] = mapped_column(String(120))
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.pending, index=True)
    matched_catalog_item_id: Mapped[str | None] = mapped_column(ForeignKey("catalog_items.id", ondelete="SET NULL"))
    duplicate_suggestion: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    batch: Mapped[CaptureBatch] = relationship(back_populates="drafts")
    additional_photos: Mapped[list[ProductPhoto]] = relationship(back_populates="draft", foreign_keys="ProductPhoto.draft_id")
    extraction_result: Mapped[ExtractionResult | None] = relationship()
    matched_catalog_item: Mapped[CatalogItem | None] = relationship()
    audit_events: Mapped[list["DraftAuditEvent"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DraftAuditEvent.created_at, DraftAuditEvent.id",
    )


class DraftAuditEvent(Base):
    __tablename__ = "draft_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("product_drafts.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    draft: Mapped[ProductDraft] = relationship(back_populates="audit_events")
    __table_args__ = (
        CheckConstraint("action IN ('edited', 'approved', 'excluded')", name="ck_draft_audit_action"),
        Index("ix_draft_audit_events_draft_created", "draft_id", "created_at"),
    )


class MisaExportProfile(Base):
    __tablename__ = "misa_export_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    worksheet_name: Mapped[str] = mapped_column(String(31), nullable=False)
    start_row: Mapped[int] = mapped_column(Integer, nullable=False)
    column_mapping: Mapped[dict] = mapped_column(JSON, nullable=False)
    required_fields: Mapped[list] = mapped_column(JSON, nullable=False)
    permitted_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ExportRun(Base):
    __tablename__ = "export_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("misa_export_profiles.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(32), default="Succeeded", nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    profile: Mapped[MisaExportProfile] = relationship()
