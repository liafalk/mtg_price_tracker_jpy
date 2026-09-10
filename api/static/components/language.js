/*
 * Shared language (EN/JP) state and UI wiring.
 *
 * Usage on any page (include after components/i18n.js):
 *   <script src="/static/components/i18n.js"></script>
 *   <script src="/static/components/language.js"></script>
 *
 * Exposes on window:
 *   - AppLanguage.activeLanguage  -- current language ('en' | 'ja')
 *   - AppLanguage.t(key)          -- translate an i18n key
 *   - AppLanguage.restore()       -- restore from ?lang= / localStorage and
 *                                   sync the .lang-btn buttons
 *   - AppLanguage.init(onChange)  -- wire the .lang-btn buttons; calls
 *                                   onChange() after each switch
 */
(function (global) {
  'use strict';

  const I18N = global.I18N || {};
  let activeLanguage = 'en';

  function t(key) {
    return I18N[activeLanguage][key];
  }

  function restore() {
    const saved = global.localStorage.getItem('activeLanguage');
    if (saved === 'ja' || saved === 'en') {
      activeLanguage = saved;
    }

    const params = new URLSearchParams(global.location.search);
    const lang = params.get('lang');
    if (lang === 'ja' || lang === 'en') {
      activeLanguage = lang;
    }

    document.querySelectorAll('.lang-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.language === activeLanguage);
    });
  }

  function init(onChange) {
    document.querySelectorAll('.lang-btn').forEach((button) => {
      button.addEventListener('click', () => {
        activeLanguage = button.dataset.language;
        document.querySelectorAll('.lang-btn').forEach((btn) => {
          btn.classList.toggle('active', btn === button);
        });
        global.localStorage.setItem('activeLanguage', activeLanguage);
        if (typeof onChange === 'function') onChange();
      });
    });
  }

  global.AppLanguage = {
    get activeLanguage() {
      return activeLanguage;
    },
    t,
    restore,
    init,
  };
})(window);
