(() => {
  const utils = window.SmartMeetingUtils;
  if (!utils) {
    return;
  }

  const recentCaptions = new Map();
  const CAPTION_CACHE_LIMIT = 120;
  const DEDUPE_WINDOW_MS = 12000;

  function getMeetingContext() {
    return {
      platform: utils.detectPlatform(window.location.href),
      meeting_url: window.location.href,
      meeting_external_id: utils.getMeetingIdFromUrl(window.location.href),
      participants: utils.extractParticipants(),
      captured_at: new Date().toISOString()
    };
  }

  function emitOverlayUpdate(payload) {
    window.dispatchEvent(new CustomEvent("sma:update", { detail: payload }));
  }

  function publishParticipants() {
    const context = getMeetingContext();
    chrome.runtime.sendMessage({ type: "PARTICIPANTS_UPDATE", context }, () => {
      void chrome.runtime.lastError;
    });
    emitOverlayUpdate({
      type: "MEETING_CONTEXT",
      payload: {
        platform: context.platform,
        participants: context.participants,
        meeting_url: context.meeting_url,
        meeting_external_id: context.meeting_external_id
      }
    });
  }

  function pushCaptionChunk(text) {
    const normalized = (text || "").replace(/\s+/g, " ").trim();
    if (!normalized) {
      return;
    }

    const now = Date.now();
    const lastSeenAt = recentCaptions.get(normalized) || 0;
    if (now - lastSeenAt < DEDUPE_WINDOW_MS) {
      return;
    }

    recentCaptions.set(normalized, now);
    if (recentCaptions.size > CAPTION_CACHE_LIMIT) {
      const first = recentCaptions.values().next().value;
      for (const [line, ts] of recentCaptions.entries()) {
        if (ts === first) {
          recentCaptions.delete(line);
          break;
        }
      }
    }

    chrome.runtime.sendMessage(
      {
        type: "TRANSCRIPT_CHUNK",
        chunk: normalized,
        context: getMeetingContext()
      },
      () => {
        void chrome.runtime.lastError;
      }
    );

    emitOverlayUpdate({
      type: "LIVE_TRANSCRIPT_APPEND",
      payload: {
        line: normalized,
        source: "dom_caption"
      }
    });
  }

  function scanCaptions() {
    const lines = utils.extractCaptionLines();
    lines.forEach((line) => pushCaptionChunk(line));
  }

  const captionObserver = new MutationObserver(() => {
    scanCaptions();
  });

  function startObserver() {
    if (!document.body) {
      return;
    }
    captionObserver.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true
    });
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !message.type) {
      return;
    }

    if (message.type === "GET_ACTIVE_MEETING_CONTEXT") {
      sendResponse({ ok: true, context: getMeetingContext() });
      return;
    }

    if (message.type === "LIVE_UPDATE" || message.type === "STATE_UPDATE") {
      emitOverlayUpdate(message);
      sendResponse({ ok: true });
      return;
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        startObserver();
        publishParticipants();
        scanCaptions();
      },
      { once: true }
    );
  } else {
    startObserver();
    publishParticipants();
    scanCaptions();
  }

  setInterval(publishParticipants, 5000);
  setInterval(scanCaptions, 1500);
})();
