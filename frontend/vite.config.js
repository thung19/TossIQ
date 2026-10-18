import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The FastAPI app serves `frontend/dist` as its static root in production, so
// the build output stays inside this directory. In development `npm run dev`
// proxies the API routes to the FastAPI server, which lets every in-app fetch
// stay a same-origin relative path under both setups.
const API_ROUTES = [
  '/health',
  '/classify',
  '/sort',
  '/enrich',
  '/products',
  '/stats',
  '/events',
  '/hazards',
  '/recommendations',
];

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: Object.fromEntries(
      API_ROUTES.map((route) => [route, { target: 'http://localhost:8000', changeOrigin: true }]),
    ),
  },
});
