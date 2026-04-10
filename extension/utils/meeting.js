(() => {
  const PLATFORM_MAP = [
    { host: "meet.google.com", platform: "google_meet" },
    { host: "zoom.us", platform: "zoom_web" },
    { host: "teams.microsoft.com", platform: "microsoft_teams_web" }
  ];

  function detectPlatform(url = window.location.href) {
    try {
      const parsed = new URL(url);
      const match = PLATFORM_MAP.find(({ host }) => parsed.hostname.includes(host));
      return match ? match.platform : "unknown";
    } catch (error) {
      return "unknown";
    }
  }

  function getMeetingIdFromUrl(url = window.location.href) {
    try {
      const parsed = new URL(url);
      const path = parsed.pathname.replace(/^\//, "");
      if (parsed.hostname.includes("meet.google.com")) {
        return path.split("?")[0] || "unknown-meet";
      }
      if (parsed.hostname.includes("zoom.us")) {
        const parts = path.split("/").filter(Boolean);
        return parts[parts.length - 1] || "unknown-zoom";
      }
      if (parsed.hostname.includes("teams.microsoft.com")) {
        const segments = path.split("/").filter(Boolean);
        return segments.slice(-2).join("-") || "unknown-teams";
      }
      return "unknown-meeting";
    } catch (error) {
      return "unknown-meeting";
    }
  }

  function extractParticipants() {
    const selectors = [
      "[data-participant-id] [data-self-name]",
      "[data-participant-id] [data-name]",
      "[data-self-name]",
      "[aria-label*='participant']",
      "[aria-label*='Participants']",
      "[data-tid='roster-list-item'] [data-tid='display-name']",
      "[class*='participants'] [class*='name']",
      "[class*='video-avatar__name']"
    ];

    const names = new Set();

    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => {
        const text = (node.textContent || "").trim();
        if (text && text.length <= 120) {
          names.add(text);
        }
      });
    });

    if (names.size === 0) {
      document.querySelectorAll("button, span, div").forEach((node) => {
        const label = (node.getAttribute("aria-label") || "").trim();
        if (label.toLowerCase().includes("participant") && label.length < 80) {
          names.add(label.replace(/participants?/i, "").trim());
        }
      });
    }

    return Array.from(names).filter(Boolean).slice(0, 50);
  }

  function extractCaptionLines() {
    const blockedPatterns = [
      /^close$/i,
      /^add others$/i,
      /^copy link$/i,
      /^content_copy$/i,
      /^person_add$/i,
      /^your meeting'?s ready$/i,
      /^or share this meeting link/i,
      /^people who use this meeting link/i,
      /^joined as\s+/i,
      /^meet\.google\.com\//i
    ];

    const blockedTokens = [
      "microphone",
      "camera",
      "present now",
      "meeting details",
      "join now",
      "raise hand",
      "chat with everyone",
      "turn on captions"
    ];

    function isLikelyCaptionLine(text) {
      const normalized = (text || "").replace(/\s+/g, " ").trim();
      if (!normalized || normalized.length < 6 || normalized.length > 260) {
        return false;
      }
      if (/https?:\/\//i.test(normalized) || /meet\.google\.com\//i.test(normalized)) {
        return false;
      }
      if (/^[a-z_]+$/i.test(normalized) && normalized.includes("_")) {
        return false;
      }
      if (!/[a-zA-Z]/.test(normalized)) {
        return false;
      }

      const lowered = normalized.toLowerCase();
      if (blockedPatterns.some((pattern) => pattern.test(normalized))) {
        return false;
      }
      if (blockedTokens.some((token) => lowered.includes(token))) {
        return false;
      }
      return true;
    }

    const selectors = [
      "[data-is-caption='true']",
      "[data-caption-text]",
      "[class*='caption']",
      "[class*='transcript']",
      "[data-tid='closed-caption-text']",
      "[class*='subtitle']",
      "[jsname='tgaKEf']",
      "[jsname='dsyhDe']",
      "[aria-live='polite']",
      "[aria-live='assertive']"
    ];

    const seen = new Set();
    const lines = [];
    const roots = [document];

    document.querySelectorAll("*").forEach((node) => {
      if (node.shadowRoot) {
        roots.push(node.shadowRoot);
      }
    });

    for (const root of roots) {
      for (const selector of selectors) {
        root.querySelectorAll(selector).forEach((node) => {
          const chunks = (node.innerText || node.textContent || "")
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean);

          for (const text of chunks) {
            const normalized = text
              .replace(/^\d{1,2}:\d{2}(?::\d{2})?\s*/, "")
              .replace(/\s+/g, " ")
              .trim();

            if (!isLikelyCaptionLine(normalized)) {
              continue;
            }
            if (seen.has(normalized)) {
              continue;
            }

            seen.add(normalized);
            lines.push(normalized);
          }
        });
      }
    }

    return lines;
  }

  window.SmartMeetingUtils = {
    detectPlatform,
    getMeetingIdFromUrl,
    extractParticipants,
    extractCaptionLines
  };
})();
