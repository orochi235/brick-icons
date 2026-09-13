/** JSON in, base64url out: text a URL fragment carries with nothing escaped.
 *  Knows nothing about what it carries. */

/** Longer than any state this lab writes, and short enough that a pasted
 *  novel is refused before it is parsed. */
const MAX_TEXT = 4096;

export function encodeHashJson(value: unknown): string {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** The value `encodeHashJson` was given, or undefined for anything else. */
export function decodeHashJson(text: string): unknown {
  if (!text || text.length > MAX_TEXT || !/^[A-Za-z0-9_-]+$/.test(text)) {
    return undefined;
  }
  try {
    const binary = atob(text.replace(/-/g, '+').replace(/_/g, '/'));
    const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch {
    return undefined;
  }
}
