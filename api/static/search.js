const searchResultsTable = document.getElementById('search-results-table');
const searchResultsBody = searchResultsTable.querySelector('tbody');
const searchForm = document.getElementById('search-form');
const searchTermInput = document.getElementById('search-term');
const searchBtn = document.getElementById('search-btn');
const lookupForm = document.getElementById('lookup-form');
const setCodeInput = document.getElementById('set-code');
const collectorNumberInput = document.getElementById('collector-number');
const submitBtn = document.getElementById('submit-btn');
const errorEl = document.getElementById('error');
const languageButtons = document.querySelectorAll('.lang-btn');
const recentSetsList = document.getElementById('recent-sets');

const I18N = window.I18N || {};
let activeLanguage = 'en';

function t(key) {
  return I18N[activeLanguage][key];
}

function applyUiTranslations() {
  document.getElementById('page-title').textContent = t('pageTitle');

  if (setCodeInput.tagName === 'SELECT') {
    const blankOption = setCodeInput.querySelector('option[value=""]');
    if (blankOption) {
      blankOption.textContent = activeLanguage === 'ja' ? 'セットコードを選択' : 'Select set code';
    }
  } else {
    setCodeInput.placeholder = t('setCodePlaceholder');
  }

  collectorNumberInput.placeholder = t('collectorNumberPlaceholder');
  submitBtn.textContent = t('submit');
  searchBtn.textContent = activeLanguage === 'ja' ? '検索' : 'Search';
  searchTermInput.placeholder = activeLanguage === 'ja' ? 'カード名を検索' : 'Search card name';

  const searchHeaders = searchResultsTable.querySelectorAll('th');
  if (searchHeaders.length) {
    searchHeaders[0].textContent = activeLanguage === 'ja' ? 'タイトル' : 'Title';
    searchHeaders[1].textContent = activeLanguage === 'ja' ? 'サムネイル' : 'Thumbnail';
    searchHeaders[2].textContent = activeLanguage === 'ja' ? 'セット' : 'Set';
    searchHeaders[3].textContent = activeLanguage === 'ja' ? '番号' : 'Number';
    searchHeaders[4].textContent = activeLanguage === 'ja' ? 'レアリティ' : 'Rarity';
    searchHeaders[5].textContent = activeLanguage === 'ja' ? '価格 (EN)' : 'Price (EN)';
    searchHeaders[6].textContent = activeLanguage === 'ja' ? '価格 (JP)' : 'Price (JP)';
  }
}

languageButtons.forEach((button) => {
  button.addEventListener('click', () => {
    activeLanguage = button.dataset.language;
    languageButtons.forEach((btn) => {
      btn.classList.toggle('active', btn === button);
    });
    applyUiTranslations();
    localStorage.setItem('activeLanguage', activeLanguage);
    
    // Refresh the page with new language parameter
    const params = new URLSearchParams(window.location.search);
    params.set('lang', activeLanguage);
    window.location.href = `/search?${params.toString()}`;
  });
});

async function loadSetCodes() {
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

function renderRecentSets(sets) {
  if (!recentSetsList) return;
  recentSetsList.innerHTML = '';

  if (!Array.isArray(sets) || sets.length === 0) {
    const emptyItem = document.createElement('li');
    emptyItem.className = 'recent-set-item';
    emptyItem.textContent = activeLanguage === 'ja' ? 'セットが見つかりませんでした。' : 'No sets available.';
    recentSetsList.appendChild(emptyItem);
    return;
  }

  for (const set of sets) {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.className = 'recent-set-item';
    link.href = `/search?set=${encodeURIComponent(set.code)}&lang=${activeLanguage}`;

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
      date.textContent = activeLanguage === 'ja' ? 'リリース日不明' : 'Date unknown';
    }

    link.appendChild(code);
    link.appendChild(name);
    link.appendChild(date);
    item.appendChild(link);
    recentSetsList.appendChild(item);
  }
}

async function loadRecentSets() {
  try {
    const resp = await fetch('/api/recent_sets?limit=8');
    const body = await resp.json().catch(() => ({ sets: [] }));
    renderRecentSets(body.sets || []);
  } catch (err) {
    console.error('Failed to load recent sets', err);
  }
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.style.display = 'block';
}

function renderSearchResults(results) {
  searchResultsBody.innerHTML = '';

  if (!results || results.length === 0) {
    searchResultsBody.innerHTML = `
      <tr>
        <td colspan="7">${activeLanguage === 'ja' ? '一致するカードが見つかりませんでした。' : 'No matching cards were found.'}</td>
      </tr>
    `;
    return;
  }

  for (const item of results) {
    const row = document.createElement('tr');
    const displayName = activeLanguage === 'ja' ? (item.name_jp || item.name_en) : (item.name_en || item.name_jp);
    const thumb = activeLanguage === 'ja' ? (item.thumb_jp || item.thumb) : item.thumb;
    const rarity = I18N[activeLanguage].rarity[item.rarity] || item.rarity || '—';
    const recent = item.recent_prices || {};
    const jpPrice = recent.jp_nonfoil != null ? `¥${Number(recent.jp_nonfoil).toLocaleString()}` : '—';
    const jpFoilPrice = recent.jp_foil != null ? `¥${Number(recent.jp_foil).toLocaleString()}` : '—';
    const enPrice = recent.en_nonfoil != null ? `¥${Number(recent.en_nonfoil).toLocaleString()}` : '—';
    const enFoilPrice = recent.en_foil != null ? `¥${Number(recent.en_foil).toLocaleString()}` : '—';
    const renderPriceCell = (regular, foil) => `
      <div style="display:grid; gap: 0.2rem; min-width: 120px; font-size: 0.88rem; line-height: 1.4;">
        <div>Normal: ${regular}</div>
        <div>Foil: ${foil}</div>
      </div>
    `;
    row.innerHTML = `
      <td>
        <a href="/card/${encodeURIComponent(item.set_code)}/${encodeURIComponent(item.collector_number)}?lang=${activeLanguage}" style="color:inherit;text-decoration:none;display:inline-block;">
          ${displayName || 'Unknown'}
        </a>
      </td>
      <td>
        <a href="/card/${encodeURIComponent(item.set_code)}/${encodeURIComponent(item.collector_number)}?lang=${activeLanguage}" style="display:inline-block;">
          <img src="${thumb || ''}" alt="${displayName || 'card'}" style="width:120px;height:auto;border-radius:6px;display:${thumb ? 'block' : 'none'};">
        </a>
      </td>
      <td>${(item.set_code || '').toUpperCase()}</td>
      <td>${item.collector_number || ''}</td>
      <td>${rarity}</td>
      <td>${renderPriceCell(enPrice, enFoilPrice)}</td>
      <td>${renderPriceCell(jpPrice, jpFoilPrice)}</td>
    `;
    searchResultsBody.appendChild(row);
  }
}

async function loadSearchResults(query, setCode) {
  errorEl.style.display = 'none';
  try {
    let url;
    if (setCode) {
      url = `/api/set_cards?set=${encodeURIComponent(setCode)}`;
    } else {
      url = `/api/search?q=${encodeURIComponent(query)}`;
    }
    
    const resp = await fetch(url);
    const body = await resp.json().catch(() => ({ results: [] }));
    if (!resp.ok) {
      showError(body.detail || 'Search failed');
      return;
    }
    renderSearchResults(body.results || []);
  } catch (err) {
    showError(t('noCardFound'));
  }
}

function restoreLanguage() {
  const saved = localStorage.getItem('activeLanguage');
  if (saved === 'ja' || saved === 'en') {
    activeLanguage = saved;
  }
  
  const params = new URLSearchParams(window.location.search);
  const lang = params.get('lang');
  if (lang === 'ja' || lang === 'en') {
    activeLanguage = lang;
  }
  
  languageButtons.forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.language === activeLanguage);
  });
}

restoreLanguage();
applyUiTranslations();
loadSetCodes();
loadRecentSets();

lookupForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  errorEl.style.display = 'none';
  errorEl.textContent = '';

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

searchForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const query = searchTermInput.value.trim();
  if (!query) return;
  const params = new URLSearchParams({ q: query, lang: activeLanguage });
  window.location.href = `/search?${params.toString()}`;
});

const params = new URLSearchParams(window.location.search);
const query = params.get('q') || '';
const setCode = params.get('set') || '';

if (setCode) {
  loadSearchResults('', setCode);
} else if (query) {
  loadSearchResults(query, '');
}

// Reusable suggestion dropdown for the search box.
initSuggestions(searchTermInput);
