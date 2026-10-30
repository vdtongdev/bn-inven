import logging
import time
from datetime import timedelta

from sqlalchemy import or_, select

from app.ai.openrouter import ProviderPermanentError, ProviderTransientError
from app.ai.providers import PROMPT_VERSION, get_provider
from app.core.config import get_settings
from app.db import SessionLocal
from app.models import (CatalogItem, ExtractionJob, ExtractionResult, JobStatus, ProductDraft,
                        ProductPhoto, ReviewStatus, now_utc)
from app.services import normalize_text, seed_demo_profile

logger = logging.getLogger("bn_inven.worker")


def process_one() -> bool:
    """Claim and process one job; result and draft are committed idempotently."""
    db = SessionLocal()
    try:
        now = now_utc()
        stale_before = now - timedelta(minutes=10)
        job = db.scalar(select(ExtractionJob).where(
            or_(ExtractionJob.status == JobStatus.queued,
                (ExtractionJob.status == JobStatus.running) & (ExtractionJob.updated_at < stale_before)),
            ExtractionJob.next_attempt_at <= now).order_by(ExtractionJob.created_at).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return False
        if job.status == JobStatus.running and job.attempts >= job.max_attempts:
            job.status = JobStatus.failed
            job.last_error = job.last_error or "Worker lease expired after maximum attempts"
            job.updated_at = now
            db.commit()
            return True
        job.status = JobStatus.running
        job.attempts += 1
        job.updated_at = now
        db.commit()
        photo = db.get(ProductPhoto, job.photo_id)
        path = get_settings().storage_path / photo.filename
        try:
            provider = get_provider(get_settings().ai_provider)
            result = provider.extract(path)
            payload = result.payload
            extraction = ExtractionResult(job_id=job.id, photo_id=photo.id,
                schema_version="extraction-v1", provider=result.provider, model=result.model,
                prompt_version=PROMPT_VERSION, raw_response=result.raw_response,
                observed={"product_name": payload.product_name, "product_type": payload.product_type,
                          "brand": payload.brand,
                          "model_number": payload.model_number, "barcode": payload.barcode,
                          "package_size": payload.package_size, "attributes": payload.attributes},
                suggestions={"category_code": payload.category_suggestion,
                             "primary_unit": payload.unit_suggestion,
                             "confidence": payload.confidence})
            db.add(extraction)
            db.flush()
            if photo.draft_id is None:
                duplicate_suggestion = None
                if payload.barcode:
                    catalog_match = db.scalar(select(CatalogItem).where(
                        CatalogItem.barcode == payload.barcode).order_by(CatalogItem.created_at).limit(1))
                    batch_match = db.scalar(select(ProductDraft).where(
                        ProductDraft.batch_id == photo.batch_id,
                        ProductDraft.barcode == payload.barcode,
                        ProductDraft.review_status != ReviewStatus.excluded
                    ).order_by(ProductDraft.created_at).limit(1))
                    if catalog_match:
                        duplicate_suggestion = {
                            "kind": "exact_barcode", "scope": "catalog",
                            "target_id": catalog_match.id, "item_code": catalog_match.item_code,
                            "requires_human_review": True,
                        }
                    elif batch_match:
                        duplicate_suggestion = {
                            "kind": "exact_barcode", "scope": "batch_draft",
                            "target_id": batch_match.id, "item_code": batch_match.item_code,
                            "requires_human_review": True,
                        }
                if duplicate_suggestion is None and payload.model_number:
                    catalog_match = db.scalar(select(CatalogItem).where(
                        CatalogItem.model_number == payload.model_number).order_by(CatalogItem.created_at).limit(1))
                    batch_match = db.scalar(select(ProductDraft).where(
                        ProductDraft.batch_id == photo.batch_id,
                        ProductDraft.model_number == payload.model_number,
                        ProductDraft.review_status != ReviewStatus.excluded
                    ).order_by(ProductDraft.created_at).limit(1))
                    if catalog_match:
                        duplicate_suggestion = {
                            "kind": "exact_model", "scope": "catalog",
                            "target_id": catalog_match.id, "item_code": catalog_match.item_code,
                            "requires_human_review": True,
                        }
                    elif batch_match:
                        duplicate_suggestion = {
                            "kind": "exact_model", "scope": "batch_draft",
                            "target_id": batch_match.id, "item_code": batch_match.item_code,
                            "requires_human_review": True,
                        }
                draft = ProductDraft(batch_id=photo.batch_id, extraction_result_id=extraction.id,
                    item_code=f"BN-{photo.id[:8].upper()}", product_name=normalize_text(payload.product_name),
                    brand=normalize_text(payload.brand), model_number=normalize_text(payload.model_number),
                    barcode=normalize_text(payload.barcode), category_code=payload.category_suggestion,
                    primary_unit=payload.unit_suggestion, package_size=payload.package_size,
                    item_type=None, review_status=ReviewStatus.pending,
                    duplicate_suggestion=duplicate_suggestion)
                db.add(draft)
                db.flush()
                photo.draft_id = draft.id
            job.status = JobStatus.succeeded
            job.last_error = None
            job.updated_at = now_utc()
            db.commit()
            seed_demo_profile(db)
        except ProviderPermanentError as exc:
            db.rollback()
            job = db.get(ExtractionJob, job.id)
            job.last_error = exc.public_message
            job.status = JobStatus.failed
            job.updated_at = now_utc()
            db.commit()
            logger.warning("Extraction job %s stopped: %s", job.id, exc.public_message)
        except Exception as exc:
            db.rollback()
            job = db.get(ExtractionJob, job.id)
            if isinstance(exc, ProviderTransientError):
                public_error = exc.public_message
            else:
                # Do not persist or log provider/transport exception text, which may contain secrets.
                public_error = f"Unexpected extraction failure ({type(exc).__name__})"
            job.last_error = public_error[:1000]
            job.updated_at = now_utc()
            if job.attempts >= job.max_attempts:
                job.status = JobStatus.failed
            else:
                job.status = JobStatus.queued
                job.next_attempt_at = now_utc() + timedelta(seconds=min(60, 2 ** job.attempts))
            db.commit()
            logger.warning("Extraction job %s will not complete this attempt: %s", job.id, public_error)
        return True
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    while True:
        if not process_one():
            time.sleep(get_settings().worker_poll_seconds)


if __name__ == "__main__":
    main()
