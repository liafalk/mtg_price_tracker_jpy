<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { language, t, I18N } from '$lib/i18n';
	import { fetchSearch, fetchSetCards, type CardResult } from '$lib/api';
	import SearchForms from '$lib/components/SearchForms.svelte';

	const lang = $derived($language);
	const query = $derived(page.url.searchParams.get('q') ?? '');
	const setCode = $derived(page.url.searchParams.get('set') ?? '');

	let results = $state<CardResult[]>([]);
	let loading = $state(false);
	let error = $state('');

	function displayName(item: CardResult): string {
		return lang === 'ja' ? item.name_jp || item.name_en || '' : item.name_en || item.name_jp || '';
	}

	function thumbFor(item: CardResult): string {
		return lang === 'ja' ? item.thumb_jp || item.thumb || '' : item.thumb || '';
	}

	function rarityText(item: CardResult): string {
		const key = (item.rarity ?? '').toLowerCase();
		const dict = I18N[lang];
		return dict.rarity[key as keyof typeof dict.rarity] || item.rarity || '—';
	}

	function yen(value: number | null | undefined): string {
		return value == null ? '—' : `¥${Number(value).toLocaleString()}`;
	}

	function cardLink(item: CardResult): string {
		return `/card/${item.set_code}/${item.collector_number}?lang=${lang}`;
	}

	async function load() {
		loading = true;
		error = '';
		try {
			if (setCode) {
				results = await fetchSetCards(setCode);
			} else if (query) {
				results = await fetchSearch(query);
			} else {
				results = [];
			}
		} catch (e) {
			error = e instanceof Error ? e.message : t('noCardFound');
			results = [];
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		load();
	});
</script>

<SearchForms onNavigate={goto} />

<div id="search-results-page">
	<h2>{t('searchResultsTitle')}</h2>
	{#if error}
		<p id="error" style="display: block;">{error}</p>
	{:else}
		<table id="search-results-table">
			<thead>
				<tr>
					{#if lang === 'ja'}
						<th>タイトル</th>
						<th>サムネイル</th>
						<th>セット</th>
						<th>番号</th>
						<th>レアリティ</th>
						<th>価格 (EN)</th>
						<th>価格 (JP)</th>
					{:else}
						<th>Title</th>
						<th>Thumbnail</th>
						<th>Set</th>
						<th>Number</th>
						<th>Rarity</th>
						<th>Price (EN)</th>
						<th>Price (JP)</th>
					{/if}
				</tr>
			</thead>
			<tbody>
				{#if results.length === 0}
					<tr>
						<td colspan="7">{lang === 'ja' ? '一致するカードが見つかりませんでした。' : 'No matching cards were found.'}</td>
					</tr>
				{:else}
					{#each results as item (item.id)}
						<tr>
							<td>
								<a href={cardLink(item)} style="color: inherit; text-decoration: none;">{displayName(item)}</a>
							</td>
							<td>
								{#if thumbFor(item)}
									<img src={thumbFor(item)} alt="" style="width: 120px; border-radius: 6px;" />
								{/if}
							</td>
							<td>{item.set_code.toUpperCase()}</td>
							<td>{item.collector_number}</td>
							<td>{rarityText(item)}</td>
							<td>
								<div style="display: grid; gap: 0.2rem; min-width: 120px; font-size: 0.88rem; line-height: 1.4;">
									<div>Normal: {yen(item.recent_prices?.en_nonfoil)}</div>
									<div>Foil: {yen(item.recent_prices?.en_foil)}</div>
								</div>
							</td>
							<td>
								<div style="display: grid; gap: 0.2rem; min-width: 120px; font-size: 0.88rem; line-height: 1.4;">
									<div>Normal: {yen(item.recent_prices?.jp_nonfoil)}</div>
									<div>Foil: {yen(item.recent_prices?.jp_foil)}</div>
								</div>
							</td>
						</tr>
					{/each}
				{/if}
			</tbody>
		</table>
	{/if}
</div>

<style>
	/* styles live in the global stylesheet */
</style>
