<script lang="ts">
	import { language } from '$lib/i18n';

	let {
		setCodes,
		placeholder,
		value = $bindable(''),
		onPick
	}: {
		setCodes: string[];
		placeholder?: string;
		value?: string;
		onPick?: (code: string) => void;
	} = $props();

	const lang = $derived($language);

	let open = $state(false);
	let blurTimer: ReturnType<typeof setTimeout> | undefined;

	const filtered = $derived.by(() => {
		const q = value.trim().toLowerCase();
		if (!q) return setCodes;
		return setCodes.filter((code) => code.toLowerCase().includes(q));
	});

	function onInput() {
		clearTimeout(blurTimer);
		open = true;
	}

	function onFocus() {
		clearTimeout(blurTimer);
		open = true;
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

	function pick(code: string) {
		value = code;
		open = false;
		onPick?.(code);
	}
</script>

<div class="suggestions-container">
	<input
		id="set-code"
		type="text"
		data-set-code
		placeholder={placeholder}
		bind:value={value}
		oninput={onInput}
		onfocus={onFocus}
		onblur={onBlur}
		onkeydown={onKeydown}
		autocomplete="off"
	/>
	<ul class="suggestions-list" aria-hidden={!open}>
		{#if open && filtered.length === 0}
			<li class="suggestion-empty">{lang === 'ja' ? 'セットが見つかりません' : 'No sets found'}</li>
		{:else}
			{#each filtered as code (code)}
				<li class="suggestion-item">
					<button
						type="button"
						class="suggestion-link"
						tabindex="-1"
						onclick={() => pick(code)}
					>
						<span class="suggestion-name">{code.toUpperCase()}</span>
					</button>
				</li>
			{/each}
		{/if}
	</ul>
</div>

<style>
	/* styles live in the global stylesheet */
</style>
