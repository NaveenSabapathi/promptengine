FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY apps/extension/package.json apps/extension/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json
RUN npm ci
COPY apps/web ./apps/web
COPY packages/shared-types ./packages/shared-types
RUN npm run build

FROM nginx:1.28-alpine AS runtime
RUN rm /etc/nginx/conf.d/default.conf && mkdir -p /etc/nginx/tls
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
EXPOSE 8080 8443
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/nginx-health
