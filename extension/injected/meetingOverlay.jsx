import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import TranscriptPanel from "./transcriptPanel";
import TaskPanel from "./taskPanel";

const OVERLAY_ID = "sma-overlay-root";
const STYLE_ID = "sma-overlay-style";

function injectStyles() {
  if (document.getElementById(STYLE_ID)) {
    return;
  }

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    #${OVERLAY_ID} {
      position: fixed;
      right: 12px;
      top: 70px;
      z-index: 2147483647;
      width: 360px;
      max-height: calc(100vh - 90px);
      font-family: "Manrope", "Segoe UI", sans-serif;
      animation: sma-slide-in 260ms ease-out;
    }

    @keyframes sma-slide-in {
      from { transform: translateX(24px); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }

    .sma-shell {
      border-radius: 16px;
      background: linear-gradient(180deg, #fefeff 0%, #f5f8ff 100%);
      border: 1px solid #dce4f3;
      box-shadow: 0 20px 36px rgba(20, 38, 77, 0.2);
      overflow: hidden;
      color: #1d2840;
    }

    .sma-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
      background: linear-gradient(135deg, #0f766e, #0f9f94);
      color: #fff;
    }

    .sma-head h2 {
      margin: 0;
      font-size: 14px;
      font-weight: 800;
    }

    .sma-meta {
      font-size: 11px;
      opacity: 0.9;
      margin-top: 3px;
    }

    .sma-toggle {
      border: none;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.2);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
      padding: 6px 8px;
    }

    .sma-body {
      padding: 10px;
      display: grid;
      gap: 10px;
      max-height: calc(100vh - 160px);
      overflow: auto;
    }

    .sma-card {
      border: 1px solid #dbe5fa;
      background: #fff;
      border-radius: 12px;
      padding: 10px;
    }

    .sma-card h3 {
      margin: 0 0 8px;
      font-size: 13px;
      color: #183250;
    }

    .sma-line {
      margin: 0 0 8px;
      font-size: 12px;
      line-height: 1.4;
      color: #2a3d5d;
    }

    .sma-scroll-area {
      max-height: 180px;
      overflow-y: auto;
      padding-right: 4px;
    }

    .sma-empty {
      margin: 0;
      font-size: 12px;
      color: #68768f;
    }

    .sma-summary {
      margin: 0;
      font-size: 12px;
      line-height: 1.5;
      color: #29344f;
      white-space: pre-wrap;
    }

    .sma-title-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }

    .sma-btn-small,
    .sma-btn-save {
      border: none;
      border-radius: 8px;
      background: #1d4ed8;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
      padding: 6px 10px;
    }

    .sma-btn-save {
      margin-top: 8px;
      width: 100%;
      background: #0f766e;
    }

    .sma-task {
      display: grid;
      gap: 6px;
      margin-bottom: 8px;
      background: #f8fbff;
      border: 1px solid #dbe5f5;
      border-radius: 10px;
      padding: 7px;
    }

    .sma-task input {
      border: 1px solid #c9d7f0;
      border-radius: 8px;
      padding: 7px;
      font-size: 12px;
      width: 100%;
    }

    .sma-footer {
      padding: 8px 12px;
      font-size: 11px;
      color: #51607a;
      border-top: 1px solid #dce4f3;
      background: #f3f6ff;
    }

    .sma-minimized .sma-body,
    .sma-minimized .sma-footer {
      display: none;
    }

    @media (max-width: 980px) {
      #${OVERLAY_ID} {
        width: calc(100vw - 20px);
        left: 10px;
        right: 10px;
        top: auto;
        bottom: 10px;
        max-height: 58vh;
      }

      .sma-body {
        max-height: 44vh;
      }
    }
  `;

  document.head.appendChild(style);
}

function OverlayApp() {
  const [minimized, setMinimized] = useState(false);
  const [platform, setPlatform] = useState("unknown");
  const [participants, setParticipants] = useState([]);
  const [participantEmails, setParticipantEmails] = useState({});
  const [summary, setSummary] = useState("");
  const [transcriptLines, setTranscriptLines] = useState([]);
  const [actionItems, setActionItems] = useState([]);
  const [meetingId, setMeetingId] = useState("");
  const [syncLabel, setSyncLabel] = useState("Idle");
  const [lastError, setLastError] = useState("");

  function mergeLines(incomingLines) {
    const seen = new Set();
    return incomingLines.filter((line) => {
      const normalized = (line || "").trim();
      if (!normalized || seen.has(normalized)) {
        return false;
      }
      seen.add(normalized);
      return true;
    });
  }

  const participantLabel = useMemo(() => {
    if (participants.length === 0) {
      return "No participants detected";
    }
    return participants.slice(0, 3).join(", ") + (participants.length > 3 ? ` +${participants.length - 3}` : "");
  }, [participants]);

  useEffect(() => {
    const onUpdate = (event) => {
      const message = event.detail || {};
      const payload = message.payload || {};

      if (message.type === "MEETING_CONTEXT") {
        setPlatform(payload.platform || "unknown");
        setParticipants(payload.participants || []);
      }

      if (message.type === "LIVE_TRANSCRIPT_APPEND") {
        const line = payload.line || "";
        if (line) {
          setTranscriptLines((prev) => mergeLines([...prev, line]).slice(-120));
        }
      }

      if (message.type === "STATE_UPDATE") {
        setPlatform(payload.platform || "unknown");
        setParticipants(payload.participants || []);
        setParticipantEmails(payload.participant_emails || {});
        setSummary(payload.summary || "");
        setMeetingId(payload.meeting_id || "");
        setLastError(payload.last_error || "");
        const preview = payload.transcript_preview || [];
        if (preview.length) {
          setTranscriptLines(mergeLines(preview.map((row) => row.line).filter(Boolean)).slice(-120));
        }
        setActionItems(payload.action_items || []);
        setSyncLabel(payload.capturing ? "Capturing" : "Idle");
      }

      if (message.type === "LIVE_UPDATE") {
        setSummary(payload.summary || "");
        setActionItems(payload.action_items || []);
        const preview = payload.transcript_preview || [];
        if (preview.length) {
          setTranscriptLines(mergeLines(preview.map((row) => row.line).filter(Boolean)).slice(-120));
        }
      }
    };

    window.addEventListener("sma:update", onUpdate);
    chrome.runtime.sendMessage({ type: "GET_STATE" }, (resp) => {
      if (resp?.state) {
        window.dispatchEvent(new CustomEvent("sma:update", { detail: { type: "STATE_UPDATE", payload: resp.state } }));
      }
    });

    return () => {
      window.removeEventListener("sma:update", onUpdate);
    };
  }, []);

  function saveTasks() {
    setSyncLabel("Saving tasks...");
    chrome.runtime.sendMessage({ type: "UPDATE_ACTION_ITEMS", action_items: actionItems }, (resp) => {
      if (!resp?.ok) {
        setSyncLabel(`Task save failed: ${resp?.error || "unknown"}`);
        return;
      }
      setActionItems(resp.action_items || actionItems);
      setSyncLabel(`Tasks synced at ${new Date().toLocaleTimeString()}`);
    });
  }

  function updateParticipantEmail(name, email) {
    const normalizedName = String(name || "").trim();
    if (!normalizedName) {
      return;
    }

    const key = normalizedName.toLowerCase();
    const nextEmails = { ...participantEmails, [key]: String(email || "").trim() };
    setParticipantEmails(nextEmails);

    chrome.runtime.sendMessage(
      {
        type: "UPDATE_PARTICIPANT_EMAILS",
        participant_emails: {
          [normalizedName]: String(email || "").trim()
        }
      },
      () => {
        void chrome.runtime.lastError;
      }
    );
  }

  function handleStartCapture() {
    setSyncLabel("Starting capture...");
    chrome.runtime.sendMessage({ type: "GET_ACTIVE_MEETING_CONTEXT" }, (resp) => {
      if (!resp?.context) {
        setSyncLabel("Cannot detect meeting context. Open a video call first.");
        setLastError("Meeting not detected");
        return;
      }
      chrome.runtime.sendMessage({ type: "START_CAPTURE", context: resp.context }, (startResp) => {
        if (!startResp?.ok) {
          setSyncLabel(`Start failed: ${startResp?.error || "unknown"}`);
          setLastError(startResp?.error);
          return;
        }
        setSyncLabel("Capturing...");
        setMeetingId(startResp.meeting_id);
      });
    });
  }

  function handleStopCapture() {
    setSyncLabel("Stopping capture...");
    chrome.runtime.sendMessage({ type: "STOP_CAPTURE" }, (resp) => {
      if (!resp?.ok) {
        setSyncLabel(`Stop failed: ${resp?.error || "unknown"}`);
        setLastError(resp?.error);
        return;
      }
      setSyncLabel("Capture stopped.");
      if (resp.state?.summary) setSummary(resp.state.summary);
      if (resp.state?.action_items) setActionItems(resp.state.action_items);

      // Force one final summary fetch so UI always reflects post-meeting analysis.
      chrome.runtime.sendMessage({ type: "VIEW_SUMMARY" }, (summaryResp) => {
        if (!summaryResp?.ok) {
          return;
        }
        setSummary(summaryResp.summary || "");
        setActionItems(summaryResp.action_items || []);
        setSyncLabel(`Summary updated at ${new Date().toLocaleTimeString()}`);
      });
    });
  }

  function handleRefreshSummary() {
    setSyncLabel("Refreshing summary...");
    chrome.runtime.sendMessage({ type: "VIEW_SUMMARY" }, (resp) => {
      if (!resp?.ok) {
        setSyncLabel(`Summary refresh failed: ${resp?.error || "unknown"}`);
        return;
      }
      setSummary(resp.summary || "");
      setActionItems(resp.action_items || []);
      setSyncLabel(`Summary refreshed at ${new Date().toLocaleTimeString()}`);
    });
  }

  return (
    <div className={`sma-shell ${minimized ? "sma-minimized" : ""}`}>
      <header className="sma-head">
        <div>
          <h2>Smart Meeting Assistant</h2>
          <div className="sma-meta">
            {platform} | {participantLabel}
          </div>
        </div>
        <button className="sma-toggle" onClick={() => setMinimized((v) => !v)}>
          {minimized ? "Open" : "Hide"}
        </button>
      </header>

      <main className="sma-body">
        <section className="sma-card">
          <div className="sma-title-row">
            <h3>Controls</h3>
          </div>
          <div style={{ display: "flex", gap: "8px", marginBottom: "8px" }}>
            <button type="button" className="sma-btn-small" onClick={handleStartCapture} style={{ flex: 1, background: "#16a34a" }}>
              ▶ Start
            </button>
            <button type="button" className="sma-btn-small" onClick={handleStopCapture} style={{ flex: 1, background: "#dc2626" }}>
              ⏹ Stop
            </button>
          </div>
        </section>
        <section className="sma-card">
          <h3>Participant Emails</h3>
          <div className="sma-scroll-area">
            {participants.length === 0 && <p className="sma-empty">No participants detected yet.</p>}
            {participants.map((name, index) => {
              const key = String(name || "").trim().toLowerCase();
              return (
                <div className="sma-task" key={`${index}-${name}`}>
                  <input value={name || ""} readOnly placeholder="Participant" />
                  <input
                    value={participantEmails[key] || ""}
                    onChange={(e) => updateParticipantEmail(name, e.target.value)}
                    placeholder="Email (required for task email delivery)"
                    type="email"
                  />
                </div>
              );
            })}
          </div>
        </section>
        <TranscriptPanel lines={transcriptLines} />
        <section className="sma-card">
          <div className="sma-title-row">
            <h3>Meeting Summary</h3>
            <button type="button" className="sma-btn-small" onClick={handleRefreshSummary}>
              Refresh
            </button>
          </div>
          <p className="sma-summary">{summary || "Summary will appear as transcript is analyzed."}</p>
        </section>
        <TaskPanel items={actionItems} onChange={setActionItems} onSave={saveTasks} />
      </main>

      <footer className="sma-footer">
        {lastError ? `Error: ${lastError}` : syncLabel}
        {meetingId ? ` | Meeting ID: ${meetingId}` : ""}
      </footer>
    </div>
  );
}

function mount() {
  injectStyles();

  if (document.getElementById(OVERLAY_ID)) {
    return;
  }

  const container = document.createElement("div");
  container.id = OVERLAY_ID;
  document.body.appendChild(container);

  const root = createRoot(container);
  root.render(<OverlayApp />);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount, { once: true });
} else {
  mount();
}
