<script lang="ts">
	import { language, t } from '$lib/i18n';
	import { fetchRecentSets, type RecentSet } from '$lib/api';

	let { onNavigate }: { onNavigate?: (url: string) => void } = $props();

	let sets = $state<RecentSet[]>([]);
	let loaded = $state(false);

	const lang = $derived($language);

	function formatDate(iso: string | null): string {
		if (!iso) return lang === 'ja' ? 'リリース日不明' : 'Date unknown';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return lang === 'ja' ? 'リリース日不明' : 'Date unknown';
		return d.toLocaleDateString(lang === 'ja' ? 'ja-JP' : 'en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function linkFor(set: RecentSet): string {
		return `/search?set=${encodeURIComponent(set.code)}&lang=${lang}`;
	}

	$effect(() => {
		fetchRecentSets(12)
			.then((data) => {
				sets = data;
				loaded = true;
			})
			.catch(() => {
				sets = [];
				loaded = true;
			});
	});
</script>

<aside class="sidebar-panel">
	<h2 class="recent-sets-title">{t('recentSetsTitle')}</h2>
	{#if loaded && sets.length === 0}
		<p class="hint">{lang === 'ja' ? 'セットが見つかりませんでした。' : 'No sets available.'}</p>
	{:else}
		<ul class="recent-set-list">
			{#each sets as set (set.code)}
				<li class="recent-set-item">
					<a
						href={linkFor(set)}
						class="recent-set-item-flex"
						onclick={(e) => {
							e.preventDefault();
							onNavigate?.(linkFor(set));
						}}
					>
						<img class="recent-set-icon" src={`https://svgs.scryfall.io/sets/${set.code.toLowerCase()}.svg`} alt="" />
						<span class="recent-set-code">{set.code.toUpperCase()}</span>
						<span class="recent-set-name">{set.name}</span>
						<span class="recent-set-date">{formatDate(set.release_date)}</span>
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</aside>

<style>
	/* styles live in the global stylesheet */
</style>
