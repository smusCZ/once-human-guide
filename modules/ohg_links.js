/* Related entities from /links — pack stays read-only. */
(function () {
  var ctx = document.getElementById("ctx");
  if (!ctx || !window.fetch) return;
  var labels = {
    ingredient: "surovina",
    drops: "drop",
    rewards: "odměna",
    located_at: "lokace"
  };
  async function show(table, id) {
    try {
      var res = await fetch("/links/" + encodeURIComponent(table) + "/" + encodeURIComponent(id));
      if (!res.ok) return;
      var data = await res.json();
      var box = document.getElementById("ohg-links");
      var host = box || Object.assign(document.createElement("div"), { id: "ohg-links" });
      var links = data.links || [];
      host.innerHTML = "<h4 style='margin:12px 0 6px'>Vazby (" + links.length + ")</h4>" +
        (links.slice(0, 12).map(function (l) {
          var rel = labels[l.relation] || l.relation;
          var otherTable = l.dst_table && l.dst_id && !(l.dst_table === table && l.dst_id === id) ? l.dst_table : l.src_table;
          var otherId = otherTable === l.dst_table ? l.dst_id : l.src_id;
          return "<div class='chip' data-table='" + otherTable + "' data-id='" + otherId + "'>" + rel + " · " + otherTable + "/" + otherId + "</div>";
        }).join(" ") || "<span class='muted'>\u017e\u00e1dn\u00e9 odvozen\u00e9 vazby</span>");
      var body = ctx.querySelector(".body");
      if (body && !box) body.appendChild(host);
    } catch (e) { /* offline pack */ }
  }
  document.addEventListener("click", function (ev) {
    var item = ev.target.closest("[data-table][data-id]");
    if (item) show(item.dataset.table, item.dataset.id);
  });
})();
