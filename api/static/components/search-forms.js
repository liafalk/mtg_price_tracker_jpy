/*
 * Shared search / lookup form wiring.
 *
 * Every page with the standard header forms (a #search-form with a
 * #search-term input and a #lookup-form with #set-code +
 * #collector-number) can wire them up with:
 *
 *   <script src="/static/components/search-forms.js"></script>
 *   ...
 *   initSearchForms();
 *
 * The search form navigates to /search?q=... and the lookup form
 * navigates to /card/<set>/<number> (or /search?set=... when no
 * collector number is given), both preserving the active language.
 */
(function (global) {
  'use strict';

  function initSearchForms() {
    const searchForm = document.getElementById('search-form');
    const searchTermInput = document.getElementById('search-term');
    const lookupForm = document.getElementById('lookup-form');
    const setCodeInput = document.getElementById('set-code');
    const collectorNumberInput = document.getElementById('collector-number');
    const errorEl = document.getElementById('error');

    if (lookupForm && setCodeInput && collectorNumberInput) {
      lookupForm.addEventListener('submit', (e) => {
        e.preventDefault();

        if (errorEl) {
          errorEl.style.display = 'none';
          errorEl.textContent = '';
        }

        const setCode = setCodeInput.value.trim();
        const number = collectorNumberInput.value.trim();
        if (!setCode) return;

        const lang = global.AppLanguage ? AppLanguage.activeLanguage : 'en';

        if (!number) {
          const params = new URLSearchParams({ set: setCode, lang });
          global.location.href = `/search?${params.toString()}`;
          return;
        }

        const params = new URLSearchParams({ lang });
        global.location.href = `/card/${encodeURIComponent(setCode)}/${encodeURIComponent(number)}?${params.toString()}`;
      });
    }

    if (searchForm && searchTermInput) {
      searchForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = searchTermInput.value.trim();
        if (!query) return;
        const lang = global.AppLanguage ? AppLanguage.activeLanguage : 'en';
        const params = new URLSearchParams({ q: query, lang });
        global.location.href = `/search?${params.toString()}`;
      });
    }
  }

  global.initSearchForms = initSearchForms;
})(window);
