FROM node:22-alpine AS build
WORKDIR /web
COPY package*.json ./
RUN npm ci --fetch-retries=5 --fetch-retry-factor=2 --fetch-retry-maxtimeout=120000
COPY . .
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build
FROM caddy:2-alpine
COPY --from=build /web/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
