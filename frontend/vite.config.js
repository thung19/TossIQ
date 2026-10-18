import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The FastAPI app serves `frontend/dist` as its static root in production, so
// the build output stays inside this directory. In development `npm run dev`
// proxies every request that is not served by the dev server itself to the
// FastAPI server, which keeps in-app fetches on same-origin relative paths
// under both setups without this config tracking the backend's route table.
const VITE_DEV_PATHS = String.raw`/(?:$|@|src/|node_modules/|index\.html$|favicon\.ico$)`;

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      [`^(?!${VITE_DEV_PATHS})`]: {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
