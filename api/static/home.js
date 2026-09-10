// Home page script.
//
// All shared behavior (i18n, language toggle, set-code dropdown, recent
// sets sidebar, search/lookup forms, name suggestions) now lives in
// /static/components/. This file only wires up the page-specific bits.

const setCodeInput = document.getElementById("set-code");
const collectorNumberInput = document.getElementById("collector-number");
const submitBtn = document.getElementById("submit-btn");
const searchBtn = document.getElementById("search-btn");
const searchTermInput = document.getElementById("search-term");
const recentSetsList = document.getElementById("recent-sets");

function applyUiTranslations() {
  const lang = AppLanguage.activeLanguage;
  const t = AppLanguage.t;

  document.getElementById("page-title").textContent = t("pageTitle");

  if (setCodeInput.tagName === "SELECT") {
    const blankOption = setCodeInput.querySelector('option[value=""]');
    if (blankOption) {
      blankOption.textContent =
        lang === "ja" ? "セットコードを選択" : "Select set code";
    }
  } else {
    setCodeInput.placeholder = t("setCodePlaceholder");
  }

  collectorNumberInput.placeholder = t("collectorNumberPlaceholder");
  submitBtn.textContent = t("submit");
  searchBtn.textContent = lang === "ja" ? "検索" : "Search";
  searchTermInput.placeholder =
    lang === "ja" ? "カード名を検索" : "Search card name";
  document.getElementById("recent-sets-title").textContent = t("recentSetsTitle");
}

AppLanguage.restore();
applyUiTranslations();
AppLanguage.init(applyUiTranslations);
loadSetCodes(setCodeInput);
loadRecentSets(recentSetsList, AppLanguage.activeLanguage);
initSearchForms();
// Name suggestions auto-initialize via the data-suggestions attribute.
