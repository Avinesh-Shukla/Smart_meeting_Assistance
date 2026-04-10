const DEFAULT_API_BASE = "http://localhost:8000";
const pollingByTabId = new Map();
const stateByTabId = new Map();

async function getApiBaseUrl() {
  const result = await chrome.storage.local.get(["backendBaseUrl"]);
  return result.backendBaseUrl || DEFAULT_API_BASE;
}

function stateStorageKey(tabId) {
  return `meetingState:${tabId}`;
}

async function loadState(tabId) {
  if (stateByTabId.has(tabId)) {
    return stateByTabId.get(tabId);
  }

  const stored = await chrome.storage.local.get([stateStorageKey(tabId)]);
  const value = stored[stateStorageKey(tabId)] || {
    tabId,
    capturing: false,
    participants: [],
    participant_records: [],
    participant_emails: {},
    summary: "",
    action_items: [],
    transcript_preview: []
  };

  stateByTabId.set(tabId, value);
  return value;
}

async function updateState(tabId, patch) {
  const prev = await loadState(tabId);
  const next = { ...prev, ...patch, updated_at: new Date().toISOString() };
  stateByTabId.set(tabId, next);
  await chrome.storage.local.set({ [stateStorageKey(tabId)]: next });
  await sendToTab(tabId, { type: "STATE_UPDATE", payload: next });
  return next;
}

async function sendToTab(tabId, message) {
  try {
    await chrome.tabs.sendMessage(tabId, message);
  } catch (error) {
    return;
  }
}

function normalizeParticipantRecords(participants = [], participantEmails = {}) {
  const names = Array.isArray(participants) ? participants : [];
  const seen = new Set();
  const records = [];

  for (const rawName of names) {
    const name = String(rawName || "").trim();
    if (!name) {
      continue;
    }
    const key = name.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    records.push({
      name,
      email: String(participantEmails[key] || "").trim()
    });
  }

  return records;
}

function buildParticipantEmailMap(participantRecords = []) {
  const map = {};
  for (const record of participantRecords) {
    const name = String(record?.name || "").trim();
    const email = String(record?.email || "").trim();
    if (!name || !email) {
      continue;
    }
    map[name.toLowerCase()] = email;
  }
  return map;
}

function withParticipantEmails(state, context = {}) {
  const contextParticipants = context.participants || [];
  const participantEmails = state?.participant_emails || {};
  const participantRecords = normalizeParticipantRecords(contextParticipants, participantEmails);
  return {
    ...context,
    participants: participantRecords
  };
}

async function persistMeetingParticipants(tabId, participantRecords = []) {
  const current = await loadState(tabId);
  if (!current.meeting_id) {
    return null;
  }

  const storedRecords = Array.isArray(participantRecords) ? participantRecords : [];
  const response = await apiFetch(`/meeting/${current.meeting_id}/participants`, {
    method: "POST",
    body: JSON.stringify({ participants: storedRecords })
  });

  return response;
}

async function apiFetch(path, options = {}) {
  const baseUrl = await getApiBaseUrl();
  const response = await fetch(`${baseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  const text = await response.text();
  let body = {};

  if (text) {
    try {
      body = JSON.parse(text);
    } catch (error) {
      body = { raw: text };
    }
  }

  if (!response.ok) {
    const message = body.detail || body.message || `API request failed: ${response.status}`;
    throw new Error(message);
  }

  return body;
}

function stopPolling(tabId) {
  const intervalId = pollingByTabId.get(tabId);
  if (intervalId) {
    clearInterval(intervalId);
    pollingByTabId.delete(tabId);
  }
}

function startPolling(tabId, meetingId) {
  stopPolling(tabId);

  const intervalId = setInterval(async () => {
    try {
      const data = await apiFetch(`/meeting/${meetingId}/live`, { method: "GET" });
      await updateState(tabId, {
        summary: data.summary || "",
        action_items: data.action_items || [],
        transcript_preview: data.transcript_preview || []
      });
      await sendToTab(tabId, {
        type: "LIVE_UPDATE",
        payload: data
      });
    } catch (error) {
      await updateState(tabId, { last_error: error.message });
    }
  }, 5000);

  pollingByTabId.set(tabId, intervalId);
}

chrome.tabs.onRemoved.addListener((tabId) => {
  stopPolling(tabId);
  stateByTabId.delete(tabId);
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ backendBaseUrl: DEFAULT_API_BASE });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (!message || !message.type) {
      sendResponse({ ok: false, error: "Invalid message" });
      return;
    }

    const tabId = message.tabId || sender.tab?.id;

    if (message.type === "GET_STATE") {
      const state = await loadState(tabId);
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === "PARTICIPANTS_UPDATE") {
      if (!tabId) {
        sendResponse({ ok: false, error: "Missing tabId" });
        return;
      }
      const current = await loadState(tabId);
      const participantEmails = current.participant_emails || {};
      const participants = message.context?.participants || [];
      const participantRecords = normalizeParticipantRecords(participants, participantEmails);

      const next = await updateState(tabId, {
        participants,
        participant_records: participantRecords,
        participant_emails: participantEmails,
        platform: message.context?.platform || "unknown",
        meeting_url: message.context?.meeting_url || ""
      });

      await persistMeetingParticipants(tabId, participantRecords);
      sendResponse({ ok: true, state: next });
      return;
    }

    if (message.type === "UPDATE_PARTICIPANT_EMAILS") {
      if (!tabId) {
        sendResponse({ ok: false, error: "Missing tabId" });
        return;
      }

      const current = await loadState(tabId);
      const incoming = message.participant_emails || {};
      const mergedEmails = { ...(current.participant_emails || {}) };

      Object.keys(incoming).forEach((name) => {
        const key = String(name || "").trim().toLowerCase();
        if (!key) {
          return;
        }
        mergedEmails[key] = String(incoming[name] || "").trim();
      });

      const participants = current.participants || [];
      const participantRecords = normalizeParticipantRecords(participants, mergedEmails);
      const next = await updateState(tabId, {
        participant_emails: mergedEmails,
        participant_records: participantRecords
      });

      await persistMeetingParticipants(tabId, participantRecords);

      sendResponse({ ok: true, state: next });
      return;
    }

    if (message.type === "START_CAPTURE") {
      if (!tabId) {
        sendResponse({ ok: false, error: "Missing tabId" });
        return;
      }

      const current = await loadState(tabId);
      const contextWithEmails = withParticipantEmails(current, message.context || {});

      const payload = {
        tab_id: tabId,
        platform: contextWithEmails.platform || "unknown",
        meeting_url: contextWithEmails.meeting_url || "",
        meeting_external_id: contextWithEmails.meeting_external_id || "",
        participants: contextWithEmails.participants || []
      };

      const data = await apiFetch("/meeting/start", {
        method: "POST",
        body: JSON.stringify(payload)
      });

      const next = await updateState(tabId, {
        capturing: true,
        meeting_id: data.meeting_id,
        participants: (message.context?.participants || []).map((name) => String(name || "").trim()).filter(Boolean),
        participant_records: contextWithEmails.participants || [],
        participant_emails: buildParticipantEmailMap(contextWithEmails.participants || []),
        started_at: new Date().toISOString(),
        last_error: ""
      });

      await persistMeetingParticipants(tabId, contextWithEmails.participants || []);

      startPolling(tabId, data.meeting_id);
      sendResponse({ ok: true, meeting_id: data.meeting_id, state: next });
      return;
    }

    if (message.type === "STOP_CAPTURE") {
      if (!tabId) {
        sendResponse({ ok: false, error: "Missing tabId" });
        return;
      }

      const current = await loadState(tabId);
      let finalPayload = {};
      if (current.meeting_id) {
        finalPayload = await apiFetch("/meeting/stop", {
          method: "POST",
          body: JSON.stringify({ meeting_id: current.meeting_id })
        });
      }

      stopPolling(tabId);
      const next = await updateState(tabId, {
        capturing: false,
        summary: finalPayload.summary || current.summary || "",
        action_items: finalPayload.action_items || current.action_items || [],
        last_email_status: finalPayload.email || null
      });
      sendResponse({ ok: true, state: next, email: finalPayload.email || null });
      return;
    }

    if (message.type === "TRANSCRIPT_CHUNK") {
      if (!tabId) {
        sendResponse({ ok: false, error: "Missing tabId" });
        return;
      }

      const current = await loadState(tabId);
      if (!current.meeting_id) {
        sendResponse({ ok: true, dropped: true, reason: "capture_not_started" });
        return;
      }

      const body = {
        meeting_id: current.meeting_id,
        chunk: message.chunk,
        participants: withParticipantEmails(current, message.context || {}).participants || current.participant_records || []
      };

      await apiFetch("/transcript/chunk", {
        method: "POST",
        body: JSON.stringify(body)
      });

      const transcriptPreview = [
        ...(current.transcript_preview || []),
        {
          line: message.chunk,
          source: "dom_caption",
          at: new Date().toISOString()
        }
      ].slice(-40);

      await updateState(tabId, { transcript_preview: transcriptPreview });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "VIEW_SUMMARY") {
      if (!tabId) {
        sendResponse({ ok: false, error: "Missing tabId" });
        return;
      }

      const current = await loadState(tabId);
      if (!current.meeting_id) {
        sendResponse({ ok: false, error: "No active meeting" });
        return;
      }

      const data = await apiFetch(`/meeting/${current.meeting_id}/summary`, {
        method: "GET"
      });

      await updateState(tabId, {
        summary: data.summary || "",
        action_items: data.action_items || []
      });

      sendResponse({ ok: true, summary: data.summary || "", action_items: data.action_items || [] });
      return;
    }

    if (message.type === "SYNC_DATA") {
      if (!tabId) {
        sendResponse({ ok: false, error: "Missing tabId" });
        return;
      }
      const current = await loadState(tabId);
      if (!current.meeting_id) {
        sendResponse({ ok: false, error: "No active meeting" });
        return;
      }

      const data = await apiFetch(`/meeting/${current.meeting_id}/sync`, {
        method: "POST"
      });

      sendResponse({ ok: true, synced: true, vector_count: data.vector_count || 0 });
      return;
    }

    if (message.type === "UPDATE_ACTION_ITEMS") {
      if (!tabId) {
        sendResponse({ ok: false, error: "Missing tabId" });
        return;
      }
      const current = await loadState(tabId);
      if (!current.meeting_id) {
        sendResponse({ ok: false, error: "No active meeting" });
        return;
      }

      const data = await apiFetch(`/meeting/${current.meeting_id}/action-items`, {
        method: "PUT",
        body: JSON.stringify({ action_items: message.action_items || [] })
      });

      await updateState(tabId, { action_items: data.action_items || [] });
      sendResponse({ ok: true, action_items: data.action_items || [] });
      return;
    }

    sendResponse({ ok: false, error: `Unhandled message type: ${message.type}` });
  })().catch((error) => {
    sendResponse({ ok: false, error: error.message || "Unknown error" });
  });

  return true;
});
