import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// A worktree runs its own lab server on its own port; the default is the one
// `brick-icons-lab` listens on with no arguments.
const API = process.env.LAB_API ?? 'http://127.0.0.1:8792';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@lab': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // Both loopbacks answer; with this unset Node binds only whichever
    // `localhost` resolves to first and 127.0.0.1:5178 refuses.
    host: '::',
    port: 5178,
    proxy: { '/api': API, '/ldraw': API },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        corpus: fileURLToPath(new URL('./corpus.html', import.meta.url)),
        badges: fileURLToPath(new URL('./badges.html', import.meta.url)),
        stats: fileURLToPath(new URL('./stats.html', import.meta.url)),
        // Built so `scripts/shot-sink.py` can serve the page itself. A bake of
        // the whole library must not need a dev server running beside it.
        shot: fileURLToPath(new URL('./shot.html', import.meta.url)),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    // The 3D pane needs a WebGL context jsdom does not have. Everything about
    // it that can be tested without one lives in panes/orbit.ts.
    exclude: ['**/node_modules/**', '**/ThreePane*'],
  },
});
