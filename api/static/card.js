// Card detail page script.
//
// Shared behavior (i18n, language toggle, set-code dropdown, recent sets
// sidebar, search/lookup forms, name suggestions) lives in /static/components/.
// This file keeps the page-specific card rendering, price chart, and flip.

const cardImage = document.getElementById('card-image');
const titleEl = document.getElementById('card-title');
const cardMetaEl = document.getElementById('card-meta');
const priceSummary = document.getElementById('price-summary');
const table = document.getElementById('latest-table');
const tbody = table.querySelector('tbody');
const chartWrap = document.getElementById('chart-wrap');
const canvas = document.getElementById('price-chart');
const priceHistoryHeader = document.getElementById('price-history-header');
const cardHeader = document.getElementById('card-header');
const errorEl = document.getElementById('error');
const searchTermInput = document.getElementById('search-term');
const searchBtn = document.getElementById('search-btn');
const setCodeInput = document.getElementById('set-code');
const collectorNumberInput = document.getElementById('collector-number');
const submitBtn = document.getElementById('submit-btn');
const flipCardButton = document.getElementById('flip-card-btn');

let chart = null;
let currentCardData = null;
let isBackFace = false;

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

function applyUiTranslations() {
  const lang = AppLanguage.activeLanguage;
  const t = AppLanguage.t;

  document.getElementById('page-title').textContent = t('pageTitle');

  document.querySelectorAll('[data-i18n-key]').forEach((el) => {
    const key = el.dataset.i18nKey;
    if (key && window.I18N[lang]?.[key]) {
      el.textContent = window.I18N[lang][key];
    }
  });

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

  const tableHeadings = document.querySelectorAll('#latest-table th');
  tableHeadings[0].textContent = t('tableLanguage');
  tableHeadings[1].textContent = t('tableFoil');
  tableHeadings[2].textContent = t('tablePrice');
  tableHeadings[3].textContent = t('tableStock');
  tableHeadings[4].textContent = t('tableWeeklySales');
  tableHeadings[5].textContent = t('tableLastUpdated');
  priceHistoryHeader.textContent = lang === 'ja' ? '価格履歴' : 'Price history';
  document.getElementById('recent-sets-title').textContent = t('recentSetsTitle');

  updateDisplayedCardLanguage();
}

flipCardButton.addEventListener('click', () => {
  if (!currentCardData?.card) return;
  const hasBackFace = Boolean(currentCardData.card.double_faced || currentCardData.card.img?.back_grid || currentCardData.card.img?.back_grid_jp);
  if (!hasBackFace) return;

  isBackFace = !isBackFace;
  updateDisplayedCardLanguage();
});

function updateDisplayedCardLanguage() {
  if (!currentCardData) return;

  const lang = AppLanguage.activeLanguage;
  const card = currentCardData.card;
  const name = lang === 'ja'
    ? (card.name_jp || card.name_en || AppLanguage.t('unknownName'))
    : (card.name_en || card.name_jp || AppLanguage.t('unknownName'));
  const rarityKey = String(card.rarity || '').toLowerCase();
  const rarityText = window.I18N[lang]?.rarity?.[rarityKey] || card.rarity || '—';
  const metaText = `${card.set_code.toUpperCase()} #${card.collector_number} · ${rarityText}`;

  titleEl.textContent = name;
  cardMetaEl.textContent = metaText;
  document.title = `${name} — ${metaText} | ${AppLanguage.t('pageTitle')}`;

  const hasBackFace = Boolean(card.double_faced || card.img?.back_grid || card.img?.back_grid_jp);
  flipCardButton.hidden = !hasBackFace;
  if (hasBackFace) {
    flipCardButton.textContent = isBackFace ? (lang === 'ja' ? '表面を表示' : 'Show front') : (lang === 'ja' ? '裏面を表示' : 'Show back');
  }

  const frontImage = lang === 'ja'
    ? (card.img.grid_jp || card.img.grid)
    : card.img.grid;
  const backImage = lang === 'ja'
    ? (card.img.back_grid_jp || card.img.back_grid || frontImage)
    : (card.img.back_grid || frontImage);
  const imageUrl = isBackFace ? backImage : frontImage;

  if (card.scryfall_id || imageUrl) {
    cardImage.src = imageUrl || frontImage || card.img.grid;
    cardImage.alt = name || 'Card image';
    cardImage.style.display = 'block';
    cardImage.onerror = () => { cardImage.style.display = 'none'; };
  }
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.style.display = 'block';
}

function render(data) {
  currentCardData = data;
  updateDisplayedCardLanguage();

  const lang = AppLanguage.activeLanguage;
  const t = AppLanguage.t;

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
      <div class="chip-label">${BUCKET_LABELS[bucket][lang] || bucket}</div>
      <div class="chip-value">&yen;${row.price_yen.toLocaleString()}</div>
    `;
    priceSummary.appendChild(chip);
  }

  cardHeader.style.display = 'grid';

  tbody.innerHTML = '';
  if (data.latest.length === 0) {
    showError(t('noPriceData'));
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
      label: BUCKET_LABELS[bucket][lang],
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
            title: { display: true, text: lang === 'ja' ? '日時' : 'Date' },
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

async function doLookup(setCode, number) {
  try {
    const resp = await fetch(`/api/prices?set=${encodeURIComponent(setCode)}&number=${encodeURIComponent(number)}`);
    const body = await resp.json().catch(() => ({}));

    console.log('API Response:', { status: resp.status, ok: resp.ok, body });

    if (!resp.ok) {
      showError(body.detail || `Error ${resp.status}`);
      return;
    }

    render(body);
  } catch (err) {
    console.error('Fetch error:', err);
    showError(AppLanguage.t('noCardFound'));
  }
}

function extractCardPath() {
  const pathname = window.location.pathname;
  const match = pathname.match(/^\/card\/([^/]+)\/([^/]+)$/);
  if (match) {
    const [, setCode, number] = match;
    return {
      setCode: decodeURIComponent(setCode),
      number: decodeURIComponent(number),
    };
  }
  return null;
}

AppLanguage.restore();
applyUiTranslations();
loadSetCodes(setCodeInput);
initSearchForms();
AppLanguage.init(() => {
  applyUiTranslations();
  if (currentCardData) {
    const params = new URLSearchParams({ lang: AppLanguage.activeLanguage });
    const pathname = window.location.pathname;
    window.history.replaceState({}, '', `${pathname}?${params.toString()}`);
  }
});

const card = extractCardPath();
if (card) {
  doLookup(card.setCode, card.number);
}

// Reusable suggestion dropdown for the search box.
initSuggestions(searchTermInput);

// Recent sets sidebar (shared component).
const recentSetsList = document.getElementById('recent-sets');
loadRecentSets(recentSetsList, AppLanguage.activeLanguage);