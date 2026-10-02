/* Crafting queue + shopping list. User layer only (localStorage). Pack is read-only. */
(function () {
  const KEY = "ohg_craft_queue_v1";
  function pack() {
    return window.OHG_DATA || window.OHG || {};
  }
  function recipes() {
    const data = pack();
    return data.recipes || (data.tables && data.tables.recipes) || [];
  }
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; }
  }
  function save(q) { localStorage.setItem(KEY, JSON.stringify(q)); }
  function queueAdd(id, qty) {
    const q = load();
    q[id] = (q[id] || 0) + (qty || 1);
    save(q);
    return q;
  }
  function shoppingList() {
    const q = load();
    const byId = {};
    recipes().forEach(function (r) { if (r && r.id) byId[r.id] = r; });
    const need = {};
    Object.keys(q).forEach(function (id) {
      const rec = byId[id];
      if (!rec) return;
      const ings = Array.isArray(rec.ingredients) ? rec.ingredients : String(rec.ingredients || "").split(",");
      ings.forEach(function (ing) {
        const name = (typeof ing === "string" ? ing : (ing && ing.name) || "").trim();
        if (!name) return;
        need[name] = (need[name] || 0) + q[id];
      });
    });
    return { queue: q, need: need };
  }
  window.OHGCraft = { queueAdd: queueAdd, shoppingList: shoppingList, load: load };
})();
