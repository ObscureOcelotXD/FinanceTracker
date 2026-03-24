/**
 * Fire-and-forget client error reporting when ENABLE_CLIENT_ERROR_LOG=1 on the server.
 * Does not write to the browser console.
 */
(function () {
  function reportClientError(source, message, detail) {
    try {
      fetch("/api/client_error", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: String(source || "app").slice(0, 120),
          message: String(message || "").slice(0, 2000),
          detail: detail != null ? String(detail).slice(0, 4000) : null,
        }),
        keepalive: true,
      }).catch(function () {});
    } catch (e) {}
  }
  window.reportClientError = reportClientError;
})();
