from fastapi import APIRouter

from backend.services import db
from backend.services.email_service import email_service


router = APIRouter(tags=["emails"])


@router.get("/emails/stats")
def email_stats() -> dict[str, int]:
    return db.get_email_job_stats()


@router.post("/emails/process")
def process_email_queue() -> dict[str, int]:
    return email_service.process_pending_email_jobs(limit=50)
