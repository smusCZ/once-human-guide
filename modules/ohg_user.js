/* User layer: favorites live in localStorage and optionally SQLite via API.
   Never writes the pack. */
(function () {
  var KEY = "ohg-favorites-v1";
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; }
  }
  function save(list) { localStorage.setItem(KEY, JSON.stringify(list)); }
  function has(table, id) {
    return load().some(function (x) { return x.table === table && x.id === id; });
  }
  function toggle(table, id, name) {
    var added = !has(table, id);
    var list = load().filter(function (x) { return !(x.table === table && x.id === id); });
    if (added) list.unshift({ table: table, id: id, name: name || id, at: new Date().toISOString() });
    save(list);
    if (window.fetch) {
      fetch("/user/favorites", {
        method: added ? "POST" : "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ table: table, id: id, note: name || "" })
      }).catch(function () {});
    }
    return added;
  }
  function paint() {
    var ctx = document.getElementById("ctx");
    if (!ctx) return;
    var item = document.querySelector(".item.sel[data-table][data-id]");
    if (!item) return;
    var host = document.getElementById("ohg-fav");
    if (!host) {
      host = document.createElement("div");
      host.id = "ohg-fav";
      host.style.marginTop = "10px";
      var body = ctx.querySelector(".body");
      if (body) body.appendChild(host);
    }
    var on = has(item.dataset.table, item.dataset.id);
    host.innerHTML = "<button class='btn' type='button' id='ohg-fav-btn'>" + (on ? "\u2605 Obl\u00edben\u00e9" : "\u2606 Obl\u00edbit") + "</button>";
    var btn = document.getElementById("ohg-fav-btn");
    if (btn) btn.onclick = function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      toggle(item.dataset.table, item.dataset.id, (item.querySelector("b,strong") || item).textContent.trim());
      paint();
    };
  }
  document.addEventListener("click", function () { setTimeout(paint, 40); });
  window.OHGUser = { load: load, toggle: toggle, has: has };
})();
