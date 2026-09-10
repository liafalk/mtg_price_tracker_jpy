# SvelteKit frontend — multi-stage build.
# Build stage: install deps, run svelte-kit sync + vite build.
# Run stage: serve the built app with `node build`.
#
# PUBLIC_API_BASE is baked in at build time: it's the URL the *browser*
# uses to reach the FastAPI backend (default: the host-mapped port).
ARG PUBLIC_API_BASE=http://localhost:8000
FROM node:22-alpine AS build
WORKDIR /app
ENV PUBLIC_API_BASE=$PUBLIC_API_BASE
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/build ./build
COPY --from=build /app/package.json ./package.json
CMD ["node", "build"]
