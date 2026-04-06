# syntax=docker/dockerfile:1

# ---- Build stage ----
FROM node:20-alpine AS build

RUN npm install -g pnpm

WORKDIR /app

# Copy workspace manifests and lockfile first for layer caching
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json

RUN pnpm install --frozen-lockfile

# Copy web source
COPY apps/web/ apps/web/

RUN pnpm --filter web build

# ---- Serve stage ----
FROM nginx:alpine

# Copy built assets
COPY --from=build /app/apps/web/dist /usr/share/nginx/html

# Copy nginx config
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
