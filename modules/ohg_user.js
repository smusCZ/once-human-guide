/* User layer: favorites + inventory. Pack is never written.
   Online: /user/* on the API. Offline: localStorage ohg-user. */
(function () {
  const KEY = "ohg-user-v1";
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); }
    catch (e) { return {}; }
  }
  function save(state) {
    localStorage.setItem(KEY, JSON.stringify(state));
  }
  function state() {
    const s = load();
    s.favorites = s.favorites || [];
    s.inventory = s.inventory || [];
    return s;
  }
  async function pushFav(table, id, note) {
    try {
      await fetch("/user/favorites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ table: table, id: id, note: note || "" })
      });
      const badge = document.getElementById("syncBadge");
      if (badge) { badge.textContent = "SYNC"; badge.classList.add("on"); }
    } catch (e) { /* offline */ }
  }
  function toggle(table, id, name) {
    const s = state();
    const i = s.favorites.findIndex(function (f) { return f.table === table && f.id === id; });
    if (i >= 0) s.favorites.splice(i, 1);
    else s.favorites.push({ table: table, id: id, name: name || id });
    save(s);
    pushFav(table, id, name || "");
    const toast = document.getElementById("toast");
    if (toast) {
      toast.textContent = (i >= 0 ? "Odebrano z oblibenych: " : "Oblibene: ") + (name || id);
      toast.style.display = "block";
      setTimeout(function () { toast.style.display = "none"; }, 1400);
    }
    renderStrip();
  }
  function renderStrip() {
    const ws = document.getElementById("ws");
    if (!ws || location.hash && location.hash !== "#/" && location.hash !== "#/home" && location.hash !== "") return;
    let box = document.getElementById("ohg-user-strip");
    if (!box) {
      box = document.createElement("div");
      box.id = "ohg-user-strip";
      box.className = "card";
      box.style.marginTop = "12px";
      ws.appendChild(box);
    }
    const s = state();
    box.innerHTML = "<div class='kicker'>User layer</div><h3 style='margin:4px 0'>Oblibene a inventar</h3>" +
      "<p class='muted'>Ulozeno mimo pack (" + s.favorites.length + " star / " + s.inventory.length + " inventar). Rebuild databaze to nesmaze.</p>" +
      (s.favorites.slice(0, 6).map(function (f) {
        return "<span class='chip acc'>" + (f.name || f.id) + "</span>";
      }).join(" ") || "<span class='muted'>Zatim prazdne. Alt+klik na entitu.</span>");
  }
  document.addEventListener("click", function (ev) {
    const star = ev.target.closest("[data-star]");
    if (star) {
      toggle(star.dataset.table, star.dataset.id, star.dataset.name);
      return;
    }
    const item = ev.target.closest("[data-table][data-id]");
    if (item && ev.altKey) toggle(item.dataset.table, item.dataset.id, item.dataset.name || item.textContent.trim());
  });
  window.OHGUser = { toggle: toggle, state: state };
  setTimeout(renderStrip, 400);
  window.addEventListener("hashchange", function () { setTimeout(renderStrip, 200); });
})();
