// Typed client for the FastAPI backend. All endpoints are served under /api.
//
// In development the Vite dev server proxies /api to the backend, so the
// default (empty) base works. In production the SvelteKit node server and
// FastAPI live in separate containers, so set PUBLIC_API_BASE at build time
// (e.g. PUBLIC_API_BASE=http://web:8000) to point at the backend.
//
// SvelteKit exposes PUBLIC_* vars via $env (not import.meta.env, which only
// sees VITE_* vars). The static public module is replaced at build time, so
// the value is baked into the client bundle.
import { PUBLIC_API_BASE } from '$env/static/public';

const API_BASE: string = PUBLIC_API_BASE ?? '';

export interface RecentPrices {
	jp_nonfoil: number | null;
	jp_foil: number | null;
	en_nonfoil: number | null;
	en_foil: number | null;
}

export interface CardResult {
	id: number;
	set_code: string;
	collector_number: string;
	name_en: string | null;
	name_jp: string | null;
	rarity: string | null;
	thumb: string | null;
	thumb_jp: string | null;
	recent_prices: RecentPrices;
	detail_url: string;
}

export interface Suggestion {
	id: number;
	set_code: string;
	collector_number: string;
	name_en: string | null;
	name_jp: string | null;
	thumb: string | null;
	thumb_jp: string | null;
	detail_url: string;
}

export interface RecentSet {
	code: string;
	name: string;
	name_jp: string | null;
	release_date: string | null;
}

export interface CardImage {
	grid: string | null;
	thumb: string | null;
	grid_jp: string | null;
	thumb_jp: string | null;
	back_grid: string | null;
	back_thumb: string | null;
	back_grid_jp: string | null;
	back_thumb_jp: string | null;
}

export interface CardInfo {
	name_en: string | null;
	name_jp: string | null;
	set_code: string;
	collector_number: string;
	rarity: string | null;
	double_faced: boolean;
	scryfall_id: string | null;
	scryfall_id_jp: string | null;
	img: CardImage;
    oracle_id: string | null;
    tcgplayer_id: number | null;
    cardmarket_id: number | null;
    
}

export interface LatestPrice {
	language: string;
	foil: boolean;
	price_yen: number;
	stock: number | null;
	weekly_sales: number | null;
	fetched_at: string;
}

export interface HistoryPoint {
	fetched_at: string;
	price_yen: number;
}

export type HistoryBucket = 'jp_nonfoil' | 'jp_foil' | 'en_nonfoil' | 'en_foil';

export interface PriceHistory {
	jp_nonfoil: HistoryPoint[];
	jp_foil: HistoryPoint[];
	en_nonfoil: HistoryPoint[];
	en_foil: HistoryPoint[];
}

export interface PricesResponse {
	card: CardInfo;
	latest: LatestPrice[];
	history: PriceHistory;
}

async function getJson<T>(url: string): Promise<T> {
	const res = await fetch(url);
	if (!res.ok) {
		let detail = `Error ${res.status}`;
		try {
			const body = await res.json();
			if (body?.detail) detail = body.detail;
		} catch {
			// ignore parse errors, keep default
		}
		throw new Error(detail);
	}
	return res.json() as Promise<T>;
}

export function fetchSets(): Promise<string[]> {
	return getJson<{ sets: string[] }>(`${API_BASE}/api/sets`).then((d) => d.sets);
}

export function fetchRecentSets(limit = 12): Promise<RecentSet[]> {
	return getJson<{ sets: RecentSet[] }>(`${API_BASE}/api/recent_sets?limit=${limit}`).then(
		(d) => d.sets
	);
}

export function fetchSearch(q: string): Promise<CardResult[]> {
	return getJson<{ results: CardResult[] }>(`${API_BASE}/api/search?q=${encodeURIComponent(q)}`).then(
		(d) => d.results
	);
}

export function fetchSetCards(set: string): Promise<CardResult[]> {
	return getJson<{ results: CardResult[] }>(
		`${API_BASE}/api/set_cards?set=${encodeURIComponent(set)}`
	).then((d) => d.results);
}

export function fetchSuggestions(q: string, limit = 5): Promise<Suggestion[]> {
	return getJson<{ results: Suggestion[] }>(
		`${API_BASE}/api/suggestions?q=${encodeURIComponent(q)}&limit=${limit}`
	).then((d) => d.results);
}

export function fetchPrices(set: string, number: string): Promise<PricesResponse> {
	return getJson<PricesResponse>(
		`${API_BASE}/api/prices?set=${encodeURIComponent(set)}&number=${encodeURIComponent(number)}`
	);
}
