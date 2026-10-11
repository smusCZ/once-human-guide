/* Once Human Guide — quality / audit panel (online only).
   Shows /audit and /integrity when API is available.
*/
(function () {
  const API = location.origin;
  async function loadAudit() {
    try {
      const [audit, integrity] = await Promise.all([
        fetch(API + "/audit").then(r => r.ok ? r.json() : null),
        fetch(API + "/integrity").then(r => r.ok ? r.json() : null)
      ]);
      return { audit, integrity };
    } catch (e) {
      return null;
    }
  }
  window.ohgQuality = { loadAudit };
  // Optional: auto-inject a small badge if Home is rendered by runtime
  document.addEventListener("DOMContentLoaded", () => {
    const badge = document.getElementById("syncBadge");
    if (!badge) return;
    loadAudit().then(data => {
      if (!data) return;
      const total = (data.audit && data.audit.total) || 0;
      const ok = data.integrity && data.integrity.ok;
      badge.textContent = ok && total < 50 ? "DB OK" : ("ISSUES " + total);
      badge.classList.toggle("on", ok && total < 50);
    });
  });
})();
