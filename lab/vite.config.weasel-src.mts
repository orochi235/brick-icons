// TEMPORARY (Claude, 2026-09-01): runs the lab against a weasel worktree's
// source instead of the published labkit, on port 5179, so a kit change can be
// seen here before it is released. Delete with the branch.
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { weaselAliases } from '/Users/mike/src/weasel/.claude/worktrees/prop-density/scripts/vite-aliases';

const WEASEL = '/Users/mike/src/weasel/.claude/worktrees/prop-density';
const API = 'http://127.0.0.1:8792';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: '@lab', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
      {
        find: '@weasel-js/labkit/styles.css',
        replacement: fileURLToPath(new URL('./node_modules/@weasel-js/labkit/dist/styles.css', import.meta.url)),
      },
      ...weaselAliases(WEASEL),
    ],
  },
  server: {
    port: 5179,
    proxy: { '/api': API, '/ldraw': API },
  },
});
