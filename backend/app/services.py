import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (CaptureBatch, CatalogItem, ExtractionJob, ExtractionResult, JobStatus,
                        DraftAuditEvent, MisaExportProfile, ProductDraft, ProductPhoto,
                        ReviewStatus, now_utc)
from app.schemas import ExtractionPayload
from app.product_names import update_final_name


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
    for field in ("product_name", "primary_unit"):
        value = draft.final_name if field == "product_name" else getattr(draft, field)
        if not normalize_text(value):
            missing.append(field)
    return missing


def delete_working_draft(db: Session, draft_id: str) -> None:
    # Acquire SQLite's write lock before checking jobs, serializing against worker claims.
    locked = db.execute(update(ProductDraft).where(ProductDraft.id == draft_id)
                        .values(updated_at=ProductDraft.updated_at))
    if not locked.rowcount:
        raise HTTPException(404, "Draft not found")
    draft = db.get(ProductDraft, draft_id)
    if draft.review_status == ReviewStatus.approved:
        raise HTTPException(409, "Approved catalog items cannot be removed")
    photos = db.scalars(select(ProductPhoto).where(ProductPhoto.draft_id == draft_id)).all()
    photo_ids = [photo.id for photo in photos]
    running = db.scalar(select(ExtractionJob.id).where(
        ExtractionJob.photo_id.in_(photo_ids), ExtractionJob.status == JobStatus.running).limit(1))
    if running:
        raise HTTPException(409, "Recognition is running; retry removal after it finishes")
    try:
        for photo in photos:
            (get_settings().storage_path / photo.filename).unlink(missing_ok=True)
    except OSError:
        raise HTTPException(500, "Images could not be fully removed; retry removal") from None
    # Delete the draft first to release its reference to an extraction result.
    db.execute(delete(ProductDraft).where(ProductDraft.id == draft_id))
    # Foreign keys cascade to jobs and results; draft deletion cascades to audit events.
    db.execute(delete(ProductPhoto).where(ProductPhoto.id.in_(photo_ids)))
    db.commit()


_DRAFT_AUDIT_FIELDS = (
    "product_name", "product_type", "brand", "model_number", "barcode", "category_code",
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
    update_final_name(draft)
    missing = validate_draft(draft)
    if missing:
        raise HTTPException(422, {"message": "Draft is missing required fields", "fields": missing})
    draft.product_name = normalize_text(draft.product_name)
    draft.primary_unit = normalize_text(draft.primary_unit)
    draft.review_status = ReviewStatus.approved
    catalog = CatalogItem(item_code=draft.item_code, product_name=draft.final_name,
                          brand=draft.brand, model_number=draft.model_number, barcode=draft.barcode,
                          category_code=draft.category_code,
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
                                                 "model_number": 4, "barcode": 5,
                                                 "category_code": 6, "primary_unit": 7, "package_size": 8},
                                 required_fields=["item_code", "product_name", "primary_unit"],
                                 permitted_values={}, is_demo=True))
        db.commit()
