FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_OIDC_ISSUER
ARG VITE_OIDC_CLIENT_ID
ARG VITE_OIDC_AUDIENCE
ARG VITE_OIDC_REDIRECT_URI
ARG VITE_OIDC_SCOPE
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
