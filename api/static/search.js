// Search results page script.
//
// Shared behavior (i18n, language toggle, set-code dropdown, recent sets
// sidebar, search/lookup forms, name suggestions) lives in /static/components/.
// This file keeps the page-specific result-table rendering.

const searchResultsTable = document.getElementById('search-results-table');
const searchResultsBody = searchResultsTable.querySelector('tbody');
const searchTermInput = document.getElementById('search-term');
const searchBtn = document.getElementById('search-btn');
const setCodeInput = document.getElementById('set-code');
const collectorNumberInput = document.getElementById('collector-number');
const submitBtn = document.getElementById('submit-btn');
const errorEl = document.getElementById('error');
const recentSetsList = document.getElementById('recent-sets');

function applyUiTranslations() {
  const lang = AppLanguage.activeLanguage;
  const t = AppLanguage.t;

  document.getElementById('page-title').textContent = t('pageTitle');

  if (setCodeInput.tagName === 'SELECT') {
    const blankOption = setCodeInput.querySelector('option[value=""]');
    if (blankOption) {
      blankOption.textContent = lang === 'ja' ? 'セットコードを選択' : 'Select set code';
    }
  } else {
    setCodeInput.placeholder = t('setCodePlaceholder');
  }

  collectorNumberInput.placeholder = t('collectorNumberPlaceholder');
  submitBtn.textContent = t('submit');
  searchBtn.textContent = lang === 'ja' ? '検索' : 'Search';
  searchTermInput.placeholder = lang === 'ja' ? 'カード名を検索' : 'Search card name';
  document.getElementById('recent-sets-title').textContent = t('recentSetsTitle');
  document.getElementById('search-results-title').textContent = t('searchResultsTitle');

  const searchHeaders = searchResultsTable.querySelectorAll('th');
  if (searchHeaders.length) {
    searchHeaders[0].textContent = lang === 'ja' ? 'タイトル' : 'Title';
    searchHeaders[1].textContent = lang === 'ja' ? 'サムネイル' : 'Thumbnail';
    searchHeaders[2].textContent = lang === 'ja' ? 'セット' : 'Set';
    searchHeaders[3].textContent = lang === 'ja' ? '番号' : 'Number';
    searchHeaders[4].textContent = lang === 'ja' ? 'レアリティ' : 'Rarity';
    searchHeaders[5].textContent = lang === 'ja' ? '価格 (EN)' : 'Price (EN)';
    searchHeaders[6].textContent = lang === 'ja' ? '価格 (JP)' : 'Price (JP)';
  }
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.style.display = 'block';
}

function renderSearchResults(results) {
  const lang = AppLanguage.activeLanguage;
  searchResultsBody.innerHTML = '';

  if (!results || results.length === 0) {
    searchResultsBody.innerHTML = `
      <tr>
        <td colspan="7">${lang === 'ja' ? '一致するカードが見つかりませんでした。' : 'No matching cards were found.'}</td>
      </tr>
    `;
    return;
  }

  for (const item of results) {
    const row = document.createElement('tr');
    const displayName = lang === 'ja' ? (item.name_jp || item.name_en) : (item.name_en || item.name_jp);
    const thumb = lang === 'ja' ? (item.thumb_jp || item.thumb) : item.thumb;
    const rarity = (window.I18N || {})[lang]?.rarity?.[item.rarity] || item.rarity || '—';
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
        <a href="/card/${encodeURIComponent(item.set_code)}/${encodeURIComponent(item.collector_number)}?lang=${lang}" style="color:inherit;text-decoration:none;display:inline-block;">
          ${displayName || 'Unknown'}
        </a>
      </td>
      <td>
        <a href="/card/${encodeURIComponent(item.set_code)}/${encodeURIComponent(item.collector_number)}?lang=${lang}" style="display:inline-block;">
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
    showError(AppLanguage.t('noCardFound'));
  }
}

AppLanguage.restore();
applyUiTranslations();
AppLanguage.init(applyUiTranslations);
loadSetCodes(setCodeInput);
loadRecentSets(recentSetsList, AppLanguage.activeLanguage);
initSearchForms();

const params = new URLSearchParams(window.location.search);
const query = params.get('q') || '';
const setCode = params.get('set') || '';

if (setCode) {
  loadSearchResults('', setCode);
} else if (query) {
  loadSearchResults(query, '');
}

// Name suggestions auto-initialize via the data-suggestions attribute.
