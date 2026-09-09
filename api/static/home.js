const form = document.getElementById("lookup-form");
const searchForm = document.getElementById("search-form");
const searchTermInput = document.getElementById("search-term");
const searchBtn = document.getElementById("search-btn");
const submitBtn = document.getElementById("submit-btn");
const errorEl = document.getElementById("error");
const setCodeInput = document.getElementById("set-code");
const collectorNumberInput = document.getElementById("collector-number");
const languageButtons = document.querySelectorAll(".lang-btn");
const recentSetsList = document.getElementById("recent-sets");

const I18N = window.I18N || {};
let activeLanguage = "en";

function t(key) {
  return I18N[activeLanguage][key];
}

function applyUiTranslations() {
  document.getElementById("page-title").textContent = t("pageTitle");

  if (setCodeInput.tagName === "SELECT") {
    const blankOption = setCodeInput.querySelector('option[value=""]');
    if (blankOption) {
      blankOption.textContent =
        activeLanguage === "ja" ? "セットコードを選択" : "Select set code";
    }
  } else {
    setCodeInput.placeholder = t("setCodePlaceholder");
  }

  collectorNumberInput.placeholder = t("collectorNumberPlaceholder");
  submitBtn.textContent = t("submit");
  searchBtn.textContent = activeLanguage === "ja" ? "検索" : "Search";
  searchTermInput.placeholder =
    activeLanguage === "ja" ? "カード名を検索" : "Search card name";
}

languageButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeLanguage = button.dataset.language;
    languageButtons.forEach((btn) => {
      btn.classList.toggle("active", btn === button);
    });
    applyUiTranslations();
    localStorage.setItem("activeLanguage", activeLanguage);
  });
});

async function loadSetCodes() {
  try {
    const resp = await fetch("/api/sets");
    const body = await resp.json().catch(() => ({ sets: [] }));
    const choices = body.sets || [];
    const selected = setCodeInput.value || "";

    setCodeInput.innerHTML =
      '<option value="">Select set code</option>' +
      choices
        .map((code) => `<option value="${code}">${code.toUpperCase()}</option>`)
        .join("");

    if (selected) {
      setCodeInput.value = selected;
    }
  } catch (err) {
    console.error("Failed to load set codes", err);
  }
}

function renderRecentSets(sets) {
  if (!recentSetsList) return;
  recentSetsList.innerHTML = "";

  if (!Array.isArray(sets) || sets.length === 0) {
    const emptyItem = document.createElement("li");
    emptyItem.className = "recent-set-item";
    emptyItem.textContent =
      activeLanguage === "ja"
        ? "セットが見つかりませんでした。"
        : "No sets available.";
    recentSetsList.appendChild(emptyItem);
    return;
  }

  for (const set of sets) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.className = "recent-set-item";
    link.href = `/search?set=${encodeURIComponent(set.code)}&lang=${activeLanguage}`;

    const container = document.createElement("div");
    container.className = "recent-set-item-flex";

    const icon = document.createElement('img');
    icon.className = 'recent-set-icon';
    icon.src = 'https://svgs.scryfall.io/sets/' + set.code.toLowerCase() + '.svg';

    const code = document.createElement("span");
    code.className = "recent-set-code";
    code.textContent = set.code.toUpperCase();

    const name = document.createElement("span");
    name.className = "recent-set-name";
    name.textContent = set.name || set.code.toUpperCase();

    const date = document.createElement("span");
    date.className = "recent-set-date";
    if (set.release_date) {
      const formatted = new Date(
        `${set.release_date}T00:00:00`,
      ).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
      date.textContent = formatted;
    } else {
      date.textContent =
        activeLanguage === "ja" ? "リリース日不明" : "Date unknown";
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

async function loadRecentSets() {
  try {
    const resp = await fetch("/api/recent_sets?limit=12");
    const body = await resp.json().catch(() => ({ sets: [] }));
    renderRecentSets(body.sets || []);
  } catch (err) {
    console.error("Failed to load recent sets", err);
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  errorEl.style.display = "none";
  errorEl.textContent = "";

  const setCode = setCodeInput.value.trim();
  const number = collectorNumberInput.value.trim();
  if (!setCode) return;

  if (!number) {
    const params = new URLSearchParams({ set: setCode, lang: activeLanguage });
    window.location.href = `/search?${params.toString()}`;
    return;
  }

  const params = new URLSearchParams({ lang: activeLanguage });
  window.location.href = `/card/${encodeURIComponent(setCode)}/${encodeURIComponent(number)}?${params.toString()}`;
});

searchForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const query = searchTermInput.value.trim();
  if (!query) return;
  const params = new URLSearchParams({ q: query, lang: activeLanguage });
  window.location.href = `/search?${params.toString()}`;
});

// Reusable suggestion dropdown (auto-initialized via suggestions.js).
initSuggestions(searchTermInput);

function restoreLanguage() {
  const saved = localStorage.getItem("activeLanguage");
  if (saved === "ja" || saved === "en") {
    activeLanguage = saved;
    languageButtons.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.language === saved);
    });
  }
}

restoreLanguage();
applyUiTranslations();
loadSetCodes();
loadRecentSets();
