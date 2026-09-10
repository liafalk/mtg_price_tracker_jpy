import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	server: {
		proxy: {
			// Forward API calls to the FastAPI backend during development.
			'/api': 'http://localhost:8000'
		}
	},
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// adapter-node produces a standalone Node server (run with `node build`).
			// API routing in production is handled client-side via PUBLIC_API_BASE.
			adapter: adapter()
		})
	]
});
