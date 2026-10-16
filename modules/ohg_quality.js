/* Once Human Guide — quality / status badge (online only)
   Shows DB integrity and issue count from /integrity + /audit.
   Does not modify pack. */
(function () {
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.id = "ohg-quality";
  badge.textContent = "DB…";
  badge.title = "Database quality status";

  function mount() {
    const top = document.querySelector(".topbar") || document.querySelector(".brand")?.parentElement;
    if (top && !document.getElementById("ohg-quality")) {
      top.appendChild(badge);
    }
  }

  async function refresh() {
    try {
      const [integ, audit] = await Promise.all([
        fetch("/integrity").then(r => r.ok ? r.json() : null),
        fetch("/audit").then(r => r.ok ? r.json() : null),
      ]);
      if (!integ) {
        badge.textContent = "offline";
        badge.className = "badge";
        return;
      }
      const issues = (audit && audit.count) || integ.stored_issues || 0;
      const ok = integ.ok && issues === 0;
      badge.textContent = ok ? "DB OK" : `DB ${issues} issue${issues === 1 ? "" : "s"}`;
      badge.className = "badge" + (ok ? " on" : "");
      badge.title = ok
        ? "Database integrity OK · 372 records"
        : `Issues: ${issues} · see /audit`;
    } catch (e) {
      badge.textContent = "DB ?";
      badge.className = "badge";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { mount(); refresh(); });
  } else {
    mount();
    refresh();
  }
  setInterval(refresh, 60000);
})();
