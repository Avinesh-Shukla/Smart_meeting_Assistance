from pydantic import BaseModel, Field
from fastapi import APIRouter

from backend.services.meeting_service import meeting_service


router = APIRouter(tags=["analysis"])


class AnalyzeRequest(BaseModel):
    transcript: str = Field(min_length=1)
    participants: list[str] = Field(default_factory=list)


class ActionItem(BaseModel):
    task: str
    assignee: str = ""
    deadline: str = ""


class AnalyzeResponse(BaseModel):
    summary: str
    action_items: list[ActionItem]


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    result = meeting_service.analyze_now(req.transcript, req.participants)
    return AnalyzeResponse(summary=result.get("summary", ""), action_items=result.get("action_items", []))
