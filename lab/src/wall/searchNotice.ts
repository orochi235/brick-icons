import type { RevealResult } from 'pezlie';

/** The wall's copy for a part a search found but can't show. */
export function searchNotice(partId: string, result: RevealResult): string | null {
  switch (result) {
    case 'filtered': return `${partId} is hidden by the current filter`;
    case 'absent': return `${partId} is not drawn in this slot`;
    case 'shown': return null;
  }
}
