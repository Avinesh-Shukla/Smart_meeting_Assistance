import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.analyze import router as analyze_router
from backend.routes.emails import router as emails_router
from backend.routes.meetings import router as meetings_router
from backend.routes.transcript import router as transcript_router
from backend.services.db import init_db
from backend.services.email_service import email_service


app = FastAPI(title="Smart Meeting Assistant API", version="1.0.0")
logger = logging.getLogger("smart_meeting_assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    app.state.db_ready = True
    try:
        init_db()
        email_service.start_retry_worker(interval_seconds=30)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        app.state.db_ready = False
        logger.warning("Database initialization failed; running in degraded mode: %s", exc)


@app.on_event("shutdown")
def on_shutdown() -> None:
    email_service.stop_retry_worker()


@app.get("/health")
def health() -> dict[str, str | bool]:
    db_ready = bool(getattr(app.state, "db_ready", False))
    return {"status": "ok", "db_ready": db_ready}


app.include_router(analyze_router)
app.include_router(emails_router)
app.include_router(meetings_router)
app.include_router(transcript_router)