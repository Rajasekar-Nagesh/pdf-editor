# Builds the React app, then serves it with Nginx, which also reverse-proxies /api and terminates HTTPS.
FROM node:20-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache openssl
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx/ /etc/nginx/pdfdesk/
RUN chmod +x /etc/nginx/pdfdesk/entrypoint.sh
EXPOSE 80 443
ENTRYPOINT ["/etc/nginx/pdfdesk/entrypoint.sh"]
