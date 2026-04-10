# Email Service Migration: Python SMTP → Node.js Nodemailer

This guide walks through the new email service architecture and how to set it up.

## Architecture Overview

The Smart Meeting Assistant now uses a **decoupled email service** architecture:

- **Backend (FastAPI)**: Queues email jobs to PostgreSQL database, calls nodemailer service via HTTP
- **Email Service (Node.js)**: Standalone HTTP service using `nodemailer` for SMTP handling
- **Database**: PostgreSQL stores email queue, retry logic, and delivery status

**Benefits:**
- Easier to test and debug email functionality independently
- Can scale email service separately from backend
- Mature `nodemailer` library with better SMTP support than Python's `smtplib`
- Non-blocking HTTP calls instead of synchronous SMTP connections

---

## Quick Start

### 1. Start the Node.js Email Service

```bash
# From the project root
node services/emailService.js
```

You should see:
```
[EmailService] Email service running on http://127.0.0.1:3001
[EmailService] Health check: OK
```

### 2. Configure SMTP Credentials in `.env`

See **Provider Setup** section below for your specific email provider.

### 3. Start the Backend

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 4. Test End-to-End

Create a meeting with an action item, and emails will be sent automatically.

---

## Provider Setup

### Gmail

1. **Enable 2-Step Verification** in Google Account settings
2. **Generate App Password**:
   - Go to [Google Account Security](https://myaccount.google.com/security)
   - Select "App passwords" (appears only with 2FA enabled)
   - Choose "Mail" and "Windows Computer"
   - Copy the 16-character password
3. **Update `.env`**:
   ```bash
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=xxxx xxxx xxxx xxxx  # (16-char app password, spaces optional)
   SMTP_SENDER=your-email@gmail.com
   ```

### Outlook / Microsoft 365

```bash
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USERNAME=your-email@outlook.com
SMTP_PASSWORD=your-password
SMTP_SENDER=your-email@outlook.com
```

### Custom SMTP Server

```bash
SMTP_HOST=mail.example.com
SMTP_PORT=587          # or 465 for implicit TLS
SMTP_USERNAME=username
SMTP_PASSWORD=password
SMTP_SENDER=noreply@example.com
```

---

## Configuration

### Environment Variables (`.env`)

```bash
# SMTP Configuration
SMTP_HOST=smtp.gmail.com              # SMTP server hostname
SMTP_PORT=587                         # SMTP port (587=TLS, 465=SSL)
SMTP_USERNAME=your-email@gmail.com    # SMTP login username
SMTP_PASSWORD=xxxx xxxx xxxx xxxx    # SMTP login password
SMTP_SENDER=noreply@example.com       # "From:" address in emails
SMTP_USE_TLS=true                     # Use TLS (auto-enabled for port 587)

# Email Service
EMAIL_SERVICE_URL=http://127.0.0.1:3001  # URL of Node.js email service

# Email Options
EMAIL_SUBJECT_PREFIX=Smart Meeting Assistant  # Subject line prefix

# Task Assignee Mapping (JSON)
ASSIGNEE_EMAIL_MAP={
  "alice": "alice@example.com",
  "bob": "bob@example.com",
  "carol": "carol@example.com"
}
```

### Backend Configuration (auto-loaded from `.env`)

The backend's `config.py` now includes:
- `email_service_url`: URL of the Node.js email service (default: `http://127.0.0.1:3001`)
- `smtp_host`, `smtp_port`, `smtp_username`, `smtp_password`: SMTP credentials
- `smtp_sender`: "From" email address

---

## API Reference

### Email Service HTTP Endpoints

#### GET `/health`

Check if the service is ready.

**Response:**
```json
{
  "ok": true,
  "message": "Email service operational"
}
```

#### POST `/send`

Send an email via SMTP.

**Request:**
```json
{
  "to": "recipient@example.com",
  "subject": "Your Meeting Task",
  "text": "Plain text version of the email",
  "html": "<html>HTML version...</html>"
}
```

**Success Response (200):**
```json
{
  "ok": true,
  "message_id": "<message-id@gmail.com>",
  "response": "250 OK"
}
```

**Error Response (400/500):**
```json
{
  "ok": false,
  "error": "SMTP authentication failed: Invalid credentials"
}
```

---

## Testing

### 1. Check Service Health

```bash
curl http://127.0.0.1:3001/health
```

Expected output:
```json
{"ok": true, "message": "Email service operational"}
```

### 2. Send a Test Email

```bash
curl -X POST http://127.0.0.1:3001/send \
  -H "Content-Type: application/json" \
  -d '{
    "to": "your-email@example.com",
    "subject": "Test Email",
    "text": "This is a test email",
    "html": "<p>This is a test email</p>"
  }'
```

Expected output:
```json
{
  "ok": true,
  "message_id": "<message-id@example.com>",
  "response": "250 OK"
}
```

### 3. Backend Email Queue Debugging

```bash
# Connect to PostgreSQL database
psql postgresql://postgres:postgres@localhost:5432/smart_meeting_assistant

# Check queued emails
SELECT id, recipient_email, subject, status, created_at, attempts 
FROM email_jobs 
ORDER BY created_at DESC 
LIMIT 10;

# Check failed emails
SELECT id, recipient_email, error, attempts, next_retry_at 
FROM email_jobs 
WHERE status = 'failed' 
ORDER BY next_retry_at ASC;
```

---

## Troubleshooting

### "Email service unreachable"

**Problem:** Backend can't connect to Node.js service.

**Solution:**
1. Ensure Node.js service is running:
   ```bash
   node services/emailService.js
   ```
2. Check `EMAIL_SERVICE_URL` in `.env` matches the service's actual address
3. Verify no firewall blocks port 3001:
   ```bash
   curl http://127.0.0.1:3001/health
   ```

### "SMTP authentication failed"

**Problem:** Invalid SMTP credentials.

**Solution:**
1. Double-check credentials in `.env`:
   ```bash
   echo $SMTP_USERNAME
   echo $SMTP_PASSWORD
   ```
2. For Gmail: Ensure you're using an **App Password**, not your regular password
3. Test SMTP directly:
   ```bash
   node -e "require('nodemailer').createTransport({
     host: 'smtp.gmail.com', port: 587, secure: false,
     auth: { user: 'your-email@gmail.com', pass: 'xxxx xxxx xxxx xxxx' }
   }).verify((err) => console.log(err || 'OK'))"
   ```

### "Self-signed certificate" warning (Custom SMTP)

**Problem:** Email service warns about certificate when using custom SSL servers.

**Solution:**  
This is a safety feature and typically safe to ignore. The service will still send emails. If you want to suppress the warning, the `emailService.js` already handles this for development.

### Emails not sending

**Problem:** Emails queued but not sent.

**Solution:**
1. Check the retry worker is running in the backend (should start automatically)
2. Verify SMTP is ready:
   ```bash
   # In Python backend
   from backend.services.email_service import email_service
   print(f"SMTP Ready: {email_service._smtp_ready()}")
   ```
3. Check database queue:
   ```sql
   SELECT COUNT(*) as pending FROM email_jobs WHERE status = 'pending';
   ```
4. Manually trigger retry processing:
   ```bash
   curl http://localhost:8000/api/emails/process
   ```

### Port 3001 already in use

**Problem:** Can't start Node.js service because port is in use.

**Solution:**
```bash
# Find process using port 3001
lsof -i :3001

# Kill the process
kill -9 <PID>

# Or use a different port by setting PORT environment variable
PORT=3002 node services/emailService.js
```

Then update `EMAIL_SERVICE_URL` in `.env` to match the new port.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Browser                              │
│            (Meeting Capture & UI)                       │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP
                     ▼
┌─────────────────────────────────────────────────────────┐
│            Backend (FastAPI)                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 1. Analyze meetings (LangGraph)                  │   │
│  │ 2. Extract action items                         │   │
│  │ 3. Queue emails → PostgreSQL                    │   │
│  │ 4. Call email service via HTTP                  │   │
│  └──────────────────────────────────────────────────┘   │
└────────────────┬───────────────────────┬────────────────┘
                 │ HTTP /send            │ SQL
                 ▼                       ▼
    ┌─────────────────────────┐  ┌────────────────┐
    │  Email Service (Node.js)│  │ PostgreSQL DB  │
    │     (nodemailer)        │  │                │
    │ ┌─────────────────────┐ │  │ Tables:        │
    │ │ 1. Validate SMTP    │ │  │ - email_jobs   │
    │ │ 2. Send via SMTP    │ │  │ - retries      │
    │ │ 3. Return status    │ │  │ - deliveries   │
    │ └─────────────────────┘ │  │                │
    └──────────┬──────────────┘  └────────────────┘
               │
               ▼
        ┌──────────────────┐
        │  SMTP Server     │
        │  (Gmail, Outlook,│
        │   Custom)        │
        └──────────────────┘
               │
               ▼
        ┌──────────────────┐
        │ Recipient Inbox  │
        └──────────────────┘
```

---

## Development Notes

### Service Code

The Node.js email service is located at:
- `services/emailService.js` - Main HTTP server and nodemailer integration

Key features:
- Automatic health checks on startup
- CORS headers for development
- Detailed error logging
- Graceful shutdown on SIGTERM

### Backend Code Changes

The backend's email service now:
- Imports `requests` instead of `smtplib`
- Uses `_send_via_nodemailer()` instead of `_send_single_message()`
- Makes HTTP POST calls to `/send` endpoint
- Includes timeout and error handling for network issues

See [backend/services/email_service.py](backend/services/email_service.py) for details.

### Configuration

Backend configuration in `backend/config.py` now includes:
```python
email_service_url: str = "http://127.0.0.1:3001"
```

This can be overridden via `EMAIL_SERVICE_URL` environment variable.

---

## Deployment Recommendations

### Production Setup

1. **Run Both Services as Systemd Services** (Linux):
   ```ini
   # /etc/systemd/system/email-service.service
   [Unit]
   Description=Smart Meeting Assistant Email Service
   After=network.target
   
   [Service]
   Type=simple
   User=app
   WorkingDirectory=/opt/smart-meeting-assistant
   ExecStart=/usr/bin/node services/emailService.js
   Restart=on-failure
   RestartSec=10
   StandardOutput=journal
   StandardError=journal
   
   [Install]
   WantedBy=multi-user.target
   ```

2. **Use Nginx as Reverse Proxy** (optional, for security):
   ```nginx
   upstream email_service {
       server 127.0.0.1:3001;
   }
   
   server {
       listen 8001 ssl;
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
       
       location / {
           proxy_pass http://email_service;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

3. **Use Environment-Specific Configuration**:
   - Development: `EMAIL_SERVICE_URL=http://127.0.0.1:3001`
   - Production: `EMAIL_SERVICE_URL=https://internal.company.com:8001`

4. **Mount Secrets Securely**:
   - Use `.env.production` with restricted permissions (600)
   - Consider Docker secrets or Kubernetes secrets management

---

## FAQ

**Q: Can I use Gmail without an app password?**  
A: No, Gmail requires 2-Step Verification and an App Password for third-party apps.

**Q: What happens if the email service goes down?**  
A: Emails are queued in PostgreSQL with automatic retry (backoff up to 60 minutes, max 5 attempts).

**Q: Can I send emails with attachments?**  
A: The current implementation doesn't support attachments, but the `/send` endpoint can be extended to include them.

**Q: Do I need to run the email service on the same machine as the backend?**  
A: No, you can run it on a different machine. Just update `EMAIL_SERVICE_URL` in `.env` to point to the correct address.

**Q: How do I monitor email delivery?**  
A: Check the PostgreSQL `email_jobs` table for status, or monitor logs from both services:
   ```bash
   # See Node.js service logs
   tail -f /var/log/email-service.log
   ```
