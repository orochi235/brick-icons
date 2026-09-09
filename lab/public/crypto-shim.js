/* `crypto.randomUUID` exists only in a secure context.
 *
 * `http://localhost` is treated as one and a LAN address is not, so the lab
 * works on this machine and throws on the first render on a phone or tablet
 * reaching it by IP -- weasel's core and labkit both call it while building
 * their stores. `crypto.getRandomValues` is available either way, so the
 * function can simply be supplied.
 *
 * Loaded as a classic script ahead of the module graph, because the throw
 * happens the first time a kit module runs.
 */
(function () {
  var c = globalThis.crypto;
  if (!c || typeof c.randomUUID === 'function'
        || typeof c.getRandomValues !== 'function') return;

  var hex = [];
  for (var i = 0; i < 256; i++) hex.push((i + 0x100).toString(16).slice(1));

  c.randomUUID = function randomUUID() {
    var b = c.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    return hex[b[0]] + hex[b[1]] + hex[b[2]] + hex[b[3]] + '-'
         + hex[b[4]] + hex[b[5]] + '-'
         + hex[b[6]] + hex[b[7]] + '-'
         + hex[b[8]] + hex[b[9]] + '-'
         + hex[b[10]] + hex[b[11]] + hex[b[12]] + hex[b[13]] + hex[b[14]]
         + hex[b[15]];
  };
})();
