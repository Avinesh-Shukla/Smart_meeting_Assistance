from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from backend.services.meeting_service import meeting_service
from backend.services import db


router = APIRouter(tags=["meetings"])


class StartMeetingRequest(BaseModel):
    tab_id: int | None = None
    platform: str = "unknown"
    meeting_url: str
    meeting_external_id: str = ""
    participants: list[Any] = Field(default_factory=list)


class StopMeetingRequest(BaseModel):
    meeting_id: str


class UpdateActionItemsRequest(BaseModel):
    action_items: list[dict[str, str]]


class ParticipantRecord(BaseModel):
    name: str = Field(min_length=1)
    email: str = ""
    source: str = "extension"


class UpdateParticipantsRequest(BaseModel):
    participants: list[ParticipantRecord] = Field(default_factory=list)


@router.post("/meeting/start")
def start_meeting(req: StartMeetingRequest):
    meeting_id = meeting_service.start_meeting(req.model_dump())
    return {"meeting_id": meeting_id, "status": "active"}


@router.post("/meeting/stop")
def stop_meeting(req: StopMeetingRequest):
    result = meeting_service.stop_meeting(req.meeting_id)
    return {"ok": True, **result}


@router.get("/meeting/{meeting_id}/live")
def meeting_live(meeting_id: str):
    return meeting_service.get_live_view(meeting_id)


@router.get("/meeting/{meeting_id}/summary")
def meeting_summary(meeting_id: str):
    return meeting_service.get_summary(meeting_id)


@router.post("/meeting/{meeting_id}/sync")
def sync_meeting(meeting_id: str):
    vector_count = meeting_service.sync_vectors(meeting_id)
    return {"ok": True, "vector_count": vector_count}


@router.put("/meeting/{meeting_id}/action-items")
def update_action_items(meeting_id: str, req: UpdateActionItemsRequest):
    if not isinstance(req.action_items, list):
        raise HTTPException(status_code=400, detail="action_items must be a list")
    items = meeting_service.update_action_items(meeting_id, req.action_items)
    return {"ok": True, "action_items": items}


@router.post("/meeting/{meeting_id}/participants")
def update_participants(meeting_id: str, req: UpdateParticipantsRequest):
    if not meeting_id:
        raise HTTPException(status_code=400, detail="meeting_id is required")

    participants = [item.model_dump() for item in req.participants]
    stored = db.upsert_meeting_participants(meeting_id, participants)
    return {"ok": True, "participants": stored}
