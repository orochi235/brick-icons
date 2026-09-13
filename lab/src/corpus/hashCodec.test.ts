import { describe, expect, it } from 'vitest';
import { decodeHashJson, encodeHashJson } from '@lab/corpus/hashCodec';

describe('hashCodec', () => {
  it('round-trips an object', () => {
    const value = { s: 'occt', c: '1240,880,2.4', x: 'Sticker,|' };
    expect(decodeHashJson(encodeHashJson(value))).toEqual(value);
  });

  it('round-trips non-ASCII text', () => {
    const value = { x: 'Minifig Accessoire — été, 日本' };
    expect(decodeHashJson(encodeHashJson(value))).toEqual(value);
  });

  it('writes only characters a URL fragment carries unescaped', () => {
    const text = encodeHashJson({ a: '?>>?~~~ÿÿÿ', b: [1, 2, 3] });
    expect(text).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it('answers undefined for text it did not write', () => {
    for (const bad of ['', '!!!', 'eyJh', 'bm90IGpzb24', 'x'.repeat(5000)]) {
      expect(decodeHashJson(bad)).toBeUndefined();
    }
  });
});
