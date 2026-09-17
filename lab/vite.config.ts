import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { searchForWorkspaceRoot } from 'vite';
import { defineConfig, type Plugin } from 'vitest/config';

/** Serves `/corpus` from `corpus.html`, so a lab URL carries no extension.
 *  Dev only: the build still emits the files under their own names, and
 *  `scripts/shot-sink.py` serves `shot.html` out of `dist` by that name. */
function extensionlessPages(): Plugin {
  return {
    name: 'lab-extensionless-pages',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? '/';
        const cut = url.search(/[?#]/);
        const path = cut === -1 ? url : url.slice(0, cut);
        const rest = cut === -1 ? '' : url.slice(cut);
        if (path !== '/' && !path.includes('.')) {
          const file = fileURLToPath(new URL(`.${path}.html`, import.meta.url));
          if (existsSync(file)) req.url = `${path}.html${rest}`;
        }
        next();
      });
    },
  };
}

// A worktree runs its own lab server on its own port; the default is the one
// `brick-icons-lab` listens on with no arguments.
const API = process.env.LAB_API ?? 'http://127.0.0.1:8792';

/** pezlie's `wall` and brick-icons spec, as TypeScript source from the
 *  git dependency package.json pins by sha. `PEZLIE=~/src/pezlie`
 *  reads a checkout instead, for trying unpinned pezlie work on `/wall`. */
const PEZLIE = process.env.PEZLIE
  ?? fileURLToPath(new URL('./node_modules/pezlie', import.meta.url));
const pezlieAlias = [
  { find: /^@pezlie\/wall\/(.*)$/, replacement: `${PEZLIE}/wall/$1` },
  { find: /^@pezlie\/host-brick-icons\/(.*)$/,
    replacement: `${PEZLIE}/hosts/brick-icons/$1` },
];

/** `WEASEL_SRC=~/src/weasel npm run dev` draws `@weasel-js/core`,
 *  `@weasel-js/labkit` and `@weasel-js/ui` from a weasel checkout instead of
 *  the installed ones, for measuring an unreleased renderer change against
 *  `/bench` or running the lab against a kit component that has not shipped
 *  yet. Each `dist` has to be built; the alias points at the build, not the
 *  source, so what runs is what a release would ship. Unset by default --
 *  several sessions share this checkout. */
const WEASEL_SRC = process.env.WEASEL_SRC;
// Regexes, not a bare string: a plain alias prefix-matches, and
// `@weasel-js/svg` imports `@weasel-js/core/patterns-builtin`, which then
// resolves under the root entry's own filename. The subpaths mirror the
// package's exports map, which maps each to `dist/<name>.js`.
const weaselAlias = WEASEL_SRC
  ? [{ find: /^@weasel-js\/core$/,
       replacement: `${WEASEL_SRC}/packages/core/dist/index.js` },
     { find: /^@weasel-js\/core\/(.*)$/,
       replacement: `${WEASEL_SRC}/packages/core/dist/$1.js` },
     // `@weasel-js/ui`'s components subpath is a wildcard whose target puts
     // the star mid-path (`dist/components/*/index.js`), so it is spelled out
     // rather than read off the map the way labkit's is.
     { find: /^@weasel-js\/ui$/,
       replacement: `${WEASEL_SRC}/packages/ui/dist/index.js` },
     { find: /^@weasel-js\/ui\/style\.css$/,
       replacement: `${WEASEL_SRC}/packages/ui/dist/style.css` },
     { find: /^@weasel-js\/ui\/components\/(.*)$/,
       replacement: `${WEASEL_SRC}/packages/ui/dist/components/$1/index.js` },
     ...labkitAlias(WEASEL_SRC)]
  : [];

/** labkit's subpaths read off its own exports map rather than a pattern.
 *  There isn't one to guess: most map to `dist/<name>/index.js`, but
 *  `weasel-ui` and `weasel-canvas` are `dist/passthrough/<name>.js` and
 *  `styles.css` is a file. Reading the map keeps this correct as labkit adds
 *  entry points -- a wrong guess fails as ENOENT inside esbuild's dep scan,
 *  which names the file it wanted and not the alias that asked for it. */
function labkitAlias(src: string) {
  const pkg = `${src}/packages/labkit`;
  const { exports: map } = JSON.parse(
    readFileSync(`${pkg}/package.json`, 'utf8')) as
    { exports: Record<string, { import?: string } | string> };
  return Object.entries(map).map(([sub, target]) => {
    const file = typeof target === 'string' ? target : target.import!;
    const name = sub === '.' ? '' : sub.slice(1);
    return { find: new RegExp(`^@weasel-js/labkit${name.replace(/[./]/g, '\\$&')}$`),
             replacement: `${pkg}/${file.slice(2)}` };
  });
}

/** The port this server was started on, when the command line names one. */
function launchPort(): string | undefined {
  const argv = process.argv;
  const at = argv.findIndex((a) => a === '--port' || a.startsWith('--port='));
  if (at === -1) return undefined;
  return argv[at].includes('=') ? argv[at].split('=')[1] : argv[at + 1];
}
const PORT = launchPort();

export default defineConfig({
  plugins: [react(), extensionlessPages()],
  // One dependency cache per server. Two servers in this checkout once
  // re-optimized at the same moment, each rename clobbered the other's, and
  // both served 504 for React until restarted.
  cacheDir: PORT ? `node_modules/.vite/port-${PORT}` : undefined,
  resolve: {
    alias: [
      { find: '@lab', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
      ...weaselAlias,
      ...pezlieAlias,
    ],
    // One React for the page however a dependency asked for it. R3F's hooks
    // read a context, so a second copy makes them throw "Hooks can only be
    // used within the Canvas component" from inside a Canvas.
    dedupe: ['react', 'react-dom', 'three',
             '@weasel-js/core', '@weasel-js/labkit', '@weasel-js/ui'],
  },
  /* Everything the lightbox needs, named here because nothing else imports it.
   *
   * Vite scans the entry graph at startup and optimizes what it finds. These
   * are reachable only through the 3D preview, which loads when someone opens
   * a part -- so they were discovered mid-session, and a re-optimize hands new
   * hashes to modules requested after it while the ones already loaded keep
   * the old. That is two copies of React in one page, and the wall crashed on
   * the first part anybody opened.
   *
   * Add to this whenever a route starts importing a package no eager module
   * does; `node_modules/.vite/deps/_metadata.json` lists what was optimized,
   * and anything in it that is not reachable from an entry belongs here. */
  optimizeDeps: {
    // Served as source: pre-bundled, a module WallView also imports relatively
    // would load twice.
    exclude: ['pezlie'],
    include: [
      '@react-three/fiber', '@react-three/drei', 'three',
      'three/examples/jsm/loaders/LDrawLoader.js',
      'three/examples/jsm/lines/LineMaterial.js',
      'three/examples/jsm/lines/LineSegments2.js',
      'three/examples/jsm/lines/LineSegmentsGeometry.js',
      'three/examples/jsm/materials/LDrawConditionalLineMaterial.js',
    ],
  },
  server: {
    // Both loopbacks answer; with this unset Node binds only whichever
    // `localhost` resolves to first and 127.0.0.1:5178 refuses.
    host: '::',
    port: 5178,
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), PEZLIE] },
    proxy: { '/api': API, '/ldraw': API },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        corpus: fileURLToPath(new URL('./corpus.html', import.meta.url)),
        wall: fileURLToPath(new URL('./wall.html', import.meta.url)),
        badges: fileURLToPath(new URL('./badges.html', import.meta.url)),
        stats: fileURLToPath(new URL('./stats.html', import.meta.url)),
        ingest: fileURLToPath(new URL('./ingest.html', import.meta.url)),
        review: fileURLToPath(new URL('./review.html', import.meta.url)),
        bench: fileURLToPath(new URL('./bench.html', import.meta.url)),
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
    // Source, not a build: left external, Node would load its .ts itself.
    server: { deps: { inline: [/pezlie/] } },
  },
});
