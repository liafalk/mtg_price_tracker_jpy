const form = document.getElementById('lookup-form');
const searchForm = document.getElementById('search-form');
const searchTermInput = document.getElementById('search-term');
const searchBtn = document.getElementById('search-btn');
const submitBtn = document.getElementById('submit-btn');
const errorEl = document.getElementById('error');
const cardHeader = document.getElementById('card-header');
const cardImage = document.getElementById('card-image');
const titleEl = document.getElementById('card-title');
const priceSummary = document.getElementById('price-summary');
const table = document.getElementById('latest-table');
const searchResultsPage = document.getElementById('search-results-page');
const searchResultsTable = document.getElementById('search-results-table');
const searchResultsBody = searchResultsTable.querySelector('tbody');
const tbody = table.querySelector('tbody');
const chartWrap = document.getElementById('chart-wrap');
const canvas = document.getElementById('price-chart');
const languageButtons = document.querySelectorAll('.lang-btn');
const setCodeInput = document.getElementById('set-code');
const collectorNumberInput = document.getElementById('collector-number');

const I18N = window.I18N || {};
let chart = null;
let activeLanguage = 'en';
let currentCardData = null;

const BUCKET_LABELS = {
  jp_nonfoil: { en: 'JP (non-foil)', ja: 'JP (通常版)' },
  jp_foil: { en: 'JP (foil)', ja: 'JP (foil)' },
  en_nonfoil: { en: 'EN (non-foil)', ja: 'EN (通常版)' },
  en_foil: { en: 'EN (foil)', ja: 'EN (foil)' },
};
const BUCKET_COLORS = {
  jp_nonfoil: '#2563eb',
  jp_foil: '#7c3aed',
  en_nonfoil: '#059669',
  en_foil: '#d97706',
};
const BUCKET_ORDER = ['jp_nonfoil', 'jp_foil', 'en_nonfoil', 'en_foil'];

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
  document.querySelector('.hint').textContent = t('hint');

  const tableHeadings = document.querySelectorAll('#latest-table th');
  tableHeadings[0].textContent = t('tableLanguage');
  tableHeadings[1].textContent = t('tableFoil');
  tableHeadings[2].textContent = t('tablePrice');
  tableHeadings[3].textContent = t('tableStock');
  tableHeadings[4].textContent = t('tableWeeklySales');
  tableHeadings[5].textContent = t('tableLastUpdated');

  const searchHeaders = searchResultsTable.querySelectorAll('th');
  if (searchHeaders.length) {
    searchHeaders[0].textContent = activeLanguage === 'ja' ? 'カード' : 'Card';
    searchHeaders[1].textContent = activeLanguage === 'ja' ? 'セット' : 'Set';
    searchHeaders[2].textContent = activeLanguage === 'ja' ? '番号' : 'Number';
    searchHeaders[3].textContent = activeLanguage === 'ja' ? 'レアリティ' : 'Rarity';
    searchHeaders[4].textContent = activeLanguage === 'ja' ? '価格 (EN)' : 'Price (EN)';
    searchHeaders[5].textContent = activeLanguage === 'ja' ? '価格 (JP)' : 'Price (JP)';
  }

  updateDisplayedCardLanguage();
}

languageButtons.forEach((button) => {
  button.addEventListener('click', () => {
    activeLanguage = button.dataset.language;
    languageButtons.forEach((btn) => {
      btn.classList.toggle('active', btn === button);
    });
    applyUiTranslations();

    if (currentCardData) {
      updateDisplayedCardLanguage();
    }

    const setCode = setCodeInput.value.trim();
    const number = collectorNumberInput.value.trim();
    if (setCode && number) {
      updateResourceUrl(setCode, number);
    }
  });
});

async function doLookup(setCode, number) {
  submitBtn.disabled = true;

  try {
    const resp = await fetch(`/api/prices?set=${encodeURIComponent(setCode)}&number=${encodeURIComponent(number)}`);
    const body = await resp.json().catch(() => ({}));

    if (!resp.ok) {
      showError(body.detail || `Error ${resp.status}`);
      return;
    }

    render(body);
    updateResourceUrl(setCode, number);
  } catch (err) {
    showError(t('noCardFound'));
  } finally {
    submitBtn.disabled = false;
  }
}

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

async function loadSetResults(setCode) {
  errorEl.style.display = 'none';
  try {
    const resp = await fetch(`/api/set_cards?set=${encodeURIComponent(setCode)}`);
    const body = await resp.json().catch(() => ({ results: [] }));
    if (!resp.ok) {
      showError(body.detail || 'Set lookup failed');
      return;
    }
    renderSearchResults(body.results || []);
  } catch (err) {
    showError(t('noCardFound'));
  }
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  errorEl.style.display = 'none';
  errorEl.textContent = '';
  cardHeader.style.display = 'none';
  cardImage.style.display = 'none';
  table.style.display = 'none';
  chartWrap.style.display = 'none';

  const setCode = setCodeInput.value.trim();
  const number = collectorNumberInput.value.trim();
  if (!setCode) return;

  if (!number) {
    await loadSetResults(setCode);
    return;
  }

  await doLookup(setCode, number);
});

searchForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const query = searchTermInput.value.trim();
  if (!query) return;
  const params = new URLSearchParams({ q: query, lang: activeLanguage });
  const target = `/search?${params.toString()}`;
  window.location.assign(target);
});

function showError(message) {
  errorEl.textContent = message;
  errorEl.style.display = 'block';
}

function updateDisplayedCardLanguage() {
  if (!currentCardData) return;

  const card = currentCardData.card;
  const name = activeLanguage === 'ja' ? card.name_jp : card.name_en;
  const rarity = card.rarity ? ` · ${card.rarity}` : '';
  const displayTitle = `${name} — ${card.set_code.toUpperCase()} #${card.collector_number}${rarity}`;
  titleEl.textContent = displayTitle;
  document.title = `${displayTitle} | ${t('pageTitle')}`;

  const imageUrl = activeLanguage === 'ja'
    ? (card.img.grid_jp || card.img.grid)
    : card.img.grid;

  if (card.scryfall_id || imageUrl) {
    cardImage.src = imageUrl || card.img.grid;
    cardImage.alt = name || 'Card image';
    cardImage.style.display = 'block';
    cardImage.onerror = () => { cardImage.style.display = 'none'; };
  }
}

function buildResourceUrl(setCode, number) {
  const cleanSet = String(setCode || '').trim().toLowerCase();
  const cleanNumber = String(number || '').trim();
  const base = `/card/${encodeURIComponent(cleanSet)}/${encodeURIComponent(cleanNumber)}`;
  const params = new URLSearchParams({ lang: activeLanguage });
  return `${base}?${params.toString()}`;
}

function updateResourceUrl(setCode, number) {
  const cleanSet = String(setCode || '').trim().toLowerCase();
  const cleanNumber = String(number || '').trim();
  if (!cleanSet || !cleanNumber) return;
  const nextUrl = buildResourceUrl(cleanSet, cleanNumber);
  window.history.pushState({ setCode: cleanSet, number: cleanNumber }, '', nextUrl);
}

function renderSearchResults(results) {
  searchResultsPage.style.display = 'block';
  cardHeader.style.display = 'none';
  cardImage.style.display = 'none';
  table.style.display = 'none';
  chartWrap.style.display = 'none';
  searchResultsBody.innerHTML = '';

  if (!results || results.length === 0) {
    searchResultsBody.innerHTML = `
      <tr>
        <td colspan="6">${activeLanguage === 'ja' ? '一致するカードが見つかりませんでした。' : 'No matching cards were found.'}</td>
      </tr>
    `;
    return;
  }

  for (const item of results) {
    const row = document.createElement('tr');
    const displayName = activeLanguage === 'ja' ? (item.name_jp || item.name_en) : (item.name_en || item.name_jp);
    const thumb = activeLanguage === 'ja' ? (item.thumb_jp || item.thumb) : item.thumb;
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
        <a href="${item.detail_url}?lang=${activeLanguage}" style="display:flex;align-items:center;gap:0.75rem;color:inherit;text-decoration:none;">
          <img src="${thumb || ''}" alt="${displayName || 'card'}" style="width:120px;height:auto;border-radius:6px;display:${thumb ? 'block' : 'none'};">
          <span>${displayName || 'Unknown'}</span>
        </a>
      </td>
      <td>${(item.set_code || '').toUpperCase()}</td>
      <td>${item.collector_number || ''}</td>
      <td>${item.rarity || '-'}</td>
      <td>${renderPriceCell(enPrice, enFoilPrice)}</td>
      <td>${renderPriceCell(jpPrice, jpFoilPrice)}</td>
    `;
    searchResultsBody.appendChild(row);
  }
}

async function loadSearchResults(query) {
  errorEl.style.display = 'none';
  try {
    const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
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

function render(data) {
  currentCardData = data;
  searchResultsPage.style.display = 'none';
  updateDisplayedCardLanguage();

  priceSummary.innerHTML = '';
  const sorted = [...data.latest].sort((a, b) => {
    const ai = BUCKET_ORDER.indexOf(`${a.language}_${a.foil ? 'foil' : 'nonfoil'}`);
    const bi = BUCKET_ORDER.indexOf(`${b.language}_${b.foil ? 'foil' : 'nonfoil'}`);
    return ai - bi;
  });
  for (const row of sorted) {
    const bucket = `${row.language}_${row.foil ? 'foil' : 'nonfoil'}`;
    const chip = document.createElement('div');
    chip.className = 'price-chip';
    chip.style.borderLeftColor = BUCKET_COLORS[bucket] || '#ccc';
    chip.innerHTML = `
      <div class="chip-label">${BUCKET_LABELS[bucket][activeLanguage] || bucket}</div>
      <div class="chip-value">&yen;${row.price_yen.toLocaleString()}</div>
    `;
    priceSummary.appendChild(chip);
  }

  cardHeader.style.display = 'grid';

  tbody.innerHTML = '';
  if (data.latest.length === 0) {
    showError('Card found, but there is no price data for it yet -- has the crawler run for this set?');
  } else {
    for (const row of sorted) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.language.toUpperCase()}</td>
        <td>${row.foil ? t('yes') : t('no')}</td>
        <td>&yen;${row.price_yen.toLocaleString()}</td>
        <td>${row.stock.toLocaleString()}</td>
        <td>${row.weekly_sales.toLocaleString()}</td>
        <td>${new Date(row.fetched_at).toLocaleString()}</td>
      `;
      tbody.appendChild(tr);
    }
    table.style.display = 'table';
  }

  const datasets = BUCKET_ORDER
    .filter((bucket) => data.history[bucket] && data.history[bucket].length > 0)
    .map((bucket) => ({
      label: BUCKET_LABELS[bucket][activeLanguage],
      data: data.history[bucket].map((p) => ({ x: p.fetched_at, y: p.price_yen })),
      borderColor: BUCKET_COLORS[bucket],
      backgroundColor: 'transparent',
      tension: 0.15,
      pointRadius: data.history[bucket].length > 60 ? 0 : 2,
    }));

  if (datasets.length > 0) {
    if (chart) chart.destroy();
    chart = new Chart(canvas, {
      type: 'line',
      data: { datasets },
      options: {
        scales: {
          x: {
            type: 'time',
            time: { unit: 'day' },
            title: { display: true, text: activeLanguage === 'ja' ? '日時' : 'Date' },
          },
          y: {
            title: { display: true, text: t('tablePrice') },
            beginAtZero: true,
          },
        },
        plugins: { legend: { position: 'bottom' } },
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
      },
    });
    chartWrap.style.display = 'block';
    chartWrap.style.width = '100%';
    chartWrap.style.maxWidth = '100%';
  }
}

function hydrateFromResourceUrl() {
  const params = new URLSearchParams(window.location.search);
  const lang = params.get('lang');
  if (lang === 'ja' || lang === 'en') {
    activeLanguage = lang;
    languageButtons.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.language === lang);
    });
  }

  const cardMatch = window.location.pathname.match(/^\/card\/([^/]+)\/([^/]+)$/);
  if (cardMatch) {
    const [, setCode, number] = cardMatch;
    setCodeInput.value = decodeURIComponent(setCode).toLowerCase();
    collectorNumberInput.value = decodeURIComponent(number);
    applyUiTranslations();
    doLookup(setCodeInput.value, collectorNumberInput.value);
    return;
  }

  const searchMatch = window.location.pathname.match(/^\/search$/);
  if (searchMatch) {
    const q = params.get('q') || '';
    const lang = params.get('lang');
    if (lang === 'ja' || lang === 'en') {
      activeLanguage = lang;
      languageButtons.forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.language === lang);
      });
    }
    searchTermInput.value = q;
    applyUiTranslations();
    if (q) {
      loadSearchResults(q);
    }
    return;
  }

  applyUiTranslations();
  currentCardData = null;
  searchResultsPage.style.display = 'none';
  cardHeader.style.display = 'none';
  cardImage.style.display = 'none';
  table.style.display = 'none';
  chartWrap.style.display = 'none';
}

window.addEventListener('popstate', () => {
  hydrateFromResourceUrl();
});

loadSetCodes();
hydrateFromResourceUrl();
