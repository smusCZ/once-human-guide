/* User layer against /user — never writes the pack. Falls back to localStorage. */
(function () {
  const KEY = "ohg-user-v1";
  function localGet(kind) {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}")[kind] || []; }
    catch (e) { return []; }
  }
  function localPut(kind, items) {
    const all = JSON.parse(localStorage.getItem(KEY) || "{}");
    all[kind] = items;
    localStorage.setItem(KEY, JSON.stringify(all));
  }
  async function toggleFavorite(table, id, name) {
    const items = localGet("favorite");
    const idx = items.findIndex(function (x) { return x.table === table && x.id === id; });
    const remove = idx >= 0;
    if (remove) items.splice(idx, 1); else items.push({ table: table, id: id, name: name || id });
    localPut("favorite", items);
    try {
      await fetch("/user/favorite", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ table: table, id: id, remove: remove, payload: { name: name || id } })
      });
    } catch (e) { /* offline */ }
    const toast = document.getElementById("toast");
    if (toast) {
      toast.textContent = remove ? "Odebráno z oblíbených" : "Uloženo do oblíbených";
      toast.style.display = "block";
      setTimeout(function () { toast.style.display = "none"; }, 1400);
    }
  }
  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest("[data-fav]");
    if (!btn) return;
    ev.preventDefault();
    toggleFavorite(btn.dataset.table, btn.dataset.id, btn.dataset.name);
  });
  const ctx = document.getElementById("ctx");
  if (!ctx) return;
  const obs = new MutationObserver(function () {
    const body = ctx.querySelector(".body");
    if (!body || body.querySelector("[data-fav]")) return;
    const item = document.querySelector(".item.sel,[data-table][data-id].sel");
    const table = item && item.dataset.table;
    const id = item && item.dataset.id;
    if (!table || !id) return;
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.style.marginTop = "10px";
    btn.dataset.fav = "1";
    btn.dataset.table = table;
    btn.dataset.id = id;
    btn.dataset.name = (item.querySelector("strong,b") || item).textContent.trim();
    btn.textContent = "Oblíbené";
    body.appendChild(btn);
  });
  obs.observe(ctx, { childList: true, subtree: true });
})();
