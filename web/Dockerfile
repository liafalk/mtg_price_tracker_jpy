# SvelteKit frontend — multi-stage build.
# Build stage: install deps, run svelte-kit sync + vite build.
# Run stage: serve the built app with `node build`.
#
# PUBLIC_API_BASE is baked in at build time: it's the URL the *browser*
# uses to reach the FastAPI backend (default: the host-mapped port).
FROM node:22-alpine AS build
# Re-declare inside the stage: an ARG declared before FROM is only visible
# to FROM instructions, so it must be re-declared to be used in RUN/ENV.
ARG PUBLIC_API_BASE=http://localhost:8000
WORKDIR /app
ENV PUBLIC_API_BASE=$PUBLIC_API_BASE
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build
# Keep only production deps (chart.js etc.) for the runtime stage.
RUN npm prune --omit=dev

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/build ./build
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
CMD ["node", "build"]
