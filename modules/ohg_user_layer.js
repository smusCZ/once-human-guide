/* User layer: favorites and notes stay out of the pack.
   If the local API is up, they are mirrored into once_human_user.db. */
(function () {
  const KEY = "ohg-user-v1";
  const API = location.origin;

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); }
    catch (e) { return {}; }
  }
  function save(state) {
    localStorage.setItem(KEY, JSON.stringify(state));
  }
  function badge(text, on) {
    const el = document.getElementById("syncBadge");
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("on", !!on);
  }
  async function mirror(path, method) {
    try {
      const res = await fetch(API + path, { method });
      if (!res.ok) return false;
      badge("USER DB", true);
      return true;
    } catch (e) {
      badge("LOCAL", false);
      return false;
    }
  }
  window.OHGUser = {
    state: load,
    async favorite(table, id) {
      const state = load();
      state.favorites = state.favorites || [];
      const key = table + ":" + id;
      if (!state.favorites.includes(key)) state.favorites.push(key);
      save(state);
      await mirror("/user/favorites/" + encodeURIComponent(table) + "/" + encodeURIComponent(id), "POST");
      return state.favorites;
    },
    async note(table, id, body) {
      const state = load();
      state.notes = state.notes || {};
      state.notes[table + ":" + id] = body;
      save(state);
      try {
        await fetch(API + "/user/notes/" + encodeURIComponent(table) + "/" + encodeURIComponent(id), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ body })
        });
        badge("USER DB", true);
      } catch (e) {
        badge("LOCAL", false);
      }
    }
  };
  document.addEventListener("DOMContentLoaded", function () {
    fetch(API + "/user").then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
      if (data) badge("USER DB", true);
    }).catch(function () { badge("LOCAL", false); });
  });
})();
