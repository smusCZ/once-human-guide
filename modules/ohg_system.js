/* System strip: API health, schema, record count. Pack stays read-only. */
(function () {
  const badge = document.getElementById("syncBadge");
  if (!badge || !window.fetch) return;
  async function refresh() {
    try {
      const res = await fetch("/health");
      if (!res.ok) throw new Error("health");
      const data = await res.json();
      const n = data.records == null ? "?" : data.records;
      badge.textContent = data.ok ? ("API " + n) : "DB OFF";
      badge.classList.toggle("on", !!data.ok && n === 372);
      badge.title = (data.schema || "no schema") + " · " + (data.api_version || "");
    } catch (e) {
      badge.textContent = "OFFLINE";
      badge.classList.remove("on");
      badge.title = "pack only, API nedostupné";
    }
  }
  refresh();
  setInterval(refresh, 30000);
})();
