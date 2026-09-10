<script lang="ts">
	import { language } from '$lib/i18n';
	import { fetchSuggestions, type Suggestion } from '$lib/api';

	let {
		onNavigate,
		placeholder = 'Search card name'
	}: { onNavigate?: (url: string) => void; placeholder?: string } = $props();

	let term = $state('');
	let results = $state<Suggestion[]>([]);
	let open = $state(false);
	let blurTimer: ReturnType<typeof setTimeout> | undefined;

	const lang = $derived($language);

	function displayName(s: Suggestion): string {
		return lang === 'ja' ? s.name_jp || s.name_en || '' : s.name_en || s.name_jp || '';
	}

	async function load() {
		const q = term.trim();
		if (!q) {
			results = [];
			open = false;
			return;
		}
		try {
			results = await fetchSuggestions(q, 5);
			open = results.length > 0;
		} catch {
			results = [];
			open = false;
		}
	}

	function onInput() {
		clearTimeout(blurTimer);
		load();
	}

	function onFocus() {
		clearTimeout(blurTimer);
		if (term.trim()) load();
	}

	function onBlur() {
		blurTimer = setTimeout(() => {
			open = false;
		}, 150);
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			open = false;
		}
	}

	function pick(url: string) {
		open = false;
		onNavigate?.(url);
	}
</script>

<div class="suggestions-container">
	<input
		id="search-term"
		type="text"
		data-suggestions
		placeholder={placeholder}
		bind:value={term}
		oninput={onInput}
		onfocus={onFocus}
		onblur={onBlur}
		onkeydown={onKeydown}
		autocomplete="off"
	/>
	<ul class="suggestions-list" aria-hidden={!open}>
		{#if open && results.length === 0}
			<li class="suggestion-empty">{lang === 'ja' ? 'カードが見つかりません' : 'No cards found'}</li>
		{:else}
			{#each results as s (s.id)}
				<li class="suggestion-item">
					<a href={s.detail_url} onclick={(e) => { e.preventDefault(); pick(s.detail_url); }}>
						<span class="suggestion-name">{displayName(s)} - {s.set_code.toUpperCase()} {s.collector_number}</span>
					</a>
				</li>
			{/each}
		{/if}
	</ul>
</div>

<style>
	/* styles live in the global stylesheet */
</style>
