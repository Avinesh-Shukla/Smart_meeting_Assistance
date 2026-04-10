from datetime import datetime, timedelta
from typing import Any

from backend.langgraph_flow import run_analysis
from backend.services import db
from backend.services.email_service import email_service
from backend.services.pinecone_service import PineconeService


class MeetingService:
    def __init__(self) -> None:
        self._pinecone = PineconeService()
        self._last_analysis_at: dict[str, datetime] = {}

    def start_meeting(self, payload: dict[str, Any]) -> str:
        return db.create_meeting(payload)

    def _participant_names(self, participants: list[Any]) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()

        for item in participants or []:
            if isinstance(item, dict):
                raw_name = str(item.get("name", item.get("display_name", ""))).strip()
            else:
                raw_name = str(item).strip()

            if not raw_name:
                continue

            key = raw_name.lower()
            if key in seen:
                continue

            seen.add(key)
            names.append(raw_name)

        return names

    def _participant_email_map(self, participants: list[Any]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for item in participants or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", item.get("display_name", ""))).strip().lower()
            email = str(item.get("email", item.get("email_address", ""))).strip()
            if not name or not email:
                continue
            mapping[name] = email
        return mapping

    def stop_meeting(self, meeting_id: str) -> dict[str, Any]:
        final = self.finalize_meeting(meeting_id)
        db.stop_meeting(meeting_id)
        return final

    def ingest_chunk(self, meeting_id: str, chunk: str, participants: list[Any]) -> None:
        db.append_transcript_chunk(meeting_id, chunk)
        if participants:
            db.update_meeting_participants(meeting_id, participants)
        self._run_incremental_analysis(meeting_id, self._participant_names(participants))

    def _run_incremental_analysis(self, meeting_id: str, participants: list[str]) -> None:
        now = datetime.utcnow()
        last = self._last_analysis_at.get(meeting_id)
        if last and now - last < timedelta(seconds=3):
            return

        transcript = db.get_transcript_text(meeting_id)
        if not transcript.strip():
            return

        platform, stored_participants = db.get_meeting_platform_participants(meeting_id)
        active_participants = participants or self._participant_names(stored_participants)

        analysis = run_analysis(transcript=transcript, participants=active_participants)
        db.set_analysis_result(meeting_id, analysis.get("summary", ""), analysis.get("action_items", []))
        self._last_analysis_at[meeting_id] = now

    def analyze_now(self, transcript: str, participants: list[str]) -> dict[str, Any]:
        return run_analysis(transcript=transcript, participants=participants)

    def get_live_view(self, meeting_id: str) -> dict[str, Any]:
        return {
            "summary": db.get_summary(meeting_id),
            "action_items": db.get_action_items(meeting_id),
            "transcript_preview": db.get_transcript_preview(meeting_id),
        }

    def get_summary(self, meeting_id: str) -> dict[str, Any]:
        return {
            "summary": db.get_summary(meeting_id),
            "action_items": db.get_action_items(meeting_id),
        }

    def update_action_items(self, meeting_id: str, action_items: list[dict[str, str]]) -> list[dict[str, str]]:
        return db.overwrite_action_items(meeting_id, action_items)

    def sync_vectors(self, meeting_id: str) -> int:
        preview = db.get_transcript_preview(meeting_id, limit=500)
        return self._pinecone.upsert_transcript(meeting_id, preview)

    def finalize_meeting(self, meeting_id: str) -> dict[str, Any]:
        transcript = db.get_transcript_text(meeting_id)
        platform, participants_raw = db.get_meeting_platform_participants(meeting_id)
        participants = self._participant_names(participants_raw)

        # Always perform a final write at meeting end so summary/tasks reflect the full transcript.
        if transcript.strip():
            analysis = run_analysis(transcript=transcript, participants=participants)
        else:
            analysis = {"summary": "", "action_items": []}
        db.set_analysis_result(meeting_id, analysis.get("summary", ""), analysis.get("action_items", []))

        summary = db.get_summary(meeting_id)
        action_items = db.get_action_items(meeting_id)
        meeting_url = db.get_meeting_url(meeting_id)
        assignee_email_map = db.get_meeting_participant_email_map(meeting_id)
        if not assignee_email_map:
            assignee_email_map = self._participant_email_map(participants_raw)

        if action_items:
            email_result = email_service.send_task_assignments(
                meeting_id=meeting_id,
                meeting_url=meeting_url,
                summary=summary,
                action_items=action_items,
                assignee_email_map=assignee_email_map,
            )
        else:
            email_result = email_service.send_summary_digest(
                meeting_id=meeting_id,
                meeting_url=meeting_url,
                summary=summary,
                participant_email_map=assignee_email_map,
            )

        return {
            "platform": platform,
            "summary": summary,
            "action_items": action_items,
            "email": email_result,
        }


meeting_service = MeetingService()
