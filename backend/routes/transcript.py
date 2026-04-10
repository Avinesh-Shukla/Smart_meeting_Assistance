from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from backend.services.meeting_service import meeting_service


router = APIRouter(tags=["transcript"])


class TranscriptChunkRequest(BaseModel):
    meeting_id: str
    chunk: str = Field(min_length=1)
    participants: list[Any] = Field(default_factory=list)


@router.post("/transcript/chunk")
def transcript_chunk(req: TranscriptChunkRequest):
    if not req.meeting_id:
        raise HTTPException(status_code=400, detail="meeting_id is required")

    meeting_service.ingest_chunk(req.meeting_id, req.chunk, req.participants)
    return {"ok": True}
