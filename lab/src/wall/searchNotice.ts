import type { RevealResult } from '@pezlie/wall/src/WallView';

/** `/corpus`'s wording, so the two pages say the same thing. */
export function searchNotice(partId: string, result: RevealResult): string | null {
  switch (result) {
    case 'filtered': return `${partId} is hidden by the current filter`;
    case 'absent': return `${partId} is not drawn in this slot`;
    case 'shown': return null;
  }
}
