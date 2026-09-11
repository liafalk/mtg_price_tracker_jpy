<script lang="ts">
	import { language, I18N } from '$lib/i18n';
	import { fetchSets } from '$lib/api';
	import Suggestions from './Suggestions.svelte';
	import SetCodeAutocomplete from './SetCodeAutocomplete.svelte';

	let { onNavigate }: { onNavigate?: (url: string) => void } = $props();

	const lang = $derived($language);
	const dict = $derived(I18N[lang]);

	let setCode = $state('');
	let collectorNumber = $state('');
	let setCodes = $state<string[]>([]);

	async function loadSetCodes() {
		try {
			const codes = await fetchSets();
			setCodes = codes;
		} catch {
			setCodes = [];
		}
	}

	function submitLookup(e: Event) {
		e.preventDefault();
		const code = setCode.trim();
		const num = collectorNumber.trim();
		const langParam = `lang=${lang}`;
		if (!code) return;
		if (!num) {
			onNavigate?.(`/search?set=${encodeURIComponent(code)}&${langParam}`);
		} else {
			onNavigate?.(`/card/${encodeURIComponent(code)}/${encodeURIComponent(num)}?${langParam}`);
		}
	}

	function submitSearch(e: Event) {
		e.preventDefault();
		const input = (e.currentTarget as HTMLFormElement).querySelector<HTMLInputElement>('#search-term');
		const q = input?.value.trim() ?? '';
		if (!q) return;
		onNavigate?.(`/search?q=${encodeURIComponent(q)}&lang=${lang}`);
	}

	$effect(() => {
		loadSetCodes();
	});
</script>

<div class="search-tools">
	<form class="inline-search-form" onsubmit={submitSearch}>
		<Suggestions placeholder={lang === 'ja' ? 'カード名を検索' : 'Search card name'} onNavigate={(url) => onNavigate?.(url)} />
		<button type="submit" id="search-btn">{lang === 'ja' ? '検索' : 'Search'}</button>
	</form>

	<span class="search-divider" aria-hidden="true">or</span>

	<form class="inline-search-form" onsubmit={submitLookup}>
		<SetCodeAutocomplete
			setCodes={setCodes}
			placeholder={dict.setCodePlaceholder}
			bind:value={setCode}
		/>
		<input
			id="collector-number"
			type="text"
			placeholder={dict.collectorNumberPlaceholder}
			bind:value={collectorNumber}
		/>
		<button type="submit" id="submit-btn">{dict.submit}</button>
	</form>
</div>

<style>
	/* styles live in the global stylesheet */
</style>
