import { waitFor } from '@testing-library/react';

/** Waits until `selector` matches under `root`, and resolves with the match.
 *  `waitFor` retries only a callback that throws, so handing it a bare
 *  `querySelector` accepts the first null. */
export const shown = <T extends Element = Element>(root: ParentNode, selector: string) =>
  waitFor(() => {
    const el = root.querySelector<T>(selector);
    if (!el) throw new Error(`nothing matches ${selector} yet`);
    return el;
  });
