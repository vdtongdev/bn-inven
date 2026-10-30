import logging
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.exporters.demo_xlsx import make_workbook
from app.models import (CaptureBatch, DraftAuditEvent, ExportRun, ExtractionJob,
                        ExtractionResult, JobStatus, MisaExportProfile, ProductDraft,
                        ProductPhoto, ReviewStatus)
from app.schemas import (BatchCreate, DraftAuditEventOut, DraftOut, DraftPatch, ExportCreate,
                         ExportOut, JobOut)
from app.services import (approve_draft, draft_audit_snapshot, record_draft_audit_event,
                          save_photo, seed_demo_profile, validate_draft)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("bn_inven.api")
app = FastAPI(title="BN-Inven API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().allowed_origins,
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])


def draft_output(db: Session, draft: ProductDraft) -> dict:
    extraction = db.get(ExtractionResult, draft.extraction_result_id) if draft.extraction_result_id else None
    return {"id": draft.id, "batch_id": draft.batch_id, "item_code": draft.item_code,
            "product_name": draft.product_name, "brand": draft.brand, "model_number": draft.model_number,
            "barcode": draft.barcode, "item_type": draft.item_type, "category_code": draft.category_code,
            "primary_unit": draft.primary_unit, "package_size": draft.package_size,
            "review_status": draft.review_status.value, "matched_catalog_item_id": draft.matched_catalog_item_id,
            "duplicate_suggestion": draft.duplicate_suggestion,
            "created_at": draft.created_at, "updated_at": draft.updated_at,
            "extraction": {"provider": extraction.provider, "model": extraction.model,
                           "prompt_version": extraction.prompt_version, "observed": extraction.observed,
                           "suggestions": extraction.suggestions, "raw_response": extraction.raw_response}
                          if extraction else None,
            "photo_id": extraction.photo_id if extraction else None,
            "photo_ids": [photo.id for photo in draft.batch.photos if photo.draft_id == draft.id]}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "bn-inven-api"}


@app.post("/api/batches", status_code=201)
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    batch = CaptureBatch(name=payload.name.strip())
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return {"id": batch.id, "name": batch.name, "created_at": batch.created_at,
            "photo_count": 0, "draft_count": 0}


@app.get("/api/batches")
def list_batches(db: Session = Depends(get_db)):
    batches = db.scalars(select(CaptureBatch).order_by(CaptureBatch.created_at.desc())).all()
    return [{"id": b.id, "name": b.name, "created_at": b.created_at,
             "photo_count": len(b.photos), "draft_count": len(b.drafts)} for b in batches]


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(CaptureBatch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    return {"id": batch.id, "name": batch.name, "created_at": batch.created_at,
            "photos": [{"id": p.id, "filename": p.filename, "width": p.width, "height": p.height}
                       for p in batch.photos],
            "draft_count": len(batch.drafts)}


@app.post("/api/batches/{batch_id}/photos", status_code=202)
async def upload_photo(batch_id: str, file: UploadFile = File(...), draft_id: str | None = Form(None),
                       db: Session = Depends(get_db)):
    batch = db.get(CaptureBatch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    draft = db.get(ProductDraft, draft_id) if draft_id else None
    if draft_id and (not draft or draft.batch_id != batch.id):
        raise HTTPException(404, "Draft not found in this batch")
    if draft and draft.review_status in (ReviewStatus.approved, ReviewStatus.excluded):
        raise HTTPException(409, "Approved or excluded products cannot receive new photos in this MVP")
    photo, job = await save_photo(db, batch, file, draft)
    return {"photo_id": photo.id, "job_id": job.id, "status": job.status.value}


@app.get("/api/batches/{batch_id}/drafts", response_model=list[DraftOut])
def list_drafts(batch_id: str, db: Session = Depends(get_db)):
    if not db.get(CaptureBatch, batch_id):
        raise HTTPException(404, "Batch not found")
    drafts = db.scalars(select(ProductDraft).where(ProductDraft.batch_id == batch_id)
                        .order_by(ProductDraft.created_at)).all()
    return [draft_output(db, draft) for draft in drafts]


@app.get("/api/photos/{photo_id}/image")
def get_photo_image(photo_id: str, db: Session = Depends(get_db)):
    photo = db.get(ProductPhoto, photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")
    path = get_settings().storage_path / photo.filename
    if not path.is_file():
        raise HTTPException(410, "Source image is unavailable")
    return FileResponse(path, media_type=photo.content_type, filename=photo.filename)


@app.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ExtractionJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {"id": job.id, "status": job.status.value, "attempts": job.attempts,
            "last_error": job.last_error, "draft_id": job.photo.draft_id}


@app.get("/api/drafts/{draft_id}/history", response_model=list[DraftAuditEventOut])
def draft_history(draft_id: str, db: Session = Depends(get_db)):
    if not db.get(ProductDraft, draft_id):
        raise HTTPException(404, "Draft not found")
    events = db.scalars(
        select(DraftAuditEvent)
        .where(DraftAuditEvent.draft_id == draft_id)
        .order_by(DraftAuditEvent.created_at.asc(), DraftAuditEvent.id.asc())
    ).all()
    return events


@app.patch("/api/drafts/{draft_id}", response_model=DraftOut)
def update_draft(draft_id: str, payload: DraftPatch, db: Session = Depends(get_db)):
    draft = db.get(ProductDraft, draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    before = draft_audit_snapshot(draft)
    data = payload.model_dump(exclude_unset=True)
    if data.pop("review_status", None) == ReviewStatus.excluded.value:
        draft.review_status = ReviewStatus.excluded
    elif draft.review_status == ReviewStatus.approved:
        raise HTTPException(409, "Approved catalog items are immutable in this MVP")
    else:
        for field, value in data.items():
            setattr(draft, field, value.strip() if isinstance(value, str) else value)
        draft.review_status = ReviewStatus.needs_correction
    action = "excluded" if draft.review_status == ReviewStatus.excluded else "edited"
    record_draft_audit_event(db, draft, action, before)
    db.commit()
    db.refresh(draft)
    return draft_output(db, draft)


@app.post("/api/drafts/{draft_id}/approve", response_model=DraftOut)
def approve(draft_id: str, db: Session = Depends(get_db)):
    draft = db.get(ProductDraft, draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    if draft.review_status == ReviewStatus.approved:
        return draft_output(db, draft)
    return draft_output(db, approve_draft(db, draft))


@app.get("/api/export-profiles")
def export_profiles(db: Session = Depends(get_db)):
    seed_demo_profile(db)
    return [{"id": p.id, "code": p.code, "name": p.name, "worksheet_name": p.worksheet_name,
             "start_row": p.start_row, "column_mapping": p.column_mapping,
             "required_fields": p.required_fields, "is_demo": p.is_demo}
            for p in db.scalars(select(MisaExportProfile)).all()]


@app.post("/api/exports", status_code=201, response_model=ExportOut)
def create_export(payload: ExportCreate, db: Session = Depends(get_db)):
    profile = db.get(MisaExportProfile, payload.profile_id)
    if not profile:
        raise HTTPException(404, "Export profile not found")
    drafts = db.scalars(select(ProductDraft).where(ProductDraft.id.in_(payload.draft_ids))).all()
    if len(drafts) != len(set(payload.draft_ids)):
        raise HTTPException(404, "One or more drafts were not found")
    if any(d.review_status != ReviewStatus.approved for d in drafts):
        raise HTTPException(422, "Only approved drafts can be exported")
    missing = {d.item_code: validate_draft(d) for d in drafts}
    missing = {code: fields for code, fields in missing.items() if fields}
    for row, draft in zip(rows := [{"item_code": d.item_code, "product_name": d.product_name, "brand": d.brand,
                                   "model_number": d.model_number, "barcode": d.barcode, "item_type": d.item_type,
                                   "category_code": d.category_code, "primary_unit": d.primary_unit,
                                   "package_size": d.package_size} for d in drafts], drafts):
        for field in profile.required_fields:
            if row.get(field) in (None, ""):
                missing.setdefault(draft.item_code, []).append(field)
        for field, allowed in profile.permitted_values.items():
            if row.get(field) not in (None, "") and row[field] not in allowed:
                missing.setdefault(draft.item_code, []).append(f"{field} must be one of {allowed}")
    if missing:
        raise HTTPException(422, {"message": "Required fields missing", "items": missing})
    content = make_workbook(profile, rows)
    export_id = str(uuid.uuid4())
    export_dir = get_settings().storage_path.parent / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"bn-inven-{profile.code.lower()}-{export_id[:8]}.xlsx"
    path = export_dir / filename
    path.write_bytes(content)
    run = ExportRun(id=export_id, profile_id=profile.id, file_path=str(path), item_count=len(rows), snapshot=rows)
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "status": run.status, "item_count": run.item_count,
            "created_at": run.created_at, "filename": filename}


@app.get("/api/exports/{export_id}/download")
def download_export(export_id: str, db: Session = Depends(get_db)):
    run = db.get(ExportRun, export_id)
    if not run:
        raise HTTPException(404, "Export not found")
    path = Path(run.file_path)
    if not path.is_file():
        raise HTTPException(410, "Export file is unavailable")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename=path.name)
