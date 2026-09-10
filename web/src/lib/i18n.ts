import { writable, derived, get } from 'svelte/store';

export type Language = 'en' | 'ja';

export interface RarityLabels {
	common: string;
	uncommon: string;
	rare: string;
	mythic: string;
}

export interface Dictionary {
	pageTitle: string;
	setCodePlaceholder: string;
	collectorNumberPlaceholder: string;
	submit: string;
	tableLanguage: string;
	tableFoil: string;
	tablePrice: string;
	tableStock: string;
	tableWeeklySales: string;
	tableLastUpdated: string;
	noPriceData: string;
	noCardFound: string;
	yes: string;
	no: string;
	unknownName: string;
	rarity: RarityLabels;
	inventoryQtyLabel: string;
	inventoryPriceLabel: string;
	marketPrice: string;
	inventory: string;
	save: string;
	languageEn: string;
	languageJp: string;
	inventoryNonFoil: string;
	inventoryFoil: string;
	recentSetsTitle: string;
	searchResultsTitle: string;
}

export const I18N: Record<Language, Dictionary> = {
	en: {
		pageTitle: 'JPY MTG Card Prices',
		setCodePlaceholder: 'Set code (e.g. hob)',
		collectorNumberPlaceholder: 'Collector number (e.g. 119)',
		submit: 'Look up',
		tableLanguage: 'Language',
		tableFoil: 'Foil',
		tablePrice: 'Price (¥)',
		tableStock: 'Stock',
		tableWeeklySales: 'Weekly sales',
		tableLastUpdated: 'Last updated',
		noPriceData:
			'Card found, but there is no price data for it yet -- has the crawler run for this set?',
		noCardFound: 'Could not reach the server.',
		yes: 'Yes',
		no: 'No',
		unknownName: '(name unknown)',
		rarity: {
			common: 'Common',
			uncommon: 'Uncommon',
			rare: 'Rare',
			mythic: 'Mythic Rare'
		},
		inventoryQtyLabel: 'qty',
		inventoryPriceLabel: 'price',
		marketPrice: 'Market price',
		inventory: 'Inventory',
		save: 'Save',
		languageEn: 'EN',
		languageJp: 'JP',
		inventoryNonFoil: 'Non-foil',
		inventoryFoil: 'Foil',
		recentSetsTitle: 'Recent sets',
		searchResultsTitle: 'Search results'
	},
	ja: {
		pageTitle: 'JPY MTG カード価格',
		setCodePlaceholder: 'セットコード（例: hob）',
		collectorNumberPlaceholder: '収集番号（例: 119）',
		submit: '検索',
		tableLanguage: '言語',
		tableFoil: 'Foil',
		tablePrice: '価格 (¥)',
		tableStock: '在庫',
		tableWeeklySales: '週間売上',
		tableLastUpdated: '更新日時',
		noPriceData:
			'カードは見つかりましたが、まだ価格データがありません。このセットのクローラーは走っていますか？',
		noCardFound: 'サーバーに接続できませんでした。',
		yes: 'あり',
		no: 'なし',
		unknownName: '（名前不明）',
		rarity: {
			common: 'コモン',
			uncommon: 'アンコモン',
			rare: 'レア',
			mythic: '神話レア'
		},
		inventoryQtyLabel: '数',
		inventoryPriceLabel: '価',
		marketPrice: '市場価格',
		inventory: '在庫',
		save: '保存',
		languageEn: 'EN',
		languageJp: 'JP',
		inventoryNonFoil: '通常版',
		inventoryFoil: 'Foil',
		recentSetsTitle: '最近のセット',
		searchResultsTitle: '検索結果'
	}
};

const STORAGE_KEY = 'activeLanguage';

function readStoredLanguage(): Language {
	if (typeof localStorage === 'undefined') return 'en';
	const stored = localStorage.getItem(STORAGE_KEY);
	return stored === 'ja' || stored === 'en' ? stored : 'en';
}

/**
 * Reactive language store. Mirrors the old `AppLanguage` helper:
 *  - defaults to 'en'
 *  - `restore()` reads localStorage, then lets a `?lang=` query param override
 *  - `setLanguage()` persists to localStorage
 */
export const language = writable<Language>(readStoredLanguage());

/** Translate a top-level dictionary key for the active language. */
export function t(key: Exclude<keyof Dictionary, 'rarity'>): string {
	const lang = get(language);
	return I18N[lang][key];
}

/** Localized rarity label, falling back to the raw value. */
export function rarityLabel(rarity: string | null | undefined, lang: Language = get(language)): string {
	if (!rarity) return '—';
	return I18N[lang].rarity[rarity as keyof RarityLabels] || rarity;
}

/**
 * Restore the language from localStorage, then apply a `?lang=` query param
 * override if present. Call once on app init (client-side).
 */
export function restoreLanguage(): void {
	if (typeof window === 'undefined') return;
	const stored = readStoredLanguage();
	language.set(stored);

	const params = new URLSearchParams(window.location.search);
	const fromQuery = params.get('lang');
	if (fromQuery === 'ja' || fromQuery === 'en') {
		language.set(fromQuery);
	}
}

/** Set the active language and persist it. */
export function setLanguage(lang: Language): void {
	language.set(lang);
	if (typeof localStorage !== 'undefined') {
		localStorage.setItem(STORAGE_KEY, lang);
	}
}

/** Convenience derived store for the current dictionary. */
export const dictionary = derived(language, ($lang) => I18N[$lang]);
