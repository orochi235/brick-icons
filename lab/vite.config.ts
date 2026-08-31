import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const API = 'http://127.0.0.1:8792';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@lab': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5178,
    proxy: { '/api': API, '/ldraw': API },
  },
  build: { outDir: 'dist' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    // The 3D pane needs a WebGL context jsdom does not have. Everything about
    // it that can be tested without one lives in panes/orbit.ts.
    exclude: ['**/node_modules/**', '**/ThreePane*'],
  },
});
