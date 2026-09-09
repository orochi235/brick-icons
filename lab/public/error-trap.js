/* Paints the reason a lab page failed onto the page itself.
 *
 * A phone or tablet has no console you can reach without a cable, so a page
 * whose module graph throws shows a blank screen and says nothing. This runs
 * as a classic script ahead of the module, survives the module failing to
 * parse, and reports what it saw.
 *
 * Not built by vite: it has to run when the bundle is what is broken.
 */
(function () {
  var MOUNT_DEADLINE_MS = 5000;
  var state = { errors: [], mounted: false, shown: false };

  /* Fired by a resize handler that itself resizes, which every layout in the
   * lab does; browsers report it and then carry on. A trap that raises it
   * raises something on every load, and stops being read. */
  var BENIGN = /^ResizeObserver loop/;

  function push(kind, text, detail) {
    if (BENIGN.test(String(text))) return;
    state.errors.push({ kind: kind, text: String(text || 'unknown'),
                        detail: detail ? String(detail) : '' });
    if (state.mounted) render();
  }

  window.addEventListener('error', function (e) {
    // A failed script/img/link fires at its element and never bubbles, so it
    // is only visible from the capture phase, and carries no message.
    var el = e.target;
    if (el && el !== window && el.tagName) {
      push('resource', el.tagName.toLowerCase() + ' failed to load',
           el.src || el.href || '');
      return;
    }
    var where = e.filename ? e.filename + ':' + e.lineno + ':' + e.colno : '';
    push('error', e.message, (e.error && e.error.stack) || where);
  }, true);

  window.addEventListener('unhandledrejection', function (e) {
    var r = e.reason;
    push('rejection', (r && r.message) || r, (r && r.stack) || '');
  });

  function facts() {
    var vv = window.visualViewport;
    var out = [
      ['url', location.href],
      ['agent', navigator.userAgent],
      ['window', window.innerWidth + ' x ' + window.innerHeight +
                 ' @ dpr ' + (window.devicePixelRatio || 1)],
    ];
    if (vv) out.push(['viewport', Math.round(vv.width) + ' x ' + Math.round(vv.height) +
                                  ' @ scale ' + vv.scale]);
    try {
      var c = document.createElement('canvas');
      out.push(['canvas 2d', c.getContext('2d') ? 'yes' : 'NO']);
      out.push(['webgl2', c.getContext('webgl2') ? 'yes' : 'NO']);
    } catch (err) {
      out.push(['canvas', 'threw: ' + err]);
    }
    return out;
  }

  function style() {
    if (document.getElementById('lab-trap-style')) return;
    var s = document.createElement('style');
    s.id = 'lab-trap-style';
    // Its own colors and its own type: the page's stylesheet is one of the
    // things that may not have arrived.
    s.textContent = [
      '.lab-trap{position:fixed;inset:0;z-index:2147483647;overflow:auto;',
      'background:#1b1b1f;color:#f4f4f5;padding:24px;',
      '-webkit-text-size-adjust:100%;',
      'font:15px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif;',
      'padding-bottom:calc(24px + env(safe-area-inset-bottom))}',
      '.lab-trap--badge{inset:auto 12px 12px auto;max-width:min(560px,92vw);',
      'max-height:60vh;border-radius:10px;border:1px solid #52525b;padding:14px}',
      '.lab-trap h1{margin:0 0 4px;font-size:19px;font-weight:600}',
      '.lab-trap p{margin:0 0 18px;color:#a1a1aa}',
      '.lab-trap ol{margin:0 0 18px;padding-left:22px}',
      '.lab-trap li{margin:0 0 12px}',
      '.lab-trap code{font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;',
      'display:block;white-space:pre-wrap;word-break:break-word;',
      'color:#fca5a5;margin-top:3px}',
      '.lab-trap dl{display:grid;grid-template-columns:auto 1fr;gap:3px 14px;',
      'margin:0;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}',
      '.lab-trap dt{color:#a1a1aa}',
      '.lab-trap dd{margin:0;word-break:break-word}',
      '.lab-trap button{position:absolute;top:10px;right:12px;',
      'background:none;border:0;color:#a1a1aa;font-size:22px;padding:6px}',
    ].join('');
    document.head.appendChild(s);
  }

  function render() {
    try {
      style();
      var old = document.getElementById('lab-trap');
      if (old) old.remove();
      var box = document.createElement('div');
      box.id = 'lab-trap';
      box.className = state.mounted ? 'lab-trap lab-trap--badge' : 'lab-trap';

      var h = document.createElement('h1');
      h.textContent = state.mounted
        ? state.errors.length + (state.errors.length === 1 ? ' error' : ' errors')
        : 'The page did not start';
      box.appendChild(h);

      var p = document.createElement('p');
      p.textContent = state.mounted
        ? 'The page is running; these were raised anyway.'
        : 'Nothing rendered within ' + (MOUNT_DEADLINE_MS / 1000) + 's. Screenshot this.';
      box.appendChild(p);

      if (state.errors.length) {
        var ol = document.createElement('ol');
        state.errors.forEach(function (e) {
          var li = document.createElement('li');
          li.textContent = e.kind + ': ' + e.text;
          if (e.detail) {
            var c = document.createElement('code');
            c.textContent = e.detail;
            li.appendChild(c);
          }
          ol.appendChild(li);
        });
        box.appendChild(ol);
      } else if (!state.mounted) {
        var none = document.createElement('p');
        // The useful half of the report: the module never ran and never threw,
        // which points at what it was waiting on rather than at a broken bundle.
        none.textContent = 'No error was raised — the page loaded and then '
          + 'stopped before rendering.';
        box.appendChild(none);
      }

      var dl = document.createElement('dl');
      facts().forEach(function (row) {
        var dt = document.createElement('dt');
        dt.textContent = row[0];
        var dd = document.createElement('dd');
        dd.textContent = row[1];
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      box.appendChild(dl);

      if (state.mounted) {
        var x = document.createElement('button');
        x.textContent = '×';
        x.setAttribute('aria-label', 'Dismiss');
        x.addEventListener('click', function () { box.remove(); });
        box.appendChild(x);
      }

      document.body.appendChild(box);
      state.shown = true;
    } catch (err) {
      /* A trap that throws is worse than no trap. */
    }
  }

  function check() {
    var root = document.getElementById('root');
    state.mounted = !!(root && root.children.length);
    if (!state.mounted || state.errors.length) render();
  }

  window.__labTrap = { state: state, check: check, render: render, push: push };

  setTimeout(check, MOUNT_DEADLINE_MS);
})();
