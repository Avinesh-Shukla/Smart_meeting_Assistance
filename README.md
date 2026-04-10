# Smart Meeting Assistant - Conversation to Action

Smart Meeting Assistant is an extension-first product that runs directly inside browser meetings (Google Meet, Zoom Web, and Microsoft Teams Web), captures conversation data, and converts it into live summaries and actionable tasks.

## Architecture

- Phase 1 (Capture): Python + Playwright + Whisper
- Phase 2 (Intelligence): FastAPI + LangGraph + GPT-4o
- Phase 3 (Primary Product): Chrome Extension (Manifest V3) + React
- Phase 4 (Data Layer): PostgreSQL + Pinecone

## Project Structure

```text
smart-meeting-assistant/
├── .env.example
├── NODEMAILER_SETUP.md
├── actions.csv
├── package.json
├── package-lock.json
├── requirements.txt
├── smoke_test.py
├── test_endpoints.sh
├── README.md
├── extension/
│   ├── background.js
│   ├── content.js
│   ├── manifest.json
│   ├── utils/
│   │   └── meeting.js
│   ├── injected/
│   │   ├── meetingOverlay.jsx
│   │   ├── meetingOverlay.js
│   │   ├── taskPanel.jsx
│   │   └── transcriptPanel.jsx
│   ├── popup/
│   │   ├── popup.html
│   │   ├── popup.jsx
│   │   ├── popup.css
│   │   └── popup.js
├── backend/
│   ├── __init__.py
│   ├── config.py
│   ├── langgraph_flow.py
│   ├── main.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── analyze.py
│   │   ├── emails.py
│   │   ├── meetings.py
│   │   └── transcript.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── email_service.py
│   │   ├── meeting_service.py
│   │   └── pinecone_service.py
├── capture/
│   ├── meeting_bot.py
│   └── whisper_transcriber.py
├── database/
│   └── schema.sql
├── scripts/
│   └── build-extension.mjs
└── services/
    └── emailService.js
```

## Prerequisites

- Node.js 18+
- Python 3.10+
- PostgreSQL 14+
- Chrome browser

## 1) Setup Environment

```bash
cd smart-meeting-assistant
cp .env.example .env
```

Update `.env`:

- `OPENAI_API_KEY`
- `DATABASE_URL`
- `PINECONE_API_KEY`

## 2) Install Dependencies

### JavaScript dependencies

```bash
npm install
npm run build:extension
```

### Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 3) Start Backend

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## 4) Load Extension in Chrome

1. Open Chrome and navigate to `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the `smart-meeting-assistant/extension` directory.
5. Pin the extension in the toolbar.

## 5) Test in a Meeting

1. Open a supported meeting URL:
   - `https://meet.google.com/...`
   - `https://zoom.us/...`
   - `https://teams.microsoft.com/...`
2. Confirm the right-side Smart Meeting Assistant overlay appears automatically.
3. Open extension popup and click **Start Capture**.
4. Speak in the meeting (or enable captions); transcript lines begin flowing.
5. Click **View Summary** to pull latest AI summary and action items.
6. Edit tasks directly in overlay and click **Save Tasks**.
7. Click **Sync Data** to upsert transcript embeddings into Pinecone.
8. Click **Stop Capture** when done.

## Capture Bot (Playwright + Whisper)

The extension can ingest transcript from on-page captions. For automated browser capture, run:

```bash
python capture/meeting_bot.py \
  --meeting-url "https://meet.google.com/xxx-yyyy-zzz" \
  --meeting-id "<meeting_id_from_backend>" \
  --api-base "http://localhost:8000"
```

To transcribe local audio with Whisper:

```bash
python capture/whisper_transcriber.py ./sample.wav --model base
```

## API Endpoints

- `POST /analyze`
- `POST /meeting/start`
- `POST /meeting/stop`
- `POST /transcript/chunk`
- `GET /meeting/{meeting_id}/live`
- `GET /meeting/{meeting_id}/summary`
- `POST /meeting/{meeting_id}/sync`
- `PUT /meeting/{meeting_id}/action-items`

## Notes

- The extension is the primary interface and injects a live React sidebar on supported meeting pages.
- Backend auto-runs LangGraph analysis incrementally as transcript chunks arrive.
- PostgreSQL stores meetings, transcript chunks, and action items.
- Pinecone stores transcript embeddings for semantic retrieval workflows.
