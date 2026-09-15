import type { RevealResult } from '@pezlie/wall/src/WallView';

/** `/corpus`'s wording, so the two pages say the same thing. */
export function searchNotice(part: string, result: RevealResult): string | null {
  if (result === 'filtered') return `${part} is hidden by the current filter`;
  if (result === 'absent') return `${part} is not drawn in this slot`;
  return null;
}
