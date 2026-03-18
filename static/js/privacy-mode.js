(function () {
  const STORAGE_KEY = "financeTrackerPrivacyMode";
  const MODES = new Set(["off", "masked", "demo"]);
  const OBSERVER_CONFIG = { childList: true, subtree: true, characterData: true };
  let observer = null;
  let isApplying = false;
  let applyScheduled = false;

  function safeGetMode() {
    try {
      const mode = window.localStorage.getItem(STORAGE_KEY) || "off";
      return MODES.has(mode) ? mode : "off";
    } catch (_error) {
      return "off";
    }
  }

  function safeSetMode(mode) {
    const nextMode = MODES.has(mode) ? mode : "off";
    try {
      window.localStorage.setItem(STORAGE_KEY, nextMode);
    } catch (_error) {
      // Ignore storage failures and still update the live page state.
    }
    applyPrivacyMode(nextMode);
  }

  function hashString(text) {
    let hash = 0;
    for (let i = 0; i < text.length; i += 1) {
      hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
    }
    return Math.abs(hash);
  }

  function maskText(text) {
    return String(text).replace(/[A-Za-z0-9]/g, "*");
  }

  function demoText(text) {
    const original = String(text);
    const base = hashString(original);
    let offset = 0;
    return original.replace(/[A-Za-z0-9]/g, function (character) {
      const step = (base + offset * 7) % (/\d/.test(character) ? 10 : 26);
      offset += 1;
      if (/\d/.test(character)) {
        return String(step);
      }
      const code = character.charCodeAt(0);
      const baseCode = code >= 97 ? 97 : 65;
      return String.fromCharCode(baseCode + ((code - baseCode + step + 1) % 26));
    });
  }

  function transformText(text, mode) {
    if (mode === "masked") {
      return maskText(text);
    }
    if (mode === "demo") {
      return demoText(text);
    }
    return String(text);
  }

  function updateSensitiveText(mode) {
    const elements = document.querySelectorAll("[data-sensitive], .privacy-sensitive-text");
    elements.forEach(function (element) {
      const currentText = element.textContent || "";
      const lastMode = element.dataset.privacyAppliedMode || "off";
      const originalText = element.dataset.privacyOriginalText || "";

      if (!Object.prototype.hasOwnProperty.call(element.dataset, "privacyOriginalText")) {
        element.dataset.privacyOriginalText = currentText;
      } else if (mode === "off" && lastMode === "off") {
        element.dataset.privacyOriginalText = currentText;
      } else if (
        mode !== "off" &&
        (lastMode === "off" || currentText !== transformText(originalText, lastMode))
      ) {
        element.dataset.privacyOriginalText = currentText;
      }

      const original = element.dataset.privacyOriginalText || "";
      const nextText = mode === "off" ? original : transformText(original, mode);
      if (element.textContent !== nextText) {
        element.textContent = nextText;
      }
      element.dataset.privacyAppliedMode = mode;
    });
  }

  function updateSensitiveVisuals(mode) {
    const containers = document.querySelectorAll(".privacy-sensitive-visual");
    containers.forEach(function (container) {
      let overlay = Array.from(container.children).find(function (child) {
        return child.classList && child.classList.contains("privacy-visual-overlay");
      });
      if (!overlay) {
        overlay = document.createElement("div");
        overlay.className = "privacy-visual-overlay";
        overlay.setAttribute("aria-hidden", "true");
        container.appendChild(overlay);
      }

      if (mode === "off") {
        container.classList.remove("privacy-visual-active");
        delete container.dataset.privacyVisualMode;
        overlay.textContent = "";
        return;
      }

      container.classList.add("privacy-visual-active");
      container.dataset.privacyVisualMode = mode;
      overlay.textContent = mode === "masked" ? "Masked for privacy" : "Demo mode";
    });
  }

  function ensureBadge() {
    let badge = document.getElementById("privacyModeBadge");
    if (!badge) {
      badge = document.createElement("div");
      badge.id = "privacyModeBadge";
      badge.className = "privacy-mode-badge";
      badge.innerHTML = "<strong>Privacy mode</strong><span id=\"privacyModeBadgeText\"></span>";
      document.body.appendChild(badge);
    }
    return badge;
  }

  function updateBadge(mode) {
    const badge = ensureBadge();
    const label = badge.querySelector("#privacyModeBadgeText");
    if (mode === "off") {
      badge.classList.remove("is-visible");
      if (label) {
        label.textContent = "";
      }
      return;
    }
    if (label) {
      label.textContent = mode === "masked" ? "Masked" : "Demo";
    }
    badge.classList.add("is-visible");
  }

  function updateControls(mode) {
    const select = document.getElementById("privacyModeSelect");
    if (select && select.value !== mode) {
      select.value = mode;
    }
    const status = document.getElementById("privacyModeStatus");
    if (status) {
      status.textContent =
        mode === "off"
          ? "Real values visible."
          : mode === "masked"
            ? "Sensitive values are shown as masked text and visual overlays."
            : "Sensitive values are randomized, with lighter chart/table obfuscation for demos and screenshots.";
    }
  }

  function applyPrivacyMode(mode) {
    const activeMode = MODES.has(mode) ? mode : safeGetMode();
    if (!document.body) {
      return;
    }
    applyScheduled = false;
    isApplying = true;
    if (observer) {
      observer.disconnect();
    }
    try {
      document.body.dataset.privacyMode = activeMode;
      updateSensitiveText(activeMode);
      updateSensitiveVisuals(activeMode);
      updateControls(activeMode);
      updateBadge(activeMode);
    } finally {
      isApplying = false;
      if (observer && document.body) {
        observer.observe(document.body, OBSERVER_CONFIG);
      }
    }
  }

  function scheduleApply(mode) {
    if (applyScheduled) {
      return;
    }
    applyScheduled = true;
    window.requestAnimationFrame(function () {
      applyPrivacyMode(mode || safeGetMode());
    });
  }

  function observeDom() {
    if (observer || !document.body) {
      return;
    }
    observer = new MutationObserver(function (mutations) {
      if (isApplying) {
        return;
      }
      const hasRelevantMutation = mutations.some(function (mutation) {
        return mutation.type === "characterData" || mutation.addedNodes.length > 0;
      });
      if (hasRelevantMutation) {
        scheduleApply();
      }
    });
    observer.observe(document.body, OBSERVER_CONFIG);
  }

  function initializeControls() {
    const select = document.getElementById("privacyModeSelect");
    if (!select || select.dataset.privacyBound === "true") {
      return;
    }
    select.dataset.privacyBound = "true";
    select.addEventListener("change", function (event) {
      safeSetMode(event.target.value);
    });
  }

  function initializePrivacyMode() {
    initializeControls();
    observeDom();
    scheduleApply(safeGetMode());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializePrivacyMode);
  } else {
    initializePrivacyMode();
  }
  window.addEventListener("storage", function (event) {
    if (event.key === STORAGE_KEY) {
      scheduleApply(safeGetMode());
    }
  });
})();
