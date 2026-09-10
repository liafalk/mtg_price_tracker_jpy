/*
 * Reusable card-name suggestion dropdown.
 *
 * Usage on any page:
 *   1. Include the script (after components/i18n.js):
 *        <script src="/static/components/suggestions.js"></script>
 *   2. Mark the search input so it auto-initializes:
 *        <input id="search-term" data-suggestions>
 *      OR call it explicitly:
 *        initSuggestions(document.getElementById('search-term'));
 *
 * The dropdown fetches /api/suggestions?q=... and renders up to 5 leading
 * card-name matches as links. It works in English and Japanese.
 */
(function (global) {
  'use strict';

  const LIMIT = 5;
  const EMPTY_LABEL = { en: 'No cards found', ja: 'カードが見つかりません' };

  // One dropdown container per page, keyed by the input element.
  const containers = new WeakMap();

  function getContainer(input) {
    if (containers.has(input)) return containers.get(input);

    const list = document.createElement('ul');
    list.id = 'suggestions-list';
    list.className = 'suggestions-list';
    list.setAttribute('aria-hidden', 'true');
    input.parentNode.insertBefore(list, input.nextSibling);
    containers.set(input, list);
    return list;
  }

  function showSuggestions(list) {
    list.setAttribute('aria-hidden', 'false');
    list.style.display = 'block';
  }

  function hideSuggestions(list) {
    list.innerHTML = '';
    list.setAttribute('aria-hidden', 'true');
    list.style.display = 'none';
  }

  async function renderSuggestions(input, list, results) {
    list.innerHTML = '';

    if (!Array.isArray(results) || results.length === 0) {
      const empty = document.createElement('li');
      empty.className = 'suggestion-item';
      empty.textContent = EMPTY_LABEL[getActiveLanguage()] || EMPTY_LABEL.en;
      list.appendChild(empty);
      showSuggestions(list);
      return;
    }

    for (const result of results) {
      const item = document.createElement('li');
      item.className = 'suggestion-item';

      const link = document.createElement('a');
      link.href = result.detail_url ||
        `/card/${encodeURIComponent(result.set_code)}/${encodeURIComponent(result.collector_number)}`;

      const name = document.createElement('span');
      name.className = 'suggestion-name';
      const name_i18n = (getActiveLanguage() == "en" ? result.name_en : result.name_jp) || result.name_en;
      name.textContent = name_i18n + ' - ' + result.set_code.toUpperCase() + ' ' + result.collector_number;
      link.appendChild(name);

      item.appendChild(link);
      list.appendChild(item);
    }

    showSuggestions(list);
  }

  async function fetchSuggestions(input, list, query) {
    const trimmed = query.trim();
    if (!trimmed) {
      hideSuggestions(list);
      return;
    }
    try {
      const resp = await fetch(
        `/api/suggestions?q=${encodeURIComponent(trimmed)}&limit=${LIMIT}`);
      const body = await resp.json().catch(() => ({ results: [] }));
      await renderSuggestions(input, list, body.results || []);
    } catch (err) {
      console.error('Failed to load suggestions', err);
      hideSuggestions(list);
    }
  }

  function getActiveLanguage() {
    if (global.AppLanguage) return global.AppLanguage.activeLanguage;
    const saved = (global.localStorage && global.localStorage.getItem('activeLanguage'));
    return saved === 'ja' || saved === 'en' ? saved : 'en';
  }

  function initSuggestions(input) {
    if (!input || !input.tagName || input.tagName.toLowerCase() !== 'input') {
      console.warn('initSuggestions: expected an <input> element');
      return;
    }
    if (containers.has(input)) return; // already initialized

    const list = getContainer(input);

    input.addEventListener('input', () => fetchSuggestions(input, list, input.value));
    input.addEventListener('focus', () => {
      if (input.value.trim()) fetchSuggestions(input, list, input.value);
    });
    input.addEventListener('blur', () => setTimeout(() => hideSuggestions(list), 150));
  }

  // Auto-initialize for every marked input on the page.
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('input[data-suggestions]').forEach(initSuggestions);
  });

  global.initSuggestions = initSuggestions;
})(window);
