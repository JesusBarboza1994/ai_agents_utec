# Dashboard de reservas (React + Vite) para Railway.
#
# El contexto de build es la RAIZ del repo (ai_agents_utec), no esta carpeta; por eso
# todas las rutas llevan el prefijo dashboard_reservas/. En Railway:
#   Settings -> Build -> Dockerfile Path = dashboard_reservas/Dockerfile
#   (o la variable RAILWAY_DOCKERFILE_PATH=dashboard_reservas/Dockerfile)
# Local, desde la raiz del repo:
#   docker build -f dashboard_reservas/Dockerfile -t dashboard-reservas .
#
# Multi-stage: Node compila el sitio estatico y nginx lo sirve. Como el dashboard
# llama a `/api/...` con rutas relativas, nginx hace de proxy hacia el backend de
# Clemente: el navegador solo habla con este servicio y no hace falta CORS.
#
# Variables de entorno (Railway):
#   BACKEND_URL  URL del backend, sin barra final. Ej.: https://clemente.up.railway.app
#   PORT         la inyecta Railway; nginx escucha en ese puerto.

FROM node:22-alpine AS build
WORKDIR /app
COPY dashboard_reservas/package.json dashboard_reservas/package-lock.json ./
RUN npm ci
COPY dashboard_reservas/index.html dashboard_reservas/vite.config.js ./
COPY dashboard_reservas/src ./src
RUN npm run build

FROM nginx:1.27-alpine
# El entrypoint de la imagen sustituye ${PORT} y ${BACKEND_URL} en las plantillas
# de /etc/nginx/templates y deja el resultado en /etc/nginx/conf.d.
COPY dashboard_reservas/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

ENV PORT=8080 \
    BACKEND_URL=http://localhost:5050

EXPOSE 8080
