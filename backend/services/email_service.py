import json
import requests
import threading
import time
from typing import Any

from backend.config import get_settings
from backend.services import db


class EmailService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def _email_map(self) -> dict[str, str]:
        try:
            value = json.loads(self._settings.assignee_email_map or "{}")
            if isinstance(value, dict):
                return {str(k).strip().lower(): str(v).strip() for k, v in value.items() if str(v).strip()}
        except json.JSONDecodeError:
            return {}
        return {}

    def _resolve_assignee_email(self, assignee: str, assignee_email_map: dict[str, str] | None = None) -> str:
        cleaned = (assignee or "").strip()
        if not cleaned:
            return ""
        if "@" in cleaned:
            return cleaned
        if assignee_email_map and cleaned.lower() in assignee_email_map:
            return assignee_email_map[cleaned.lower()].strip()
        return self._email_map().get(cleaned.lower(), "")

    def _dispatch_ready(self) -> bool:
        """Dispatch is ready when the nodemailer service URL is configured."""
        return bool(self._email_service_url())
    
    def _email_service_url(self) -> str:
        """Get email service endpoint (Node.js nodemailer service)"""
        base = self._settings.email_service_url or "http://127.0.0.1:3001"
        return base.rstrip("/")
    
    def _build_email_body(self, meeting_id: str, meeting_url: str, summary: str, task: dict[str, str], recipient_name: str) -> tuple[str, str]:
        """Build plain text and HTML email body"""
        deadline = (task.get("deadline") or "").strip() or "No deadline specified"
        lines = [
            f"Hello {recipient_name or 'there'},",
            "",
            "You have been assigned the following action item:",
            "",
            f"Task: {task.get('task', '').strip()}",
            f"Deadline: {deadline}",
            "",
            f"Meeting ID: {meeting_id}",
            f"Meeting URL: {meeting_url}",
            "",
            "Meeting Summary:",
            summary or "No summary available.",
            "",
            "Sent by Smart Meeting Assistant",
        ]
        text = "\n".join(lines)
        
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
              <h2 style="color: #0f766e;">🎯 Action Item Assignment</h2>
              <p>Hello <strong>{recipient_name or 'there'}</strong>,</p>
              <p>You have been assigned the following action item from a recent meeting:</p>
              
              <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 15px 0;">
                <p><strong>Task:</strong> {task.get('task', '').strip()}</p>
                <p><strong>Deadline:</strong> {deadline}</p>
              </div>
              
              <h3>Meeting Details</h3>
              <ul>
                <li><strong>Meeting ID:</strong> {meeting_id}</li>
                <li><strong>Meeting URL:</strong> <a href="{meeting_url}">{meeting_url}</a></li>
              </ul>
              
              <h3>Meeting Summary</h3>
              <p>{summary or 'No summary available.'}</p>
              
              <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
              <p style="font-size: 12px; color: #666; text-align: center;">
                Sent by Smart Meeting Assistant
              </p>
            </div>
          </body>
        </html>
        """
        
        return text, html

    def _send_via_nodemailer(self, recipient_email: str, subject: str, text: str, html: str) -> None:
        """Send email via Node.js nodemailer service"""
        url = f"{self._email_service_url()}/send"
        payload = {
            "to": recipient_email,
            "subject": subject,
            "text": text,
            "html": html,
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                raise ValueError(result.get("error", "Email service returned error"))
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Email service unreachable ({url}): {str(e)}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Email service returned invalid response: {str(e)}")

    def _send_job_now(self, job: dict[str, Any]) -> None:
        recipient_email = (job.get("recipient_email") or "").strip() or self._resolve_assignee_email(
            job.get("recipient_name", "")
        )
        if not recipient_email:
            raise ValueError(f"No recipient email mapped for {job.get('recipient_name', '')}")

        subject = job["subject"]
        text = job["body"]
        # Build HTML version from plain text (simple text formatting)
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
              <h2 style="color: #0f766e;">📋 Action Item</h2>
              <pre style="font-family: Arial, sans-serif; white-space: pre-wrap; word-wrap: break-word;">{text}</pre>
              <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
              <p style="font-size: 12px; color: #666; text-align: center;">
                Sent by Smart Meeting Assistant
              </p>
            </div>
          </body>
        </html>
        """
        self._send_via_nodemailer(recipient_email, subject, text, html)

    def _process_claimed_jobs(self, claimed: list[dict[str, Any]]) -> dict[str, int]:
        sent = 0
        failed = 0

        for job in claimed:
            try:
                if not job.get("recipient_email") and not self._resolve_assignee_email(job.get("recipient_name", "")):
                    raise ValueError(f"No recipient email mapped for {job.get('recipient_name', '')}")
                self._send_job_now(job)
                db.mark_email_job_sent(job["id"])
                sent += 1
            except Exception as exc:
                failed += 1
                db.mark_email_job_retry(job["id"], str(exc), int(job.get("attempts", 0)) + 1)

        return {"claimed": len(claimed), "sent": sent, "failed": failed}

    def process_pending_email_jobs_for_meeting(self, meeting_id: str, limit: int = 20) -> dict[str, int]:
        if not self._dispatch_ready():
            return {"claimed": 0, "sent": 0, "failed": 0}

        claimed = db.claim_due_email_jobs_for_meeting(meeting_id=meeting_id, limit=limit)
        return self._process_claimed_jobs(claimed)

    def send_task_assignments(
        self,
        meeting_id: str,
        meeting_url: str,
        summary: str,
        action_items: list[dict[str, str]],
        assignee_email_map: dict[str, str] | None = None,
    ) -> dict[str, object]:
        if not action_items:
            return {"sent": 0, "failed": 0, "errors": [], "skipped": True, "queued": 0}

        queued = 0
        for item in action_items:
            assignee = (item.get("assignee") or "").strip()
            resolved_email = (item.get("recipient_email") or "").strip() or self._resolve_assignee_email(
                assignee,
                assignee_email_map,
            )
            body_lines = [
                f"Hello {assignee or resolved_email or 'there'},",
                "",
                "You have been assigned the following action item:",
                "",
                f"Task: {item.get('task', '').strip()}",
                f"Deadline: {(item.get('deadline') or '').strip() or 'No deadline specified'}",
                "",
                f"Meeting ID: {meeting_id}",
                f"Meeting URL: {meeting_url}",
                "",
                "Meeting Summary:",
                summary or "No summary available.",
                "",
                "Sent by Smart Meeting Assistant",
            ]
            subject = f"{self._settings.email_subject_prefix}: Assigned Meeting Task"
            db.enqueue_email_job(
                meeting_id=meeting_id,
                recipient_email=resolved_email,
                recipient_name=assignee,
                subject=subject,
                body="\n".join(body_lines),
            )
            queued += 1

        if not self._dispatch_ready():
            return {"sent": 0, "failed": 0, "errors": [], "skipped": True, "queued": queued}

        result = self.process_pending_email_jobs_for_meeting(meeting_id=meeting_id, limit=queued)
        return {"sent": result["sent"], "failed": result["failed"], "errors": [], "skipped": False, "queued": queued}

    def process_pending_email_jobs(self, limit: int = 20) -> dict[str, int]:
        if not self._dispatch_ready():
            return {"claimed": 0, "sent": 0, "failed": 0}

        claimed = db.claim_due_email_jobs(limit=limit)
        return self._process_claimed_jobs(claimed)

    def send_summary_digest(
        self,
        meeting_id: str,
        meeting_url: str,
        summary: str,
        participant_email_map: dict[str, str],
    ) -> dict[str, object]:
        recipients = sorted({email.strip() for email in (participant_email_map or {}).values() if email.strip()})
        if not recipients:
            return {"sent": 0, "failed": 0, "errors": [], "skipped": True, "queued": 0}

        queued = 0
        subject = f"{self._settings.email_subject_prefix}: Meeting Summary"
        for recipient_email in recipients:
            body_lines = [
                "Hello,",
                "",
                "Here is the final meeting summary:",
                "",
                summary or "No summary available.",
                "",
                f"Meeting ID: {meeting_id}",
                f"Meeting URL: {meeting_url}",
                "",
                "Sent by Smart Meeting Assistant",
            ]
            db.enqueue_email_job(
                meeting_id=meeting_id,
                recipient_email=recipient_email,
                recipient_name="",
                subject=subject,
                body="\n".join(body_lines),
            )
            queued += 1

        if not self._dispatch_ready():
            return {"sent": 0, "failed": 0, "errors": [], "skipped": True, "queued": queued}

        result = self.process_pending_email_jobs_for_meeting(meeting_id=meeting_id, limit=queued)
        return {"sent": result["sent"], "failed": result["failed"], "errors": [], "skipped": False, "queued": queued}

    def start_retry_worker(self, interval_seconds: int = 30) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()

        def _worker() -> None:
            while not self._stop_event.is_set():
                try:
                    self.process_pending_email_jobs(limit=20)
                except Exception:
                    pass
                self._stop_event.wait(interval_seconds)

        self._worker_thread = threading.Thread(target=_worker, name="email-retry-worker", daemon=True)
        self._worker_thread.start()

    def stop_retry_worker(self) -> None:
        self._stop_event.set()


email_service = EmailService()
