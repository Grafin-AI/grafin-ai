import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Hoisted so the vi.mock factory below (itself hoisted) can reference it.
// Field-for-field the shape returned by GET /api/v1/alerts.
const { alert } = vi.hoisted(() => ({
  alert: {
    id: 2,
    event_seq: 3,
    transaction_id: 4214452,
    severity: 'medium',
    typology: 'Smurfing',
    created_at: '2026-08-12T12:00:00+00:00',  // ingestion time — must NOT be shown
    event_time: '2025-09-01T11:00:00+00:00',  // dataset time — what the analyst needs
    acknowledged: false,
  },
}));

vi.mock('../api/queries', () => ({
  useAlerts: () => ({ data: { alerts: [alert] }, isLoading: false, isError: false }),
  useAckAlert: () => ({ mutate: vi.fn() }),
}));

vi.mock('./TransactionDetailsModal', () => ({
  TransactionDetailsModal: ({ isOpen, transactionId }: { isOpen: boolean; transactionId: number | null }) =>
    isOpen ? <div role="dialog">detail {transactionId}</div> : null,
}));

import { AlertsPanel } from './AlertsPanel';

describe('AlertsPanel timestamp', () => {
  it("renders the alert's dataset event_time as an absolute UTC date", () => {
    render(<AlertsPanel />);

    // Same formatter as the live feed, so the two panels read identically.
    // Month matched as Sep/Sept — en-GB's short September is CLDR-dependent.
    expect(screen.getByText(/^01 Sept?\.? 2025, 11:00$/)).toBeInTheDocument();

    // Regression guard: the wall-clock ingestion time (created_at, 2026) must not
    // be what the panel shows.
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument();

    // The old relative rendering ("N minutes ago" / "just now") is gone.
    expect(screen.queryByText(/ago|just now/)).not.toBeInTheDocument();
  });
});

describe('AlertsPanel detail', () => {
  it('opens the transaction detail when the alert card is clicked', () => {
    render(<AlertsPanel />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Lihat detail transaksi 4214452/ }));
    expect(screen.getByRole('dialog')).toHaveTextContent('detail 4214452');
  });
});
