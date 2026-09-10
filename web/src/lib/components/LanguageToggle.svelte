<script lang="ts">
	import { language, setLanguage } from '$lib/i18n';

	let { onLanguageChange }: { onLanguageChange?: () => void } = $props();

	function choose(lang: 'en' | 'ja') {
		setLanguage(lang);
		onLanguageChange?.();
	}
</script>

<div class="language-toggle" role="group" aria-label="Language">
	<button
		type="button"
		class="lang-btn"
		class:active={$language === 'en'}
		data-language="en"
		onclick={() => choose('en')}
	>
		English
	</button>
	<button
		type="button"
		class="lang-btn"
		class:active={$language === 'ja'}
		data-language="ja"
		onclick={() => choose('ja')}
	>
		日本語
	</button>
</div>
