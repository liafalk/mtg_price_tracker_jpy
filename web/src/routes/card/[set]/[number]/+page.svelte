<script lang="ts">
	import { goto } from '$app/navigation';
	import Chart from 'chart.js/auto';
	import 'chartjs-adapter-date-fns';
	import { language, t, I18N, type RarityLabels } from '$lib/i18n';
	import { fetchPrices, type PricesResponse, type HistoryBucket } from '$lib/api';
	import SearchForms from '$lib/components/SearchForms.svelte';

	const BUCKET_ORDER: HistoryBucket[] = ['jp_nonfoil', 'jp_foil', 'en_nonfoil', 'en_foil'];

	const BUCKET_COLORS: Record<HistoryBucket, string> = {
		jp_nonfoil: '#2563eb',
		jp_foil: '#7c3aed',
		en_nonfoil: '#059669',
		en_foil: '#d97706'
	};

	const BUCKET_LABELS: Record<HistoryBucket, { en: string; ja: string }> = {
		jp_nonfoil: { en: 'JP (non-foil)', ja: 'JP (通常版)' },
		jp_foil: { en: 'JP (foil)', ja: 'JP (foil)' },
		en_nonfoil: { en: 'EN (non-foil)', ja: 'EN (通常版)' },
		en_foil: { en: 'EN (foil)', ja: 'EN (foil)' }
	};

	const CONDITIONS = ['NM', 'EX', 'LP'];
	const LANGUAGES = [
		{ key: 'en', label: 'EN' },
		{ key: 'ja', label: 'JP' }
	];
	const FOILS = [
		{ key: 'nonfoil', labelKey: 'inventoryNonFoil' as const },
		{ key: 'foil', labelKey: 'inventoryFoil' as const }
	];

	let { set, number } = $props();

	let data = $state<PricesResponse | null>(null);
	let error = $state<string | null>(null);
	let isBackFace = $state(false);

	// Chart instance is intentionally not reactive state.
	let chart: Chart<'line', { x: string; y: number }[]> | null = null;
	let chartCanvas = $state<HTMLCanvasElement | null>(null);

	const lang = $derived($language);
	const dict = $derived(I18N[lang]);

	const hasBackFace = $derived(
		!!data &&
			(data.card.double_faced || !!data.card.img.back_grid || !!data.card.img.back_grid_jp)
	);

	const cardName = $derived(
		data
			? lang === 'ja'
				? data.card.name_jp || data.card.name_en || t('unknownName')
				: data.card.name_en || data.card.name_jp || t('unknownName')
			: ''
	);

	const rarityText = $derived(
		data ? I18N[lang].rarity[data.card.rarity as keyof RarityLabels] || data.card.rarity || '—' : '—'
	);

	const metaText = $derived(
		data ? `${data.card.set_code.toUpperCase()} #${data.card.collector_number} · ${rarityText}` : ''
	);

	const frontImage = $derived(
		data ? (lang === 'ja' ? data.card.img.grid_jp || data.card.img.grid : data.card.img.grid) : null
	);

	const backImage = $derived(
		data
			? lang === 'ja'
				? data.card.img.back_grid_jp || data.card.img.back_grid || frontImage
				: data.card.img.back_grid || frontImage
			: null
	);

	const imageUrl = $derived(isBackFace ? backImage : frontImage);

	const showImage = $derived(
		!!data && !!imageUrl && (!!data.card.scryfall_id || !!data.card.scryfall_id_jp)
	);

	const priceChips = $derived.by(() => {
		if (!data) return [];
		const latest = data.latest;
		return BUCKET_ORDER.map((bucket) => {
			const [langCode, foilCode] = bucket.split('_') as [string, string];
			const foil = foilCode === 'foil';
			return {
				bucket,
				label: BUCKET_LABELS[bucket][lang],
				color: BUCKET_COLORS[bucket],
				price: latest.find((p) => p.language === langCode && p.foil === foil)?.price_yen ?? null
			};
		});
	});

	function toggleFace() {
		if (hasBackFace) isBackFace = !isBackFace;
	}

	function yen(value: number | null | undefined): string {
		return value == null ? '—' : `¥${Number(value).toLocaleString()}`;
	}

	async function load() {
		error = null;
		data = null;
		isBackFace = false;
		try {
			data = await fetchPrices(set, number);
		} catch (e) {
			error = e instanceof Error ? e.message : t('noCardFound');
		}
	}

	// Keep the ?lang= query param in sync on the card page (mirrors card.js).
	$effect(() => {
		if (typeof window === 'undefined') return;
		const current = new URLSearchParams(window.location.search).get('lang');
		if (current !== lang) {
			const url = new URL(window.location.href);
			url.searchParams.set('lang', lang);
			history.replaceState({}, '', url.toString());
		}
	});

	$effect(() => {
		if (typeof document === 'undefined') return;
		if (data) {
			document.title = `${cardName} — ${metaText} | ${t('pageTitle')}`;
		}
	});

	$effect(() => {
		load();
	});

	// (Re)build the chart whenever data or language changes.
	$effect(() => {
		if (!data || !chartCanvas) return;
		const history = data.history;
		const datasets = BUCKET_ORDER.filter((b) => history[b].length > 0).map((bucket) => ({
			label: BUCKET_LABELS[bucket][lang],
			data: history[bucket].map((p) => ({ x: p.fetched_at, y: p.price_yen })),
			borderColor: BUCKET_COLORS[bucket],
			backgroundColor: 'transparent',
			tension: 0.15,
			pointRadius: history[bucket].length > 60 ? 0 : 2
		}));

		if (chart) {
			chart.destroy();
			chart = null;
		}

		if (datasets.length > 0) {
			chart = new Chart(chartCanvas, {
				type: 'line',
				data: { datasets },
				options: {
					responsive: true,
					maintainAspectRatio: false,
					scales: {
						x: {
							type: 'time',
							time: { unit: 'day' },
							title: { display: true, text: lang === 'ja' ? '日時' : 'Date' }
						},
						y: {
							title: { display: true, text: t('tablePrice') },
							beginAtZero: true
						}
					},
					plugins: {
						legend: { position: 'bottom' }
					},
					interaction: { mode: 'nearest', axis: 'x', intersect: false }
				}
			});
		}

		return () => {
			if (chart) {
				chart.destroy();
				chart = null;
			}
		};
	});

</script>

<SearchForms onNavigate={goto} />

{#if error}
	<p id="error" style="display: block;">{error}</p>
{/if}

{#if data}
	<section id="card-header" style="display: grid;">
		<div class="card-visual">
			{#if showImage}
				<img
					id="card-image"
					style="display: block;"
					src={imageUrl}
					alt={cardName}
					onerror={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
				/>
			{/if}
			{#if hasBackFace}
				<button id="flip-card-btn" type="button" onclick={toggleFace}>
					{isBackFace
						? lang === 'ja'
							? '表面を表示'
							: 'Show front'
						: lang === 'ja'
							? '裏面を表示'
							: 'Show back'}
				</button>
			{/if}
		</div>

		<div class="card-content">
			<h2 id="card-title">{cardName}</h2>
			<span id="card-meta">{metaText}</span>

			<span class="section-label">{t('marketPrice')}</span>
			<div class="compact-panel">
				<div id="price-summary">
					{#each priceChips as chip (chip.bucket)}
						<div class="price-chip" style="border-left-color: {chip.color};">
							<span class="chip-label">{chip.label}</span>
							<span class="chip-value">{yen(chip.price)}</span>
						</div>
					{/each}
				</div>
			</div>

			<div class="inventory-title-row">
				<span class="section-label">{t('inventory')}</span>
				<button class="inventory-save-btn" type="button">{t('save')}</button>
			</div>

			{#each LANGUAGES as langDef (langDef.key)}
				<div class="inventory-language-container">
					<span class="inventory-language-header">{langDef.label}</span>
					<div class="inventory-type-grid">
						{#each FOILS as foil (foil.key)}
							<div class="inventory-type-block">
								<span class="inventory-type-header">{dict[foil.labelKey]}</span>
								<div class="inventory-condition-grid">
									{#each CONDITIONS as cond (cond)}
										<div class="inventory-condition-row">
											<span>{cond}</span>
											<div class="inventory-input-pair">
												<span class="inventory-field-wrap">
													<input
														type="number"
														min="0"
														value="0"
														aria-label="{langDef.label} {foil.key} {cond} quantity"
													/>
													<span class="inventory-field-label">{dict.inventoryQtyLabel}</span>
												</span>
												<span class="inventory-field-wrap">
													<input
														type="number"
														min="0"
														step="0.01"
														value="0"
														placeholder="¥"
														aria-label="{langDef.label} {foil.key} {cond} price"
													/>
													<span class="inventory-field-label">{dict.inventoryPriceLabel}</span>
												</span>
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/each}

			<div class="history-panel">
				<div class="history-panel-header">
					<h3 id="price-history-header">{lang === 'ja' ? '価格履歴' : 'Price history'}</h3>
				</div>

				{#if data.latest.length === 0}
					<p id="error" style="display: block;">{t('noPriceData')}</p>
				{:else}
					<div id="chart-wrap" style="display: block;">
						<canvas id="price-chart" bind:this={chartCanvas}></canvas>
					</div>

					<table id="latest-table" style="display: table;">
						<thead>
							<tr>
								<th>{t('tableLanguage')}</th>
								<th>{t('tableFoil')}</th>
								<th>{t('tablePrice')}</th>
								<th>{t('tableStock')}</th>
								<th>{t('tableWeeklySales')}</th>
								<th>{t('tableLastUpdated')}</th>
							</tr>
						</thead>
						<tbody>
							{#each data.latest as row (row.fetched_at + row.language + String(row.foil))}
								<tr>
									<td>{row.language.toUpperCase()}</td>
									<td>{row.foil ? t('yes') : t('no')}</td>
									<td>{yen(row.price_yen)}</td>
									<td>{row.stock ?? '—'}</td>
									<td>{row.weekly_sales ?? '—'}</td>
									<td>{new Date(row.fetched_at).toLocaleString()}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</div>
		</div>
	</section>
{/if}

<style>
	/* styles live in the global stylesheet */
</style>
