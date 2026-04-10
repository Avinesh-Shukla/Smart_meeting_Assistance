import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from backend.config import get_settings


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)


def init_db() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "database" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for statement in [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]:
            conn.execute(text(statement))


def create_or_get_default_user() -> str:
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")).mappings().first()
        if row:
            return str(row["id"])

        user_id = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, full_name)
                VALUES (:id, :email, :full_name)
                """
            ),
            {"id": user_id, "email": "default@smartmeeting.local", "full_name": "Default User"},
        )
        return user_id


def create_meeting(payload: dict[str, Any]) -> str:
    meeting_id = str(uuid.uuid4())
    user_id = create_or_get_default_user()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO meetings (
                    id,
                    user_id,
                    platform,
                    external_id,
                    meeting_url,
                    participants,
                    started_at,
                    status
                )
                VALUES (
                    :id,
                    :user_id,
                    :platform,
                    :external_id,
                    :meeting_url,
                    CAST(:participants AS JSONB),
                    NOW(),
                    'active'
                )
                """
            ),
            {
                "id": meeting_id,
                "user_id": user_id,
                "platform": payload.get("platform", "unknown"),
                "external_id": payload.get("meeting_external_id", ""),
                "meeting_url": payload.get("meeting_url", ""),
                "participants": json.dumps(payload.get("participants", [])),
            },
        )

    if payload.get("participants"):
        update_meeting_participants(meeting_id, payload.get("participants", []))

    return meeting_id


def update_meeting_participants(meeting_id: str, participants: list[Any]) -> None:
    normalized_records: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in participants or []:
        if isinstance(item, dict):
            display_name = str(item.get("name", item.get("display_name", ""))).strip()
            email_address = str(item.get("email", item.get("email_address", ""))).strip()
            source = str(item.get("source", "extension")).strip() or "extension"
        else:
            display_name = str(item).strip()
            email_address = ""
            source = "extension"

        if not display_name:
            continue

        key = display_name.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized_records.append(
            {
                "display_name": display_name,
                "email_address": email_address,
                "source": source,
            }
        )

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM meeting_participants WHERE meeting_id = :meeting_id"),
            {"meeting_id": meeting_id},
        )

        for record in normalized_records:
            conn.execute(
                text(
                    """
                    INSERT INTO meeting_participants (
                        id,
                        meeting_id,
                        display_name,
                        email_address,
                        source,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :meeting_id,
                        :display_name,
                        :email_address,
                        :source,
                        NOW(),
                        NOW()
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "meeting_id": meeting_id,
                    **record,
                },
            )

        conn.execute(
            text(
                """
                UPDATE meetings
                SET participants = CAST(:participants AS JSONB), updated_at = NOW()
                WHERE id = :meeting_id
                """
            ),
            {
                "meeting_id": meeting_id,
                "participants": json.dumps(normalized_records),
            },
        )


def upsert_meeting_participants(meeting_id: str, participants: list[dict[str, str]]) -> list[dict[str, str]]:
    update_meeting_participants(meeting_id, participants)
    return get_meeting_participants(meeting_id)


def get_meeting_participants(meeting_id: str) -> list[dict[str, str]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT display_name, email_address, source
                FROM meeting_participants
                WHERE meeting_id = :meeting_id
                ORDER BY display_name ASC
                """
            ),
            {"meeting_id": meeting_id},
        ).mappings().all()

    return [
        {
            "name": row["display_name"] or "",
            "email": row["email_address"] or "",
            "source": row["source"] or "extension",
        }
        for row in rows
    ]


def get_meeting_participant_email_map(meeting_id: str) -> dict[str, str]:
    participants = get_meeting_participants(meeting_id)
    return {
        participant["name"].strip().lower(): participant["email"].strip()
        for participant in participants
        if participant["name"].strip() and participant["email"].strip()
    }


def stop_meeting(meeting_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE meetings
                SET ended_at = NOW(), status = 'completed'
                WHERE id = :meeting_id
                """
            ),
            {"meeting_id": meeting_id},
        )


def append_transcript_chunk(meeting_id: str, chunk: str, source: str = "extension") -> None:
    if not chunk.strip():
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO transcripts (id, meeting_id, chunk_text, source, created_at)
                VALUES (:id, :meeting_id, :chunk_text, :source, NOW())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "meeting_id": meeting_id,
                "chunk_text": chunk.strip(),
                "source": source,
            },
        )


def get_transcript_text(meeting_id: str) -> str:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT chunk_text
                FROM transcripts
                WHERE meeting_id = :meeting_id
                ORDER BY created_at ASC
                """
            ),
            {"meeting_id": meeting_id},
        ).mappings().all()

    return "\n".join(row["chunk_text"] for row in rows)


def set_analysis_result(meeting_id: str, summary: str, action_items: list[dict[str, str]]) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE meetings SET summary = :summary, updated_at = NOW() WHERE id = :meeting_id"),
            {"summary": summary, "meeting_id": meeting_id},
        )

        conn.execute(text("DELETE FROM action_items WHERE meeting_id = :meeting_id"), {"meeting_id": meeting_id})

        for item in action_items:
            conn.execute(
                text(
                    """
                    INSERT INTO action_items (id, meeting_id, task, assignee, deadline, status, created_at)
                    VALUES (:id, :meeting_id, :task, :assignee, :deadline, 'open', NOW())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "meeting_id": meeting_id,
                    "task": item.get("task", "").strip(),
                    "assignee": item.get("assignee", "").strip(),
                    "deadline": item.get("deadline", "").strip(),
                },
            )


def get_action_items(meeting_id: str) -> list[dict[str, str]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT task, assignee, deadline
                FROM action_items
                WHERE meeting_id = :meeting_id
                ORDER BY created_at ASC
                """
            ),
            {"meeting_id": meeting_id},
        ).mappings().all()

    return [
        {
            "task": row["task"] or "",
            "assignee": row["assignee"] or "",
            "deadline": row["deadline"] or "",
        }
        for row in rows
    ]


def overwrite_action_items(meeting_id: str, action_items: list[dict[str, str]]) -> list[dict[str, str]]:
    set_analysis_result(meeting_id, get_summary(meeting_id), action_items)
    return get_action_items(meeting_id)


def get_summary(meeting_id: str) -> str:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT summary FROM meetings WHERE id = :meeting_id"),
            {"meeting_id": meeting_id},
        ).mappings().first()

    return (row["summary"] if row else "") or ""


def get_meeting_platform_participants(meeting_id: str) -> tuple[str, list[Any]]:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT platform, participants FROM meetings WHERE id = :meeting_id"),
            {"meeting_id": meeting_id},
        ).mappings().first()

    if not row:
        return "unknown", []

    return row["platform"] or "unknown", (row["participants"] or [])


def get_meeting_url(meeting_id: str) -> str:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT meeting_url FROM meetings WHERE id = :meeting_id"),
            {"meeting_id": meeting_id},
        ).mappings().first()

    return (row["meeting_url"] if row else "") or ""


def get_transcript_preview(meeting_id: str, limit: int = 40) -> list[dict[str, str]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT chunk_text, source, created_at
                FROM transcripts
                WHERE meeting_id = :meeting_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"meeting_id": meeting_id, "limit": limit},
        ).mappings().all()

    rows = list(reversed(rows))
    return [
        {
            "line": row["chunk_text"],
            "source": row["source"],
            "at": row["created_at"].isoformat() if row.get("created_at") else "",
        }
        for row in rows
    ]


def enqueue_email_job(
    meeting_id: str,
    recipient_email: str,
    recipient_name: str,
    subject: str,
    body: str,
) -> str:
    job_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO email_jobs (
                    id,
                    meeting_id,
                    recipient_email,
                    recipient_name,
                    subject,
                    body,
                    status,
                    attempts,
                    last_error,
                    next_retry_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :meeting_id,
                    :recipient_email,
                    :recipient_name,
                    :subject,
                    :body,
                    'pending',
                    0,
                    '',
                    NOW(),
                    NOW(),
                    NOW()
                )
                """
            ),
            {
                "id": job_id,
                "meeting_id": meeting_id,
                "recipient_email": recipient_email,
                "recipient_name": recipient_name,
                "subject": subject,
                "body": body,
            },
        )
    return job_id


def claim_due_email_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                WITH claimed AS (
                    SELECT id
                    FROM email_jobs
                    WHERE status IN ('pending', 'retry')
                      AND next_retry_at <= NOW()
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT :limit
                )
                UPDATE email_jobs ej
                SET status = 'processing', updated_at = NOW()
                FROM claimed
                WHERE ej.id = claimed.id
                RETURNING ej.id, ej.meeting_id, ej.recipient_email, ej.recipient_name,
                          ej.subject, ej.body, ej.status, ej.attempts, ej.last_error
                """
            ),
            {"limit": limit},
        ).mappings().all()

    return [dict(row) for row in rows]


def claim_due_email_jobs_for_meeting(meeting_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                WITH claimed AS (
                    SELECT id
                    FROM email_jobs
                    WHERE meeting_id = :meeting_id
                      AND status IN ('pending', 'retry')
                      AND next_retry_at <= NOW()
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT :limit
                )
                UPDATE email_jobs ej
                SET status = 'processing', updated_at = NOW()
                FROM claimed
                WHERE ej.id = claimed.id
                RETURNING ej.id, ej.meeting_id, ej.recipient_email, ej.recipient_name,
                          ej.subject, ej.body, ej.status, ej.attempts, ej.last_error
                """
            ),
            {"meeting_id": meeting_id, "limit": limit},
        ).mappings().all()

    return [dict(row) for row in rows]


def mark_email_job_sent(job_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE email_jobs
                SET status = 'sent',
                    sent_at = NOW(),
                    updated_at = NOW(),
                    last_error = ''
                WHERE id = :job_id
                """
            ),
            {"job_id": job_id},
        )


def mark_email_job_retry(job_id: str, error_message: str, attempts: int) -> None:
    delay_minutes = min(60, 2 ** min(attempts, 5))
    next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE email_jobs
                SET status = CASE WHEN :attempts >= 5 THEN 'failed' ELSE 'retry' END,
                    attempts = :attempts,
                    last_error = :error_message,
                    next_retry_at = :next_retry_at,
                    updated_at = NOW()
                WHERE id = :job_id
                """
            ),
            {
                "job_id": job_id,
                "attempts": attempts,
                "error_message": error_message[:500],
                "next_retry_at": next_retry_at,
            },
        )


def get_email_job_stats() -> dict[str, int]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT status, COUNT(*) AS count
                FROM email_jobs
                GROUP BY status
                """
            )
        ).mappings().all()

    stats = {"pending": 0, "processing": 0, "retry": 0, "failed": 0, "sent": 0}
    for row in rows:
        stats[row["status"]] = int(row["count"])
    return stats
