// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}

		// Public env vars (exposed to the client bundle at build time).
		interface Env {
			/** Base URL the browser uses to reach the FastAPI backend. */
			PUBLIC_API_BASE?: string;
		}
	}
}

export {};
