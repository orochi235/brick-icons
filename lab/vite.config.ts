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
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test-setup.ts'] },
});
