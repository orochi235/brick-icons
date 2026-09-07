import type { CellBadge } from '@lab/corpus/paint';
import type { DefectStatus } from '@lab/defects/useDefects';

/** What a defect's status looks like where it is read rather than set.
 *
 *  The same badge shape the wall's tags use, so a status and a tag sitting
 *  in one detail view read as one kind of thing. No mark: a status is a word
 *  and there is no picture of `wontfix` worth learning. Only `open` carries
 *  a live color -- it is the one that asks for something.
 *
 *  Beside `STATUSES`, so a new status cannot reach the dropdowns and not
 *  this. */
/** Keyed by plain string, not by `DefectStatus`: the lab's server is
 *  long-lived and can be older or newer than the page, so a status it has
 *  not heard of must miss rather than fail to compile. The `satisfies` keeps
 *  the four it does know exhaustive. */
export const STATUS_BADGES: Record<string, CellBadge | undefined> = {
  open: { tag: 'open', field: '#c2410c', ink: '#ffffff' },
  fixed: { tag: 'fixed', field: '#2f7d4f', ink: '#ffffff' },
  wontfix: { tag: 'wontfix', field: '#4a4a4f', ink: '#d8d8dc' },
  notabug: { tag: 'notabug', field: '#4a4a4f', ink: '#d8d8dc' },
} satisfies Record<DefectStatus, CellBadge>;
