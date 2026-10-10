import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// El proxy evita CORS: el navegador habla con :5173 y Vite reenvia /api al servidor Flask.
const API = process.env.VITE_API_URL || "http://localhost:5000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": API } },
});
