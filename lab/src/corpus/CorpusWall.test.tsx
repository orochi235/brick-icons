import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { CorpusWall } from '@lab/corpus/CorpusWall';

it('says it is loading before the cells arrive', () => {
  render(<CorpusWall client={{ cells: () => new Promise(() => {}),
                               corpusSources: () => new Promise(() => {}) } as any} />);
  expect(screen.getByText(/loading the corpus/i)).toBeTruthy();
});
