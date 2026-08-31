import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DefectCard } from '@lab/defects/DefectCard';
import type { Defect } from '@lab/defects/useDefects';

const defect: Defect = {
  id: 'd1', part: '3941', engines: ['occt'], status: 'open',
  title: 'borehole rim not drawn', mark: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 },
  seen: { angle: '30,25' }, filed: '2026-08-31', notes: 'only at 30,25',
};

const props = { defect, onStatus: () => {}, onClose: () => {} };

describe('DefectCard', () => {
  it('shows the title and the notes', () => {
    render(<DefectCard {...props} />);
    expect(screen.getByText('borehole rim not drawn')).toBeTruthy();
    expect(screen.getByText('only at 30,25')).toBeTruthy();
  });

  it('names the engines and the settings it was seen at', () => {
    const { container } = render(<DefectCard {...props} />);
    const meta = container.querySelector('.defect-card-meta')!.textContent;
    expect(meta).toMatch(/occt/);
    expect(meta).toMatch(/angle 30,25/);
  });

  it('changes the status', () => {
    const onStatus = vi.fn();
    render(<DefectCard {...props} onStatus={onStatus} />);
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: 'fixed' } });
    expect(onStatus).toHaveBeenCalledWith('d1', 'fixed');
  });

  it('closes', () => {
    const onClose = vi.fn();
    render(<DefectCard {...props} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText(/close/i));
    expect(onClose).toHaveBeenCalled();
  });
});
