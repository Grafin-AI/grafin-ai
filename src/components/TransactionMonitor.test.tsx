import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Hoisted so the vi.mock factory below (which is itself hoisted) can reference it.
const { item } = vi.hoisted(() => ({
  item: {
    seq: 1, transaction_id: 1, bank: 'BRI', type: 'ACH', amount: 1000000,
    fraud_score: 0.9, typology: 'Fan-Out', status: 'flagged' as const,
    surfaced_at: '2026-08-12T09:15:00Z',  // ingestion time — "today", must NOT be shown
    event_time: '2025-09-03T14:22:00Z',   // dataset time — this is what the analyst needs
  },
}));

vi.mock('../api/useLiveTransactions', () => ({
  useLiveTransactions: () => ({ items: [item] }),
}));
// The modals are irrelevant here and would drag in data fetching; stub them out.
vi.mock('./TransactionDetailsModal', () => ({ TransactionDetailsModal: () => null }));
vi.mock('./UserProfileDetailsModal', () => ({ UserProfileDetailsModal: () => null }));

import { TransactionMonitor } from './TransactionMonitor';

describe('TransactionMonitor timestamp', () => {
  it('renders event_time as an absolute UTC date, not a relative age', () => {
    render(<TransactionMonitor />);

    // The dataset timestamp, formatted deterministically (en-GB + UTC).
    expect(screen.getByText('03 Sept 2025, 14:22')).toBeInTheDocument();

    // Regression guard for the original defect: the wall-clock ingestion time
    // (surfaced_at) must not be what the feed shows.
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument();

    // The old relative rendering ("N hours ago") is gone — against a Sept-2025 dataset
    // it degenerated into a meaningless five-figure hour count.
    expect(screen.queryByText(/ago/)).not.toBeInTheDocument();
  });
});
