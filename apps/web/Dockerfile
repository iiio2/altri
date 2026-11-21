# syntax=docker/dockerfile:1
# Build from the repo root: docker build -f apps/web/Dockerfile .

FROM node:26-slim AS base
ENV NEXT_TELEMETRY_DISABLED=1
# Node 25+ no longer ships corepack; npm is used only to bootstrap the pinned pnpm (root package.json).
RUN npm install --global pnpm@12.21.0 && npm cache clean --force

FROM base AS build
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY apps/api/package.json apps/api/
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --filter web
COPY apps/web apps/web
# Rewrites (next.config.ts) are compiled into the build, so the API address the Next server proxies to is fixed
# here. NEXT_PUBLIC_API_WS_URL is inlined into the browser bundle; empty ⇒ ws://<page host>:8000.
ARG API_URL=http://api:8000
ARG NEXT_PUBLIC_API_WS_URL=
ENV API_URL=$API_URL \
    NEXT_OUTPUT=standalone
RUN if [ -z "$NEXT_PUBLIC_API_WS_URL" ]; then unset NEXT_PUBLIC_API_WS_URL; fi && pnpm --filter web build

FROM node:26-slim AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
# Standalone output mirrors the workspace layout: the server lives at apps/web/server.js.
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=node:node /repo/apps/web/public ./apps/web/public
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
