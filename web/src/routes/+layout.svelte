<script lang="ts">
	import { onMount } from 'svelte';
	import { restoreLanguage, t } from '$lib/i18n';
	import LanguageToggle from '$lib/components/LanguageToggle.svelte';
	import RecentSets from '$lib/components/RecentSets.svelte';
	import '../lib/styles.css';

	let { children } = $props();

	onMount(() => {
		restoreLanguage();
	});
</script>

<div class="page-header">
	<h1 id="page-title">{t('pageTitle')}</h1>
	<LanguageToggle />
</div>

<div class="layout-shell">
	<RecentSets />
	<main class="main-column">
		{@render children()}
	</main>
</div>

<style>
	/* styles live in the global stylesheet */
</style>
