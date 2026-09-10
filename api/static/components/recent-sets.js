/*
 * Shared "Recent sets" sidebar widget.
 *
 * Usage on any page (include after components/i18n.js and
 * components/language.js):
 *   <script src="/static/components/recent-sets.js"></script>
 *
 * Exposes on window:
 *   - renderRecentSets(listEl, sets, lang) -- renders the set list
 *   - loadRecentSets(listEl, lang)         -- fetches /api/recent_sets
 *     and renders it into the given <ul>
 */
(function (global) {
  'use strict';

  function renderRecentSets(recentSetsList, sets, lang) {
    if (!recentSetsList) return;
    recentSetsList.innerHTML = '';

    if (!Array.isArray(sets) || sets.length === 0) {
      const emptyItem = document.createElement('li');
      emptyItem.className = 'recent-set-item';
      emptyItem.textContent = lang === 'ja' ? 'セットが見つかりませんでした。' : 'No sets available.';
      recentSetsList.appendChild(emptyItem);
      return;
    }

    for (const set of sets) {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.className = 'recent-set-item';
      link.href = `/search?set=${encodeURIComponent(set.code)}&lang=${lang}`;

      const container = document.createElement('div');
      container.className = 'recent-set-item-flex';

      const icon = document.createElement('img');
      icon.className = 'recent-set-icon';
      icon.src = 'https://svgs.scryfall.io/sets/' + set.code.toLowerCase() + '.svg';

      const code = document.createElement('span');
      code.className = 'recent-set-code';
      code.textContent = set.code.toUpperCase();

      const name = document.createElement('span');
      name.className = 'recent-set-name';
      name.textContent = set.name || set.code.toUpperCase();

      const date = document.createElement('span');
      date.className = 'recent-set-date';
      if (set.release_date) {
        const formatted = new Date(`${set.release_date}T00:00:00`).toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        });
        date.textContent = formatted;
      } else {
        date.textContent = lang === 'ja' ? 'リリース日不明' : 'Date unknown';
      }

      link.appendChild(container);
      container.appendChild(icon);
      container.appendChild(code);
      container.appendChild(name);
      link.appendChild(date);
      item.appendChild(link);
      recentSetsList.appendChild(item);
    }
  }

  async function loadRecentSets(recentSetsList, lang) {
    try {
      const resp = await fetch('/api/recent_sets?limit=12');
      const body = await resp.json().catch(() => ({ sets: [] }));
      renderRecentSets(recentSetsList, body.sets || [], lang);
    } catch (err) {
      console.error('Failed to load recent sets', err);
    }
  }

  global.renderRecentSets = renderRecentSets;
  global.loadRecentSets = loadRecentSets;
})(window);
