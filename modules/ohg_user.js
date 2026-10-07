/* Once Human Guide — user layer. Never writes the pack. */
(function () {
  var KEY = "ohg-favorites-v1";
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "[]"); }
    catch (e) { return []; }
  }
  function save(items) {
    localStorage.setItem(KEY, JSON.stringify(items));
  }
  function keyOf(table, id) { return table + ":" + id; }
  async function sync(item) {
    try {
      await fetch("/user/favorites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ table: item.table, id: item.id, note: item.note || "" })
      });
    } catch (e) { /* offline is fine */ }
  }
  window.OHGUser = {
    list: load,
    toggle: function (table, id, note) {
      var items = load();
      var k = keyOf(table, id);
      var idx = items.findIndex(function (x) { return keyOf(x.table, x.id) === k; });
      if (idx >= 0) {
        items.splice(idx, 1);
        save(items);
        fetch("/user/favorites/" + encodeURIComponent(table) + "/" + encodeURIComponent(id), { method: "DELETE" }).catch(function () {});
        return false;
      }
      var item = { table: table, id: id, note: note || "", at: new Date().toISOString() };
      items.unshift(item);
      save(items);
      sync(item);
      return true;
    }
  };
})();
