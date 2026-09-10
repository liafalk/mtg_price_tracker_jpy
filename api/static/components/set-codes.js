/*
 * Shared set-code dropdown loader.
 *
 * Usage on any page (include after components/i18n.js):
 *   <script src="/static/components/set-codes.js"></script>
 *
 * Exposes on window:
 *   - loadSetCodes(selectEl) -- fetches /api/sets and fills the given
 *     <select> (or <input>) with set-code options, preserving the
 *     currently selected value.
 */
(async function (global) {
  'use strict';

  async function loadSetCodes(setCodeInput) {
    try {
      const resp = await fetch('/api/sets');
      const body = await resp.json().catch(() => ({ sets: [] }));
      const choices = body.sets || [];
      const selected = setCodeInput.value || '';

      setCodeInput.innerHTML = '<option value="">Select set code</option>' + choices
        .map((code) => `<option value="${code}">${code.toUpperCase()}</option>`)
        .join('');

      if (selected) {
        setCodeInput.value = selected;
      }
    } catch (err) {
      console.error('Failed to load set codes', err);
    }
  }

  global.loadSetCodes = loadSetCodes;
})(window);
