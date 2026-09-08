import { expect, it } from 'vitest';
import {
  CLASS_SPECS, DEFAULT_SHOWN, FILTER_SPECS, SORT_SPECS, classKeys, filterKeys,
  filterTable, sortKeys, sortTable,
  type ClassFacts, type FilterFacts, type SortFacts,
} from '@lab/corpus/criteria';

const facts: SortFacts = {
  id: '3001', category: 'Brick', status: 'unreviewed', extra_d99: null,
  secs: null, made_at: null, year_from: null, sets: null,
};

const plain: FilterFacts = {
  sha: null, error: null, printed: false, obsolete: false, base: true,
};

const unclassed: ClassFacts = { moved: false, out_of_scope: false };

it('lists the orders the way the menu offers them', () => {
  expect(sortKeys()).toEqual([
    'id', 'category', 'status', 'extra_d99', 'secs', 'made_at', 'year', 'sets',
  ]);
});

it('reads each order off the field it names', () => {
  const by = (key: string) => SORT_SPECS.find((s) => s.key === key)!;
  expect(by('id').value(facts)).toBe('3001');
  expect(by('category').value(facts)).toBe('Brick');
  expect(by('status').value(facts)).toBe('unreviewed');
  expect(by('extra_d99').value({ ...facts, extra_d99: 4 })).toBe(4);
  expect(by('secs').value({ ...facts, secs: 1.5 })).toBe(1.5);
  expect(by('made_at').value({ ...facts, made_at: '2025-01-01' })).toBe('2025-01-01');
  expect(by('year').value({ ...facts, year_from: 1962 })).toBe(1962);
  expect(by('sets').value({ ...facts, sets: 90 })).toBe(90);
});

it('has no answer for a part nothing measured', () => {
  const measured = ['extra_d99', 'secs', 'made_at', 'year', 'sets'];
  for (const key of measured) {
    expect(SORT_SPECS.find((s) => s.key === key)!.value(facts)).toBeNull();
  }
});

// The metrics read worst-first; the descriptive keys read alphabetically.
it('runs the metrics backwards and the descriptive keys forwards', () => {
  expect(SORT_SPECS.filter((s) => s.desc).map((s) => s.key))
    .toEqual(['extra_d99', 'secs', 'made_at', 'sets']);
  expect(SORT_SPECS.filter((s) => !s.desc).map((s) => s.key))
    .toEqual(['id', 'category', 'status', 'year']);
});

it('lists the filters the way the menu offers them', () => {
  expect(filterKeys()).toEqual([
    'all', 'rendered', 'unrendered', 'errors', 'printed', 'obsolete', 'base',
  ]);
});

it('gives each filter the predicate the wall narrows by', () => {
  const by = (key: string) => FILTER_SPECS.find((f) => f.key === key)!;
  expect(by('all').keep(plain)).toBe(true);
  expect(by('rendered').keep({ ...plain, sha: 'abc' })).toBe(true);
  expect(by('rendered').keep(plain)).toBe(false);
  expect(by('unrendered').keep(plain)).toBe(true);
  expect(by('unrendered').keep({ ...plain, sha: 'abc' })).toBe(false);
  expect(by('errors').keep({ ...plain, error: 'boom' })).toBe(true);
  expect(by('errors').keep(plain)).toBe(false);
  expect(by('printed').keep({ ...plain, printed: true })).toBe(true);
  expect(by('printed').keep(plain)).toBe(false);
  expect(by('obsolete').keep({ ...plain, obsolete: true })).toBe(true);
  expect(by('obsolete').keep(plain)).toBe(false);
  expect(by('base').keep(plain)).toBe(true);
  expect(by('base').keep({ ...plain, base: false })).toBe(false);
});

it('lists the classes the way the checkboxes offer them', () => {
  expect(classKeys()).toEqual(['moved', 'outOfScope']);
});

it('gives each class the predicate that puts a cell in it', () => {
  const by = (key: string) => CLASS_SPECS.find((c) => c.key === key)!;
  expect(by('moved').member({ ...unclassed, moved: true })).toBe(true);
  expect(by('moved').member(unclassed)).toBe(false);
  expect(by('outOfScope').member({ ...unclassed, out_of_scope: true })).toBe(true);
  expect(by('outOfScope').member(unclassed)).toBe(false);
});

it('starts the wall with the redirects off and the out-of-scope parts on', () => {
  expect(DEFAULT_SHOWN).toEqual({ moved: false, outOfScope: true });
});

it('names every sort, filter and class the way the menus do', () => {
  expect(SORT_SPECS.map((s) => s.label)).toEqual([
    'id', 'category', 'status', 'extra_d99', 'secs', 'made_at', 'year', 'sets',
  ]);
  expect(FILTER_SPECS.map((f) => f.label)).toEqual([
    'all', 'rendered', 'unrendered', 'errors', 'printed', 'obsolete', 'base',
  ]);
  expect(CLASS_SPECS.map((c) => c.label)).toEqual(['moved', 'out of scope']);
});

// A repeated key would lose one entry out of `sortTable`/`filterTable` and
// give the menu two options that select the same thing.
it('gives every sort, filter and class its own key', () => {
  for (const keys of [sortKeys(), filterKeys(), classKeys()]) {
    expect(new Set(keys).size).toBe(keys.length);
  }
});

it('looks a sort or a filter up by its key', () => {
  expect(sortTable().sets.desc).toBe(true);
  expect(sortTable().year.value({ ...facts, year_from: 1978 })).toBe(1978);
  expect(filterTable().errors.keep({ ...plain, error: 'boom' })).toBe(true);
  expect(Object.keys(sortTable())).toEqual(sortKeys());
  expect(Object.keys(filterTable())).toEqual(filterKeys());
});
