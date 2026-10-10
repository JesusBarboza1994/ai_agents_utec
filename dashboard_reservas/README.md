# Dashboard de reservas

Dashboard basico (React + Vite), sin autenticacion, que solo lista las reservas de Clemente.

1. Servidor: en `../Clemente_Multiagente` ejecutar con las rutas de depuracion activas
   `CLEMENTE_DEBUG_ROUTES=1 python run.py` (puerto 5000).
2. Dashboard: `npm install && npm run dev` -> http://localhost:5173

Vite hace proxy de `/api` a `http://localhost:5000` (cambiar con `VITE_API_URL`).

## Despliegue en Railway

El `Dockerfile` compila el sitio y lo sirve con nginx, que reenvia `/api/` al backend. El contexto de build es la raiz del repo (`ai_agents_utec`): en Railway pon `Dockerfile Path = dashboard_reservas/Dockerfile`.
En el servicio de Railway define:

- `BACKEND_URL`: URL del backend de Clemente, sin barra final (por ejemplo `https://clemente.up.railway.app`).

`PORT` lo pone Railway. El backend debe tener `CLEMENTE_DEBUG_ROUTES=1` para exponer
`/api/reservas` y `/api/chats`, que **no tienen autenticacion**: cualquiera con la URL
del dashboard vera reservas y conversaciones.
