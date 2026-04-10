import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

function useActiveTab() {
  const [tab, setTab] = useState(null);

  useEffect(() => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      setTab(tabs[0] || null);
    });
  }, []);

  return tab;
}

function App() {
  const tab = useActiveTab();
  const [context, setContext] = useState(null);
  const [state, setState] = useState({ capturing: false, action_items: [], summary: "" });
  const [status, setStatus] = useState("Ready");
  const [busy, setBusy] = useState(false);
  const [participantEmails, setParticipantEmails] = useState({});

  const isMeetingTab = useMemo(() => {
    const url = tab?.url || "";
    return /meet\.google\.com|zoom\.us|teams\.microsoft\.com/i.test(url);
  }, [tab]);

  function getContext() {
    return new Promise((resolve) => {
      if (!tab?.id) {
        resolve(null);
        return;
      }
      chrome.tabs.sendMessage(tab.id, { type: "GET_ACTIVE_MEETING_CONTEXT" }, (resp) => {
        if (chrome.runtime.lastError) {
          resolve(null);
          return;
        }
        resolve(resp?.context || null);
      });
    });
  }

  function getState() {
    return new Promise((resolve) => {
      if (!tab?.id) {
        resolve(null);
        return;
      }
      chrome.runtime.sendMessage({ type: "GET_STATE", tabId: tab.id }, (resp) => {
        if (chrome.runtime.lastError) {
          resolve(null);
          return;
        }
        resolve(resp?.state || null);
      });
    });
  }

  async function refresh() {
    if (!tab?.id) {
      return;
    }
    const [ctx, currentState] = await Promise.all([getContext(), getState()]);
    if (ctx) {
      setContext(ctx);
    }
    if (currentState) {
      setState(currentState);
      setParticipantEmails(currentState.participant_emails || {});
    }
  }

  useEffect(() => {
    refresh();
  }, [tab?.id]);

  function sendMessage(payload) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(payload, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(response || { ok: false, error: "No response" });
      });
    });
  }

  async function startCapture() {
    if (!tab?.id || !context) {
      setStatus("Open a supported meeting tab first.");
      return;
    }

    setBusy(true);
    const res = await sendMessage({ type: "START_CAPTURE", tabId: tab.id, context });
    setBusy(false);

    if (!res.ok) {
      setStatus(`Start failed: ${res.error}`);
      return;
    }

    setStatus("Capture started.");
    await refresh();
  }

  async function stopCapture() {
    if (!tab?.id) {
      return;
    }
    setBusy(true);
    const res = await sendMessage({ type: "STOP_CAPTURE", tabId: tab.id });
    setBusy(false);

    if (!res.ok) {
      setStatus(`Stop failed: ${res.error}`);
      return;
    }

    setStatus("Capture stopped.");
    await refresh();
  }

  async function viewSummary() {
    if (!tab?.id) {
      return;
    }
    setBusy(true);
    const res = await sendMessage({ type: "VIEW_SUMMARY", tabId: tab.id });
    setBusy(false);

    if (!res.ok) {
      setStatus(`Summary failed: ${res.error}`);
      return;
    }

    setState((prev) => ({ ...prev, summary: res.summary, action_items: res.action_items || [] }));
    setStatus("Summary updated.");
  }

  async function syncData() {
    if (!tab?.id) {
      return;
    }

    setBusy(true);
    const res = await sendMessage({ type: "SYNC_DATA", tabId: tab.id });
    setBusy(false);

    if (!res.ok) {
      setStatus(`Sync failed: ${res.error}`);
      return;
    }

    setStatus(`Synced transcript vectors: ${res.vector_count || 0}`);
  }

  async function updateParticipantEmail(name, email) {
    if (!tab?.id) {
      return;
    }

    const trimmedName = String(name || "").trim();
    if (!trimmedName) {
      return;
    }

    const next = { ...participantEmails, [trimmedName.toLowerCase()]: String(email || "").trim() };
    setParticipantEmails(next);

    const res = await sendMessage({
      type: "UPDATE_PARTICIPANT_EMAILS",
      tabId: tab.id,
      participant_emails: {
        [trimmedName]: String(email || "").trim()
      }
    });

    if (!res.ok) {
      setStatus(`Email map update failed: ${res.error}`);
      return;
    }

    setStatus("Participant email saved.");
  }

  return (
    <div className="popup">
      <div className="card">
        <div className="header">
          <h1 className="title">Smart Meeting Assistant</h1>
          <span className={`badge ${state.capturing ? "badge-live" : "badge-idle"}`}>
            {state.capturing ? "LIVE" : "IDLE"}
          </span>
        </div>

        {!isMeetingTab && <div className="status">This tab is not a supported meeting page.</div>}

        <div className="section">
          <h3>Meeting</h3>
          <div className="value">{context?.meeting_url || tab?.url || "No active tab"}</div>
        </div>

        <div className="section">
          <h3>Participants</h3>
          <div className="value">{(context?.participants || []).join(", ") || "No participants detected yet."}</div>
        </div>

        <div className="section">
          <h3>Participant Emails</h3>
          <div className="value">
            {(context?.participants || []).length ? (
              <ul className="list">
                {(context?.participants || []).map((name, index) => {
                  const key = String(name || "").trim().toLowerCase();
                  return (
                    <li key={`${key}-${index}`} style={{ marginBottom: 6 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>{name}</div>
                      <input
                        type="email"
                        value={participantEmails[key] || ""}
                        placeholder="Enter email"
                        onChange={(e) => updateParticipantEmail(name, e.target.value)}
                        style={{ width: "100%" }}
                      />
                    </li>
                  );
                })}
              </ul>
            ) : (
              "No participants detected yet."
            )}
          </div>
        </div>

        <div className="controls">
          <button className="btn-start" disabled={busy || !isMeetingTab || state.capturing} onClick={startCapture}>
            Start Capture
          </button>
          <button className="btn-stop" disabled={busy || !state.capturing} onClick={stopCapture}>
            Stop Capture
          </button>
          <button className="btn-summary" disabled={busy || !isMeetingTab} onClick={viewSummary}>
            View Summary
          </button>
          <button className="btn-sync" disabled={busy || !isMeetingTab} onClick={syncData}>
            Sync Data
          </button>
        </div>

        <div className="section">
          <h3>Summary</h3>
          <div className="value">{state.summary || "No summary available yet."}</div>
        </div>

        <div className="section">
          <h3>Action Items</h3>
          <div className="value">
            {state.action_items?.length ? (
              <ul className="list">
                {state.action_items.map((item, index) => (
                  <li key={`${item.task}-${index}`}>
                    <strong>{item.task}</strong>
                    {" - "}
                    {item.assignee || "Unassigned"}
                    {item.deadline ? ` (${item.deadline})` : ""}
                  </li>
                ))}
              </ul>
            ) : (
              "No action items extracted yet."
            )}
          </div>
        </div>

        <div className="status">{status}</div>
      </div>
    </div>
  );
}

const root = createRoot(document.getElementById("app"));
root.render(<App />);
