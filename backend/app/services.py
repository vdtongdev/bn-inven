import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (CaptureBatch, CatalogItem, ExtractionJob, ExtractionResult, JobStatus,
                        DraftAuditEvent, MisaExportProfile, ProductDraft, ProductPhoto,
                        ReviewStatus, now_utc)
from app.schemas import ExtractionPayload


def normalize_text(value: str | None) -> str | None:
    value = " ".join(value.split()) if value else None
    return value or None


async def save_photo(db: Session, batch: CaptureBatch, upload: UploadFile,
                     draft: ProductDraft | None = None) -> tuple[ProductPhoto, ExtractionJob]:
    settings = get_settings()
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if upload.content_type not in allowed:
        raise HTTPException(415, "Upload a JPEG, PNG, or WebP image")
    data = await upload.read(settings.max_upload_bytes + 1)
    if not data or len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is empty or exceeds the upload limit")
    digest = hashlib.sha256(data).hexdigest()
    existing_query = select(ProductPhoto).where(ProductPhoto.batch_id == batch.id,
                                                ProductPhoto.sha256 == digest)
    if draft:
        # A duplicate image belonging to another product must not redirect this upload.
        existing_query = existing_query.where(ProductPhoto.draft_id == draft.id)
    else:
        # An excluded product stays excluded; a new capture needs a reviewable draft.
        existing_query = existing_query.outerjoin(ProductDraft, ProductPhoto.draft_id == ProductDraft.id).where(
            or_(ProductPhoto.draft_id.is_(None), ProductDraft.review_status != ReviewStatus.excluded))
    existing = db.scalar(existing_query.order_by(ProductPhoto.created_at.desc()))
    if existing:
        job = db.scalar(select(ExtractionJob).where(ExtractionJob.photo_id == existing.id)
                        .order_by(ExtractionJob.created_at.desc()))
        if job:
            return existing, job
    safe_name = f"{uuid.uuid4().hex}{allowed[upload.content_type]}"
    try:
        import io
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width < 1 or height < 1 or width * height > settings.max_image_pixels:
                raise HTTPException(413, "Image dimensions are not allowed")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Image could not be decoded") from None
    target = settings.storage_path / safe_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    photo = ProductPhoto(batch_id=batch.id, draft_id=draft.id if draft else None,
                         filename=safe_name, content_type=upload.content_type,
                         byte_size=len(data), width=width, height=height, sha256=digest)
    db.add(photo)
    db.flush()
    job = ExtractionJob(photo_id=photo.id, max_attempts=get_settings().worker_max_attempts)
    db.add(job)
    db.commit()
    db.refresh(photo)
    db.refresh(job)
    return photo, job


def validate_draft(draft: ProductDraft) -> list[str]:
    missing = []
    for field in ("product_name", "item_type", "primary_unit"):
        if not normalize_text(getattr(draft, field)):
            missing.append(field)
    return missing


_DRAFT_AUDIT_FIELDS = (
    "product_name", "brand", "model_number", "barcode", "item_type", "category_code",
    "primary_unit", "package_size", "review_status", "matched_catalog_item_id",
)


def draft_audit_snapshot(draft: ProductDraft) -> dict[str, str | None]:
    snapshot = {}
    for field in _DRAFT_AUDIT_FIELDS:
        value = getattr(draft, field)
        snapshot[field] = value.value if isinstance(value, ReviewStatus) else value
    return snapshot


def record_draft_audit_event(
    db: Session,
    draft: ProductDraft,
    action: str,
    before: dict[str, str | None],
) -> DraftAuditEvent | None:
    after = draft_audit_snapshot(draft)
    changes = {
        field: {"before": before[field], "after": after[field]}
        for field in _DRAFT_AUDIT_FIELDS
        if before[field] != after[field]
    }
    if not changes:
        return None
    event = DraftAuditEvent(draft_id=draft.id, action=action, changes=changes)
    db.add(event)
    return event


def approve_draft(db: Session, draft: ProductDraft) -> ProductDraft:
    before = draft_audit_snapshot(draft)
    missing = validate_draft(draft)
    if missing:
        raise HTTPException(422, {"message": "Draft is missing required fields", "fields": missing})
    draft.product_name = normalize_text(draft.product_name)
    draft.primary_unit = normalize_text(draft.primary_unit)
    draft.review_status = ReviewStatus.approved
    catalog = CatalogItem(item_code=draft.item_code, product_name=draft.product_name,
                          brand=draft.brand, model_number=draft.model_number, barcode=draft.barcode,
                          item_type=draft.item_type, category_code=draft.category_code,
                          primary_unit=draft.primary_unit, package_size=draft.package_size)
    db.add(catalog)
    db.flush()
    draft.matched_catalog_item_id = catalog.id
    record_draft_audit_event(db, draft, "approved", before)
    db.commit()
    db.refresh(draft)
    return draft


def seed_demo_profile(db: Session) -> None:
    profile = db.scalar(select(MisaExportProfile).where(MisaExportProfile.code == "GENERIC_DEMO"))
    if not profile:
        db.add(MisaExportProfile(code="GENERIC_DEMO", name="GENERIC / DEMO (not an official MISA template)",
                                 worksheet_name="Demo Items", start_row=2,
                                 column_mapping={"item_code": 1, "product_name": 2, "brand": 3,
                                                 "model_number": 4, "barcode": 5, "item_type": 6,
                                                 "category_code": 7, "primary_unit": 8, "package_size": 9},
                                 required_fields=["item_code", "product_name", "item_type", "primary_unit"],
                                 permitted_values={}, is_demo=True))
        db.commit()
