FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.18.3 --activate
RUN apk add --no-cache git
RUN git init . && git remote add origin https://github.com/keygen-sh/keygen-portal.git \
    && git fetch --depth 1 origin 2d4bb657273528aafdfd725cd7203021a067c742 \
    && git checkout --detach FETCH_HEAD && rm -rf .git
RUN pnpm install --frozen-lockfile
ARG KEYGEN_ACCOUNT_ID
ARG KEYGEN_ADMIN_EMAIL=admin@example.com
ENV VITE_ADMIN_EMAIL=$KEYGEN_ADMIN_EMAIL
ENV VITE_KEYGEN_ACCOUNT_ID=$KEYGEN_ACCOUNT_ID \
    VITE_KEYGEN_HOST=localhost:8443 \
    VITE_KEYGEN_VERSION=1.8 \
    VITE_KEYGEN_EDITION=CE \
    VITE_KEYGEN_MODE=singleplayer \
    VITE_KEYGEN_AUTHENTICATION_SCHEME=token
COPY portal-customize.mjs /tmp/portal-customize.mjs
COPY portal-advanced.mjs /tmp/portal-advanced.mjs
COPY portal-i18n/ /app/license-localization/
RUN node /app/license-localization/test.mjs \
    && node /tmp/portal-customize.mjs && node /tmp/portal-advanced.mjs \
    && node /app/license-localization/install.mjs && pnpm build

FROM nginx:1.28-alpine
COPY portal.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
