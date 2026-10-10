# Dashboard de reservas

Dashboard basico (React + Vite), sin autenticacion, que solo lista las reservas de Clemente.

1. Servidor: en `../Clemente_Multiagente` ejecutar con las rutas de depuracion activas
   `CLEMENTE_DEBUG_ROUTES=1 python run.py` (puerto 5000).
2. Dashboard: `npm install && npm run dev` -> http://localhost:5173

Vite hace proxy de `/api` a `http://localhost:5000` (cambiar con `VITE_API_URL`).
