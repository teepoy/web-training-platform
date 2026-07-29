
# ---- Build stage ----
FROM node:20-alpine AS build

ARG NPM_CONFIG_REGISTRY=""
ENV NPM_CONFIG_REGISTRY=${NPM_CONFIG_REGISTRY}

RUN corepack enable && corepack prepare pnpm@10.5.0 --activate

WORKDIR /app

# Copy workspace manifests and lockfile first for layer caching
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/sc-map-element/package.json packages/sc-map-element/package.json

RUN pnpm install --frozen-lockfile

# Copy web source
COPY apps/web/ apps/web/
COPY packages/sc-map-element/ packages/sc-map-element/

RUN pnpm --filter web build

# ---- Dev stage ----
FROM node:20-alpine AS dev

ARG NPM_CONFIG_REGISTRY=""
ENV NPM_CONFIG_REGISTRY=${NPM_CONFIG_REGISTRY}

RUN corepack enable && corepack prepare pnpm@10.5.0 --activate

WORKDIR /app

# Copy workspace manifests and lockfile first for layer caching
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/sc-map-element/package.json packages/sc-map-element/package.json

RUN pnpm install --frozen-lockfile

# Copy web source
COPY apps/web/ apps/web/
COPY packages/sc-map-element/ packages/sc-map-element/

WORKDIR /app/apps/web

EXPOSE 5173

CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "5173"]

# ---- Prod stage ----
FROM nginx:alpine AS prod

# Copy built assets
COPY --from=build /app/apps/web/dist /usr/share/nginx/html

# Copy nginx config
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
