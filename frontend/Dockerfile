# Build environment
FROM node:18-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . ./
RUN npm run build

# Production environment — nginx serves the SPA and proxies /api/ to the
# FastAPI backend so the React app talks to the bridge through a single
# origin (matching the URLs documented in README.md).
FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O- http://localhost/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
