<script lang="ts">
	import { goto } from '$app/navigation';
	import SearchForms from '$lib/components/SearchForms.svelte';
</script>

<SearchForms onNavigate={goto} />

<style>
	/* styles live in the global stylesheet */
</style>
