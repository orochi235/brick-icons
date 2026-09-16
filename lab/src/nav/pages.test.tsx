import { expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { LabSwitcher } from '@weasel-js/labkit';
import { LAB_PATH, PAGES } from '@lab/nav/pages';

const openMenu = (title: string) => fireEvent.click(screen.getByRole('button', { name: title }));

it('lists the lab beside the walls, and marks it open on the lab', () => {
  render(<LabSwitcher title="brick-icons lab" pages={PAGES} path={LAB_PATH} />);
  openMenu('brick-icons lab');
  const lab = screen.getByRole('menuitem', { name: 'Lab' });
  expect(lab.getAttribute('aria-current')).toBe('page');
  expect(screen.getByRole('menuitem', { name: 'Wall' }).getAttribute('href')).toBe('/corpus');
  expect(screen.getByRole('menuitem', { name: 'New wall' }).getAttribute('href')).toBe('/wall');
});

it('reaches the lab from a wall', () => {
  render(<LabSwitcher title="brick-icons wall" pages={PAGES} path="/wall" />);
  openMenu('brick-icons wall');
  const lab = screen.getByRole('menuitem', { name: 'Lab' });
  expect(lab.getAttribute('href')).toBe(LAB_PATH);
  expect(lab.getAttribute('aria-current')).toBeNull();
});
